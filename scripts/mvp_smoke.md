# MVP smoke checklist

Offline path (no real cookies):

```bash
cd /root/projects/xianyu-radar
source .venv/bin/activate
radar init-db
pytest -q

# parse search fixture
radar search --dry-parse-fixture tests/fixtures/search_results.json

# discover offline (no seller_id in fixture → skipped_no_seller)
radar discover --keyword "Sony A7M4" --fixture tests/fixtures/search_results.json --no-enrich

# baseline + second scan via shop fixture (manual seller id)
radar scan-seller demo_seller --fixture tests/fixtures/shop_items.json --keyword "无关关键词"
# run again after editing fixture or use apply twice with different sets via tests

radar candidates --since 24h
radar events --since 24h
```

Online path (requires real cookie):

1. Export goofish cookies to `data/state/default.json` (see `data/state/README.md`).
2. `radar auth check` then optionally `radar auth check --ping`
3. `radar discover --keyword "你的已验证商品关键词"`
4. `radar pool list`
5. `radar scan-pool`  # first pass = baseline
6. Wait / run again → NEW_ITEM may enter candidates
7. `radar candidates --since 24h`
8. Long run: `radar run --interval 90 --jitter 30`

## Known limits

- Search/detail may hit x5sec; auth pause is set on session failures.
- MVP candidate rule: title contains watch keyword → treat as target, skip candidate.
- No GUI / AI / auto-list / shipping.
- `_research/` is read-only reference.
