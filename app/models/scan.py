from datetime import UTC, datetime

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Scan(Base):
    """Persisted state for a single HubSpot extraction scan.

    Tracks per-object-type progress so `GET /api/scan/{id}/status` can
    report it across separate requests, independent of the process that
    originally handled `POST /api/scan/start`.
    """

    __tablename__ = "scans"

    scan_id: Mapped[str] = mapped_column(primary_key=True)
    org_id: Mapped[str]
    status: Mapped[str] = mapped_column(default="started")

    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Per-object-type progress, e.g.:
    # {"contacts": {"status": "in_progress", "records_extracted": 100, ...}}
    progress: Mapped[dict] = mapped_column(JSON, default=dict)

    # The original request params: object_types, filters, output_format,
    # destination. Needed to resume a scan and useful for statistics/list
    # filtering later.
    config: Mapped[dict] = mapped_column(JSON, default=dict)
