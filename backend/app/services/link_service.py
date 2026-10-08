"""Link service — manages the per-wire Linux bridges.

M4 phase 02 — one Docker network (Linux bridge) per wire the user
drew. The bridge name follows the convention
``proj_<project_short>_link_<link_short>`` and is stored on the
``ProjectLink.docker_bridge_name`` column so the capture and router
proxy can find it later without re-deriving.

Why a bridge per wire (not a per-project bridge)?

  M2-07 had one capture per project; M4 splits that into one capture
  per wire. The cleanest way to scope a capture to "exactly this
  wire" is to have the wire be its own bridge — then the capture
  attaches to that bridge's interface and sees only the frames on
  that wire.

  The cost is more bridges (one per wire the user drew) but Docker
  is happy to manage hundreds of bridges, and each bridge is
  essentially free on the host kernel.

Naming
------
  Bridge name max length: 15 chars (Linux `ip link add` rejects
  longer). The format ``proj_<12>_link_<4>`` is 25 chars, which
  is too long — so we use the short 12-char form for the project
  and a 1-char form for the link, totalling
  ``proj_<8>_l_<4>`` = 19 chars. Still too long. We use
  ``p<8>l<4>`` (no underscores) = 13 chars. Clean.

  But Docker's own bridge naming is also length-bounded and the
  name we set is used as the *alias*, not the *interface name*.
  The actual interface that appears on the host is `br-<hash>`.
  So in practice we set a short name for display + lookup, and
  Docker translates the rest.
"""

from __future__ import annotations

import ipaddress
import re
import uuid
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import APIError, NotFound

from app.core.docker_client import get_docker_client


# Docker network label we put on every per-wire bridge.
LABEL_LINK = "containernet.link=true"
LABEL_PROJECT = "containernet.project"
LABEL_LINK_ID = "containernet.link_id"
LABEL_PROJECT_ID = "containernet.project_id"


# ─── name helpers ──────────────────────────────────────────────────────

def _short_id(value: str, n: int) -> str:
    """Return the first ``n`` chars of a UUID with dashes stripped."""
    return value.replace("-", "")[:n]


def bridge_name(project_id: str, link_id: str) -> str:
    """Generate a Linux-bridge-safe name for a per-wire bridge.

    The format is ``cn<8>p<4>l<4>`` where:
      * ``cn`` is the ContainerNet prefix (2 chars)
      * ``<8>`` is the first 8 hex chars of the project UUID
      * ``p<4>`` is a 4-char project hash (avoids collisions on
        similarly-prefixed project ids)
      * ``l<4>`` is the first 4 hex chars of the link UUID

    Total: 2+8+1+4+1+4 = 20 chars. Docker's `--network name` is
    used as an *alias*; the actual interface on the host is named
    `br-<hash>`, so the alias can be up to Docker's per-name limit
    (which is 64 chars but the alias used here is also passed to
    `ip link` on the host via the bridge, where the 15-char
    limit applies for the actual interface name; we therefore
    keep ours short and use a hash).

    For lookup, we filter by the LABEL_LINK_ID label, not by name,
    so the name itself only needs to be unique-enough.
    """
    p = _short_id(project_id, 8)
    l = _short_id(link_id, 4)
    return f"cn{p[:8]}p{p[8:12] if len(p) > 8 else 'p'}l{l}"[:20]


# Cap to 15 chars to be safe with Linux's IFNAMSIZ. The labels are
# the source of truth; this is just a human-readable label.
def short_bridge_name(project_id: str, link_id: str) -> str:
    """Linux-bridge-friendly short name (≤ 15 chars).

    The format ``c<8>_<4>`` = 13 chars:
      * ``c`` is the ContainerNet prefix
      * ``<8>`` is the first 8 hex chars of the project UUID
      * ``_<4>`` is the first 4 hex chars of the link UUID
    """
    p = _short_id(project_id, 8)
    l = _short_id(link_id, 4)
    return f"c{p}_{l}"


# ─── data shapes ───────────────────────────────────────────────────────

@dataclass
class BridgeInfo:
    network_id: str       # Docker network id (used for connect calls)
    name: str             # Docker network name (alias)
    short_name: str       # Linux-bridge-friendly name
    subnet_cidr: str      # e.g. "10.30.10.0/24"


# ─── create / delete ───────────────────────────────────────────────────

def create_bridge_for_link(
    *,
    project_id: str,
    link_id: str,
    iface_a_ip: str | None = None,
    iface_a_mask: str | None = None,
    iface_b_ip: str | None = None,
    iface_b_mask: str | None = None,
) -> BridgeInfo:
    """Create one Docker network (Linux bridge) for a single wire.

    If both endpoints have IPs and matching masks, the bridge's
    subnet is set to the network address of the lower IP + the mask
    (so the bridge routes the right range). Otherwise we fall back
    to a default 10.250.<link-hash>.0/24 so the wire still works
    for connectivity (just without a meaningful IP range).

    The function is idempotent: if a network with the same
    LABEL_LINK_ID already exists, it is returned unchanged.

    Returns a ``BridgeInfo`` the caller stores on the
    ``ProjectLink.docker_bridge_name`` column.
    """
    client = get_docker_client()

    # Idempotency check.
    existing = find_bridge_by_link_id(project_id, link_id)
    if existing is not None:
        return existing

    subnet, gateway = _derive_subnet(iface_a_ip, iface_a_mask, iface_b_ip, iface_b_mask, link_id)
    name = bridge_name(project_id, link_id)
    short = short_bridge_name(project_id, link_id)

    labels = {
        LABEL_LINK.split("=")[0]: "true",
        LABEL_PROJECT.split("=")[0]: project_id,
        LABEL_LINK_ID.split("=")[0]: link_id,
        LABEL_PROJECT_ID.split("=")[0]: project_id,
    }

    # The IPAM pool: subnet always, gateway only when _derive_subnet
    # found a non-conflicting one. Docker ignores gateway=None (auto-
    # picks the network's first address) — we pass gateway="" which
    # Docker also ignores for user-defined bridges. So the only
    # working way to set a non-default gateway is to pass a literal
    # string address. See _derive_subnet's docstring.
    pool_kwargs: dict = {"subnet": subnet}
    if gateway is not None:
        pool_kwargs["gateway"] = gateway

    try:
        net = client.networks.create(
            name=name,
            driver="bridge",
            labels=labels,
            ipam=docker.types.IPAMConfig(
                pool_configs=[docker.types.IPAMPool(**pool_kwargs)]
            ),
            options={
                "com.docker.network.bridge.name": short,
            },
        )
    except APIError as exc:
        # If the alias name collides (rare, but possible after a
        # botched cleanup), try a UUID-suffixed alias.
        if "already exists" in str(exc).lower():
            net = client.networks.create(
                name=f"{name}-{uuid.uuid4().hex[:6]}",
                driver="bridge",
                labels=labels,
                ipam=docker.types.IPAMConfig(
                    pool_configs=[docker.types.IPAMPool(**pool_kwargs)]
                ),
                options={
                    "com.docker.network.bridge.name": short,
                },
            )
        else:
            raise

    return BridgeInfo(
        network_id=net.id,
        name=net.name,
        short_name=short,
        subnet_cidr=subnet,
    )


def delete_bridge_for_link(*, project_id: str, link_id: str) -> bool:
    """Delete the per-wire bridge for a link. Idempotent.

    Any containers still attached are disconnected first so the
    bridge can be removed cleanly.
    """
    client = get_docker_client()
    info = find_bridge_by_link_id(project_id, link_id)
    if info is None:
        return False
    try:
        net = client.networks.get(info.network_id)
    except NotFound:
        return False
    # Disconnect every attached container; swallow errors.
    for cid in list(net.attrs.get("Containers", {}).keys()):
        try:
            net.disconnect(cid, force=True)
        except APIError:
            pass
    try:
        net.remove()
    except APIError:
        # Best effort.
        return False
    return True


def find_bridge_by_link_id(project_id: str, link_id: str) -> BridgeInfo | None:
    """Look up a bridge by its link label. Returns None if missing."""
    client = get_docker_client()
    nets = client.networks.list(
        filters={
            "label": [
                f"{LABEL_LINK_ID.split('=')[0]}={link_id}",
                f"{LABEL_PROJECT_ID.split('=')[0]}={project_id}",
            ]
        }
    )
    if not nets:
        return None
    net = nets[0]
    ipam = (net.attrs.get("IPAM") or {}).get("Config") or []
    subnet = ipam[0]["Subnet"] if ipam else ""
    return BridgeInfo(
        network_id=net.id,
        name=net.name,
        short_name=(net.attrs.get("Options") or {}).get(
            "com.docker.network.bridge.name", net.name
        ),
        subnet_cidr=subnet,
    )


def list_bridges_for_project(project_id: str) -> list[BridgeInfo]:
    client = get_docker_client()
    nets = client.networks.list(
        filters={
            "label": [
                f"{LABEL_LINK.split('=')[0]}=true",
                f"{LABEL_PROJECT.split('=')[0]}={project_id}",
            ]
        }
    )
    out: list[BridgeInfo] = []
    for net in nets:
        ipam = (net.attrs.get("IPAM") or {}).get("Config") or []
        subnet = ipam[0]["Subnet"] if ipam else ""
        out.append(
            BridgeInfo(
                network_id=net.id,
                name=net.name,
                short_name=(net.attrs.get("Options") or {}).get(
                    "com.docker.network.bridge.name", net.name
                ),
                subnet_cidr=subnet,
            )
        )
    return out


# ─── helpers ───────────────────────────────────────────────────────────

# Sanity check on subnet_mask values from ProjectInterface.subnet_mask.
_MASK_RE = re.compile(r"^/(\d+)$")


def _valid_mask(mask: str | None) -> int | None:
    if not mask:
        return None
    m = _MASK_RE.match(mask.strip())
    if not m:
        return None
    n = int(m.group(1))
    if 0 <= n <= 32:
        return n
    return None


def _derive_subnet(
    iface_a_ip: str | None,
    iface_a_mask: str | None,
    iface_b_ip: str | None,
    iface_b_mask: str | None,
    link_id: str,
) -> tuple[str, str | None]:
    """Pick the bridge's subnet AND a non-conflicting gateway IP.

    Returns ``(subnet, gateway_or_None)``.

    If both endpoints are configured with a valid IPv4 + matching mask,
    the subnet is the network address of the lower IP, and the gateway
    is the **last usable** address in that subnet (e.g. ``.254`` for a
    /24). This avoids the very common case where the user assigns
    ``10.0.0.1/24`` to their router, then Docker auto-picks
    ``10.0.0.1`` as the bridge gateway, and the container attach fails
    with "Address already in use".

    Otherwise we fall back to a per-link deterministic /30 in
    10.250.0.0/16 so the wire is still usable. A /30 has only two
    usable host slots; we leave the gateway unset (Docker will pick
    one, but in practice /30 point-to-point links don't need a gateway
    IP for endpoint-to-endpoint traffic).
    """
    a_mask = _valid_mask(iface_a_mask)
    b_mask = _valid_mask(iface_b_mask)
    if (
        iface_a_ip and iface_b_ip
        and a_mask is not None and a_mask == b_mask
    ):
        try:
            a = ipaddress.IPv4Address(iface_a_ip)
            b = ipaddress.IPv4Address(iface_b_ip)
            lower = min(a, b)
            network = ipaddress.IPv4Network(
                f"{lower}/{a_mask}", strict=False
            )
            hosts = list(network.hosts())
            if hosts:
                gateway = str(hosts[-1])  # e.g. .254 for a /24
            else:
                # /31 or /32: no host range, no room for a gateway.
                gateway = None
            return str(network), gateway
        except (ipaddress.AddressValueError, ValueError):
            pass
    # Deterministic fallback so two links don't share a subnet. A
    # /30 has only two usable hosts; no room for a third gateway IP.
    h = _short_id(link_id, 4)
    hi = int(h[:2], 16) if h[:2] else 0
    lo = int(h[2:4], 16) if len(h) >= 4 else 0
    return f"10.250.{hi % 256}.{lo % 256}/30", None


def get_bridge_for_link_id(link_id: str) -> dict[str, Any] | None:
    """Lower-level lookup: return raw network attrs (used by tests)."""
    client = get_docker_client()
    nets = client.networks.list(
        filters={"label": f"{LABEL_LINK_ID.split('=')[0]}={link_id}"}
    )
    return nets[0].attrs if nets else None
