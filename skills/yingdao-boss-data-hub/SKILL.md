---
name: yingdao-boss-data-hub
description: Fetch customer/client data from Yingdao's Boss platform through the Boss login, asCode exchange, and AppStudio token chain, then download all paginated datasource records for a specified business group. Use when a user asks to pull, export, refresh, or inspect Yingdao Boss customer tables, configure this workflow for first use, or produce the shared latest dataset that a downstream analysis skill will consume.
---

# Yingdao Boss Data Hub

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
runtime/yingdao-boss-data-hub/config.local.json
```

## Install dependencies

Run from the skill root directory:

```bash
pip install -r skills/yingdao-boss-data-hub/scripts/requirements.txt
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
runtime/yingdao-boss/latest-app-run-insights.json
```

These files are the handoff point for the downstream analysis skill.
That analysis skill should read these files by default instead of expecting a new timestamped export every run.

## Running the script

Use the default configured business group and update the shared latest dataset:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py
```

Use an explicit config path:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py --config ./runtime/yingdao-boss-data-hub/config.local.json
```

Override the business group for one run:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py --business-group "江苏业务组"
```

Write a custom one-off output file instead of the shared latest path:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py --output ./custom-output.json
```

Update the shared latest dataset and also save an archive snapshot:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py --archive
```

### Fetching Contracts

Ensure you have run `fetch_clients.py` first, then run:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_contracts.py
```

It supports similar arguments (`--config`, `--output`, `--page-size`, `--archive`, `--clients-input`).
Furthermore, you can pull a specific client's contracts using the `--client-no` or `--client-name` flag (e.g. `--client-name "江苏**"`) which will save their data independently to `contracts-{client}.json`.

### Analyzing Expiring Orders

Once contracts are pulled, you can evaluate the expiration status of customer purchases.

```bash
python3 skills/yingdao-boss-data-hub/scripts/analyze_expiring_orders.py
```

This script:
1. Groups all records by client.
2. Identifies the "latest contract" per client.
3. Filters their orders down to valid main subscription types (`new`, `renew`); `add` upsell orders do not override the main subscription expiration date.
4. Extracts the minimum start date, maximum expiration date, and sum of those valid items.
5. Groups clients into categories (`Expired (已过期)`, `0-30 Days`, `31-60 Days`, `61-90 Days`). Clients expired for more than 30 days are automatically hidden.
6. Prints the results securely to the console and outputs `contracts-expiration-summary.json` inside the `runtime/yingdao-boss` directory.

### Fetching App Dashboards (Application Lists)

You can pull the detailed list of applications and their usage statistics for your clients:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_apps.py
```

This script will automatically:
1. Load `latest-clients.json` to get `organizationUuid` values.
2. Translate `organizationUuid` to `tenantUuid` via the Boss `mergeInfo` API.
3. Fetch paginated app records via `queryAppDashboardInfo`.
4. Output to `runtime/yingdao-boss/latest-apps.json`.

Like the contract fetcher, you can pull apps for a specific client to save them independently:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_apps.py --client-name "江苏**"
```

### Fetching Tenant Data Reports (Daily Statistics)

You can pull the daily usage data reports (daily statistics) for your clients:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_tenant_reports.py
```

This script will automatically:
1. Load `latest-clients.json` to get `organizationUuid` values.
2. Translate `organizationUuid` to `tenantUuid` via the Boss `mergeInfo` API.
3. Fetch daily report data ranges via `queryTenantDataDayListRange`.
4. Output to `runtime/yingdao-boss/latest-reports.json`.

You can also target specific clients or override the date range (defaulting to the last 365 days):

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_tenant_reports.py \
  --client-name "妮茜雅" \
  --start-date "20250616" \
  --end-date "20260615"
```

### Building App Run Insights from Detailed XLSX Exports

The customer success dashboard can optionally show `运行洞察` in the client drawer.
This feature is based on detailed BOSS XLSX exports, not on the normal daily report API.

Generate app run insight aggregates from a downloaded tenant dashboard XLSX:

```bash
python skills/yingdao-boss-data-hub/scripts/build_app_run_insights.py \
  runtime/yingdao-boss/客户数据看板.xlsx \
  --output runtime/yingdao-boss/latest-app-run-insights.json \
  --client-name "客户名称" \
  --organization-uuid "organizationUuid" \
  --custom-no "客户编号"
```

The dashboard builder treats `latest-app-run-insights.json` as optional. If it is missing, the dashboard still builds and the `运行洞察` tab shows an empty state for clients without detailed run data.

Run insight user and maintenance docs:

- `skills/yingdao-boss-data-hub/docs/run-insights-csm-guide.md`
- `skills/yingdao-boss-data-hub/docs/run-insights-technical.md`

### Building the Customer Success Action Dashboard

Use the static dashboard workflow when the user wants to inspect client-success risk, renewal follow-up priority, per-client daily metric trends, or the generated customer-success workbench.

Recommended one-command workflow:

```bash
python3 skills/yingdao-boss-data-hub/dashboard/refresh_dashboard.py
```

`refresh_dashboard.py` checks whether each related JSON output is already from today (timezone default: `Asia/Shanghai`). If a file is fresh, it skips the corresponding data fetch/analyze step; if a file is missing or stale, it runs the needed step. It always rebuilds `dashboard.html` at the end.

Equivalent full data refresh order:

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py
python3 skills/yingdao-boss-data-hub/scripts/fetch_contracts.py
python3 skills/yingdao-boss-data-hub/scripts/analyze_expiring_orders.py
python3 skills/yingdao-boss-data-hub/scripts/fetch_tenant_reports.py
python3 skills/yingdao-boss-data-hub/dashboard/build_data.py
```

The dashboard builder reads:

- `runtime/yingdao-boss/latest-reports.json` (required): daily tenant report rows and metric trends
- `runtime/yingdao-boss/latest-clients.json` (optional): CS owner, service stage, cooperation status, deployment type, renewal metadata
- `runtime/yingdao-boss/contracts-expiration-summary.json` (optional): near-expiration contract buckets and contract details
- `runtime/yingdao-boss/latest-app-run-insights.json` (optional): detailed app-run aggregates for `运行洞察`

It writes the self-contained static dashboard:

```text
skills/yingdao-boss-data-hub/dashboard/dashboard.html
```

Dashboard file responsibilities:

- `dashboard/_template.html`: source template for layout, styles, CSM diagnosis rules, filters, drawer interactions, table rendering, and per-client ECharts line charts
- `dashboard/build_data.py`: build script that merges the JSON inputs and injects them into the template
- `dashboard/dashboard.html`: generated artifact to open in a browser; do not hand-edit because it is overwritten by `build_data.py`
- `dashboard/refresh_dashboard.py`: orchestration script that skips same-day JSON fetches and then rebuilds the dashboard

If only daily report data is available, `build_data.py` still generates the dashboard and gracefully omits client profile / expiration enrichments.

Current dashboard behavior:

- Two top-level modes:
  - `指标观察`: default objective metric view, sorted from low to high by the selected metric.
  - `CSM 诊断`: action workbench with Top 10 priority follow-up, action queues, and renewal quarter view.
- Default metric: `dayRunCnt` / 运行次数.
- Supported comparison modes: period-over-period, year-over-year, and no comparison.
- Metric charts can overlay the comparison period as a dashed line.
- Structured filters cover service stage, customer tier, renewal quarter, and CS owner.
- Service stage filtering defaults to hiding lost/expired customers.
- `CSM 诊断` Top 10 excludes expired recovery and data-check queues.
- Customer cards open a drawer with all 9 metric trend charts, contract summary, and BOSS detail link.
- Customer drawers include the optional `运行洞察` tab when detailed app-run data is available.
- The drawer has independent comparison controls, independent Y-axis scaling, configurable chart columns, and persisted width.
- Browser-local settings use `localStorage` keys:
  - `dashboard_card_fields`
  - `dashboard_drawer_width`
  - `dashboard_drawer_chart_columns`
  - `dashboard_core_apps_v1`

## Output format

The output uses a stable structure for downstream skills:

```json
{
  "schema": "yingdao-boss-data-hub.v1",
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

## Dashboard Export Workflow (`export_dashboard.py`)

This script automates the three-step async export flow for tenant dashboard data.

1. Looks up `组织UUID` for each client by matching `组织名称` in `latest-clients.json`.
2. Submits export requests to the Boss API (uses Boss `accessToken` directly — no AppStudio chain).
3. Polls the export task list every 10 seconds (up to 3 minutes) until all tasks reach `status=success`, matched by client name and date in the `fileName`.
4. Downloads each xlsx via the pre-signed COS URL and saves it to the output directory.

Dates are computed automatically: `endDate` = yesterday, `startDate` = 365 days before `endDate`.

### Prerequisites

`fetch_clients.py` must have been run at least once so that `latest-clients.json` is available.

### Running

Export dashboards for one or more clients using defaults:

```bash
python3 skills/yingdao-boss-data-hub/scripts/export_dashboard.py \
  --client-names "南京***电子商务有限公司" "上海***电子商务有限公司"
```

With a custom config and output directory:

```bash
python3 skills/yingdao-boss-data-hub/scripts/export_dashboard.py \
  --client-names "江苏***药房连锁有限公司" \
  --config ./runtime/yingdao-boss-data-hub/config.local.json \
  --output-dir ./runtime/yingdao-boss/exports
```

Override the end date (useful for back-filling):

```bash
python3 skills/yingdao-boss-data-hub/scripts/export_dashboard.py \
  --client-names "南京***电子商务有限公司" \
  --end-date 20260401
```

### Output

Downloaded xlsx files are saved to `output_dir` (default `/tmp`). The script also prints a JSON summary:

```json
{
  "ok": true,
  "start_date": "20250428",
  "end_date": "20260427",
  "results": [
    {"client": "南京***电子商务有限公司", "status": "ok", "file": "/tmp/南京***电子商务有限公司数据看板_xxx.xlsx"}
  ]
}
```

### Config keys (`export_dashboard`)

- `output_dir`: where to save xlsx files (default: `/tmp`)
- `poll_interval_seconds`: seconds between task-list polls (default: `10`)
- `poll_max_seconds`: total wait budget before timeout error (default: `180`)
- `task_page_size`: number of recent tasks fetched per poll (default: `10`)

## Resources

- `skills/yingdao-boss-data-hub/scripts/fetch_clients.py`: end-to-end fetch script for client basic data
- `skills/yingdao-boss-data-hub/scripts/fetch_contracts.py`: end-to-end fetch script for client contracts
- `skills/yingdao-boss-data-hub/scripts/export_dashboard.py`: three-step async export of tenant dashboard xlsx files
- `skills/yingdao-boss-data-hub/scripts/analyze_expiring_orders.py`: analysis script for isolating clients with soon-to-expire subscriptions
- `skills/yingdao-boss-data-hub/scripts/fetch_apps.py`: end-to-end fetch script for client application lists & dashboard stats
- `skills/yingdao-boss-data-hub/scripts/fetch_tenant_reports.py`: end-to-end fetch script for client daily tenant reports
- `skills/yingdao-boss-data-hub/dashboard/build_data.py`: builds the self-contained customer-success dashboard from latest JSON outputs
- `skills/yingdao-boss-data-hub/dashboard/refresh_dashboard.py`: refreshes stale dashboard JSON inputs, skips same-day outputs, and rebuilds the dashboard
- `skills/yingdao-boss-data-hub/dashboard/_template.html`: source template for the generated dashboard
- `skills/yingdao-boss-data-hub/dashboard/dashboard.html`: generated static dashboard artifact
- `skills/yingdao-boss-data-hub/scripts/requirements.txt`: Python dependencies
- `skills/yingdao-boss-data-hub/config.template.json`: configuration template without secrets
- `skills/yingdao-boss-data-hub/references/api-notes.md`: request flow, enums, schema translation, and shared-data notes
