# Session file format

Used by `radar auth check` / all online commands.

## Cookie header (simplest)

Save as `data/state/default.json`:

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
- On auth/session failures the scheduler sets `meta.auth_paused` and stops scanning until you fix cookies and run `radar scan-pool --clear-auth-pause` (or delete the meta row).
