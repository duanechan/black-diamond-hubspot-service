from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.models.scan import Scan


class ScanNotFoundError(ValueError):
    """Raised when a scan_id has no corresponding row."""

    def __init__(self, scan_id: str) -> None:
        super().__init__(f"Scan '{scan_id}' not found")
        self.scan_id = scan_id


class ScanRepository:
    """Data-access layer for persisted scan state.

    Each method opens and closes its own session — sessions are not
    held across calls or shared across threads. This matters because
    scan progress is updated from a background extraction thread,
    separate from the request thread that created the scan.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """Initializes the repository.

        Args:
            session_factory: Produces new SQLAlchemy sessions on demand.
        """
        self._session_factory = session_factory

    def create(self, scan_id: str, org_id: str, config: dict) -> Scan:
        """Creates and persists a new scan in the "started" state.

        Args:
            scan_id: Unique scan identifier, supplied by the caller.
            org_id: Organization identifier.
            config: The original scan request parameters (object_types,
                filters, output_format, destination), needed later for
                resuming.

        Returns:
            The newly created scan.
        """
        with self._session_factory() as session:
            scan = Scan(
                scan_id=scan_id,
                org_id=org_id,
                status="started",
                progress={},
                config=config,
            )
            session.add(scan)
            session.commit()
            session.refresh(scan)
            session.expunge(scan)
            return scan

    def get(self, scan_id: str) -> Scan:
        """Fetches a scan by ID.

        Args:
            scan_id: The scan to fetch.

        Returns:
            The scan.

        Raises:
            ScanNotFoundError: If no scan exists with that ID.
        """
        with self._session_factory() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                raise ScanNotFoundError(scan_id)
            session.expunge(scan)
            return scan

    def update_object_progress(
        self,
        scan_id: str,
        object_type: str,
        entry: dict,
    ) -> None:
        """Updates a single object type's entry within `progress`.

        Merges `entry` into `progress[object_type]`, leaving other
        object types' entries untouched. Also bumps `updated_at`.

        Args:
            scan_id: The scan to update.
            object_type: Which object type's progress entry to set.
            entry: The new progress data for that object type (e.g.
                `{"status": "in_progress", "records_extracted": 100, ...}`).

        Raises:
            ScanNotFoundError: If no scan exists with that ID.
        """
        with self._session_factory() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                raise ScanNotFoundError(scan_id)
            # Reassign (not mutate in place) so SQLAlchemy detects the
            # change on a JSON column - in-place dict mutation is not
            # reliably tracked as "dirty" by the ORM.
            scan.progress = {**scan.progress, object_type: entry}
            scan.updated_at = datetime.now(UTC)
            session.commit()

    def update_status(self, scan_id: str, status: str) -> None:
        """Updates a scan's overall status.

        Args:
            scan_id: The scan to update.
            status: New status (e.g. "in_progress", "completed", "failed",
                "cancelled").

        Raises:
            ScanNotFoundError: If no scan exists with that ID.
        """
        with self._session_factory() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                raise ScanNotFoundError(scan_id)
            scan.status = status
            scan.updated_at = datetime.now(UTC)
            session.commit()

    def list(
        self,
        org_id: str | None = None,
        status: str | None = None,
    ) -> list[Scan]:
        """Lists scans, optionally filtered by org and/or status.

        Args:
            org_id: If given, only return scans for this organization.
            status: If given, only return scans with this status.

        Returns:
            Matching scans.
        """
        with self._session_factory() as session:
            query = session.query(Scan)
            if org_id is not None:
                query = query.filter(Scan.org_id == org_id)
            if status is not None:
                query = query.filter(Scan.status == status)
            scans = query.all()
            for scan in scans:
                session.expunge(scan)
            return scans

    def delete(self, scan_id: str) -> None:
        """Deletes a scan record.

        Args:
            scan_id: The scan to delete.

        Raises:
            ScanNotFoundError: If no scan exists with that ID.
        """
        with self._session_factory() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                raise ScanNotFoundError(scan_id)
            session.delete(scan)
            session.commit()
