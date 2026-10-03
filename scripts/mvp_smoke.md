# MVP smoke checklist

离线自动测试使用临时数据库，不写入运行数据库：

```bash
cd /root/projects/xianyu-radar
source .venv/bin/activate
pytest -q
```

Online path (requires real cookie):

1. Configure Helper using `docs/session_format.md`; log in and handle verification in Helper.
2. `radar auth check` then optionally `radar auth check --ping`
3. `radar discover --keyword "你的已验证商品关键词"`
4. `radar pool list`
5. `radar scan-pool`  # seller 的首次成功店铺扫描始终是 baseline，不生成候选
6. Wait / run again → NEW_ITEM may enter candidates
7. `radar candidates --quality normal --since 24h`；旧记录用 `--quality legacy_unverified` 复核
8. Long run: `radar run --interval 90 --jitter 30`

## Known limits

- Search/detail may hit x5sec; auth pause is set on session failures.
- MVP candidate rule: title contains watch keyword → treat as target, skip candidate.
- No AI / auto-list / shipping. The Web UI supports manual operation.
- `_research/` is read-only reference.
- 不完整或商品数骤降的扫描不会立即生成变化事件；诊断信息在最近扫描记录中查看。
