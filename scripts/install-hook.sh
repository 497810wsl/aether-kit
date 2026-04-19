#!/usr/bin/env bash
# install-hook.sh · Aether Kit global Cursor hook installer · macOS / Linux
#
# Copies aether-dispatch.py + aether.mdc to ~/.cursor/ and merges the
# sessionStart hook into ~/.cursor/hooks.json (preserving any existing
# hooks · never overwrites unrelated entries).
#
# Usage:
#   ./scripts/install-hook.sh            # install
#   ./scripts/install-hook.sh --force    # overwrite existing Aether files
#   ./scripts/install-hook.sh --dry-run  # preview · no filesystem writes
#
# After install: restart Cursor. Any workspace with aether/bin/aether_hook.py
# will auto-handshake on session start. Non-Aether workspaces are unaffected.
#
# Requires: python3 in PATH · jq (optional · for cleaner hooks.json merge).

set -euo pipefail

FORCE=0
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help)
            sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "unknown arg: $arg"; exit 1 ;;
    esac
done

# ----- locate ourselves -----
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
src_dispatcher="$repo_root/kit/.cursor-global/hooks/aether-dispatch.py"
src_mdc="$repo_root/kit/.cursor-global/rules/aether.mdc"
src_hooks_json="$repo_root/kit/.cursor-global/hooks.json"

cursor_dir="$HOME/.cursor"
tgt_dispatcher="$cursor_dir/hooks/aether-dispatch.py"
tgt_mdc="$cursor_dir/rules/aether.mdc"
tgt_hooks_json="$cursor_dir/hooks.json"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Aether Kit · install global Cursor hook"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  source : $repo_root"
echo "  target : $cursor_dir"
[ $DRY_RUN -eq 1 ] && echo "  MODE   : DRY RUN (no filesystem writes)"
[ $FORCE -eq 1 ]   && echo "  MODE   : FORCE (overwrite existing Aether files)"
echo ""

# ----- precheck · Python -----
if ! command -v python3 >/dev/null 2>&1; then
    if ! command -v python >/dev/null 2>&1; then
        echo "✗ python not found in PATH"
        echo "  aether-dispatch.py requires Python 3.6+"
        exit 1
    fi
    PY=python
else
    PY=python3
fi
echo "✓ Python: $($PY --version 2>&1)"

# ----- precheck · source files -----
for f in "$src_dispatcher" "$src_mdc" "$src_hooks_json"; do
    if [ ! -f "$f" ]; then
        echo "✗ missing source file: $f"
        echo "  is this a valid aether-kit checkout?"
        exit 1
    fi
done
echo "✓ all source files present"

# ----- helper · sha256 portable -----
sha() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

# ----- step 1 · dirs -----
echo ""
echo "▶ step 1 · prepare target dirs"
for d in "$cursor_dir" "$cursor_dir/hooks" "$cursor_dir/rules"; do
    if [ ! -d "$d" ]; then
        echo "  creating $d"
        [ $DRY_RUN -eq 0 ] && mkdir -p "$d"
    else
        echo "  exists   $d"
    fi
done

# ----- step 2 · dispatcher -----
echo ""
echo "▶ step 2 · install dispatcher"
install_file() {
    local src="$1" tgt="$2"
    if [ -f "$tgt" ] && [ $FORCE -eq 0 ]; then
        if [ "$(sha "$src")" = "$(sha "$tgt")" ]; then
            echo "  ✓ up to date · $tgt"
            return 0
        else
            echo "  ✗ $tgt exists and differs"
            echo "    re-run with --force to upgrade"
            exit 1
        fi
    fi
    echo "  installing $tgt"
    if [ $DRY_RUN -eq 0 ]; then
        cp "$src" "$tgt"
        chmod +x "$tgt" 2>/dev/null || true
    fi
}
install_file "$src_dispatcher" "$tgt_dispatcher"

# ----- step 3 · rule -----
echo ""
echo "▶ step 3 · install rule"
install_file "$src_mdc" "$tgt_mdc"

# ----- step 4 · merge hooks.json -----
echo ""
echo "▶ step 4 · merge hooks.json"

dispatch_cmd="$PY \"$tgt_dispatcher\""

if [ -f "$tgt_hooks_json" ]; then
    echo "  found existing $tgt_hooks_json · merging"
    # Use Python itself for merging · portable · doesn't require jq.
    if [ $DRY_RUN -eq 0 ]; then
        $PY - "$tgt_hooks_json" "$dispatch_cmd" <<'PYEOF'
import json, sys, os
target, cmd = sys.argv[1], sys.argv[2]
try:
    with open(target, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception:
    print(f"  ✗ existing hooks.json is not valid JSON · aborting (fix or --force)")
    sys.exit(1)
if not isinstance(data, dict):
    data = {}
data.setdefault("version", 1)
hooks = data.setdefault("hooks", {})
ss = hooks.get("sessionStart", [])
if not isinstance(ss, list):
    ss = []
if any(isinstance(h, dict) and "aether-dispatch.py" in str(h.get("command", "")) for h in ss):
    print("  ✓ aether-dispatch already registered · leaving unchanged")
else:
    ss.append({"command": cmd, "timeout": 30})
    hooks["sessionStart"] = ss
    with open(target, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("  ✓ appended aether-dispatch to sessionStart")
PYEOF
    else
        echo "  (dry-run · would merge into $tgt_hooks_json)"
    fi
else
    echo "  creating $tgt_hooks_json"
    if [ $DRY_RUN -eq 0 ]; then
        # Write fresh file with real path baked in
        cat > "$tgt_hooks_json" <<EOF
{
  "version": 1,
  "_comment": "Aether Kit · user-level hooks · installed by aether-kit/scripts/install-hook.sh · remove with uninstall-hook.sh or delete this file",
  "hooks": {
    "sessionStart": [
      {
        "command": "$dispatch_cmd",
        "timeout": 30
      }
    ]
  }
}
EOF
    fi
fi

# ----- done -----
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✓ Aether Kit global hook installed"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo "    1. Restart Cursor"
echo "    2. Open any workspace"
echo "       - if it has aether/bin/aether_hook.py · session auto-handshakes"
echo "       - if not · nothing changes · you won't notice it's installed"
echo ""
echo "  To uninstall:"
echo "    ./scripts/uninstall-hook.sh"
echo ""
