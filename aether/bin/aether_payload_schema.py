#!/usr/bin/env python3
"""
aether_payload_schema.py — hook payload schema discoverer · **CENTRAL-ONLY**

> **Scope: CENTRAL-ONLY by design** · see `aether/docs/PATH-RESOLUTION-SPEC.md` §3.4
>
> `.cursor/hooks/.discovery/` only exists at **workspace-level** (the one
> that Cursor runs). It has no per-project counterpart — the hooks that
> write into it do so via `WORKSPACE_ROOT / ".cursor" / "hooks"` regardless
> of payload. The schema discoverer therefore has nothing per-project to
> audit; it's inherently central-scoped.

扫描 `.cursor/hooks/.discovery/` 中所有真实 Cursor hook payload 样本 ·
按 event 名分组 · 提取每个 event 的字段集 + 类型 + 出现频率 + 样本值 ·
生成人可读的 `aether/docs/hook-payload-schema.md`。

为什么这个工具存在(coll-0072 真实痛点):

  · `transcript_path` 字段从 Day 7 起就在每个 payload 里 · 我们一直没看见
  · `aether_hook.py` 只读 `event_name` / `tool_name` 等已知字段
  · 漏掉的字段没人主动盘点 · 直到 Owner 贴官方文档才发现
  · 这个工具把"漏掉字段"从"看运气"变成"机器审计"

流程:
  1. 扫 .cursor/hooks/.discovery/<event>-*.json (hook dispatcher 自动留的样本)
  2. 跳过空 `{}` payload (Cursor Windows bug 已知 · 已在 hook.py 里诚实标记)
  3. 对剩余样本 · 用 walk_json 提取 (path, type, sample_value) tuples
  4. union 同 event 所有样本的 path 集合 · 算出现率
  5. 写 `aether/docs/hook-payload-schema.md` · markdown 表

用法:
  python bin/aether_payload_schema.py                # 写 docs · stdout summary
  python bin/aether_payload_schema.py --json         # 机器输出(给 selfcheck 用)
  python bin/aether_payload_schema.py --check        # 比对官方文档已知字段 · 报缺漏
  python bin/aether_payload_schema.py --print        # 不写文件 · 只 stdout markdown

设计原则:
  1. 0 依赖 · stdlib only
  2. 增量友好 · 每次扫描都是全量重写 · 不维护中间 state
  3. 诚实 · 空 payload 计入 sample_count 但不污染字段统计
  4. 输出含 `_aether_unused` 标记 · 提示哪些字段从未被 aether_hook.py 读过
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = ROOT.parent
DISCOVERY_DIR = WORKSPACE_ROOT / ".cursor" / "hooks" / ".discovery"
OUTPUT_PATH = ROOT / "docs" / "hook-payload-schema.md"
HOOK_PY = ROOT / "bin" / "aether_hook.py"

# Fields that aether_hook.py is KNOWN to consume. Used for "unused field"
# detection. Update this set when you start using a new field — otherwise
# the schema doc will keep marking it as `_aether_unused`.
KNOWN_CONSUMED_FIELDS = {
    # Universal base fields documented in cursor.com/docs/hooks
    "conversation_id",
    "generation_id",
    "model",
    "hook_event_name",
    "session_id",
    "transcript_path",
    "workspace_roots",
    # event-specific that we already use
    "tool_name", "toolName", "tool", "name",
    "tool_input", "args", "input",
    "tool_call", "toolCall",
    "event_name", "eventName",
    "reason",
    "text",
    "trigger", "context_usage_percent", "messages_to_compact",
    "is_first_compaction",
    "context_tokens", "context_window_size", "message_count",
    "composer_mode", "is_background_agent",
    "duration_ms", "duration",
    "status", "final_status",
    "prompt",
    # Day 8 PM additions (consumed by handle_beforeSubmitPrompt observation event)
    "cursor_version", "user_email", "cwd", "sandbox",
    # Day 8 PM 档位 2 fields
    "failure_type", "error_message", "is_interrupt",
}


def walk_json(obj: Any, prefix: str = "") -> list[tuple[str, str, Any]]:
    """Yield (path, type_name, sample_value) tuples for every leaf in obj.

    For dicts · recurses with `prefix.key` path.
    For lists · records `prefix[]` once with the list type · doesn't dive
      into list items (would explode the schema for transcripts etc.).
    For scalars · records (prefix, type_name, value-or-stringified-trim).
    """
    out: list[tuple[str, str, Any]] = []
    if isinstance(obj, dict):
        if not obj and prefix:
            out.append((prefix, "object(empty)", {}))
        for k, v in obj.items():
            new_prefix = f"{prefix}.{k}" if prefix else k
            out.extend(walk_json(v, new_prefix))
    elif isinstance(obj, list):
        type_name = f"array<{type(obj[0]).__name__}>" if obj else "array(empty)"
        sample = obj[0] if obj and isinstance(obj[0], (str, int, float, bool)) else None
        if sample is not None and isinstance(sample, str) and len(sample) > 60:
            sample = sample[:60] + "..."
        out.append((prefix, type_name, sample if sample is not None else "[...]"))
    else:
        if obj is None:
            out.append((prefix, "null", None))
        elif isinstance(obj, bool):
            out.append((prefix, "boolean", obj))
        elif isinstance(obj, int):
            out.append((prefix, "integer", obj))
        elif isinstance(obj, float):
            out.append((prefix, "number", obj))
        elif isinstance(obj, str):
            sample = obj if len(obj) <= 60 else obj[:60] + "..."
            out.append((prefix, "string", sample))
        else:
            out.append((prefix, type(obj).__name__, str(obj)[:60]))
    return out


def event_name_from_filename(name: str) -> str:
    """Extract the event from `<event>-<timestamp>-<rand>.json`.

    Special case: `postToolUse-unknown-tool-...` keeps the full prefix so
    we can tell discovery samples apart from real postToolUse payloads.
    """
    stem = name.removesuffix(".json")
    # Find the last `-<8-digit-Z-stamp>-` boundary
    parts = stem.split("-")
    # Walk back to find first part that looks like a timestamp (8+ digits + T)
    for i, p in enumerate(parts):
        if "T" in p and "Z" in p and len(p) >= 14:
            return "-".join(parts[:i])
    return stem


def scan() -> dict[str, dict]:
    """Returns {event_name: {samples_total, samples_empty, fields: {path: {type_counts, occurrences, sample_value}}}}."""
    if not DISCOVERY_DIR.exists():
        return {}
    by_event: dict[str, dict] = defaultdict(
        lambda: {"samples_total": 0, "samples_empty": 0, "fields": defaultdict(
            lambda: {"types": defaultdict(int), "occurrences": 0, "sample_value": None})}
    )
    for path in DISCOVERY_DIR.glob("*.json"):
        event = event_name_from_filename(path.name)
        by_event[event]["samples_total"] += 1
        try:
            raw = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not raw or raw == "{}":
            by_event[event]["samples_empty"] += 1
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or not payload:
            by_event[event]["samples_empty"] += 1
            continue
        for field_path, type_name, sample in walk_json(payload):
            f = by_event[event]["fields"][field_path]
            f["types"][type_name] += 1
            f["occurrences"] += 1
            if f["sample_value"] is None and sample not in (None, "", {}, []):
                f["sample_value"] = sample
    return {k: dict(v) for k, v in by_event.items()}


def detect_unused(by_event: dict) -> dict[str, list[str]]:
    """For each event · list fields that exist in payloads but aren't in
    KNOWN_CONSUMED_FIELDS. These are 'aether is leaving data on the table'
    candidates."""
    unused: dict[str, list[str]] = {}
    for event, data in by_event.items():
        leftovers = []
        for path in data.get("fields", {}):
            # Top-level field name only (don't flag nested.x as unused if x is consumed)
            top = path.split(".")[0]
            if top not in KNOWN_CONSUMED_FIELDS:
                leftovers.append(path)
        if leftovers:
            unused[event] = sorted(leftovers)
    return unused


def render_markdown(by_event: dict, unused: dict[str, list[str]]) -> str:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Cursor Hook Payload Schema · 自动发现",
        "",
        "> 由 `aether/bin/aether_payload_schema.py` 在 "
        f"{now} 自动生成。",
        "> **不要手工编辑** · 重跑工具即可刷新。",
        "",
        "## 为什么这份文档存在",
        "",
        "Day 7 起,`transcript_path` 字段就在每个 hook payload 里 · 我们一直没看见。",
        "Day 8 中午对照官方文档才发现 hook 利用率只有 22%。本工具把 \"漏掉字段\" "
        "从 \"看运气\" 变成 \"机器审计\":每次扫 `.cursor/hooks/.discovery/` 的真实样本 · "
        "把每个 event 实际收到的字段全部列出来 · 标出 aether_hook.py 还没读过的字段。",
        "",
        "## 字段消费白名单",
        "",
        f"`aether_hook.py` 当前已知会读 **{len(KNOWN_CONSUMED_FIELDS)}** 个顶层字段:",
        "",
        "```",
        ", ".join(sorted(KNOWN_CONSUMED_FIELDS)),
        "```",
        "",
        "任何在样本里出现但不在此名单的顶层字段 · 都会标 `_aether_unused`。",
        "添加消费时同步更新 `aether_payload_schema.py` 的 `KNOWN_CONSUMED_FIELDS`。",
        "",
        "## 各 event 字段表",
        "",
    ]
    if not by_event:
        lines += ["_(no discovery samples yet · 重启 Cursor 让 hooks 生成样本)_", ""]
        return "\n".join(lines)

    for event in sorted(by_event.keys()):
        data = by_event[event]
        total = data["samples_total"]
        empty = data["samples_empty"]
        non_empty = total - empty
        empty_pct = (empty / total * 100) if total else 0
        lines.append(f"### `{event}`")
        lines.append("")
        lines.append(
            f"- 样本数: **{total}** · 其中空 payload `{{}}`: {empty} ({empty_pct:.0f}%) "
            f"· 真实样本: {non_empty}"
        )
        if empty_pct >= 50 and non_empty == 0:
            lines.append(
                "- ⚠ **Cursor Windows hook bug 命中**: 100% 空 payload · "
                "无字段可分析 · 参考 Anthropic GH #48009"
            )
        lines.append("")
        fields = data.get("fields", {})
        if not fields:
            lines.append("_(无字段 · 全部样本为空)_")
            lines.append("")
            continue
        lines.append("| field | 类型 | 出现率 | 样本值 | 状态 |")
        lines.append("|---|---|---:|---|---|")
        unused_set = set(unused.get(event, []))
        for path in sorted(fields.keys()):
            f = fields[path]
            occ = f["occurrences"]
            occ_pct = (occ / non_empty * 100) if non_empty else 0
            type_str = ", ".join(sorted(f["types"].keys()))
            sample = f["sample_value"]
            sample_str = json.dumps(sample, ensure_ascii=False) if sample is not None else "_(empty)_"
            if len(sample_str) > 60:
                sample_str = sample_str[:60] + "..."
            sample_str = sample_str.replace("|", "\\|")
            status = "🔴 `_aether_unused`" if path in unused_set else "✅"
            lines.append(
                f"| `{path}` | {type_str} | {occ_pct:.0f}% ({occ}/{non_empty}) | `{sample_str}` | {status} |"
            )
        lines.append("")

    # Summary section
    lines.append("---")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    total_events = len(by_event)
    total_samples = sum(d["samples_total"] for d in by_event.values())
    total_empty = sum(d["samples_empty"] for d in by_event.values())
    unused_total = sum(len(v) for v in unused.values())
    lines.append(f"- 已观测 events: **{total_events}**")
    lines.append(f"- 样本总数: **{total_samples}** · 空 payload: {total_empty} "
                 f"({total_empty/total_samples*100 if total_samples else 0:.0f}%)")
    lines.append(f"- aether 未消费字段总数: **{unused_total}**")
    if unused:
        lines.append("")
        lines.append("### 未消费字段速查(`_aether_unused`)")
        lines.append("")
        for event in sorted(unused.keys()):
            lines.append(f"- **`{event}`**: {', '.join(f'`{p}`' for p in unused[event])}")
    lines.append("")
    lines.append("## 怎么消费一个 `_aether_unused` 字段")
    lines.append("")
    lines.append("1. 决定哪个 `handle_<event>()` 应该读它")
    lines.append("2. 在 `aether_hook.py` 的 handler 里用 `payload.get('<field>')`")
    lines.append("3. 把字段名加到 `aether_payload_schema.py` 的 `KNOWN_CONSUMED_FIELDS`")
    lines.append("4. 重跑本工具 · 字段标记从 🔴 变 ✅")
    lines.append("")
    return "\n".join(lines)


def emit_json(by_event: dict, unused: dict) -> str:
    """Compact machine-readable form for selfcheck / tooling."""
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events": {},
        "unused_field_count": sum(len(v) for v in unused.values()),
        "unused_by_event": unused,
    }
    for event, data in by_event.items():
        out["events"][event] = {
            "samples_total": data["samples_total"],
            "samples_empty": data["samples_empty"],
            "field_count": len(data.get("fields", {})),
            "fields": sorted(data.get("fields", {}).keys()),
        }
    return json.dumps(out, ensure_ascii=False)


def cmd_check() -> int:
    """Exit non-zero if there are unused fields · for selfcheck integration."""
    by_event = scan()
    unused = detect_unused(by_event)
    total_unused = sum(len(v) for v in unused.values())
    if total_unused == 0:
        print(f"✅ no unused fields · {len(by_event)} events scanned")
        return 0
    print(f"⚠ {total_unused} unused field(s) across {len(unused)} event(s):")
    for event in sorted(unused.keys()):
        print(f"  · {event}: {', '.join(unused[event])}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover Cursor hook payload schemas from real samples")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON to stdout")
    ap.add_argument("--check", action="store_true",
                    help="print unused fields · exit 1 if any (for selfcheck)")
    ap.add_argument("--print", dest="print_only", action="store_true",
                    help="print markdown to stdout · don't write file")
    args = ap.parse_args()

    if args.check:
        return cmd_check()

    by_event = scan()
    unused = detect_unused(by_event)

    if args.json:
        print(emit_json(by_event, unused))
        return 0

    md = render_markdown(by_event, unused)

    if args.print_only:
        print(md)
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(md, encoding="utf-8")
    total_events = len(by_event)
    total_samples = sum(d["samples_total"] for d in by_event.values())
    unused_total = sum(len(v) for v in unused.values())
    print(f"wrote {OUTPUT_PATH.relative_to(WORKSPACE_ROOT)}")
    print(f"  events: {total_events} · samples: {total_samples} · unused fields: {unused_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
