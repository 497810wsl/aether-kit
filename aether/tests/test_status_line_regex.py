#!/usr/bin/env python3
"""
test_status_line_regex.py — Regression guard for RULE 00 status line regex.

Runs standalone (no pytest dep):
    python aether/tests/test_status_line_regex.py

Also callable by a future CI step. Exits 0 when all cases pass, 1 otherwise.

Why this test exists
────────────────────
Day 12 (coll-0092) changed the RULE 00 regex from a single pattern to two
alternatives (registered · unregistered). The regex lives in
`.cursor/rules/aether.mdc` and must stay in sync with the status line
built by `aether_handshake._status_line()`. Drift between the two =
broken sessionStart contract = silent Owner surprise.

These fixtures pin down:
  1. Each of 4 scope forms (S1-S4) matches the expected regex branch.
  2. Negative cases (malformed / old-format) do NOT match.
  3. The aether_handshake script actually emits lines that match.

Fixture design derives from STATUS-LINE-SCOPE-FIX.md §6.2 · keep in sync.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # aether/
REPO = ROOT.parent                                      # central repo root

# ─── The two canonical RULE 00 regex alternatives ────────────────────
# These MUST mirror what's pinned in `.cursor/rules/aether.mdc` RULE 00.
# If you change one, change the other (and bump STATUS-LINE-SCOPE-FIX.md).

# Score segment may contain interior `·` when expanded
# (e.g. "86/100 (32 ok · 2 warn · 3 fail)"). Using non-greedy `.+?` so
# the trailing `· scope: [^·]+ · handover: ...` anchor forces expansion
# only as far as needed to reach the scope marker.
REGISTERED_RE = re.compile(
    r"^⟁ Aether · Day \d+/30 · .+? · scope: [^·]+ · handover: day-\d+-handover\.md$"
)
UNREGISTERED_RE = re.compile(
    r"^⟁ Aether · unregistered · scope: guest @ [^·]+ · handover: none$"
)


def matches_rule_00(line: str) -> str | None:
    """Return which branch matches · or None."""
    if REGISTERED_RE.match(line):
        return "registered"
    if UNREGISTERED_RE.match(line):
        return "unregistered"
    return None


# ─── fixtures ─────────────────────────────────────────────────────────

POSITIVE = [
    # (name, status_line, expected_branch)
    ("S1 · dev-self",
     "⟁ Aether · Day 12/30 · 86/100 (32 ok · 2 warn · 3 fail) · scope: dev-self · handover: day-11-handover.md",
     "registered"),
    ("S1 · dev-self full score",
     "⟁ Aether · Day 12/30 · 100/100 (31 ok · 0 warn · 0 fail) · scope: dev-self · handover: day-11-handover.md",
     "registered"),
    ("S2 · guest + handover",
     "⟁ Aether · Day 3/30 · ?/? · scope: guest @ cursor-api-proxy · handover: day-2-handover.md",
     "registered"),
    ("S3 · guest + empty handover",
     "⟁ Aether · Day 1/30 · ?/? · scope: guest @ demo-proj · handover: day-0-handover.md",
     "registered"),
    ("S4 · unregistered",
     "⟁ Aether · unregistered · scope: guest @ novel-project · handover: none",
     "unregistered"),
    ("S4 · unregistered · short name",
     "⟁ Aether · unregistered · scope: guest @ x · handover: none",
     "unregistered"),
]

NEGATIVE = [
    # Lines that MUST NOT match either branch
    ("old format · no scope segment",
     "⟁ Aether · Day 12/30 · 100/100 (31 ok · 0 warn · 0 fail) · handover: day-11-handover.md"),
    ("malformed · wrong glyph",
     "△ Aether · Day 12/30 · 86/100 · scope: dev-self · handover: day-11-handover.md"),
    ("malformed · missing Day",
     "⟁ Aether · 12/30 · 86/100 · scope: dev-self · handover: day-11-handover.md"),
    ("malformed · unregistered + dev-self (impossible combo)",
     "⟁ Aether · unregistered · scope: dev-self · handover: none"),
    ("malformed · unregistered but has handover file",
     "⟁ Aether · unregistered · scope: guest @ x · handover: day-0-handover.md"),
    ("malformed · registered but handover=none",
     "⟁ Aether · Day 1/30 · ?/? · scope: guest @ x · handover: none"),
]


# ─── runners ──────────────────────────────────────────────────────────

def run_positive() -> tuple[int, int]:
    passes = fails = 0
    for name, line, want in POSITIVE:
        got = matches_rule_00(line)
        if got == want:
            print(f"  [ok] {name}  → {want}")
            passes += 1
        else:
            print(f"  [FAIL] {name}  · want={want} · got={got}")
            print(f"         line: {line}")
            fails += 1
    return passes, fails


def run_negative() -> tuple[int, int]:
    passes = fails = 0
    for name, line in NEGATIVE:
        got = matches_rule_00(line)
        if got is None:
            print(f"  [ok] {name}")
            passes += 1
        else:
            print(f"  [FAIL] {name}  · unexpectedly matched {got}")
            print(f"         line: {line}")
            fails += 1
    return passes, fails


def run_handshake_live() -> tuple[int, int]:
    """Invoke `aether_handshake.py --test --scope <s> --workspace <w>` for
    each of the 4 scenarios and verify the emitted status line matches
    the expected branch.

    This is the glue test: if the script ever drifts from the regex,
    the static fixture tests above would pass while Owner's real session
    would fail. This check fires the actual CLI.
    """
    handshake = ROOT / "bin" / "aether_handshake.py"
    if not handshake.exists():
        print(f"  [skip] {handshake} missing")
        return 0, 0

    # Create an ephemeral overlay under tmp for S2/S3
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="aether-test-"))
    overlay_handover = tmp / ".aether" / "handover"
    overlay_handover.mkdir(parents=True, exist_ok=True)

    # Cases must run in an order that doesn't contaminate each other's
    # fixtures. T3 needs an empty handover dir · T2 needs a day-2 file.
    # Fixture prep happens inside the loop, keyed by name.
    cases = [
        # (name, extra args, expected branch, must-contain snippet, fixture fn)
        ("T1 · dev-self",
         ["--scope", "dev-self"],
         "registered", "scope: dev-self", None),
        ("T4 · guest + no overlay",
         ["--scope", "guest", "--workspace", str(tmp.parent)],
         "unregistered", "unregistered", None),
        ("T3 · guest + empty overlay",
         ["--scope", "guest", "--workspace", str(tmp)],
         "registered", "Day 1/30", None),
        ("T2 · guest + day-2-handover.md",
         ["--scope", "guest", "--workspace", str(tmp)],
         "registered", "Day 3/30",
         lambda: (overlay_handover / "day-2-handover.md").write_text("# test", encoding="utf-8")),
    ]

    passes = fails = 0
    for name, extra, want, must_contain, fixture in cases:
        if fixture is not None:
            fixture()
        r = subprocess.run(
            [sys.executable, str(handshake), "--test"] + extra,
            capture_output=True, text=True, encoding="utf-8",
        )
        m = re.search(r"^Status line: (.+)$", r.stdout, re.MULTILINE)
        if not m:
            print(f"  [FAIL] {name}  · no 'Status line:' in output")
            print(f"         stdout: {r.stdout[:300]}")
            fails += 1
            continue
        line = m.group(1).strip()
        branch = matches_rule_00(line)
        if branch != want:
            print(f"  [FAIL] {name}  · want={want} got={branch}")
            print(f"         line: {line}")
            fails += 1
            continue
        if must_contain not in line:
            print(f"  [FAIL] {name}  · missing snippet '{must_contain}'")
            print(f"         line: {line}")
            fails += 1
            continue
        print(f"  [ok] {name}  → {branch}  · {line[:80]}...")
        passes += 1

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    return passes, fails


# ─── main ─────────────────────────────────────────────────────────────

def main() -> int:
    print("Status line regex regression · Day 12 · coll-0092")
    print("=" * 60)

    print("\n[1/3] Positive fixtures · should match one of the two branches")
    pp, pf = run_positive()

    print("\n[2/3] Negative fixtures · MUST NOT match either branch")
    np_, nf = run_negative()

    print("\n[3/3] Live handshake invocation · script output must match regex")
    hp, hf = run_handshake_live()

    total_pass = pp + np_ + hp
    total_fail = pf + nf + hf
    total = total_pass + total_fail

    print("\n" + "=" * 60)
    if total_fail == 0:
        print(f"all {total} checks pass")
        return 0
    print(f"{total_fail}/{total} FAIL · positive={pf} negative={nf} live={hf}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
