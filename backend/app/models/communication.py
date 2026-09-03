"""Communication ORM model — records every host-to-host message."""

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
    source_host_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("hosts.host_id"), index=True
    )
    dest_host_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("hosts.host_id"), index=True
    )
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
        return f"<Communication {self.source_host_id} -> {self.dest_host_id} {self.status}>"