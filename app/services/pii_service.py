import hashlib
import hmac


class PIIService:
    """Masks PII fields in HubSpot records before they leave the service.

    Selected property fields are replaced with deterministic HMAC-SHA256
    hashes when masking is enabled. Deterministic hashing means the same
    input value always produces the same hash, so masked values remain
    usable as join/dedup keys downstream without exposing the real data.
    """

    # Standard CRM objects (contacts, companies, deals, etc.) use
    # lowercase property names (e.g. "firstname"). Owners and
    # engagements are reshaped from APIs that return camelCase field
    # names (e.g. "firstName") - both variants are listed so masking
    # isn't silently bypassed by a casing difference between sources.
    FIELDS = [
        "email",
        "firstname",
        "firstName",
        "lastname",
        "lastName",
        "phone",
    ]

    def __init__(self, enabled: bool, hmac_key: str) -> None:
        """Initializes the PII masking service.

        Args:
            enabled: Whether PII masking is enabled. When False, `mask()`
                returns records unchanged.
            hmac_key: Secret key used to generate deterministic HMAC
                hashes.
        """
        self._enabled = enabled
        self._hmac_key = hmac_key

    @property
    def enabled(self) -> bool:
        return self._enabled

    def mask(self, records: list[dict]) -> list[dict]:
        """Masks PII fields in a page of HubSpot records.

        Modifies and returns the same records in place; if masking is
        disabled, the records are returned unchanged.

        Args:
            records: Records to mask, as returned by
                `HubSpotClient.iter_objects` (each with a `properties`
                dict containing the actual field values).

        Returns:
            The same records, with PII fields masked if enabled.
        """
        if not self._enabled:
            return records
        for record in records:
            self._apply_mask(record)
        return records

    def _apply_mask(self, record: dict) -> None:
        """Masks PII fields within a single record's `properties` dict."""
        properties = record.get("properties")
        if not properties:
            return
        for field in self.FIELDS:
            if field in properties and properties[field] is not None:
                properties[field] = hmac.new(
                    key=self._hmac_key.encode(),
                    msg=str(properties[field]).encode(),
                    digestmod=hashlib.sha256,
                ).hexdigest()
