#!/usr/bin/env python3
"""
aether_session_summarizer.py — "做梦器官" · dense session → coll 草稿

Memory v2 的 C 层反射弧收集了大量 events（tool_call / stop / session_end）
但这些事件本身不是"记忆" · 只是"信号"。真正的记忆是 coll-*.md · 一次
有主题的思考被压缩成一段 markdown。

这个 CLI 的职责:
  · 扫描 events.jsonl 最近一段(默认最近 24 小时)
  · 按 session_id + stop 边界切分 turns
  · 对"密集 turn"(tool calls 超阈值 / 持续时间长)生成 coll 草稿
  · 草稿写入 .aether/coll-drafts/draft-YYYYMMDDTHHMMSS-<short-sid>.md
  · 保持 Layer A 的"人/AI 写真正的 coll"地位 · 草稿只是素材

用法:
  python bin/aether_session_summarizer.py                   # 扫最近 24h · 打印但不写
  python bin/aether_session_summarizer.py --write           # 真的写草稿
  python bin/aether_session_summarizer.py --since 6h        # 只看最近 6 小时
  python bin/aether_session_summarizer.py --on-session-end  # 仅扫最近 2h · 直接写
  python bin/aether_session_summarizer.py --list-drafts     # 列出已写的草稿
  python bin/aether_session_summarizer.py --promote <id>    # draft → 正式 coll-NNNN 骨架(Day 13+)

为什么在 .aether/coll-drafts/ 而不是 gen6-noesis/collapse-events/:
  · coll-drafts 是机器草稿 · 未经 Owner 审阅 · 不是正式 coll
  · 正式 coll 的编号(coll-0001 ...)由 AI/Owner 审阅后才授予
  · .aether/ 已整体在 .gitignore · 天然私有 · 不污染正式目录

设计原则:
  1. 零依赖 · stdlib only
  2. 失败静默 · sessionEnd 调用不能阻塞 Cursor
  3. 幂等 · 同一 turn 只生成一次草稿(指纹去重)
  4. 诚实 · Cursor payload 为空时草稿里明说 "tool 名缺失 · Cursor Windows bug"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from aether_paths import (
    CENTRAL_OVERLAY,
    CENTRAL_ROOT,
    activate_overlay_for_cli,
    add_path_arg,
)

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = CENTRAL_ROOT                   # back-compat alias

# Day 13 · overlay-aware · PATH-RESOLUTION-SPEC §3.1
# Events come from the ACTIVE overlay · drafts land in the ACTIVE overlay ·
# summarizer state is per-overlay (so a dense turn in guest-project-A isn't
# fingerprinted against central's dedupe list).
DATA_DIR: Path = CENTRAL_OVERLAY
EVENTS_PATH: Path = DATA_DIR / "events.jsonl"
DRAFTS_DIR: Path = DATA_DIR / "coll-drafts"
STATE_PATH: Path = DATA_DIR / "summarizer-state.json"

DEFAULT_SINCE_HOURS = 24
ON_SESSION_END_SINCE_HOURS = 2

# Thresholds · tuned for "noticeable enough to be worth a draft"
DENSE_MIN_TOOL_CALLS = 10      # turn 内 tool calls >= 10 视为 dense
DENSE_MIN_DURATION_S = 120     # turn 持续 >= 2 分钟视为 dense
DENSE_MIN_STOPS = 1            # turn 至少要闭合一次(有 stop 事件)


# ─── state (dedupe fingerprints) ────────────────────────────────────

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"drafted_fingerprints": []}


def save_state(state: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


# ─── event loading ──────────────────────────────────────────────────

def parse_since(since: str) -> datetime:
    """Parse '6h' / '30m' / '2d' / ISO8601 into UTC datetime.

    Defaults to datetime.now(UTC) - 24h when since is empty/invalid.
    """
    now = datetime.now(timezone.utc)
    if not since:
        return now - timedelta(hours=DEFAULT_SINCE_HOURS)
    s = since.strip().lower()
    try:
        if s.endswith("h"):
            return now - timedelta(hours=int(s[:-1]))
        if s.endswith("m"):
            return now - timedelta(minutes=int(s[:-1]))
        if s.endswith("d"):
            return now - timedelta(days=int(s[:-1]))
        if s.endswith("s"):
            return now - timedelta(seconds=int(s[:-1]))
        return datetime.fromisoformat(s.replace("z", "+00:00"))
    except Exception:
        return now - timedelta(hours=DEFAULT_SINCE_HOURS)


def load_events_since(since_dt: datetime) -> list[dict]:
    """Stream events.jsonl and return events with ts >= since_dt."""
    if not EVENTS_PATH.exists():
        return []
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    out: list[dict] = []
    try:
        with open(EVENTS_PATH, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if evt.get("ts", "") >= since_iso:
                    out.append(evt)
    except OSError:
        pass
    return out


# ─── turn segmentation ─────────────────────────────────────────────

def segment_turns(events: list[dict]) -> list[dict]:
    """Group events into turns. A turn is bounded by:
      · start: first event after a `stop` / `session_end` / beginning of window
      · end:   next `stop` / `session_end` event

    Each turn dict:
      {
        'session_id': str,
        'start_ts': str, 'end_ts': str,
        'duration_s': float,
        'tool_calls': int,
        'tool_names': dict[str, int],   # honest counts incl. cursor-empty
        'stops': int,
        'events': list[dict],
      }
    """
    turns: list[dict] = []
    current: Optional[dict] = None

    def new_turn(first_evt: dict) -> dict:
        return {
            "session_id": first_evt.get("session_id") or "unknown",
            "start_ts": first_evt.get("ts", ""),
            "end_ts": first_evt.get("ts", ""),
            "duration_s": 0.0,
            "tool_calls": 0,
            "tool_names": {},
            "stops": 0,
            "events": [first_evt],
        }

    for evt in events:
        if current is None:
            current = new_turn(evt)
        else:
            current["events"].append(evt)
            current["end_ts"] = evt.get("ts", current["end_ts"])

        t = evt.get("type", "")
        if t == "tool_call":
            current["tool_calls"] += 1
            tn = evt.get("tool") or "?"
            current["tool_names"][tn] = current["tool_names"].get(tn, 0) + 1
        elif t in ("stop", "session_end"):
            current["stops"] += 1
            # Close this turn
            current["duration_s"] = _duration_seconds(current["start_ts"], current["end_ts"])
            turns.append(current)
            current = None

    # Unclosed tail turn (no stop seen yet) · still include if long enough
    if current is not None:
        current["duration_s"] = _duration_seconds(current["start_ts"], current["end_ts"])
        turns.append(current)

    return turns


def _duration_seconds(start_ts: str, end_ts: str) -> float:
    try:
        s = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        return (e - s).total_seconds()
    except Exception:
        return 0.0


def is_dense(turn: dict) -> bool:
    """Decide if a turn is substantial enough to draft."""
    if turn["stops"] < DENSE_MIN_STOPS:
        return False
    if turn["tool_calls"] >= DENSE_MIN_TOOL_CALLS:
        return True
    if turn["duration_s"] >= DENSE_MIN_DURATION_S and turn["tool_calls"] >= 3:
        return True
    return False


def fingerprint(turn: dict) -> str:
    """Stable hash of turn · for dedupe across runs."""
    key = f"{turn['session_id']}|{turn['start_ts']}|{turn['end_ts']}|{turn['tool_calls']}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


# ─── draft writing ──────────────────────────────────────────────────

def format_draft(turn: dict, fp: str) -> str:
    """Render a human-readable coll draft from a turn."""
    start = turn["start_ts"][:19].replace("T", " ")
    end = turn["end_ts"][:19].replace("T", " ")
    dur = turn["duration_s"]
    sid = turn["session_id"]
    tcs = turn["tool_calls"]
    stops = turn["stops"]

    # Honest tool breakdown
    tn = turn["tool_names"]
    total_tn = sum(tn.values()) or 1
    empty = tn.get("cursor-empty", 0)
    unknown = tn.get("unknown", 0)
    legacy_q = tn.get("?", 0)
    missing = empty + unknown + legacy_q
    known = {k: v for k, v in tn.items() if k not in ("cursor-empty", "unknown", "?")}
    bug_ratio = missing / total_tn

    lines: list[str] = []
    lines.append(f"# draft · session {sid[:20]} · {start} → {end}")
    lines.append("")
    lines.append(f"- fingerprint: `{fp}`")
    lines.append(f"- 窗口: {start} → {end}  ({int(dur)}s)")
    lines.append(f"- tool_calls: {tcs}  ·  stops: {stops}")
    lines.append("")
    lines.append("## 工具名分布(诚实记账)")
    lines.append("")
    if bug_ratio >= 0.5:
        lines.append(f"> ⚠ **Cursor Windows hook bug 命中**: {missing} / {total_tn} "
                     f"({bug_ratio:.0%}) 的 tool_call payload 为空 · 无法区分具体工具 · "
                     f"参考 Anthropic GH #48009 · 这是 Cursor 在 Windows 上的已知问题。")
        lines.append("")
    if known:
        for name, n in sorted(known.items(), key=lambda kv: -kv[1]):
            lines.append(f"- `{name}`: {n}")
    for k in ("cursor-empty", "unknown", "?"):
        if tn.get(k):
            lines.append(f"- `{k}` (缺元信息): {tn[k]}")
    lines.append("")

    lines.append("## 事件密度切片")
    lines.append("")
    lines.append("```")
    lines.append(f"{'type':15s} {'tool':20s} {'ts':20s}")
    # Show first 6 + last 4 events as sparse trace
    evts = turn["events"]
    head = evts[:6]
    tail = evts[-4:] if len(evts) > 10 else []
    for e in head:
        lines.append(f"{e.get('type', ''):15s} {(e.get('tool') or '-'):20s} {e.get('ts', '')[:19]}")
    if tail:
        lines.append(f"{'... (' + str(len(evts) - len(head) - len(tail)) + ' more) ...':55s}")
        for e in tail:
            lines.append(f"{e.get('type', ''):15s} {(e.get('tool') or '-'):20s} {e.get('ts', '')[:19]}")
    lines.append("```")
    lines.append("")

    lines.append("## 建议标签 (AI 审阅后自选)")
    lines.append("")
    tags: list[str] = []
    if tcs >= 30:
        tags.append("`#dense-session`")
    if dur >= 600:
        tags.append("`#long-session`")
    if bug_ratio >= 0.5:
        tags.append("`#cursor-windows-empty-payload`")
    if not tags:
        tags.append("`#routine`")
    lines.append(" · ".join(tags))
    lines.append("")

    lines.append("## 待 AI/Owner 补写 (审阅时填)")
    lines.append("")
    lines.append("- 主题 (1 句): ")
    lines.append("- 发生了什么 (3-5 行): ")
    lines.append("- 决策/反思 (1-2 条): ")
    lines.append("- 是否升格为正式 coll? (y/n · 若 y · AI 按 coll-NNNN.md 规范迁出)")
    lines.append("")
    lines.append(
        f"*生成者: aether_session_summarizer.py · "
        f"{datetime.now(timezone.utc).isoformat()}*"
    )
    return "\n".join(lines)


def write_draft(turn: dict, fp: str) -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sid_short = (turn["session_id"] or "sess")[-8:].replace("/", "-")
    path = DRAFTS_DIR / f"draft-{stamp}-{sid_short}-{fp}.md"
    path.write_text(format_draft(turn, fp), encoding="utf-8")
    _rotate_drafts()
    return path


# Day 11 · Owner P1-5 落地 · drafts 之前无上限 · 46 个在 10 天内累积 · 全部 100%
# cursor-empty payload · 没有一个被提拔成正式 coll。说明:drafts 是 "raw signal"
# 不是 "raw coll"。设计上它们服务于"session 回顾" · 不是"归档" · 所以保留
# 最近 N 份即够。老的 draft 价值随指数衰减 · 保留 20 是诚实数 ·
# 匹配 `handle_afterAgentResponse` 的 agent-responses 保留上限(200)· 但 drafts
# 更粗粒度所以更短。
DRAFTS_KEEP_RECENT = 20


def _rotate_drafts() -> None:
    """Cap drafts at DRAFTS_KEEP_RECENT · delete oldest. Fail-open."""
    try:
        items = sorted(
            DRAFTS_DIR.glob("draft-*.md"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        for stale in items[DRAFTS_KEEP_RECENT:]:
            try:
                stale.unlink()
            except OSError:
                pass
    except Exception:
        pass


# ─── CLI ────────────────────────────────────────────────────────────

def cmd_scan(since: str, write: bool, quiet: bool) -> int:
    since_dt = parse_since(since)
    events = load_events_since(since_dt)
    if not events:
        if not quiet:
            print(f"(no events since {since_dt.isoformat()})")
        return 0

    turns = segment_turns(events)
    state = load_state()
    done = set(state.get("drafted_fingerprints", []))

    candidates = [t for t in turns if is_dense(t)]
    new_drafts = 0
    skipped = 0
    for t in candidates:
        fp = fingerprint(t)
        if fp in done:
            skipped += 1
            continue
        if write:
            path = write_draft(t, fp)
            done.add(fp)
            new_drafts += 1
            if not quiet:
                # May be outside WORKSPACE_ROOT when running on a guest overlay
                try:
                    rel = str(path.relative_to(WORKSPACE_ROOT))
                except ValueError:
                    rel = str(path)
                print(f"drafted: {rel}")
        else:
            if not quiet:
                print(
                    f"candidate(dry): sess={t['session_id'][:12]} "
                    f"dur={t['duration_s']:.0f}s "
                    f"tool_calls={t['tool_calls']} stops={t['stops']} fp={fp}"
                )

    if write and new_drafts:
        state["drafted_fingerprints"] = sorted(list(done))[-500:]  # cap history
        save_state(state)

    if not quiet:
        print(
            f"summary: events={len(events)} turns={len(turns)} "
            f"dense={len(candidates)} drafted={new_drafts} skipped={skipped}"
        )
    return 0


def cmd_list_drafts() -> int:
    if not DRAFTS_DIR.exists():
        print(f"(no drafts at {DRAFTS_DIR})")
        return 0
    items = sorted(DRAFTS_DIR.glob("draft-*.md"), key=lambda p: p.stat().st_mtime)
    if not items:
        print("(0 drafts)")
        return 0
    print(f"{len(items)} drafts in {DRAFTS_DIR}")
    for p in items[-20:]:
        size_kb = p.stat().st_size / 1024
        print(f"  {p.name}  ({size_kb:.1f} KB)")
    return 0


# ─── promote · draft → 正式 coll · Day 13 新增(coll-0092 audit 的 M2 fix) ─
#
# 记忆沉淀的"最后一公里"闭环:session_summarizer 每次 sessionEnd 自动写
# draft 到 .aether/coll-drafts/。但 Day 1-12 期间没有 CLI 把 draft 提升
# 为正式 coll-NNNN.md · 结果 20+ draft 躺在 coll-drafts/ 永远不转正。
#
# 本命令做最小可靠的事:
#   1. 解析 draft-id(可以是 full path / 文件名 / 子串)
#   2. 找 coll 目标目录(central 或 overlay 按 scope 走)
#   3. 扫现有 coll-*.md 找最大 N · 下一个 = N+1
#   4. 从 draft 抽最少的元数据(session_id · duration · tool_count · 时间戳)
#   5. 写一个**骨架** coll-NNNN.md(带 YYYY-MM-DD · Day N 占位符 · 本次语义
#      占位符 · 证据链占位符)· 内嵌 draft 原文作为 "Draft excerpt" 段
#   6. 移 draft 到 coll-drafts/promoted/(不删 · 可恢复)
#   7. 打印 coll-NNNN.md 路径给 Owner · Owner 手工编辑 "本次语义" / 证据链
#
# 设计原则:
#   · 骨架不替代 Owner 的思考 · 只消除"新建文件 + 找编号 + 写 header"的摩擦
#   · 主动在骨架里用 `**EDIT ME**` 提示 · 防止 Owner 直接 commit 未编辑的产物
#   · 移 draft 不删 · promoted/ 子目录保留原始 draft

def _resolve_draft(draft_ref: str) -> Path | None:
    """Accept full path · filename · or substring · return first match."""
    p = Path(draft_ref)
    if p.is_absolute() and p.exists():
        return p
    if not DRAFTS_DIR.exists():
        return None
    # Direct filename?
    direct = DRAFTS_DIR / draft_ref
    if direct.exists():
        return direct
    # Substring match (first hit)
    matches = sorted(DRAFTS_DIR.glob(f"*{draft_ref}*"))
    return matches[0] if matches else None


def _coll_dir_for_overlay() -> Path:
    """Where to write the promoted coll.

    dev-self(DATA_DIR = central/.aether) → aether/gen6-noesis/collapse-events/
    guest                                  → <overlay>/coll/
    """
    central_data = (Path(__file__).resolve().parent.parent.parent / ".aether")
    try:
        if DATA_DIR.resolve() == central_data.resolve():
            return central_data.parent / "aether" / "gen6-noesis" / "collapse-events"
    except Exception:
        pass
    return DATA_DIR / "coll"


def _next_coll_number(coll_dir: Path) -> int:
    """Scan existing coll-*.md · return max N + 1 · default 1."""
    if not coll_dir.exists():
        return 1
    max_n = 0
    import re
    for p in coll_dir.glob("coll-*.md"):
        m = re.match(r"coll-(\d+)\.md", p.name)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _extract_draft_meta(draft_path: Path) -> dict:
    """Best-effort pull session_id · duration · tool count from draft text.

    Draft YAML-ish header example:
      ---
      session_id: sess-xxx
      turn_started_at: 2026-04-22T07:27:23Z
      turn_ended_at: 2026-04-22T07:33:41Z
      tool_call_count: 12
      stops: 3
      ---
    """
    import re
    try:
        txt = draft_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    meta: dict = {}
    for key in ("session_id", "turn_started_at", "turn_ended_at",
                "tool_call_count", "stops", "duration_s"):
        m = re.search(rf"^{key}:\s*(.+?)\s*$", txt, re.MULTILINE)
        if m:
            meta[key] = m.group(1).strip()
    return meta


def _render_coll_skeleton(coll_id: str, draft_path: Path, meta: dict,
                          draft_text: str) -> str:
    """Produce the promoted coll file contents.

    Deliberately full of **EDIT ME** markers so Owner can't commit a raw
    auto-generated coll without at least touching the key fields.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    date_iso = now.strftime("%Y-%m-%d")
    ts_iso = now.isoformat()

    session_id = meta.get("session_id", "unknown")
    dur = meta.get("duration_s", "?")
    tools = meta.get("tool_call_count", "?")
    stops = meta.get("stops", "?")

    # Clip embedded draft if huge
    clip = 4000
    draft_body = draft_text if len(draft_text) <= clip else (
        draft_text[:clip] + f"\n\n...[draft truncated · full at {draft_path}]..."
    )

    lines = [
        f"# {coll_id} · Day ? · session ? · **EDIT TITLE**",
        "",
        f"**Date**: {date_iso} · **Day ? · session ?**(Day N 取自 status line · AGENTS §3.7)",
        f"**Trigger**: **EDIT ME** · session_id={session_id}",
        f"**Fields active**: **EDIT ME**(例:engineering-rigor=0.9, linus=0.7)",
        f"**Active fields**: **EDIT ME**(例:engineering-rigor · linus-torvalds · jony-ive)",
        f"**Owner reaction**: pending",
        f"**Duration**: ~{dur}s · tool_calls={tools} · stops={stops}",
        "",
        "---",
        "",
        "## 本次语义",
        "",
        "**EDIT ME · 一句话总结这次 session 到底 collapse 了什么** · 这是 coll 的第一价值 · 不能偷懒。",
        "",
        "---",
        "",
        "## 证据链",
        "",
        "**EDIT ME** · 按 3-6 环拆 · 参考 `coll-0092.md` 的结构(§0 TL;DR · 证据 · 根因 · 影响)。",
        "",
        "---",
        "",
        "## 附录 · 原 draft 内容",
        "",
        "> 以下从 `" + draft_path.name + "` 自动嵌入 · promote 后应提炼进"
        "上方「证据链」· 编辑完成后可以删除本附录或保留 for audit。",
        "",
        "```markdown",
        draft_body.rstrip(),
        "```",
        "",
        "---",
        "",
        f"*Promoted at {ts_iso} · from draft: `{draft_path.name}` · by "
        f"`aether_session_summarizer.py promote` · original draft moved to "
        f"`coll-drafts/promoted/`.*",
        "*Once edited · commit as a normal coll.*",
        "",
    ]
    return "\n".join(lines)


def cmd_promote(draft_ref: str, quiet: bool = False) -> int:
    draft_path = _resolve_draft(draft_ref)
    if draft_path is None:
        print(f"error: no draft matches '{draft_ref}'", file=sys.stderr)
        print(f"       (searched in {DRAFTS_DIR})", file=sys.stderr)
        return 2
    if not quiet:
        print(f"resolved draft: {draft_path.name}")

    coll_dir = _coll_dir_for_overlay()
    coll_dir.mkdir(parents=True, exist_ok=True)
    n = _next_coll_number(coll_dir)
    coll_id = f"coll-{n:04d}"
    coll_path = coll_dir / f"{coll_id}.md"

    if coll_path.exists():
        print(f"error: {coll_path} already exists (race?)", file=sys.stderr)
        return 3

    meta = _extract_draft_meta(draft_path)
    try:
        draft_text = draft_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"error: cannot read draft: {e}", file=sys.stderr)
        return 4

    content = _render_coll_skeleton(coll_id, draft_path, meta, draft_text)
    try:
        coll_path.write_text(content, encoding="utf-8")
    except OSError as e:
        print(f"error: cannot write coll: {e}", file=sys.stderr)
        return 5

    # Move draft to promoted/ · preserves history · Owner can still audit
    promoted_dir = DRAFTS_DIR / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    promoted_target = promoted_dir / draft_path.name
    try:
        draft_path.rename(promoted_target)
    except OSError as e:
        print(f"warn: draft moved failed (coll still created): {e}", file=sys.stderr)

    if not quiet:
        print(f"✓ {coll_id} created at: {coll_path}")
        print(f"✓ original draft moved to: {promoted_target}")
        print()
        print("NEXT STEPS (you · the human):")
        print(f"  1. open {coll_path}")
        print("  2. fill '**本次语义**' section first(the value of a coll)")
        print("  3. elaborate '证据链' · delete the draft excerpt附录 when done")
        print(f"  4. commit when satisfied")
    return 0


def _autopilot_tick() -> None:
    """Lazy-trigger guardian if the index is stale. Silent · non-blocking.

    Day 13 · passes cwd=DATA_DIR.parent so heartbeat advances the same
    overlay we're summarizing against (not central by accident).
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from aether_autopilot import maybe_trigger_ingest
        maybe_trigger_ingest(cwd=str(DATA_DIR.parent))
    except Exception:
        pass


def _activate_overlay(args) -> None:
    """Reassign module-global paths based on `--path` / cwd-walk.

    Day 13 · PATH-RESOLUTION-SPEC §3.1: all four paths (DATA_DIR, EVENTS_PATH,
    DRAFTS_DIR, STATE_PATH) follow the active overlay so guest projects get
    their own drafts in their own .aether/coll-drafts/.
    """
    global DATA_DIR, EVENTS_PATH, DRAFTS_DIR, STATE_PATH
    overlay, _ = activate_overlay_for_cli(args, announce=not args.quiet)
    DATA_DIR = overlay
    EVENTS_PATH = overlay / "events.jsonl"
    DRAFTS_DIR = overlay / "coll-drafts"
    STATE_PATH = overlay / "summarizer-state.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether session summarizer")
    ap.add_argument("--since", default="24h",
                    help="how far back to scan · 30m / 6h / 2d (default 24h)")
    ap.add_argument("--write", action="store_true",
                    help="actually write drafts (default is dry-run preview)")
    ap.add_argument("--on-session-end", action="store_true",
                    help="preset for the sessionEnd hook · last 2h · --write")
    ap.add_argument("--list-drafts", action="store_true",
                    help="list existing drafts and exit")
    ap.add_argument("--promote",
                    metavar="DRAFT_ID",
                    help="promote a draft to a formal coll-NNNN.md skeleton "
                         "(accepts full path · filename · or substring) · "
                         "Day 13 addition closing the memory-sedimentation loop")
    ap.add_argument("--quiet", action="store_true")
    add_path_arg(ap)
    args = ap.parse_args()

    _activate_overlay(args)
    # Autopilot tick AFTER overlay activation so heartbeat fires on the
    # correct overlay (Day 13 fix · previously always central).
    _autopilot_tick()

    if args.list_drafts:
        return cmd_list_drafts()

    if args.promote:
        return cmd_promote(args.promote, quiet=args.quiet)

    if args.on_session_end:
        args.since = f"{ON_SESSION_END_SINCE_HOURS}h"
        args.write = True

    return cmd_scan(args.since, args.write, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
