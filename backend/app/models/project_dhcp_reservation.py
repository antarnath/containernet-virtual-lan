"""ProjectDHCPREServation ORM model — one row per MAC→IP static
binding on a DHCP-server router interface.

M5-01 feature 1.4. A reservation ties a known client MAC to a
specific IP that the pool always hands out. dnsmasq implements
this with a ``dhcp-host=MAC,IP`` line in the iface's conf; the
backend persists one row per binding and pushes the list to the
router agent at start time.

Why a separate table (not a JSON column on the iface)?
  Reservations are first-class records the user can list, add,
  delete individually. A JSON column would force the API to
  diff+patch the array; a relational table is simpler and
  gives us FK cascade when the iface is deleted.

  Pool / mac / IP validation also becomes per-row instead of
  "validate the array on every PUT". The pool membership check
  in particular is naturally a per-row check.

Cardinality: a few rows per iface in practice (10s, not 1000s),
so a separate table is fine.
"""

from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, TypeDecorator, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET, MACADDR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.host import Base

if TYPE_CHECKING:
    from app.models.project_interface import ProjectInterface


# ─── MAC column type ─────────────────────────────────────────────────
# PostgreSQL has a native MACADDR type, but like INET it needs a
# Python object on bind. We use a TypeDecorator that accepts
# either a ``str`` (the form we get from / use everywhere) or a
# ``macaddress.EUI48`` (less common, but the type the DB returns).
# A plain string round-trips cleanly enough that we don't bother
# with the macaddress lib.
_MAC_RE = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")


def _normalize_mac(value) -> str | None:
    """Return a canonical lowercase colon-separated MAC, or None."""
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip().lower()
        if not _MAC_RE.match(v):
            return None
        return v
    # macaddress.EUI48 or similar
    s = str(value).strip().lower()
    if not _MAC_RE.match(s):
        return None
    return s


class _MacString(TypeDecorator):
    """Persist as MACADDR on PostgreSQL, accept/return ``str``.

    Mirrors the ``_IPv4AddressINET`` decorator in
    ``project_interface.py``: callers (the service layer) pass
    plain strings, the DB gets the native type.
    """
    impl = String(17)  # 12 hex + 5 colons
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        return _normalize_mac(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        return _normalize_mac(value)


class _IPv4AddressINET(TypeDecorator):
    """Same decorator as on ProjectInterface — keep the IP as a
    string in Python, INET in PostgreSQL."""
    impl = INET
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, str):
            return ipaddress.IPv4Address(value)
        return value

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            return str(value)
        return str(value)


class ProjectDHCPREServation(Base):
    __tablename__ = "project_dhcp_reservations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    iface_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project_interfaces.id", ondelete="CASCADE"),
        index=True,
    )
    # The MAC we're binding. Stored as a normalised lowercase string
    # (e.g. "aa:bb:cc:dd:ee:ff"). The host's MAC is the same format
    # (``ProjectInterface.mac_address``) so a UI can simply copy
    # that field into the reservation form.
    mac_address: Mapped[str] = mapped_column(_MacString(), nullable=False)
    # The fixed IP. Must lie inside the iface's DHCP pool (validated
    # in the service layer). dnsmasq's ``dhcp-host=MAC,IP`` form
    # happily accepts an IP outside the pool — but we reject it
    # so the UI can't put a host on a subnet it can't reach.
    ip_address: Mapped[str] = mapped_column(_IPv4AddressINET(), nullable=False)
    # Optional hostname. When set, dnsmasq's
    # ``dhcp-host=MAC,IP,hostname`` form binds the hostname too and
    # adds a local-DNS entry. NULL is fine; we just omit the
    # hostname segment of the dhcp-host line.
    hostname: Mapped[str | None] = mapped_column(String(63), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        # Two reservations on the same iface can't bind the same MAC
        # twice (no ambiguity, just refuse to silently overwrite).
        UniqueConstraint(
            "iface_id", "mac_address", name="uq_reservation_iface_mac"
        ),
        # Same for IP: two reservations on the same iface binding
        # the same IP would race and confuse dnsmasq.
        UniqueConstraint(
            "iface_id", "ip_address", name="uq_reservation_iface_ip"
        ),
    )

    # ── relationship ─────────────────────────────────────────────────
    iface: Mapped["ProjectInterface"] = relationship(back_populates="reservations")

    def __repr__(self) -> str:
        host_part = f" {self.hostname!r}" if self.hostname else ""
        return f"<ProjectDHCPREServation {self.mac_address} → {self.ip_address}{host_part}>"
