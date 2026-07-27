MINIMUM_KEY_LENGTH = 32
PLACEHOLDER_PREFIX = "REPLACE_WITH"
LOG_LEVELS = ["debug", "info", "warning", "error", "critical"]
KAFKA_TOPIC_PREFIX_BY_OBJECT: dict[str, str] = {
    "contacts": "hs.contacts",
    "companies": "hs.companies",
    "deals": "hs.deals",
    "tickets": "hs.tickets",
    "leads": "hs.leads",
    "owners": "hs.owners",
    "engagements": "hs.engagements",
}
