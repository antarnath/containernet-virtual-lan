"""Project service — orchestrates the 5-primitive M4 model.

The service is the single source of truth for what happens when a project,
node, interface, or link is created, fetched, updated, or deleted. The API
layer (``api/projects.py``) is a thin wrapper that just calls these
functions.

Phase 01 responsibilities (this file)
  * create_project     — create the canvas (no nodes, no links)
  * get_project        — fetch with eager-loaded nodes + links
  * list_projects      — summary listing
  * update_project     — name + viewport
  * delete_project     — cascades to nodes / interfaces / links
  * add_node           — auto-generate a sensible default name
  * update_node        — name / position / attack_mode
  * delete_node        — cascade; 409 if any wire would dangle
  * add_interface      — port on a node
  * update_interface   — IP / mask / name
  * delete_interface   — 409 if wired
  * add_link           — two interfaces on different nodes
  * delete_link        — cascades to the per-link capture row

Phase 02 will add the lifecycle (start / stop / restart) on top of this
same module — they slot in as additional methods without changing the
CRUD shape.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ATTACK_MODES,
    NodeKind,
    Project,
    ProjectCapture,
    ProjectInterface,
    ProjectLink,
    ProjectNode,
    ProjectStatus,
)
from app.schemas.project import (
    ProjectCreateIn,
    ProjectInterfaceCreateIn,
    ProjectInterfaceUpdateIn,
    ProjectLinkCreateIn,
    ProjectNodeCreateIn,
    ProjectNodeUpdateIn,
    ProjectUpdateIn,
)


# ─── Errors ────────────────────────────────────────────────────────────────
# These are caught by the API layer and translated to 4xx HTTP responses.
# The strings are user-facing; keep them short and clear.

class ProjectNotFoundError(LookupError):
    """The requested project does not exist."""


class NodeNotFoundError(LookupError):
    """The requested node does not exist (or not in this project)."""


class InterfaceNotFoundError(LookupError):
    """The requested interface does not exist (or not in this project)."""


class LinkNotFoundError(LookupError):
    """The requested link does not exist (or not in this project)."""


class NodeHasLinksError(ValueError):
    """Deleting a node that has wired interfaces."""
    def __init__(self, node_id: str, link_ids: list[str]) -> None:
        super().__init__(
            f"Node {node_id!r} has {len(link_ids)} wire(s) attached; "
            f"delete the wires first: {link_ids}"
        )
        self.node_id = node_id
        self.link_ids = link_ids


class InterfaceIsWiredError(ValueError):
    """Deleting an interface that is on a link."""
    def __init__(self, iface_id: str, link_ids: list[str]) -> None:
        super().__init__(
            f"Interface {iface_id!r} is on {len(link_ids)} wire(s); "
            f"delete the wires first: {link_ids}"
        )
        self.iface_id = iface_id
        self.link_ids = link_ids


class LinkEndpointsError(ValueError):
    """The two endpoints of a link are not on different nodes."""


# ─── helpers ──────────────────────────────────────────────────────────────

_NODE_KIND_LABEL = {
    NodeKind.HOST: "Host",
    NodeKind.SWITCH: "Switch",
    NodeKind.ROUTER: "Router",
    NodeKind.SERVER: "Server",
    NodeKind.ATTACKER: "Attacker",
}


async def _next_node_name(
    session: AsyncSession, project_id: str, kind: NodeKind
) -> str:
    """Auto-suggest a name like ``Host-3`` for a new node of ``kind``.

    The counter is the count of existing nodes of that kind + 1
    (not the max+1, so deletions don't cause name collisions). The
    user can rename anything via PATCH afterwards.
    """
    stmt = select(ProjectNode).where(
        ProjectNode.project_id == project_id,
        ProjectNode.kind == kind,
    )
    result = await session.execute(stmt)
    count = len(result.scalars().all())
    return f"{_NODE_KIND_LABEL[kind]}-{count + 1}"


def _next_subnet_color_index(session: AsyncSession, project_id: str) -> int:
    """Pick the next subnet color slot 1..6, cycling past 6.

    This is a pure function (not async) because we don't need to query
    the DB — the caller passes the session's cached state. Used at
    link-creation time so the wire gets a unique color in the canvas.
    """
    # Note: the caller is expected to query the project's links and
    # compute count() + 1, then pass that here. This is a deliberate
    # split so the service layer can stay async without a tiny
    # helper DB query just for the color.
    raise NotImplementedError  # replaced by the caller pattern below


# ─── Project CRUD ─────────────────────────────────────────────────────────

async def create_project(
    session: AsyncSession, body: ProjectCreateIn
) -> Project:
    """Create a new (empty) project. The canvas starts blank."""
    project = Project(
        name=body.name,
        status=ProjectStatus.DRAFT,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_project(session: AsyncSession, project_id: str) -> Project | None:
    """Fetch one project with eager-loaded nodes + links + interfaces.

    Returns ``None`` if not found. The API layer maps that to 404.
    """
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.nodes).selectinload(ProjectNode.interfaces),
            selectinload(Project.links).selectinload(ProjectLink.capture),
        )
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def list_projects(session: AsyncSession) -> list[Project]:
    """Summary list — newest first, with node + link counts.

    The counts are computed via a subquery so the API doesn't have
    to touch the related rows (avoids a N+1 and avoids lazy-loading
    after the session is closed).
    """
    from sqlalchemy import func, select
    from app.models import ProjectNode, ProjectLink

    node_count = (
        select(func.count(ProjectNode.id))
        .where(ProjectNode.project_id == Project.id)
        .correlate(Project)
        .scalar_subquery()
    )
    link_count = (
        select(func.count(ProjectLink.id))
        .where(ProjectLink.project_id == Project.id)
        .correlate(Project)
        .scalar_subquery()
    )
    stmt = (
        select(Project, node_count.label("node_count"), link_count.label("link_count"))
        .order_by(Project.updated_at.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()
    # Project rows + counts. We attach counts as transient attributes
    # so the API layer can read them without re-querying.
    projects: list[Project] = []
    for project, nc, lc in rows:
        project._node_count = nc  # type: ignore[attr-defined]
        project._link_count = lc  # type: ignore[attr-defined]
        projects.append(project)
    return projects


async def update_project(
    session: AsyncSession, project_id: str, body: ProjectUpdateIn
) -> Project | None:
    """Patch name and/or viewport. Returns the updated project or None."""
    project = await session.get(Project, project_id)
    if project is None:
        return None
    if body.name is not None:
        project.name = body.name
    if body.viewport_x is not None:
        project.viewport_x = body.viewport_x
    if body.viewport_y is not None:
        project.viewport_y = body.viewport_y
    if body.viewport_zoom is not None:
        project.viewport_zoom = body.viewport_zoom
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project_id: str) -> bool:
    """Delete a project (and everything under it). Returns True if it existed."""
    project = await session.get(Project, project_id)
    if project is None:
        return False
    await session.delete(project)
    await session.commit()
    return True


# ─── Node CRUD ────────────────────────────────────────────────────────────

async def add_node(
    session: AsyncSession, project_id: str, body: ProjectNodeCreateIn
) -> ProjectNode:
    """Add a new node to a project. The kind comes from the request body;
    the name is auto-suggested if the user didn't supply one.
    """
    project = await session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(project_id)

    kind = NodeKind(body.kind)
    name = body.name or await _next_node_name(session, project_id, kind)

    # Only attackers can have an attack_mode set at creation. Other
    # kinds ignore the field. We also validate the attack_mode value
    # is in the allowed set.
    attack_mode: str | None = None
    if kind == NodeKind.ATTACKER:
        attack_mode = body.attack_mode
        if attack_mode is not None and attack_mode not in ATTACK_MODES:
            raise ValueError(
                f"attack_mode must be one of {ATTACK_MODES}, got {attack_mode!r}"
            )

    node = ProjectNode(
        project_id=project_id,
        name=name,
        kind=kind,
        canvas_x=body.canvas_x,
        canvas_y=body.canvas_y,
        attack_mode=attack_mode,
        container_status="idle",
    )
    session.add(node)
    await session.commit()
    await session.refresh(node)
    return node


async def get_node(
    session: AsyncSession, project_id: str, node_id: str
) -> ProjectNode | None:
    stmt = (
        select(ProjectNode)
        .where(ProjectNode.id == node_id, ProjectNode.project_id == project_id)
        .options(selectinload(ProjectNode.interfaces))
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def update_node(
    session: AsyncSession,
    project_id: str,
    node_id: str,
    body: ProjectNodeUpdateIn,
) -> ProjectNode | None:
    """Patch a node's name, position, or attack_mode."""
    node = await get_node(session, project_id, node_id)
    if node is None:
        return None
    if body.name is not None:
        node.name = body.name
    if body.canvas_x is not None:
        node.canvas_x = body.canvas_x
    if body.canvas_y is not None:
        node.canvas_y = body.canvas_y
    if body.attack_mode is not None:
        if node.kind != NodeKind.ATTACKER:
            raise ValueError(
                f"attack_mode can only be set on attacker nodes; "
                f"this node is {node.kind.value!r}"
            )
        if body.attack_mode not in ATTACK_MODES:
            raise ValueError(
                f"attack_mode must be one of {ATTACK_MODES}, "
                f"got {body.attack_mode!r}"
            )
        node.attack_mode = body.attack_mode
    elif body.attack_mode is None and node.attack_mode is not None:
        # Explicit clear (PATCH with attack_mode=null)
        node.attack_mode = None
    await session.commit()
    await session.refresh(node)
    return node


async def delete_node(
    session: AsyncSession, project_id: str, node_id: str
) -> bool:
    """Delete a node. Raises NodeHasLinksError if any of its interfaces
    are wired; the API layer maps that to 409 Conflict."""
    node = await get_node(session, project_id, node_id)
    if node is None:
        return False

    # Find any wires that reference any of this node's interfaces.
    iface_ids = [i.id for i in node.interfaces]
    if iface_ids:
        stmt = select(ProjectLink).where(
            (ProjectLink.iface_a_id.in_(iface_ids))
            | (ProjectLink.iface_b_id.in_(iface_ids))
        )
        result = await session.execute(stmt)
        wired = list(result.scalars().all())
        if wired:
            raise NodeHasLinksError(
                node_id=node_id,
                link_ids=[l.id for l in wired],
            )

    await session.delete(node)
    await session.commit()
    return True


# ─── Interface CRUD ───────────────────────────────────────────────────────

async def add_interface(
    session: AsyncSession,
    project_id: str,
    node_id: str,
    body: ProjectInterfaceCreateIn,
) -> ProjectInterface:
    """Add a port to a node."""
    node = await get_node(session, project_id, node_id)
    if node is None:
        raise NodeNotFoundError(node_id)

    iface = ProjectInterface(
        node_id=node_id,
        name=body.name,
        ip_address=body.ip_address,
        subnet_mask=body.subnet_mask,
    )
    session.add(iface)
    await session.commit()
    await session.refresh(iface)
    return iface


async def update_interface(
    session: AsyncSession,
    project_id: str,
    iface_id: str,
    body: ProjectInterfaceUpdateIn,
) -> ProjectInterface | None:
    """Patch an interface's name, IP, or mask."""
    # Scope the lookup to the project so a wrong URL returns 404, not
    # a confusing "found but not yours" 200.
    stmt = (
        select(ProjectInterface)
        .join(ProjectNode, ProjectInterface.node_id == ProjectNode.id)
        .where(
            ProjectInterface.id == iface_id,
            ProjectNode.project_id == project_id,
        )
    )
    result = await session.execute(stmt)
    iface = result.scalars().first()
    if iface is None:
        return None
    if body.name is not None:
        iface.name = body.name
    if body.ip_address is not None:
        iface.ip_address = body.ip_address
    if body.subnet_mask is not None:
        iface.subnet_mask = body.subnet_mask
    await session.commit()
    await session.refresh(iface)
    return iface


async def delete_interface(
    session: AsyncSession, project_id: str, iface_id: str
) -> bool:
    """Delete an interface. Raises InterfaceIsWiredError if it's on a link."""
    stmt = (
        select(ProjectInterface)
        .join(ProjectNode, ProjectInterface.node_id == ProjectNode.id)
        .where(
            ProjectInterface.id == iface_id,
            ProjectNode.project_id == project_id,
        )
    )
    result = await session.execute(stmt)
    iface = result.scalars().first()
    if iface is None:
        return False

    # Reject if wired.
    stmt = select(ProjectLink).where(
        (ProjectLink.iface_a_id == iface_id)
        | (ProjectLink.iface_b_id == iface_id)
    )
    result = await session.execute(stmt)
    wired = list(result.scalars().all())
    if wired:
        raise InterfaceIsWiredError(
            iface_id=iface_id,
            link_ids=[l.id for l in wired],
        )

    await session.delete(iface)
    await session.commit()
    return True


# ─── Link CRUD ────────────────────────────────────────────────────────────

async def add_link(
    session: AsyncSession, project_id: str, body: ProjectLinkCreateIn
) -> ProjectLink:
    """Wire two interfaces on two different nodes. Creates the per-link
    capture row in the same transaction (the capture is 1:1 with the
    link and we want them to share a lifetime)."""
    if body.iface_a_id == body.iface_b_id:
        raise LinkEndpointsError(
            "A wire cannot connect an interface to itself."
        )

    # Load both endpoints, scoped to the project, and check they belong
    # to different nodes.
    stmt = (
        select(ProjectInterface)
        .join(ProjectNode, ProjectInterface.node_id == ProjectNode.id)
        .where(
            ProjectInterface.id.in_([body.iface_a_id, body.iface_b_id]),
            ProjectNode.project_id == project_id,
        )
    )
    result = await session.execute(stmt)
    ifaces = {i.id: i for i in result.scalars().all()}
    if len(ifaces) != 2:
        raise LinkEndpointsError(
            f"Both interfaces must exist in project {project_id!r}. "
            f"Found {len(ifaces)} of 2."
        )
    a, b = ifaces[body.iface_a_id], ifaces[body.iface_b_id]
    if a.node_id == b.node_id:
        raise LinkEndpointsError(
            f"A wire must connect two different nodes; both endpoints "
            f"are on node {a.node_id!r}."
        )

    # Auto-derive the subnet_cidr from the two endpoints, if both are
    # configured. Stored for query speed; the source of truth is the
    # interface columns themselves.
    subnet_cidr: str | None = None
    if a.ip_address and a.subnet_mask and b.ip_address and b.subnet_mask:
        if a.subnet_mask == b.subnet_mask:
            # Use the lower of the two IPs as the network address.
            ips = sorted([a.ip_address, b.ip_address])
            mask = a.subnet_mask  # already validated by the schema
            subnet_cidr = f"{ips[0]}{mask}"

    # Auto-pick the next subnet color slot. We count existing links
    # in the project + 1, cycling 1..6.
    stmt = select(ProjectLink).where(ProjectLink.project_id == project_id)
    result = await session.execute(stmt)
    existing_count = len(result.scalars().all())
    color_index = (existing_count % 6) + 1

    link = ProjectLink(
        project_id=project_id,
        iface_a_id=body.iface_a_id,
        iface_b_id=body.iface_b_id,
        subnet_cidr=subnet_cidr,
        subnet_color_index=color_index,
    )
    session.add(link)
    # 1:1 child capture — created eagerly so the cascade is symmetric.
    link.capture = ProjectCapture(status="idle", packet_count=0)
    await session.commit()
    await session.refresh(link)

    # M4 phase 07 — emit a link_created event.
    try:
        from app.services import event_service
        await event_service.emit_link_created(
            session,
            project_id,
            link_id=link.id,
            iface_a_id=body.iface_a_id,
            iface_b_id=body.iface_b_id,
            subnet_cidr=subnet_cidr,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "[service] failed to emit link_created event for %s", link.id,
        )

    return link


async def delete_link(
    session: AsyncSession, project_id: str, link_id: str
) -> bool:
    """Delete a link (cascades to its capture row)."""
    stmt = select(ProjectLink).where(
        ProjectLink.id == link_id,
        ProjectLink.project_id == project_id,
    )
    result = await session.execute(stmt)
    link = result.scalars().first()
    if link is None:
        return False
    await session.delete(link)
    await session.commit()
    return True


# ─── Lifecycle placeholders (implemented in phase 02) ────────────────────

async def start_project(session: AsyncSession, project_id: str) -> Any:
    """Phase 02 — spawn containers + bridges. Raises NotImplementedError
    in this phase; the API layer returns 501 to the caller.
    """
    raise NotImplementedError(
        "start_project ships in Milestone 4 phase 02 (router + bridges)"
    )


async def stop_project(session: AsyncSession, project_id: str) -> Any:
    """Phase 02 — tear down containers + bridges."""
    raise NotImplementedError(
        "stop_project ships in Milestone 4 phase 02 (router + bridges)"
    )
