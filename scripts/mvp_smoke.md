# MVP smoke checklist

离线自动测试使用临时数据库，不写入运行数据库：

```bash
cd /root/projects/xianyu-radar
source .venv/bin/activate
pytest -q
```

Online path (requires real cookie):

1. Export goofish cookies to `data/state/default.json` (see `docs/session_format.md`).
2. `radar auth check` then optionally `radar auth check --ping`
3. `radar discover --keyword "你的已验证商品关键词"`
4. `radar pool list`
5. `radar scan-pool`  # baseline only when the seller has no prior active items
6. Wait / run again → NEW_ITEM may enter candidates
7. `radar candidates --since 24h`
8. Long run: `radar run --interval 90 --jitter 30`

## Known limits

- Search/detail may hit x5sec; auth pause is set on session failures.
- MVP candidate rule: title contains watch keyword → treat as target, skip candidate.
- No AI / auto-list / shipping. The Web UI supports manual operation.
- `_research/` is read-only reference.
