"""Constants for the Private Repos integration."""

DOMAIN = "private_repos"

CONF_GITHUB_USER = "github_user"
CONF_GITHUB_PAT = "github_pat"
CONF_ACCOUNT_TYPE = "account_type"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 360  # minutes

ACCOUNT_TYPE_ORG = "org"
ACCOUNT_TYPE_USER = "user"

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
