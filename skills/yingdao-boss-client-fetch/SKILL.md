---
name: yingdao-boss-client-fetch
description: Fetch customer/client data from Yingdao's Boss platform through the Boss login, asCode exchange, and AppStudio token chain, then download all paginated datasource records for a specified business group. Use when a user asks to pull, export, refresh, or inspect Yingdao Boss customer tables, configure this workflow for first use, or produce the shared latest dataset that a downstream analysis skill will consume.
---

# Yingdao Boss Client Fetch

## Overview

Use this skill to fetch client data from Yingdao's Boss platform for a business group.
The workflow authenticates through the Boss platform, exchanges tokens, downloads every page from the configured AppStudio datasource, and writes a **shared latest dataset** for downstream analysis.

## First-time setup

Before the first real run, create `config.local.json` by copying `config.template.json` and fill in these required values:

- `auth.username`
- `auth.password`
- `defaults.default_business_group`

If any of these are missing, stop and ask the user to complete configuration before running the script.
Do not package or share real credentials.
Do not keep `config.local.json` or fetched customer-data outputs inside the skill folder when packaging; keep only the template in the packaged skill.

Recommended runtime config location:

```text
runtime/yingdao-boss-client-fetch/config.local.json
```

## Install dependencies

Run from the skill root directory:

```bash
pip install -r skills/yingdao-boss-client-fetch/scripts/requirements.txt
```

## Default workflow

1. Load `config.local.json`.
2. Validate that username, password, and default business group are configured.
3. Encrypt the Boss password with the built-in RSA public key.
4. Call the Boss LDAP login endpoint and extract `accessToken`.
5. Call the Boss `getAsCode` endpoint with that token and extract `ascode`.
6. Call the AppStudio `generateTokenByCode` endpoint and extract `appStudio_v2_accessToken`.
7. Call the datasource execution endpoint starting from page `1`.
8. Continue in a loop until the returned `pages` value is reached.
9. Merge all `dataList` rows into a single result set.
10. Write the result into the shared latest dataset file.

## Shared-data mode

Default behavior is:

- overwrite the latest shared dataset
- do not create a new timestamped file each run
- keep disk usage stable

Default shared dataset location:

```text
runtime/yingdao-boss/latest-clients.json
```

This file is the handoff point for the downstream analysis skill.
That analysis skill should read this file by default instead of expecting a new timestamped export every run.

## Running the script

Use the default configured business group and update the shared latest dataset:

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py
```

Use an explicit config path:

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py --config ./runtime/yingdao-boss-client-fetch/config.local.json
```

Override the business group for one run:

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py --business-group "江苏业务组"
```

Write a custom one-off output file instead of the shared latest path:

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py --output ./custom-output.json
```

Update the shared latest dataset and also save an archive snapshot:

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py --archive
```

## Output format

The output uses a stable structure for downstream skills:

```json
{
  "schema": "yingdao-boss-client-fetch.v1",
  "meta": {
    "fetched_at": "...",
    "business_group": "江苏业务组",
    "page_size": 100,
    "page_count": 1,
    "row_count": 59,
    "total": 59,
    "nsId": "...",
    "pageId": "..."
  },
  "rows": [ ... ]
}
```

Keep the raw row structure for now. Field mapping can be added later without changing the fetch-and-handoff contract.

## When to adjust configuration

Read `references/api-notes.md` when you need to change:

- endpoint URLs
- `nsId`
- `pageId`
- page size
- fixed filters
- business-group filter column id
- default displayed column ids
- proxy behavior (`network.use_env_proxy`)
- shared latest vs archive behavior (`storage.*`)

## Resources

- `skills/yingdao-boss-client-fetch/scripts/fetch_clients.py`: end-to-end fetch script
- `skills/yingdao-boss-client-fetch/scripts/requirements.txt`: Python dependencies
- `skills/yingdao-boss-client-fetch/config.template.json`: configuration template without secrets
- `skills/yingdao-boss-client-fetch/references/api-notes.md`: request flow and shared-data notes
