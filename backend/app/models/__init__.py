"""Re-export all ORM models so callers can do `from app.models import ...`.

Note: every new model must be imported here BEFORE ``init_db`` is called,
or SQLAlchemy won't know about its table when ``Base.metadata.create_all``
runs on backend startup.

M4 model surface (5-primitive):
  * Project
  * ProjectNode (kind ∈ {host, switch, router, server, attacker})
  * ProjectInterface
  * ProjectLink
  * ProjectCapture

The legacy ``Host`` model is kept so any code path that still imports
it (none in M4) doesn't crash; it's not part of the 5-primitive model.
The M2 ``ProjectHost`` and ``ProjectEdge`` tables are dropped at
startup by the _PATCHES list in core/database.py.
"""

from app.models.host import Base, Host, HostStatus
from app.models.project import Project, ProjectStatus
# M4 — the 5-primitive model
from app.models.project_node import ProjectNode, NodeKind, ATTACK_MODES
from app.models.project_interface import ProjectInterface
from app.models.project_link import ProjectLink
from app.models.project_capture import ProjectCapture
# M4 phase 03 — anomaly detector
from app.models.anomaly_event import (
    AnomalyEvent,
    AnomalyKind,
    AnomalySeverity,
)
# M4 phase 05 — communication / message log
from app.models.communication import Communication

__all__ = [
    "Base",
    "Host", "HostStatus",  # legacy, not used by M4
    "Project", "ProjectStatus",
    # M4
    "ProjectNode", "NodeKind", "ATTACK_MODES",
    "ProjectInterface",
    "ProjectLink",
    "ProjectCapture",
    # M4 phase 03
    "AnomalyEvent", "AnomalyKind", "AnomalySeverity",
    # M4 phase 05
    "Communication",
]
