"""Imports every module's models so SQLAlchemy and Alembic see the full metadata."""

from app.modules.attendance import models as attendance_models  # noqa: F401
from app.modules.audit import models as audit_models  # noqa: F401
from app.modules.complaints import models as complaint_models  # noqa: F401
from app.modules.directory import models as directory_models  # noqa: F401
from app.modules.files import models as file_models  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.leaves import models as leave_models  # noqa: F401
from app.modules.notifications import models as notification_models  # noqa: F401
from app.modules.orders import models as order_models  # noqa: F401
from app.modules.payroll import models as payroll_models  # noqa: F401
from app.modules.rbac import models as rbac_models  # noqa: F401
from app.modules.reports import models as report_models  # noqa: F401
from app.modules.settings import models as settings_models  # noqa: F401
from app.modules.tasks import models as task_models  # noqa: F401
from app.platform import models as platform_models  # noqa: F401

__all__ = ["ALL_TABLES"]


def ALL_TABLES():
    from app.core.db import Base

    return sorted(Base.metadata.tables)