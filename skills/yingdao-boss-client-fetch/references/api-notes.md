# API Notes

## Authentication chain

1. Boss LDAP login
   - endpoint: `endpoints.boss_login_url`
   - request body: username + RSA-encrypted password
   - output: `data.accessToken`

2. Boss asCode exchange
   - endpoint: `endpoints.boss_ascode_url`
   - header: `Authorization: Bearer {accessToken}`
   - output: `data`

3. AppStudio token exchange
   - endpoint: `endpoints.appstudio_token_url`
   - query param: `code={ascode}`
   - output: `data.accessToken`

## Datasource request

Use `endpoints.datasource_exec_url` with:

- `Authorization: Bearer {appStudio_v2_accessToken}`
- `Content-Type: application/json`
- `Referer: endpoints.referer`

The request body uses current defaults from `config.template.json`:

- `nsId`
- `pageId`
- `name`
- `envId`
- `editorMode`
- `build_show_columns`
- `fixed_filters`
- `business_group_filter`

## Pagination

Start from page `1`.
Keep requesting until `current_page >= pages`.
Read rows from `dataList`.

## Shared-data handoff

Default output mode is `storage.mode = "latest"`.
That means each fetch overwrites the shared latest dataset instead of creating an ever-growing pile of timestamped JSON files.

Default shared file:

```text
runtime/yingdao-boss/latest-clients.json
```

Optional archive behavior:

- `storage.mode = "archive"` -> write only timestamped archive files
- `storage.mode = "both"` -> write shared latest + archive files
- CLI `--archive` -> keep default latest behavior and also write one archive snapshot for that run

Downstream analysis skills should treat `runtime/yingdao-boss/latest-clients.json` as the default handoff file.

## Proxy handling

The script defaults to `network.use_env_proxy = false`, so Python `requests` ignores `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` environment variables unless you explicitly turn that on.

## Current required user configuration

The installer must fill these values before the first production run:

- `auth.username`
- `auth.password`
- `defaults.default_business_group`

If they are missing, the script should stop with a clear error.

## Response extraction

The datasource response may be wrapped. The current script tries common nested paths and then reads:

- `pages`
- `total`
- `dataList`

Keep this logic tolerant because the platform response can contain extra wrapper layers.
