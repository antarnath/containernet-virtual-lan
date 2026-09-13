"""Re-export all ORM models so callers can do `from app.models import ...`.

Note: every new model must be imported here BEFORE ``init_db`` is called,
or SQLAlchemy won't know about its table when ``Base.metadata.create_all``
runs on backend startup.
"""

from app.models.host import Base, Host, HostStatus
from app.models.communication import Communication, CommStatus
from app.models.project import Project, ProjectStatus
from app.models.project_host import ProjectHost, ProjectHostStatus
from app.models.project_edge import ProjectEdge

__all__ = [
    "Base",
    "Host", "HostStatus",
    "Communication", "CommStatus",
    "Project", "ProjectStatus",
    "ProjectHost", "ProjectHostStatus",
    "ProjectEdge",
]
