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

## Contract / Order Fetch Workflow (`fetch_contracts.py`)

This script can be executed *after* `fetch_clients.py` has run.

1. It reads the shared `latest-clients.json` file.
2. It extracts unique `客户编号` (customNo) across all clients.
3. It performs the same authentication flow into AppStudio.
4. For each client, it queries `contract_datasource` payload with the customNo added to `variables.queryBaseInfo.data`.
5. It handles pagination, adds a `_customNo` key to track origin, and combines everything.
6. The compiled list is saved to `runtime/yingdao-boss/latest-contracts.json`.

## Shared-data mode

Default behavior is:

- overwrite the latest shared dataset
- do not create a new timestamped file each run
- keep disk usage stable

Default shared dataset locations:

```text
runtime/yingdao-boss/latest-clients.json
runtime/yingdao-boss/latest-contracts.json
```

These files are the handoff point for the downstream analysis skill.
That analysis skill should read these files by default instead of expecting a new timestamped export every run.

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

### Fetching Contracts

Ensure you have run `fetch_clients.py` first, then run:

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_contracts.py
```

It supports similar arguments (`--config`, `--output`, `--page-size`, `--archive`, `--clients-input`).
Furthermore, you can pull a specific client's contracts using the `--client-no` or `--client-name` flag (e.g. `--client-name "江苏**"`) which will save their data independently to `contracts-{client}.json`.

### Analyzing Expiring Orders

Once contracts are pulled, you can evaluate the expiration status of customer purchases.

```bash
python3 skills/yingdao-boss-client-fetch/scripts/analyze_expiring_orders.py
```

This script:
1. Groups all records by client.
2. Identifies the "latest contract" per client.
3. Filters their orders down to valid subscription types (`new`, `renew`, `add`).
4. Extracts the minimum start date, maximum expiration date, and sum of those valid items.
5. Groups clients into categories (`Expired (已过期)`, `0-30 Days`, `31-60 Days`). Clients expired for more than 30 days are automatically hidden.
6. Prints the results securely to the console and outputs `contracts-expiration-summary.json` inside the `runtime/yingdao-boss` directory.

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

- `skills/yingdao-boss-client-fetch/scripts/fetch_clients.py`: end-to-end fetch script for client basic data
- `skills/yingdao-boss-client-fetch/scripts/fetch_contracts.py`: end-to-end fetch script for client contracts
- `skills/yingdao-boss-client-fetch/scripts/analyze_expiring_orders.py`: analysis script for isolating clients with soon-to-expire subscriptions
- `skills/yingdao-boss-client-fetch/scripts/requirements.txt`: Python dependencies
- `skills/yingdao-boss-client-fetch/config.template.json`: configuration template without secrets
- `skills/yingdao-boss-client-fetch/references/api-notes.md`: request flow, enums, schema translation, and shared-data notes
