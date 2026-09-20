# BLS 事件日历维护

目标：即使 BLS 的 ICS 日历在当前主机返回 403，晨间看板仍能使用经过校验的就业、CPI 和 PPI 官方发布日期。

## 每日流程

1. 只读取 BLS 官方页面：
   - `https://www.bls.gov/schedule/news_release/empsit.htm`
   - `https://www.bls.gov/schedule/news_release/cpi.htm`
   - `https://www.bls.gov/schedule/news_release/ppi.htm`
2. 采集从运行时起未来 120 天内的 Employment Situation、Consumer Price Index、Producer Price Index。
3. 把候选写入 `data/context/schedules/bls/candidate.json`。候选不能直接进入看板。
4. 运行：

   ```bash
   python3 scripts/validate_bls_schedule.py --candidate data/context/schedules/bls/candidate.json
   ```

5. 只有命令返回 0 且 `promoted=true`，生产缓存 `data/context/schedules/bls/latest.json` 才会被替换。校验失败或需要人工复核时，不得直接编辑 `latest.json`。

## 候选格式

```json
{
  "schema_version": "1.0",
  "candidate_id": "bls-YYYYMMDD-HHMM",
  "generated_at": "ISO-8601 UTC",
  "producer": {
    "type": "codex_scheduled_task",
    "model": "gpt-5.6-sol",
    "reasoning_effort": "medium"
  },
  "events": [
    {
      "release_type": "employment_situation | cpi | ppi",
      "title": "官方英文事件名与参考月份",
      "reference_period": "August 2026",
      "starts_at": "ISO-8601 UTC",
      "timezone": "America/New_York",
      "source_url": "对应的 bls.gov 官方日程页",
      "source_name": "U.S. Bureau of Labor Statistics",
      "evidence_text": "能直接支持日期、年份与 08:30 AM 的简短官方页面证据"
    }
  ]
}
```

## 硬校验

- 来源必须是 HTTPS 的 `bls.gov` 官方域名。
- 事件类型、标题和参考月份必须匹配。
- 发布时间必须换算为 `America/New_York` 当地 08:30。
- 近 45 天必须同时覆盖就业、CPI、PPI。
- 同类型同时间不能重复。
- 近 45 天事件若相对上一版消失，或移动超过 3 天，只记录 `needs_review`，不自动替换生产缓存。
- 缓存 7 天内正常使用，8 至 14 天降级使用，超过 14 天停止使用。
