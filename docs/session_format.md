# Session file format

Used by `radar auth check` / all online commands.

## Cookie header (simplest)

Save as `data/prod/state/default.json` for real scans, or `data/demo/state/default.json` for demo data:

```json
{
  "cookie": "_m_h5_tk=TOKEN_TIMESTAMP; _m_h5_tk_enc=...; cookie2=..."
}
```

## Cookies array (Asher / Chrome extension style)

```json
{
  "cookies": [
    { "name": "_m_h5_tk", "value": "TOKEN_TIMESTAMP", "domain": ".goofish.com" },
    { "name": "cookie2", "value": "..." }
  ]
}
```

## Notes

- `_m_h5_tk` is **required**. Sign token = substring before the first `_`.
- Do not commit real cookie files. `data/` is gitignored.
- 扫描遇到登录态失效时会写入 `meta.auth_paused` 并停止后续扫描。更新 Cookie 后可运行 `radar scan-pool --clear-auth-pause` 清除暂停。
