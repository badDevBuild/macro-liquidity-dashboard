#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "data" / "snapshots" / "latest.json"
SOURCES_PATH = ROOT / "config" / "sources.json"
OUTPUT_DIR = ROOT / "reports" / "data-channel-validation"
EVIDENCE_DB = OUTPUT_DIR / "evidence.sqlite3"


GROUP_LABELS = {
    "fed_balance_sheet": "联储资产负债表",
    "fiscal_cash": "财政现金",
    "money_market": "货币市场",
    "market_transmission": "市场传导",
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_evidence_db(
    headline_rows: list[dict], group_rows: list[dict], route_rows: list[dict]
) -> None:
    EVIDENCE_DB.parent.mkdir(parents=True, exist_ok=True)
    temporary = EVIDENCE_DB.with_suffix(".sqlite3.tmp")
    if temporary.exists():
        temporary.unlink()
    db = sqlite3.connect(temporary)
    try:
        db.executescript(
            """
            CREATE TABLE report_headlines (
                run_id TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                publication_status TEXT NOT NULL,
                analysis_allowed INTEGER NOT NULL,
                metric_count INTEGER NOT NULL,
                source_route_count INTEGER NOT NULL,
                coverage_ratio REAL NOT NULL,
                revision_count INTEGER NOT NULL,
                conflict_count INTEGER NOT NULL
            );
            CREATE TABLE group_coverage (
                group_id TEXT PRIMARY KEY,
                group_label TEXT NOT NULL,
                eligible INTEGER NOT NULL,
                total INTEGER NOT NULL,
                minimum INTEGER NOT NULL,
                coverage_ratio REAL NOT NULL,
                passed INTEGER NOT NULL
            );
            CREATE TABLE source_routes (
                source_id TEXT PRIMARY KEY,
                metric_id TEXT NOT NULL,
                source_owner TEXT NOT NULL,
                authority TEXT NOT NULL,
                quality_status TEXT NOT NULL,
                observed_at TEXT,
                age_days INTEGER,
                selected_for_metric INTEGER NOT NULL,
                cadence TEXT NOT NULL
            );
            """
        )
        db.executemany(
            "INSERT INTO report_headlines VALUES (:run_id, :completed_at, :publication_status, :analysis_allowed, :metric_count, :source_route_count, :coverage_ratio, :revision_count, :conflict_count)",
            [
                {**row, "analysis_allowed": int(row["analysis_allowed"])}
                for row in headline_rows
            ],
        )
        db.executemany(
            "INSERT INTO group_coverage VALUES (:group_id, :group_label, :eligible, :total, :minimum, :coverage_ratio, :passed)",
            [{**row, "passed": int(row["passed"])} for row in group_rows],
        )
        db.executemany(
            "INSERT INTO source_routes VALUES (:source_id, :metric_id, :source_owner, :authority, :quality_status, :observed_at, :age_days, :selected_for_metric, :cadence)",
            [
                {**row, "selected_for_metric": int(row["selected_for_metric"])}
                for row in route_rows
            ],
        )
        db.commit()
    finally:
        db.close()
    temporary.replace(EVIDENCE_DB)


def build() -> dict:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    registry = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    publication = snapshot["publication"]
    selected_sources = {
        metric_id: metric["source_id"] for metric_id, metric in snapshot["metrics"].items()
    }

    group_rows = []
    for group_id, check in publication["group_checks"].items():
        group_rows.append(
            {
                "group_id": group_id,
                "group_label": GROUP_LABELS[group_id],
                "eligible": check["eligible"],
                "total": check["total"],
                "minimum": check["minimum"],
                "coverage_ratio": check["eligible"] / check["total"],
                "passed": check["passed"],
            }
        )

    route_rows = []
    source_health = snapshot["source_health"]
    for configured in registry["sources"]:
        health = source_health[configured["id"]]
        route_rows.append(
            {
                "source_id": configured["id"],
                "metric_id": configured["metric_id"],
                "source_owner": configured["source_owner"],
                "authority": configured["authority"],
                "quality_status": health["quality_status"],
                "observed_at": health["observed_at"],
                "age_days": health["age_days"],
                "selected_for_metric": selected_sources.get(configured["metric_id"])
                == configured["id"],
                "cadence": configured["cadence"],
            }
        )

    headline_rows = [
        {
            "run_id": snapshot["run_id"],
            "completed_at": snapshot["completed_at"],
            "publication_status": publication["status"],
            "analysis_allowed": publication["analysis_allowed"],
            "metric_count": publication["total_metric_count"],
            "source_route_count": len(snapshot["source_health"]),
            "coverage_ratio": publication["coverage_ratio"],
            "revision_count": snapshot["revision_count_detected"],
            "conflict_count": len(snapshot["reconciliation_issues"]),
        }
    ]

    title = "宏观流动性数据通道：现场验证报告"
    generated_at = snapshot["completed_at"]
    evidence_path = "reports/data-channel-validation/evidence.sqlite3"
    canonical_sources = [
        {
            "id": "report_headlines_sql",
            "label": "现场验证头部指标",
            "path": evidence_path,
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "id": "report-headlines-v1",
                "sql": "SELECT run_id, completed_at, publication_status, analysis_allowed, metric_count, source_route_count, coverage_ratio, revision_count, conflict_count FROM report_headlines",
                "description": "读取最终现场验证的指标数、来源路径数、覆盖率、修订和冲突计数。",
                "tables_used": ["report_headlines"],
                "executed_at": generated_at,
                "metric_definitions": {
                    "coverage_ratio": "可进入分析的唯一指标数除以 12 个门禁指标。",
                    "revision_count": "幂等复跑中同一来源、指标和观测日期出现值变化的记录数。"
                }
            }
        },
        {
            "id": "group_coverage_sql",
            "label": "关键分组门禁结果",
            "path": evidence_path,
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "id": "group-coverage-v1",
                "sql": "SELECT group_id, group_label, eligible, total, minimum, coverage_ratio, passed FROM group_coverage ORDER BY CASE group_id WHEN 'fed_balance_sheet' THEN 1 WHEN 'fiscal_cash' THEN 2 WHEN 'money_market' THEN 3 ELSE 4 END",
                "description": "读取四个关键分组的可用指标数、总数和最低发布门槛。",
                "tables_used": ["group_coverage"],
                "executed_at": generated_at,
                "metric_definitions": {
                    "eligible": "质量状态为 fresh_network 或 fresh_cache 的唯一指标数。",
                    "minimum": "该分组允许正式发布所需的最低可用指标数。"
                }
            }
        },
        {
            "id": "source_routes_sql",
            "label": "最终来源路径状态",
            "path": evidence_path,
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "id": "source-routes-v1",
                "sql": "SELECT source_id, metric_id, source_owner, authority, quality_status, observed_at, age_days, selected_for_metric, cadence FROM source_routes ORDER BY metric_id, source_id",
                "description": "读取最终现场复跑中 14 条来源路径的质量状态和正式选用状态。",
                "tables_used": ["source_routes"],
                "executed_at": generated_at,
                "metric_definitions": {
                    "selected_for_metric": "在同一指标的候选来源中被解析器正式选用的路径。",
                    "age_days": "报告生成日与该来源最新观测日期之间的日历天数。"
                }
            }
        },
        {
            "id": "pipeline_implementation",
            "label": "数据通道实现",
            "path": "src/liquidity_channel/core.py",
        },
    ]

    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": title,
            "generatedAt": generated_at,
            "blocks": [
                {
                    "id": "report_title",
                    "type": "markdown",
                    "body": f"# {title}",
                },
                {
                    "id": "technical_summary",
                    "type": "markdown",
                    "sourceId": "report_headlines_sql",
                    "body": (
                        "## 技术结论\n\n"
                        "- **首批通道已端到端跑通。** 最终现场复跑覆盖 12 个核心指标、14 条来源路径，覆盖率为 100%。\n"
                        "- **少量缺失不会拖垮更新。** 缺 1–2 项且四个关键分组仍达到最低配额时，系统继续发布并明确标记为降级。\n"
                        "- **成功抓取不等于数据可用。** 新鲜度、范围、跨源口径和分组配额都会独立校验；冲突值不会进入分析。\n"
                        "- **当前还不是生产硬通过。** 需要在部署主机连续运行 14 天，覆盖周末、节假日、发布日和故障演练后再启用正式定时任务。\n\n"
                        f"验证批次：`{snapshot['run_id']}`；完成时间：`{snapshot['completed_at']}`；发布状态：`{publication['status']}`。"
                    ),
                },
                {
                    "id": "headline_metrics",
                    "type": "metric-strip",
                    "cardIds": ["metric_count", "route_count", "coverage", "revisions"],
                },
                {
                    "id": "group_gate_finding",
                    "type": "markdown",
                    "sourceId": "group_coverage_sql",
                    "body": (
                        "## 四个关键分组均通过发布门禁\n\n"
                        "最终快照的四组可用指标数分别为 2、2、4、4，均高于最低要求 1、1、3、3。"
                        "这意味着个别指标中断时可以继续分析，但任一关键分组整体失效时仍会阻止更新。"
                    ),
                },
                {
                    "id": "group_coverage_chart_block",
                    "type": "chart",
                    "chartId": "group_coverage_chart",
                },
                {
                    "id": "scope_and_definitions",
                    "type": "markdown",
                    "sourceId": "report_headlines_sql",
                    "body": (
                        "## 指标口径和来源路径已经明确分开\n\n"
                        "12 个指标是发布门禁的分母；14 条路径包含总资产和准备金的两个官方备份来源。"
                        "准备金采用 WRESBAL 的周平均口径，不与 H.4.1 的周三时点值混用。"
                        "下面的表列出每条路径的真实状态及其是否被选为该指标的正式值。"
                    ),
                },
                {
                    "id": "source_route_table_block",
                    "type": "table",
                    "tableId": "source_route_table",
                },
                {
                    "id": "methodology",
                    "type": "markdown",
                    "body": (
                        "## 通道用确定性规则处理网络、格式和发布\n\n"
                        "每个来源独立执行连接超时、总超时和指数退避；成功响应先原样留存，再由固定解析器提取历史。"
                        "数据会经过日期、数值范围、重复日期、新鲜度与跨源一致性检查。"
                        "网络失败时，只在缓存值仍处于该指标正常发布时间窗口内才允许继续分析。"
                        "每次尝试都会写入运行清单；只有通过门禁的快照才会原子替换正式 `latest.json`。"
                    ),
                },
                {
                    "id": "robustness_and_limits",
                    "type": "markdown",
                    "body": (
                        "## 两个现场失败已转化为自动防护，但长期稳定性仍需观察\n\n"
                        "现场验证发现 FRED 会拒绝当前项目自定义 User-Agent，因此请求身份改为按来源配置；"
                        "还发现准备金周平均与周三时点值曾被混用，现已通过明确命名和双源同日期校验修正。"
                        "尚未完成的是 14 天连续运行、美国节假日新鲜度校准、磁盘保留策略和生产告警链。"
                    ),
                },
                {
                    "id": "recommended_next_steps",
                    "type": "markdown",
                    "body": (
                        "## 下一步先做 14 天影子运行，再接页面和 Agent\n\n"
                        "1. 在最终部署主机每天固定时间运行通道，并保存来源成功率、耗时和连续失败次数。\n"
                        "2. 演练缺 1 项、缺 2 项、同一分组整体失败和跨源数值冲突。\n"
                        "3. 只有连续观察通过后，才接入移动端看板；Agent 只读取已发布快照和明确缺失说明。"
                    ),
                },
                {
                    "id": "further_questions",
                    "type": "markdown",
                    "body": (
                        "## 后续需要回答的问题\n\n"
                        "- 美国节假日前后的真实发布时间窗口是否需要按日历动态计算？\n"
                        "- FRED 全域故障超过缓存新鲜度后，哪些市场传导指标值得增加独立备用源？\n"
                        "- 生产通知应通过什么渠道发送，哪些状态只提示、哪些状态需要立即告警？"
                    ),
                },
            ],
            "cards": [
                {
                    "id": "metric_count",
                    "dataset": "headlines",
                    "sourceId": "report_headlines_sql",
                    "description": "进入发布门禁的唯一指标数。",
                    "metrics": [{"label": "核心指标", "field": "metric_count", "format": "number"}],
                },
                {
                    "id": "route_count",
                    "dataset": "headlines",
                    "sourceId": "report_headlines_sql",
                    "description": "包含两个 H.4.1 直接备份。",
                    "metrics": [{"label": "来源路径", "field": "source_route_count", "format": "number"}],
                },
                {
                    "id": "coverage",
                    "dataset": "headlines",
                    "sourceId": "report_headlines_sql",
                    "description": "最终复跑中可进入分析的指标比例。",
                    "metrics": [{"label": "最终覆盖率", "field": "coverage_ratio", "format": "percent"}],
                },
                {
                    "id": "revisions",
                    "dataset": "headlines",
                    "sourceId": "report_headlines_sql",
                    "description": "幂等复跑中检测到的历史修订。",
                    "metrics": [{"label": "重复运行误修订", "field": "revision_count", "format": "number"}],
                },
            ],
            "charts": [
                {
                    "id": "group_coverage_chart",
                    "title": "可用于分析的指标数（按关键分组）",
                    "description": "最终现场复跑；最低门槛分别为 1、1、3、3。",
                    "type": "bar",
                    "dataset": "group_coverage",
                    "sourceId": "group_coverage_sql",
                    "encodings": {
                        "x": {"field": "group_label", "type": "nominal"},
                        "y": {"field": "eligible", "type": "quantitative"},
                    },
                }
            ],
            "tables": [
                {
                    "id": "source_route_table",
                    "title": "最终来源路径状态",
                    "description": "最终现场复跑；按指标标识排序。",
                    "dataset": "source_routes",
                    "sourceId": "source_routes_sql",
                    "defaultSort": {"field": "metric_id", "direction": "asc"},
                    "columns": [
                        {"field": "metric_id", "label": "指标"},
                        {"field": "source_id", "label": "来源路径"},
                        {"field": "source_owner", "label": "发布机构"},
                        {"field": "authority", "label": "权威级别"},
                        {"field": "quality_status", "label": "质量状态"},
                        {"field": "observed_at", "label": "观测日期", "format": "date"},
                        {"field": "age_days", "label": "数据年龄（天）", "format": "number"},
                        {"field": "selected_for_metric", "label": "正式选用"},
                    ],
                }
            ],
            "sources": canonical_sources,
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": {
                "headlines": headline_rows,
                "group_coverage": group_rows,
                "source_routes": route_rows,
            },
        },
        "sources": canonical_sources,
    }
    return artifact


if __name__ == "__main__":
    output = OUTPUT_DIR / "artifact.json"
    artifact = build()
    datasets = artifact["snapshot"]["datasets"]
    write_evidence_db(
        datasets["headlines"], datasets["group_coverage"], datasets["source_routes"]
    )
    write_json(output, artifact)
    print(output)
