"""Communication ORM model — records every host-to-host message.

Phase 06 — Project-Scoped Communication
---------------------------------------
Every communication row now carries a ``project_id`` (FK -> projects.id)
so a project's communication log is naturally isolated from sibling
projects. The legacy global ``hosts.host_id`` FK is dropped: messages in
the dynamic era are always between two ``ProjectHost`` rows belonging to
the same project.

The ``project_id`` column is declared ``nullable=True`` (with a default
empty string) so existing legacy rows from before Phase 06 don't break
backwards compatibility for one release cycle. Rows created by the new
``trigger_communication(project_id, ...)`` always have it set.

The composite uniqueness is enforced at the service layer: the
orchestrator refuses to dispatch unless both source and dest host rows
exist in the same project.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.host import Base


class CommStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class Communication(Base):
    __tablename__ = "communications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Phase 06 — project scope. Nullable so the table is forward-compatible
    # with legacy rows from before Phase 06; the new code path always sets it.
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        default="",
    )

    source_host_id: Mapped[str] = mapped_column(String(50), index=True)
    dest_host_id: Mapped[str] = mapped_column(String(50), index=True)
    protocol: Mapped[str] = mapped_column(String(20), default="HTTP")
    payload: Mapped[str] = mapped_column(Text)
    data_size: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum(CommStatus, name="comm_status"), default=CommStatus.PENDING
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        proj = self.project_id or "<legacy>"
        return (
            f"<Communication project={proj} "
            f"{self.source_host_id} -> {self.dest_host_id} {self.status}>"
        )
