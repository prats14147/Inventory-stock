"""backend/app/models/system_setting.py

DB-backed key/value store for admin-tunable operations knobs (lead times,
safety-stock factor, low-stock threshold).

Why a table instead of only env vars: operators need to view and edit these
from the /settings page without redeploying. The env var remains the default;
a row here overrides it. Values are stored as text and parsed per key.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), nullable=False, default="admin")

    def __repr__(self) -> str:
        return f"<SystemSetting {self.key}={self.value}>"
