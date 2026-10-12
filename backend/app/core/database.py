"""Async SQLAlchemy engine and session factory."""

from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Base


engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# ─── Lightweight forward-migrations ──────────────────────────────────────────
# `Base.metadata.create_all` is a no-op on tables that already exist. When a
# new column is added to a model (Phase 06's `Communications.project_id`), the
# running DB silently lacks it until someone runs Alembic. Until then, we
# patch known missing columns idempotently on every startup so existing
# deployments don't break.

_PATCHES: list[tuple[str, str]] = [
    # (DDL statement, label for logging). Each must be idempotent.
    (
        "ALTER TABLE communications ADD COLUMN IF NOT EXISTS project_id varchar(36)",
        "communications.project_id column",
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_communications_project_id ON communications (project_id)",
        "communications.project_id index",
    ),
    # Phase 06 dropped the legacy FKs to `hosts(host_id)` from the model. Drop
    # them on disk too — they only existed because the static pc1/pc2/pc3
    # agent put rows into `communications`; with dynamic per-project comms
    # `source_host_id`/`dest_host_id` reference `project_hosts.host_id`, not
    # `hosts.host_id`.
    (
        "ALTER TABLE communications DROP CONSTRAINT IF EXISTS communications_source_host_id_fkey",
        "drop legacy communications.source_host_id FK",
    ),
    (
        "ALTER TABLE communications DROP CONSTRAINT IF EXISTS communications_dest_host_id_fkey",
        "drop legacy communications.dest_host_id FK",
    ),
    # ─── M4: drop the M2 flat-topology tables ─────────────────────────
    # The M2 model had ``project_hosts`` (one row per host) and
    # ``project_edges`` (one row per mesh link). M4 replaces them with
    # the 5-primitive model: ``project_nodes``, ``project_interfaces``,
    # ``project_links``, ``project_captures``. The data does not
    # survive (no templates → no automatic migration path for an
    # arbitrary user-drawn topology). If a user has M2 data they care
    # about, they should have exported it before this migration ran.
    # ``CASCADE`` drops dependent FK constraints automatically.
    (
        "DROP TABLE IF EXISTS project_edges CASCADE",
        "M4: drop project_edges (M2 model)",
    ),
    (
        "DROP TABLE IF EXISTS project_hosts CASCADE",
        "M4: drop project_hosts (M2 model)",
    ),
    # M4 added viewport state to the projects table (canvas pan/zoom).
    # These are new columns; the M2 projects table doesn't have them.
    # ``ADD COLUMN IF NOT EXISTS`` is idempotent.
    (
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS viewport_x REAL NOT NULL DEFAULT 0",
        "M4: add projects.viewport_x",
    ),
    (
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS viewport_y REAL NOT NULL DEFAULT 0",
        "M4: add projects.viewport_y",
    ),
    (
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS viewport_zoom REAL NOT NULL DEFAULT 1.0",
        "M4: add projects.viewport_zoom",
    ),
    # The M2 model made ``topology_type``, ``host_count``, ``subnet``,
    # and ``gateway`` NOT NULL. The M4 model leaves them NULL. The
    # on-disk table still has the old NOT NULL constraints, which
    # would block an INSERT. Drop the NOT NULL constraints idempotently.
    (
        "ALTER TABLE projects ALTER COLUMN topology_type DROP NOT NULL",
        "M4: relax projects.topology_type NOT NULL",
    ),
    (
        "ALTER TABLE projects ALTER COLUMN host_count DROP NOT NULL",
        "M4: relax projects.host_count NOT NULL",
    ),
    (
        "ALTER TABLE projects ALTER COLUMN subnet DROP NOT NULL",
        "M4: relax projects.subnet NOT NULL",
    ),
    (
        "ALTER TABLE projects ALTER COLUMN gateway DROP NOT NULL",
        "M4: relax projects.gateway NOT NULL",
    ),
    # ─── M5-01 / 1.2: DHCP server config columns on project_interfaces.
    # `dhcp_enabled` defaults to FALSE so existing rows remain OFF.
    # `dhcp_pool_start` / `dhcp_pool_end` use INET so they match the
    # existing `ip_address` column type. `dhcp_lease_time` defaults
    # to 43200 (12h) so existing rows have a sensible value.
    (
        "ALTER TABLE project_interfaces ADD COLUMN IF NOT EXISTS dhcp_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "M5-01/1.2: add project_interfaces.dhcp_enabled",
    ),
    (
        "ALTER TABLE project_interfaces ADD COLUMN IF NOT EXISTS dhcp_pool_start INET",
        "M5-01/1.2: add project_interfaces.dhcp_pool_start",
    ),
    (
        "ALTER TABLE project_interfaces ADD COLUMN IF NOT EXISTS dhcp_pool_end INET",
        "M5-01/1.2: add project_interfaces.dhcp_pool_end",
    ),
    (
        "ALTER TABLE project_interfaces ADD COLUMN IF NOT EXISTS dhcp_lease_time INTEGER NOT NULL DEFAULT 43200",
        "M5-01/1.2: add project_interfaces.dhcp_lease_time",
    ),
    (
        "ALTER TABLE project_interfaces ADD COLUMN IF NOT EXISTS dhcp_dns VARCHAR(255)",
        "M5-01/1.2: add project_interfaces.dhcp_dns",
    ),
    # ─── M5-01 / 1.3: DHCP relay config columns on project_interfaces.
    # `dhcp_relay_enabled` defaults to FALSE; `dhcp_relay_server` is
    # nullable. Mutually exclusive with `dhcp_enabled` at the API
    # layer (an iface is either a server or a relay, never both).
    (
        "ALTER TABLE project_interfaces ADD COLUMN IF NOT EXISTS dhcp_relay_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "M5-01/1.3: add project_interfaces.dhcp_relay_enabled",
    ),
    (
        "ALTER TABLE project_interfaces ADD COLUMN IF NOT EXISTS dhcp_relay_server INET",
        "M5-01/1.3: add project_interfaces.dhcp_relay_server",
    ),
    # ─── M5-01 / 1.4: DHCP reservations table.
    # One row per (iface, MAC, IP) binding. The table is created
    # by `Base.metadata.create_all` on startup; these statements
    # add the two UNIQUE constraints idempotently so they show up
    # on existing deployments that already had a reservation row
    # but without the constraints (e.g. an early internal release).
    (
        "CREATE TABLE IF NOT EXISTS project_dhcp_reservations ("
        "id VARCHAR(36) PRIMARY KEY, "
        "iface_id VARCHAR(36) NOT NULL REFERENCES project_interfaces(id) "
        "ON DELETE CASCADE, "
        "mac_address VARCHAR(17) NOT NULL, "
        "ip_address INET NOT NULL, "
        "hostname VARCHAR(63), "
        "created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), "
        "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()"
        ")",
        "M5-01/1.4: create project_dhcp_reservations table",
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_project_dhcp_reservations_iface_id "
        "ON project_dhcp_reservations (iface_id)",
        "M5-01/1.4: index project_dhcp_reservations.iface_id",
    ),
    (
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint "
        "WHERE conname = 'uq_reservation_iface_mac') THEN "
        "ALTER TABLE project_dhcp_reservations "
        "ADD CONSTRAINT uq_reservation_iface_mac UNIQUE (iface_id, mac_address); "
        "END IF; END $$",
        "M5-01/1.4: add uq_reservation_iface_mac constraint",
    ),
    (
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint "
        "WHERE conname = 'uq_reservation_iface_ip') THEN "
        "ALTER TABLE project_dhcp_reservations "
        "ADD CONSTRAINT uq_reservation_iface_ip UNIQUE (iface_id, ip_address); "
        "END IF; END $$",
        "M5-01/1.4: add uq_reservation_iface_ip constraint",
    ),
]


async def _apply_patches() -> None:
    """Apply idempotent ALTER TABLE patches that handle the Phase 06 → on-disk
    schema gap. Each statement is safe to run multiple times."""
    async with engine.begin() as conn:
        for stmt, label in _PATCHES:
            try:
                await conn.execute(text(stmt))
            except Exception as exc:  # pragma: no cover - defensive
                # Don't crash the backend if a patch fails; the operator
                # will see the error in logs and can intervene.
                print(f"[db] patch failed ({label}): {stmt!r} → {exc}")


async def init_db() -> None:
    """Create all tables on startup, then apply forward-migration patches.
    Alembic replaces this entirely once a migration history exists."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _apply_patches()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        yield session