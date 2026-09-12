# Data security notes (Radar)

## Secrets on disk

| Path | Contents | Expected mode |
|------|----------|---------------|
| `.env` | Broker token, account id | `0600` |
| `data/<env>/state/*.json` | Local pasted cookies (fallback) | `0600` |
| `data/<env>/radar.sqlite3` | Sellers / items / events (no cookies in broker mode) | `0600` |
| `data/` directories | Runtime data | `0700` |

Broker mode keeps leased cookies **in memory only**; do not write them to `state/`.

## API hygiene

- `/api/status` and `/api/auth/*` never return Cookie plaintext or `_m_h5_tk`.
- Auth views expose `token_prefix` (8 chars) and `lease_active` only.
- Broker errors are redacted before raising.

## Ops checklist

```bash
chmod 600 .env
chmod -R go-rwx data/
# rotate broker token on Helper + Radar together, then recreate Helper app / restart Radar
```
