# Changelog: Upgrade to Native Boss APIs (2026-06-08)

## Background

Previously, the customer and contract fetching scripts accessed the Yingdao Boss platform data by exchanging tokens through the AppStudio gateway (`login/ldap` -> `getAsCode` -> `generateTokenByCode`) and querying AppStudio data execution endpoints. 

Around June 2026, the AppStudio datasource endpoints started returning `4003 - 无权限操作` (No permission to operate) for the LDAP account, indicating that access to the AppStudio workspaces/pages had been deactivated or migrated.

To restore functionality, this update migrates all fetching logic to use the Boss platform's native REST APIs and simplifies the authentication pipeline.

---

## Changes Implemented

### 1. Simplified Authentication Flow
- **Bypassed AppStudio Token Chain**: Removed `get_ascode` and `get_appstudio_token` helper functions from `fetch_clients.py` and their references in `fetch_contracts.py`.
- **Direct Bearer Token Usage**: The native Boss APIs authenticate using the direct `accessToken` returned from LDAP login (`login_to_yingdao_boss`).

### 2. Native Endpoint Migration
- **Client List Fetching (`fetch_clients.py`)**:
  - Moved from AppStudio to `/boss/api/v3/aftersales/scene/query`.
  - Refactored query payload parameters to use native scene query structure (`conditions`, `showColumnIds`, `page`, `size`, `sortCondition`).
  - Reused existing filter definitions (`fixed_filters`, `business_group_filter`) and column IDs (`build_show_columns`) from the configuration.
- **Contract Fetching (`fetch_contracts.py`)**:
  - Moved from AppStudio to `/boss/api/v3/oms/oms/contract/pageAndOrder`.
  - Refactored request payload to a clean parameter query (`customNo`, `statusList`, `paymentStatusList`, `page`, `size`, `sortColumn`, `isAsc`).
  - Kept compatibility with downstream analysis scripts by retaining the identical layout for returned contract and sub-order records.

### 3. App Dashboard Statistics Fetching (`fetch_apps.py`)
- **Direct tenantUuid Fallback**: If a client has no merge record in Boss, the `mergeInfo` API returns a 404 error. The script now automatically falls back to using the `organizationUuid` directly as the `tenantUuid` instead of skipping the client.
- **Robust Error Validation & Retries**: Added support to parse and bubble up application-level API errors (even on HTTP 200). Implemented a 3-attempt retry loop for dashboard queries to gracefully handle transient rate limit errors (`500 - 访问频繁，稍后再试`).

### 4. Configuration Cleanups
- Removed deprecated AppStudio endpoint URLs (`boss_ascode_url`, `appstudio_token_url`, `datasource_exec_url`) from `config.template.json` and `config.local.json`.
- Removed deprecated datasource IDs (`nsId`, `pageId`, etc.) and the entire `contract_datasource` block.

---

## Verification & Usage

All updated scripts were tested successfully in the `llm` conda environment:

1. **Client Data Fetching**:
   ```bash
   python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py --business-group "江苏业务组"
   ```
2. **Contract Fetching**:
   ```bash
   python3 skills/yingdao-boss-data-hub/scripts/fetch_contracts.py
   ```
3. **App statistics Fetching**:
   ```bash
   python3 skills/yingdao-boss-data-hub/scripts/fetch_apps.py
   ```
4. **Downstream Expiration Analysis**:
   ```bash
   python3 skills/yingdao-boss-data-hub/scripts/analyze_expiring_orders.py
   ```
