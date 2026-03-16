# Private Integrations for Home Assistant

Manage custom Home Assistant integrations from private GitHub repositories. Scoped to a single GitHub org or user account. Uses HA's native update entities for discovery, installation, and updates.

## Overview

- Scans a GitHub org/user for repos containing valid `custom_components/` integrations
- Each discovered integration surfaces as a native HA update entity
- Discovery is automatic; installation is manual
- Compatible with HACS repository structure

## Setup

1. Add the integration via the HA UI
2. Provide your GitHub org/user and a fine-grained PAT

### GitHub PAT

Create a [fine-grained personal access token](https://github.com/settings/tokens?type=beta) scoped to your org or user:

| Permission | Access | Purpose |
|---|---|---|
| Contents | Read-only | Download integration files |
| Metadata | Read-only | List and inspect repositories |

## Repository Structure

```
your-repo/
├── custom_components/
│   └── your_domain/
│       ├── __init__.py
│       ├── manifest.json
│       └── ...
├── hacs.json            (optional)
└── README.md
```

**Required:** `custom_components/<domain>/manifest.json` with `domain`, `name`, and `version`.

**Optional:** `hacs.json` at repo root for additional metadata (display name, HA version requirements).

## How It Works

1. **Discover** — Scans the org on a regular interval for repos with a valid `custom_components/<domain>/manifest.json`
2. **Review** — Discovered integrations appear in Settings > System > Updates
3. **Install** — Select which integrations to install
4. **Update** — New releases show up as available updates with release notes
