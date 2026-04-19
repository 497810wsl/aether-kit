#!/usr/bin/env bash
# uninstall-hook.sh · reverses install-hook.sh
#
# Removes ~/.cursor/hooks/aether-dispatch.py, ~/.cursor/rules/aether.mdc,
# and strips the aether-dispatch entry from ~/.cursor/hooks.json while
# preserving any other user hooks.

set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

cursor_dir="$HOME/.cursor"
tgt_dispatcher="$cursor_dir/hooks/aether-dispatch.py"
tgt_mdc="$cursor_dir/rules/aether.mdc"
tgt_hooks_json="$cursor_dir/hooks.json"

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Aether Kit · uninstall global Cursor hook"
echo "═══════════════════════════════════════════════════════════"
echo ""

for f in "$tgt_dispatcher" "$tgt_mdc"; do
    if [ -f "$f" ]; then
        echo "  removing $f"
        [ $DRY_RUN -eq 0 ] && rm -f "$f"
    else
        echo "  not present $f"
    fi
done

if [ -f "$tgt_hooks_json" ] && [ $DRY_RUN -eq 0 ]; then
    $PY - "$tgt_hooks_json" <<'PYEOF'
import json, sys, os
target = sys.argv[1]
try:
    with open(target, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception:
    print("  ✗ hooks.json not valid JSON · left untouched")
    sys.exit(0)
if not isinstance(data, dict):
    sys.exit(0)
hooks = data.get("hooks", {})
ss = hooks.get("sessionStart", [])
kept = [h for h in ss if not (isinstance(h, dict) and "aether-dispatch.py" in str(h.get("command", "")))]
if len(kept) != len(ss):
    if kept:
        hooks["sessionStart"] = kept
    else:
        hooks.pop("sessionStart", None)
    user_hooks = [k for k in hooks if not k.startswith("_")]
    if not user_hooks:
        os.remove(target)
        print(f"  removed now-empty {target}")
    else:
        with open(target, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  updated {target} (kept your other hooks)")
else:
    print("  no aether-dispatch entry in hooks.json")
PYEOF
elif [ ! -f "$tgt_hooks_json" ]; then
    echo "  not present $tgt_hooks_json"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✓ Aether Kit global hook removed"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Restart Cursor to apply."
echo ""
