job "BD-HubSpot-Service-Prod-App" {
  datacenters = ["glynac-dc"]
  type        = "service"
  namespace   = "extraction-service"

  update {
    max_parallel     = 1
    health_check     = "task_states"
    min_healthy_time = "30s"
  }

  group "black-diamond-hubspot-prod-service" {
    count = 1

    shutdown_delay = "5s"

    network {
      port "http" {
        static       = 5722
        to           = 5722
        host_network = "private"
      }
    }

    service {
      name = "black-diamond-hubspot-service-prod"
      tags = ["apps", "logs.promtail"]
      port = "http"
      check {
        name     = "api-health"
        type     = "http"
        # Trailing slash matters: /api/health (no slash) returns a 308 redirect,
        # which Nomad's HTTP check does not follow and will report as failing.
        path     = "/api/health/"
        interval = "30s"
        timeout  = "10s"
      }
    }

    constraint {
      attribute = "${attr.unique.hostname}"
      value     = "Worker-08"  # TODO: confirm target host per environment before applying
    }

    # Runs once before the main task starts, on every deploy. Applies any pending
    # Alembic migrations. On a database that predates Alembic (has "scans" from the
    # old create_all()), this will fail until someone runs `alembic stamp head`
    # against it once, out of band — see README.md "Database migrations".
    task "migrate" {
      driver = "docker"

      lifecycle {
        hook    = "prestart"
        sidecar = false
      }

      config {
        image       = "harbor-registry.service.consul:8085/black-diamond/black-diamond-hubspot-service:IMAGE_TAG_PLACEHOLDER"
        command     = "alembic"
        args        = ["upgrade", "head"]
        dns_servers = ["172.17.0.1", "172.18.0.1", "8.8.8.8", "8.8.4.4", "1.1.1.1"]
      }

      vault {
        role = "blackdiamond"
      }

      # Uses the same full secret set as the main task: env.py currently calls
      # validate_settings(), which requires every configured variable, not just
      # the DB_* ones migrations actually need. Narrowing that is a follow-up.
      template {
        destination = "secrets/env"
        env         = true
        data        = <<EOF

APP_VERSION="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.APP_VERSION }}{{ end }}"
APP_TITLE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.APP_TITLE }}{{ end }}"
FLASK_ENV="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.FLASK_ENV }}{{ end }}"
FLASK_DEBUG="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.FLASK_DEBUG }}{{ end }}"
SECRET_KEY="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.SECRET_KEY }}{{ end }}"
PORT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PORT }}{{ end }}"
HOST="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HOST }}{{ end }}"
ENVIRONMENT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.ENVIRONMENT }}{{ end }}"
LOG_LEVEL="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.LOG_LEVEL }}{{ end }}"
LOG_FORMAT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.LOG_FORMAT }}{{ end }}"
LOKI_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.LOKI_ENABLED }}{{ end }}"
DB_HOST="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_HOST }}{{ end }}"
DB_PORT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_PORT }}{{ end }}"
DB_NAME="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_NAME }}{{ end }}"
DB_USER="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_USER }}{{ end }}"
DB_PASSWORD="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_PASSWORD }}{{ end }}"
DB_SCHEMA="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_SCHEMA }}{{ end }}"
HUBSPOT_ACCESS_TOKEN="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_ACCESS_TOKEN }}{{ end }}"
HUBSPOT_PORTAL_ID="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_PORTAL_ID }}{{ end }}"
HUBSPOT_BASE_URL="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_BASE_URL }}{{ end }}"
HUBSPOT_API_VERSION="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_API_VERSION }}{{ end }}"
HUBSPOT_PAGE_SIZE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_PAGE_SIZE }}{{ end }}"
HUBSPOT_RATE_LIMIT_RPS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_RATE_LIMIT_RPS }}{{ end }}"
HUBSPOT_INCLUDE_ASSOCIATIONS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_INCLUDE_ASSOCIATIONS }}{{ end }}"
MAX_CONCURRENT_SCANS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MAX_CONCURRENT_SCANS }}{{ end }}"
SCAN_TIMEOUT_HOURS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.SCAN_TIMEOUT_HOURS }}{{ end }}"
CLEANUP_DAYS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLEANUP_DAYS }}{{ end }}"
HMAC_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HMAC_ENABLED }}{{ end }}"
HMAC_SECRET_KEY_CORE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HMAC_SECRET_KEY_CORE }}{{ end }}"
HMAC_SECRET_KEY_ENGINEER="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HMAC_SECRET_KEY_ENGINEER }}{{ end }}"
HMAC_SIGNATURE_MAX_AGE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HMAC_SIGNATURE_MAX_AGE }}{{ end }}"
MINIO_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_ENABLED }}{{ end }}"
MINIO_ENDPOINT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_ENDPOINT }}{{ end }}"
MINIO_ACCESS_KEY="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_ACCESS_KEY }}{{ end }}"
MINIO_SECRET_KEY="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_SECRET_KEY }}{{ end }}"
MINIO_SECURE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_SECURE }}{{ end }}"
MINIO_BUCKET="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_BUCKET }}{{ end }}"
KAFKA_BOOTSTRAP_SERVERS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.KAFKA_BOOTSTRAP_SERVERS }}{{ end }}"
KAFKA_CONSUMER_GROUP_ID="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.KAFKA_CONSUMER_GROUP_ID }}{{ end }}"
KAFKA_AUTO_OFFSET_RESET="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.KAFKA_AUTO_OFFSET_RESET }}{{ end }}"
KAFKA_ENABLE_AUTO_COMMIT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.KAFKA_ENABLE_AUTO_COMMIT }}{{ end }}"
CLICKHOUSE_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_ENABLED }}{{ end }}"
CLICKHOUSE_HOST="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_HOST }}{{ end }}"
CLICKHOUSE_PORT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_PORT }}{{ end }}"
CLICKHOUSE_USER="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_USER }}{{ end }}"
CLICKHOUSE_PASSWORD="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_PASSWORD }}{{ end }}"
CLICKHOUSE_DATABASE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_DATABASE }}{{ end }}"
PII_MASKING_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PII_MASKING_ENABLED }}{{ end }}"
PII_SERVICE_URL="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PII_SERVICE_URL }}{{ end }}"
PII_HMAC_KEY="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PII_HMAC_KEY }}{{ end }}"
PII_SERVICE_ID="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PII_SERVICE_ID }}{{ end }}"
ALLOWED_ORIGINS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.ALLOWED_ORIGINS }}{{ end }}"
BD_CORE_URL="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.BD_CORE_URL }}{{ end }}"

EOF
      }

      resources {
        cpu    = 256
        memory = 256
      }
    }

    task "black-diamond-hubspot-service" {
      driver = "docker"

      config {
        image       = "harbor-registry.service.consul:8085/black-diamond/black-diamond-hubspot-service:IMAGE_TAG_PLACEHOLDER"
        ports       = ["http"]
        dns_servers = ["172.17.0.1", "172.18.0.1", "8.8.8.8", "8.8.4.4", "1.1.1.1"]
      }

      vault {
        role = "blackdiamond"
      }

      template {
        destination = "secrets/env"
        env         = true
        data        = <<EOF

APP_VERSION="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.APP_VERSION }}{{ end }}"
APP_TITLE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.APP_TITLE }}{{ end }}"
FLASK_ENV="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.FLASK_ENV }}{{ end }}"
FLASK_DEBUG="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.FLASK_DEBUG }}{{ end }}"
SECRET_KEY="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.SECRET_KEY }}{{ end }}"
PORT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PORT }}{{ end }}"
HOST="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HOST }}{{ end }}"
ENVIRONMENT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.ENVIRONMENT }}{{ end }}"
LOG_LEVEL="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.LOG_LEVEL }}{{ end }}"
LOG_FORMAT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.LOG_FORMAT }}{{ end }}"
LOKI_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.LOKI_ENABLED }}{{ end }}"
DB_HOST="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_HOST }}{{ end }}"
DB_PORT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_PORT }}{{ end }}"
DB_NAME="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_NAME }}{{ end }}"
DB_USER="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_USER }}{{ end }}"
DB_PASSWORD="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_PASSWORD }}{{ end }}"
DB_SCHEMA="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.DB_SCHEMA }}{{ end }}"
HUBSPOT_ACCESS_TOKEN="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_ACCESS_TOKEN }}{{ end }}"
HUBSPOT_PORTAL_ID="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_PORTAL_ID }}{{ end }}"
HUBSPOT_BASE_URL="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_BASE_URL }}{{ end }}"
HUBSPOT_API_VERSION="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_API_VERSION }}{{ end }}"
HUBSPOT_PAGE_SIZE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_PAGE_SIZE }}{{ end }}"
HUBSPOT_RATE_LIMIT_RPS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_RATE_LIMIT_RPS }}{{ end }}"
HUBSPOT_INCLUDE_ASSOCIATIONS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HUBSPOT_INCLUDE_ASSOCIATIONS }}{{ end }}"
MAX_CONCURRENT_SCANS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MAX_CONCURRENT_SCANS }}{{ end }}"
SCAN_TIMEOUT_HOURS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.SCAN_TIMEOUT_HOURS }}{{ end }}"
CLEANUP_DAYS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLEANUP_DAYS }}{{ end }}"
HMAC_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HMAC_ENABLED }}{{ end }}"
HMAC_SECRET_KEY_CORE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HMAC_SECRET_KEY_CORE }}{{ end }}"
HMAC_SECRET_KEY_ENGINEER="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HMAC_SECRET_KEY_ENGINEER }}{{ end }}"
HMAC_SIGNATURE_MAX_AGE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.HMAC_SIGNATURE_MAX_AGE }}{{ end }}"
MINIO_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_ENABLED }}{{ end }}"
MINIO_ENDPOINT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_ENDPOINT }}{{ end }}"
MINIO_ACCESS_KEY="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_ACCESS_KEY }}{{ end }}"
MINIO_SECRET_KEY="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_SECRET_KEY }}{{ end }}"
MINIO_SECURE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_SECURE }}{{ end }}"
MINIO_BUCKET="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.MINIO_BUCKET }}{{ end }}"
KAFKA_BOOTSTRAP_SERVERS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.KAFKA_BOOTSTRAP_SERVERS }}{{ end }}"
KAFKA_CONSUMER_GROUP_ID="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.KAFKA_CONSUMER_GROUP_ID }}{{ end }}"
KAFKA_AUTO_OFFSET_RESET="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.KAFKA_AUTO_OFFSET_RESET }}{{ end }}"
KAFKA_ENABLE_AUTO_COMMIT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.KAFKA_ENABLE_AUTO_COMMIT }}{{ end }}"
CLICKHOUSE_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_ENABLED }}{{ end }}"
CLICKHOUSE_HOST="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_HOST }}{{ end }}"
CLICKHOUSE_PORT="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_PORT }}{{ end }}"
CLICKHOUSE_USER="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_USER }}{{ end }}"
CLICKHOUSE_PASSWORD="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_PASSWORD }}{{ end }}"
CLICKHOUSE_DATABASE="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.CLICKHOUSE_DATABASE }}{{ end }}"
PII_MASKING_ENABLED="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PII_MASKING_ENABLED }}{{ end }}"
PII_SERVICE_URL="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PII_SERVICE_URL }}{{ end }}"
PII_HMAC_KEY="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PII_HMAC_KEY }}{{ end }}"
PII_SERVICE_ID="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.PII_SERVICE_ID }}{{ end }}"
ALLOWED_ORIGINS="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.ALLOWED_ORIGINS }}{{ end }}"
BD_CORE_URL="{{ with secret "secrets/data/blackdiamond/blackdiamond-hubspot-service-prod" }}{{ .Data.data.BD_CORE_URL }}{{ end }}"

EOF
      }

      resources {
        cpu    = 1024
        memory = 1024
      }
    }
  }
}
