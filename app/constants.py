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

SUPPORTED_OBJECTS: dict[str, dict] = {
    "contacts": {
        "label": "Contacts",
        "api_endpoint": "/crm/v3/objects/contacts",
        "default_properties": ["email", "firstname", "lastname", "lastmodifieddate"],
        "supports_incremental": True,
        "supports_associations": True,
        "association_targets": ["companies"],
    },
    "companies": {
        "label": "Companies",
        "api_endpoint": "/crm/v3/objects/companies",
        "default_properties": ["name", "domain", "lastmodifieddate"],
        "supports_incremental": True,
        "supports_associations": True,
        "association_targets": ["contacts"],
    },
    "deals": {
        "label": "Deals",
        "api_endpoint": "/crm/v3/objects/deals",
        "default_properties": ["dealname", "amount", "dealstage", "lastmodifieddate"],
        "supports_incremental": True,
        "supports_associations": True,
        "association_targets": ["contacts", "companies"],
    },
    "tickets": {
        "label": "Tickets",
        "api_endpoint": "/crm/v3/objects/tickets",
        "default_properties": [
            "subject",
            "content",
            "hs_pipeline_stage",
            "lastmodifieddate",
        ],
        "supports_incremental": True,
        "supports_associations": True,
        "association_targets": ["contacts", "companies"],
    },
    "leads": {
        "label": "Leads",
        "api_endpoint": "/crm/v3/objects/leads",
        "default_properties": [
            "hs_lead_name",
            "hs_lead_type",
            "hs_lead_label",
            "lastmodifieddate",
        ],
        "supports_incremental": True,
        "supports_associations": True,
        "association_targets": ["contacts"],
    },
}
