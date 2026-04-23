#!/usr/bin/env python3
"""
aether_install.py — 装 Aether hooks · 4 个 scope · 4 种模式

scope(选一个):
  · 默认            · target 项目级 · 装 <target>/.cursor/hooks.json
  · --global        · 用户级 · 装 ~/.cursor/hooks.json (所有 Cursor 会话生效)

模式(选一个):
  · 默认            · shared · hooks.json 用绝对路径调中央 aether/
  · --copy          · 拷 aether/ 公开子集到 target (--global 不支持 copy)
  · --uninstall     · 移除我们装的 · 绝不删 user 其他 hook
  · --check         · 看状态

数据隔离(自动):
  hook 触发时 · 用 payload.workspace_roots[0] 决定数据目录:
    · 全局模式打开任意项目 → 那个项目的 .aether/ 收 events / transcripts / agent-responses
    · CLI 直接调 → 中央 aether 的 .aether/
  这意味着 OpenClaw 的对话痕迹不会污染你写小说项目的痕迹。

CLI:
  # 项目级
  python bin/aether_install.py D:/path/to/target --apply
  python bin/aether_install.py D:/path/to/target --copy --apply
  python bin/aether_install.py D:/path/to/target --uninstall --apply
  python bin/aether_install.py D:/path/to/target --check

  # 全局(推荐 · 一次装 · 所有项目用)
  python bin/aether_install.py --global --apply
  python bin/aether_install.py --global --check
  python bin/aether_install.py --global --uninstall --apply

安全保证:
  1. 永不覆盖已存在的 .cursor/hooks.json 不备份
  2. target 不能是中央 aether 自身 / aether/ 子目录
  3. 默认 dry-run · 显示会做什么 · --apply 才真做
  4. 全局模式装在 ~/.cursor/ · 永远是 shared variant(不拷文件)

Owner 真实测试流程(全局模式 · 装一次终身):
  1. python aether/bin/aether_install.py --global --apply
  2. 重启 Cursor
  3. 任意打开一个项目(比如 D:/OpenClaw/x)新 chat
  4. AI 第一行应贴 ⟁ Aether · Day N/30 状态行
  5. 数据写到该项目的 .aether/events.jsonl · 不污染中央
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent              # aether/
WORKSPACE_ROOT = ROOT.parent                                # current workspace root

# Files we install · used by --check and --uninstall to identify our install
INSTALL_MANIFEST_NAME = ".aether-install.json"

# Global install · ~/.cursor/hooks.json · sister manifest in ~/.cursor/
USER_CURSOR_DIR = Path.home() / ".cursor"
GLOBAL_HOOKS_PATH = USER_CURSOR_DIR / "hooks.json"
GLOBAL_MANIFEST_PATH = USER_CURSOR_DIR / INSTALL_MANIFEST_NAME

# ANSI · shared with all aether CLIs (Day 13 · B-choice follow-up to coll-0084)
# Install flow is sensitive · this migration is 1:1 constant aliasing only ·
# no behavior change · `_c` keeps its exact (code, text, color) signature.
import aether_paths as _ap                                       # noqa: E402
RESET  = _ap.RESET
BOLD   = _ap.BOLD
RED    = _ap.RED
GREEN  = _ap.GREEN
YELLOW = _ap.YELLOW
CYAN   = _ap.CYAN
GRAY   = _ap.GRAY
_c     = _ap.c


# ─── target validation ─────────────────────────────────────────────

def validate_target(target: Path) -> tuple[bool, str]:
    """Returns (ok, reason)."""
    if not target.exists():
        return False, f"target does not exist: {target}"
    if not target.is_dir():
        return False, f"target is not a directory: {target}"
    target_resolved = target.resolve()
    if target_resolved == WORKSPACE_ROOT.resolve():
        return False, ("target is the current Aether workspace itself · "
                       "you don't install Aether onto its own home")
    # Walk up to check we're not inside aether/ subtree
    try:
        target_resolved.relative_to(ROOT.resolve())
        return False, f"target is inside aether/ subtree · pick a different project"
    except ValueError:
        pass  # good · target is outside aether/
    return True, ""


# ─── shared mode ──────────────────────────────────────────────────

def _pwsh_safe_cmd(python_exec: str, script: Path, event: str) -> str:
    """Build a platform-safe hook command string.

    CRITICAL · Day 8 discovery(Cursor forum confirmed): Cursor 3.x on Windows
    runs `hooks.json` commands through PowerShell, not cmd.exe. PowerShell
    refuses to treat a bare quoted path as an executable:

        $input | "C:\\python.exe" "script.py" --event X
        → "Expressions are only allowed as the first element of a pipeline"

    PowerShell needs the `&` call operator to treat a quoted string as
    a command:

        $input | & "C:\\python.exe" "script.py" --event X

    On POSIX(macOS/Linux · bash) · leading `& ` would mean background fork ·
    so we only emit it on Windows. POSIX gets plain `"path" "script" --event X`
    which bash executes directly.
    """
    import os
    if os.name == "nt":
        return f'& "{python_exec}" "{script}" --event {event}'
    return f'"{python_exec}" "{script}" --event {event}'


def hooks_json_shared(aether_bin: Path, python_exec: str, scope: str = "project") -> dict:
    """Generate hooks.json that points absolute paths to the central aether/.

    scope: 'project' (target/.cursor/hooks.json) or 'global' (~/.cursor/hooks.json).
    Commands use `& "..."` PowerShell call-operator form (see _pwsh_safe_cmd docstring).
    """
    import os
    hook = aether_bin / "aether_hook.py"
    guardian = aether_bin / "aether_guardian.py"
    scope_note = ("USER-LEVEL · all Cursor sessions across all projects" if scope == "global"
                  else "PROJECT-LEVEL · this single project only")
    if os.name == "nt":
        guardian_cmd = f'& "{python_exec}" "{guardian}" --once'
    else:
        guardian_cmd = f'"{python_exec}" "{guardian}" --once'
    return {
        "version": 1,
        "_comment": (f"Aether hooks · SHARED mode · {scope_note} · installed by aether_install.py · "
                     f"central aether at: {aether_bin.parent.parent}"),
        "_install_mode": "shared",
        "_install_scope": scope,
        "_central_aether": str(aether_bin.parent.parent.resolve()),
        "_central_python": python_exec,
        "_installed_at": datetime.now(timezone.utc).isoformat(),
        "_powershell_note": ("commands use `& \"...\"` call operator · "
                             "required on Windows(Cursor runs hooks via PowerShell) · "
                             "harmless on POSIX"),
        "_data_isolation": ("hooks honor payload.workspace_roots · "
                            "events / transcripts / agent-responses go to "
                            "<target-project>/.aether/ · NOT central .aether/"),
        "_uninstall": ("python <central-aether>/bin/aether_install.py --global --uninstall --apply"
                       if scope == "global"
                       else "python <central-aether>/bin/aether_install.py <this-target> --uninstall --apply"),
        "hooks": {
            "sessionStart": [
                {"command": _pwsh_safe_cmd(python_exec, hook, "sessionStart"), "timeout": 30},
                {"command": guardian_cmd, "timeout": 20},
            ],
            "postToolUse": [
                {"command": _pwsh_safe_cmd(python_exec, hook, "postToolUse"), "timeout": 5},
            ],
            "afterAgentResponse": [
                {"command": _pwsh_safe_cmd(python_exec, hook, "afterAgentResponse"), "timeout": 5},
            ],
            "preCompact": [
                {"command": _pwsh_safe_cmd(python_exec, hook, "preCompact"), "timeout": 10},
            ],
            "afterAgentThought": [
                {"command": _pwsh_safe_cmd(python_exec, hook, "afterAgentThought"), "timeout": 5},
            ],
            "postToolUseFailure": [
                {"command": _pwsh_safe_cmd(python_exec, hook, "postToolUseFailure"), "timeout": 5},
            ],
            "beforeShellExecution": [
                {"command": _pwsh_safe_cmd(python_exec, hook, "beforeShellExecution"), "timeout": 5},
            ],
            "sessionEnd": [
                {"command": _pwsh_safe_cmd(python_exec, hook, "sessionEnd"), "timeout": 60},
            ],
            "stop": [
                {"command": _pwsh_safe_cmd(python_exec, hook, "stop"), "timeout": 30},
            ],
        },
    }


# ─── copy mode (subset) ────────────────────────────────────────────

# What gets copied in --copy mode. We deliberately exclude:
#   · gen6-noesis/* (Owner's private memory · sensitive)
#   · gen5-ecoware/species-registry.json (Owner-specific evolution)
#   · gen5-ecoware/nursery/* (in-progress seeds)
#   · labs/chronicle/* (Owner's history)
#   · docs/daily/* (handover docs)
#   · docs/30-day-plan.md (Owner's plan)
#   · 1.md / 2.md / 3.md (sensitive AI analysis)
#   · .aether-persona/ (already gitignored · Owner's exports)
COPY_INCLUDE = [
    "bin",                      # all CLIs
    "00-origin",                # constitution
    "gen4-morphogen",           # field definitions (incl. starter fields)
    "gen5-ecoware/README.md",
    "gen5-ecoware/symbiosis.md",
    "gen5-ecoware/food-chain.md",
    "gen5-ecoware/species-registry.template.json",
    "gen5-ecoware/nursery/README.md",
    "gen6-noesis/README.md",
    "gen6-noesis/resonance-map.md",
    "gen6-noesis/collapse-events/_template.md",
    "gen7-logos",
    "labs/README.md",
    "labs/examples",
    "demo",
    "meta",
    "docs/MODES.md",
    "docs/PROTOCOL-0.md",
    "docs/USAGE-MODEL.md",
    "docs/cognitive-recipes.md",
    "docs/persona-marketplace.md",
    "docs/recipes",
    "docs/integration",
    "docs/USAGE-DAILY.md",
    "docs/contact.md",
    "AGENTS.md",
    "README.md",
    "PROJECT-MAP.md",
    "STRATEGY.md",
    "ROADMAP.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "quickstart.md",
]


def copy_subset(src_aether: Path, dst_aether: Path) -> list[str]:
    """Copy the public subset of aether/ into dst_aether/. Returns list of
    relative paths actually copied (for the install manifest)."""
    copied: list[str] = []
    for rel in COPY_INCLUDE:
        s = src_aether / rel
        if not s.exists():
            continue
        d = dst_aether / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_file():
            shutil.copy2(s, d)
            copied.append(rel)
        elif s.is_dir():
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(s, d, ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".aether-persona", "_probe_*",
            ))
            copied.append(rel + "/")
    return copied


def hooks_json_copy(target: Path, python_exec: str) -> dict:
    """Generate hooks.json that uses relative paths · target ships its own
    aether/ subtree. Same shape as our own .cursor/hooks.json."""
    return {
        "version": 1,
        "_comment": ("Aether hooks · COPY mode · installed by aether_install.py · "
                     "self-contained · runs target's own aether/ subtree"),
        "_install_mode": "copy",
        "_installed_at": datetime.now(timezone.utc).isoformat(),
        "_uninstall": "python aether/bin/aether_install.py . --uninstall --apply",
        "hooks": {
            "sessionStart": [
                {"command": "python aether/bin/aether_hook.py --event sessionStart", "timeout": 30},
                {"command": "python aether/bin/aether_guardian.py --once", "timeout": 20},
            ],
            "postToolUse": [
                {"command": "python aether/bin/aether_hook.py --event postToolUse", "timeout": 5},
            ],
            "afterAgentResponse": [
                {"command": "python aether/bin/aether_hook.py --event afterAgentResponse", "timeout": 5},
            ],
            "preCompact": [
                {"command": "python aether/bin/aether_hook.py --event preCompact", "timeout": 10},
            ],
            "afterAgentThought": [
                {"command": "python aether/bin/aether_hook.py --event afterAgentThought", "timeout": 5},
            ],
            "postToolUseFailure": [
                {"command": "python aether/bin/aether_hook.py --event postToolUseFailure", "timeout": 5},
            ],
            "beforeShellExecution": [
                {"command": "python aether/bin/aether_hook.py --event beforeShellExecution", "timeout": 5},
            ],
            "sessionEnd": [
                {"command": "python aether/bin/aether_hook.py --event sessionEnd", "timeout": 60},
            ],
            "stop": [
                {"command": "python aether/bin/aether_hook.py --event stop", "timeout": 30},
            ],
        },
    }


# ─── manifest (so uninstall knows what we installed) ───────────────

def write_manifest(target: Path, mode: str, files: list[str], hooks_backup: str | None) -> None:
    manifest_path = target / INSTALL_MANIFEST_NAME
    manifest_path.write_text(json.dumps({
        "version": 1,
        "mode": mode,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "central_aether": str(WORKSPACE_ROOT.resolve()) if mode == "shared" else None,
        "central_python": sys.executable if mode == "shared" else None,
        "installed_files": files,
        "hooks_backup": hooks_backup,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def read_manifest(target: Path) -> dict | None:
    p = target / INSTALL_MANIFEST_NAME
    if not p.exists():
        return None
    cfg, _ = _read_json_tolerant(p)
    return cfg


# ─── command handlers ──────────────────────────────────────────────

def _cli_wrapper_path() -> Path:
    """Where to put the `aether` executable shim · platform-specific default
    PATH location so user doesn't need to modify PATH env var.

    Windows · %LOCALAPPDATA%\\Microsoft\\WindowsApps\\aether.bat
              (this folder is always on user PATH on Win10+)
    POSIX   · ~/.local/bin/aether
              (most distros default · macOS Homebrew brew_user adds it · safe)
    """
    import os
    if os.name == "nt":
        local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return local_app / "Microsoft" / "WindowsApps" / "aether.bat"
    return Path.home() / ".local" / "bin" / "aether"


def _is_in_path(executable_path: Path) -> bool:
    """Check whether the wrapper's parent directory is on PATH."""
    import os
    parent = str(executable_path.parent.resolve()).lower()
    paths = os.environ.get("PATH", "").split(os.pathsep)
    return any(p.strip().lower().rstrip("\\/") == parent.rstrip("\\/") for p in paths if p.strip())


def _discover_subcommands(central: Path) -> tuple[list[str], list[str]]:
    """Discover all aether_*.py subcommand names + curated "common" subset.

    Day 11 (coll-0083 A1-4 fix): wrapper used to hand-maintain a list of
    6 "common" subcommands and omit the other 20+ · leading to false
    "aether: unknown command" impressions. Now we glob at install time.

    Returns (common, all). `all` is sorted alphabetically. `common` is
    ordered by how often Owner actually uses them (daily first).
    """
    bin_dir = central / "aether" / "bin"
    excluded = {"aether_paths", "aether_hook"}
    all_cmds: list[str] = []
    for p in sorted(bin_dir.glob("aether_*.py")):
        stem = p.stem
        if stem in excluded:
            continue
        all_cmds.append(stem[len("aether_"):])

    # Curated order · most-used first · unknown drops off the list silently
    curated = ["daily", "tasks", "project", "federate",
               "doctor", "query", "selfcheck", "install"]
    common = [c for c in curated if c in all_cmds]
    return common, sorted(all_cmds)


def _wrap_for_echo(items: list[str], indent: str = "         ", width: int = 72) -> list[str]:
    """Wrap a comma-separated list into lines suitable for `echo` lines."""
    lines: list[str] = []
    cur = indent
    for i, it in enumerate(items):
        piece = it + ("," if i < len(items) - 1 else "")
        # +1 for space between items
        if len(cur) + len(piece) + 1 > width and cur.strip():
            lines.append(cur.rstrip())
            cur = indent
        cur += piece + " "
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


def _generate_wrapper_content(central: Path, python_exec: str) -> str:
    """Generate the platform-specific shell wrapper.

    Windows .bat:
      · uses enabledelayedexpansion + shift loop to correctly forward
        arguments after the subcommand · preserves quoted args
      · maps `aether <sub> [args]` → python <central>\\aether\\bin\\aether_<sub>.py [args]

    POSIX shell:
      · uses ${@:2} for tail-args (preserves quoting)

    The subcommand help block is generated at install time by scanning
    aether/bin/aether_*.py so it stays in sync without manual updates.
    """
    import os
    common, all_cmds = _discover_subcommands(central)
    if os.name == "nt":
        # CRITICAL: avoid `if (...)` blocks · they conflict with user args
        # containing `(` `)` (e.g. `--proof "coll-0080 (pending)"`).
        # All conditionals use single-line `if X==Y goto :label` form.
        # `set "args=%args% "%~1""` works for first iteration too because
        # leading space is harmless · no need for `if defined args` block.
        return (
            "@echo off\n"
            "REM Aether CLI wrapper · auto-generated by aether_install.py --global\n"
            "REM See: aether/docs/USING-IN-OTHER-PROJECTS.md\n"
            "setlocal enabledelayedexpansion\n"
            "set \"AETHER_PYTHON=" + python_exec + "\"\n"
            "set \"AETHER_CENTRAL=" + str(central) + "\"\n"
            "if \"%~1\"==\"\" goto :aether_help\n"
            "if \"%~1\"==\"--help\" goto :aether_help\n"
            "if \"%~1\"==\"-h\" goto :aether_help\n"
            "if \"%~1\"==\"--version\" goto :aether_version\n"
            "set \"subcmd=%~1\"\n"
            "set \"args=\"\n"
            ":aether_loop\n"
            "shift /1\n"
            "if \"%~1\"==\"\" goto :aether_run\n"
            "set \"args=!args! \"%~1\"\"\n"
            "goto :aether_loop\n"
            ":aether_run\n"
            "if not exist \"%AETHER_CENTRAL%\\aether\\bin\\aether_!subcmd!.py\" goto :aether_unknown\n"
            "\"%AETHER_PYTHON%\" \"%AETHER_CENTRAL%\\aether\\bin\\aether_!subcmd!.py\" !args!\n"
            "endlocal & exit /b %errorlevel%\n"
            ":aether_unknown\n"
            "echo aether: unknown command '!subcmd!' 1>&2\n"
            "echo aether: try 'aether --help' 1>&2\n"
            "endlocal & exit /b 2\n"
            ":aether_help\n"
            "echo Aether CLI - usage: aether ^<subcommand^> [args]\n"
            "echo.\n"
            + "echo Common:  " + "  ".join(common) + "\n"
            + "echo.\n"
            + "echo All:\n"
            + "".join(f"echo {line}\n"
                      for line in _wrap_for_echo(all_cmds, indent="         "))
            + "echo.\n"
            + "echo Help:    aether ^<cmd^> --help\n"
              "echo Source:  %AETHER_CENTRAL%\\aether\n"
              "echo See:     %AETHER_CENTRAL%\\aether\\quickstart.md\n"
              "endlocal & exit /b 0\n"
            ":aether_version\n"
            "echo aether-cli - global wrapper\n"
            "echo central: %AETHER_CENTRAL%\n"
            "endlocal & exit /b 0\n"
        )
    # POSIX shell
    return (
        "#!/usr/bin/env bash\n"
        "# Aether CLI wrapper · auto-generated by aether_install.py --global\n"
        "# See: aether/docs/USING-IN-OTHER-PROJECTS.md\n"
        "set -e\n"
        "AETHER_PYTHON=\"" + python_exec + "\"\n"
        "AETHER_CENTRAL=\"" + str(central) + "\"\n"
        "if [ \"$#\" -eq 0 ] || [ \"$1\" = \"--help\" ]; then\n"
        "  cat <<EOF\n"
        "Aether CLI · usage: aether <subcommand> [args]\n"
        "\n"
        "Common:  " + "  ".join(common) + "\n"
        "\n"
        "All:\n"
        + "\n".join(_wrap_for_echo(all_cmds, indent="  ")) + "\n"
        "\n"
        "Help:    aether <cmd> --help\n"
        "Source:  $AETHER_CENTRAL/aether\n"
        "See:     $AETHER_CENTRAL/aether/quickstart.md\n"
        "EOF\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"--version\" ]; then\n"
        "  echo \"aether-cli · global wrapper\"\n"
        "  echo \"central: $AETHER_CENTRAL\"\n"
        "  exit 0\n"
        "fi\n"
        "subcmd=\"$1\"\n"
        "shift\n"
        "script=\"$AETHER_CENTRAL/aether/bin/aether_${subcmd}.py\"\n"
        "if [ ! -f \"$script\" ]; then\n"
        "  echo \"aether: unknown command '$subcmd'\" >&2\n"
        "  echo \"aether: try 'aether --help'\" >&2\n"
        "  exit 2\n"
        "fi\n"
        "exec \"$AETHER_PYTHON\" \"$script\" \"$@\"\n"
    )


def _install_mdc(scope: str, central: Path, target: Path | None, color: bool) -> Path | None:
    """Install Aether's `.cursor/rules/aether.mdc` so RULE 00 + 5-mode table
    are alwaysApply'd. Without this · briefing-only injection is too soft ·
    AI may ignore status line + mode tags.

    scope='global' → ~/.cursor/rules/aether.mdc (Cursor 3.x supports user-level rules)
    scope='project' → <target>/.cursor/rules/aether.mdc

    Returns destination path on success · None on failure.
    """
    src = central / ".cursor" / "rules" / "aether.mdc"
    if not src.exists():
        print(_c(YELLOW, f"  ⚠ central mdc not found: {src} · cannot install rules", color))
        return None

    if scope == "global":
        dest = Path.home() / ".cursor" / "rules" / "aether.mdc"
    elif scope == "project":
        if not target:
            return None
        dest = target / ".cursor" / "rules" / "aether.mdc"
    else:
        return None

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        return dest
    except OSError as e:
        print(_c(YELLOW, f"  ⚠ mdc install failed: {e}", color))
        return None


def _install_cli_wrapper(central: Path, python_exec: str, color: bool) -> tuple[Path | None, bool]:
    """Write the `aether` shim to a PATH location.

    Returns (path, in_path_now). path is None on write failure.
    """
    import os
    wrapper_path = _cli_wrapper_path()
    try:
        wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        content = _generate_wrapper_content(central, python_exec)
        wrapper_path.write_text(content, encoding="utf-8")
        # Mark executable on POSIX
        if os.name != "nt":
            try:
                wrapper_path.chmod(0o755)
            except OSError:
                pass
        return (wrapper_path, _is_in_path(wrapper_path))
    except OSError as e:
        print(_c(YELLOW, f"  ⚠ wrapper install failed: {e}", color))
        return (None, False)


def _read_json_tolerant(path: Path) -> tuple[dict | None, str | None]:
    """Read JSON tolerating UTF-8 BOM (Notepad/VSCode default on Windows
    sometimes adds it). Returns (parsed, error). UTF-8-sig handles both
    BOM and no-BOM cases automatically."""
    try:
        text = path.read_text(encoding="utf-8-sig")
        return (json.loads(text), None)
    except Exception as e:
        return (None, str(e))


def cmd_check_global(color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_install · check · GLOBAL (~/.cursor/)", color))
    print()
    if not GLOBAL_HOOKS_PATH.exists():
        print(_c(GRAY, "  · no global hooks.json · Aether NOT globally installed", color))
        return 0
    cfg, err = _read_json_tolerant(GLOBAL_HOOKS_PATH)
    if cfg is None:
        print(_c(RED, f"  ✕ ~/.cursor/hooks.json malformed: {err}", color))
        return 1
    if cfg.get("_install_scope") == "global" and cfg.get("_install_mode") == "shared":
        central = cfg.get("_central_aether", "?")
        central_path = Path(central) if central != "?" else None
        if central_path and central_path.exists():
            print(_c(GREEN, f"  ✓ Aether installed globally · central: {central}", color))
        else:
            print(_c(RED, f"  ✕ BROKEN · central aether missing: {central}", color))
            print(_c(YELLOW, "     ALL Cursor sessions will fail hooks · "
                            "uninstall + reinstall from valid path", color))
        print(_c(GRAY, f"     installed_at: {cfg.get('_installed_at')}", color))
        print(_c(GRAY, f"     hooks: {len(cfg.get('hooks', {}))}", color))
    else:
        print(_c(YELLOW, "  ⚠ ~/.cursor/hooks.json exists but NOT installed by us "
                        f"(no _install_scope=global) · won't touch it", color))

    # CLI wrapper status
    wrapper_path = _cli_wrapper_path()
    if wrapper_path.exists():
        in_path = _is_in_path(wrapper_path)
        if in_path:
            print(_c(GREEN, f"  ✓ CLI wrapper installed · {wrapper_path}", color))
            print(_c(GREEN, f"     `aether <cmd>` works from any directory", color))
        else:
            print(_c(YELLOW, f"  ⚠ CLI wrapper at {wrapper_path}", color))
            print(_c(YELLOW, f"     but {wrapper_path.parent} NOT on PATH · add it to use `aether <cmd>` globally", color))
    else:
        print(_c(GRAY, f"  · CLI wrapper not installed (run install --global --apply to add it)", color))

    # User-level rules (mdc) status · CRITICAL for RULE 00 + 5-mode
    mdc_path = Path.home() / ".cursor" / "rules" / "aether.mdc"
    if mdc_path.exists():
        print(_c(GREEN, f"  ✓ user-level rules · {mdc_path} ({mdc_path.stat().st_size} bytes)", color))
        print(_c(GREEN, f"     RULE 00 + 5-mode table alwaysApply across all projects", color))
    else:
        print(_c(YELLOW, f"  ⚠ user-level rules NOT installed · AI may NOT vbpaste status line / mode tags", color))
        print(_c(YELLOW, f"     fix: aether install --global --apply (will add it)", color))
    return 0


def cmd_install_global(apply: bool, color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_install · GLOBAL mode · ~/.cursor/", color))
    print()
    print(_c(GRAY, "  装到用户级别 · 所有 Cursor 会话 · 任何项目都会触发 Aether hooks", color))
    print(_c(GRAY, "  数据按项目自动隔离 · 项目 A 的对话不污染项目 B", color))
    print()

    existing_text: str | None = None
    backup_name: str | None = None
    if GLOBAL_HOOKS_PATH.exists():
        # utf-8-sig tolerates BOM (Windows Notepad / some VSCode configs add it)
        existing_text = GLOBAL_HOOKS_PATH.read_text(encoding="utf-8-sig")
        try:
            j = json.loads(existing_text)
            if j.get("_install_scope") == "global":
                print(_c(GRAY, "  · existing ~/.cursor/hooks.json is from us · will replace", color))
            else:
                print(_c(YELLOW, "  ⚠ existing ~/.cursor/hooks.json is NOT from us · "
                                "will back up to hooks.json.bak", color))
        except Exception:
            print(_c(YELLOW, "  ⚠ existing ~/.cursor/hooks.json malformed · will back up", color))

    actions = [
        f"create {GLOBAL_HOOKS_PATH} (shared mode · absolute paths to {WORKSPACE_ROOT})",
        f"write {GLOBAL_MANIFEST_PATH.name} (uninstall manifest)",
    ]
    if existing_text and "\"_install_scope\": \"global\"" not in existing_text:
        actions.append(f"back up existing hooks.json → hooks.json.bak")

    for a in actions:
        print(_c(GRAY, f"  · would {a}", color))

    if not apply:
        print()
        print(_c(YELLOW, "  (dry-run · pass --apply to actually install)", color))
        return 0

    print()
    print(_c(BOLD, "applying...", color))

    USER_CURSOR_DIR.mkdir(parents=True, exist_ok=True)

    if existing_text and "\"_install_scope\": \"global\"" not in existing_text:
        bak = GLOBAL_HOOKS_PATH.with_suffix(".json.bak")
        if bak.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            bak = USER_CURSOR_DIR / f"hooks.json.bak.{stamp}"
        bak.write_text(existing_text, encoding="utf-8")
        backup_name = bak.name
        print(_c(GREEN, f"  ✓ backed up existing hooks.json → {backup_name}", color))

    cfg = hooks_json_shared(ROOT / "bin", sys.executable, scope="global")
    GLOBAL_HOOKS_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(_c(GREEN, f"  ✓ wrote {GLOBAL_HOOKS_PATH}", color))

    # Install the CLI wrapper · `aether <cmd>` accessible from any directory
    wrapper_path, wrapper_in_path = _install_cli_wrapper(WORKSPACE_ROOT, sys.executable, color)
    if wrapper_path:
        rel = wrapper_path
        print(_c(GREEN, f"  ✓ wrote CLI wrapper · {wrapper_path.name} → {wrapper_path.parent}", color))
        if wrapper_in_path:
            print(_c(GREEN, f"  ✓ wrapper directory IS on PATH · "
                          f"`aether <cmd>` works from any directory", color))
        else:
            print(_c(YELLOW, f"  ⚠ wrapper directory NOT on PATH · add manually:", color))
            print(_c(YELLOW, f"     {wrapper_path.parent}", color))

    # Install user-level mdc · CRITICAL for RULE 00 + 5-mode auto-activation
    # Without this · briefing injection is too soft · AI may ignore status line
    mdc_path = _install_mdc("global", WORKSPACE_ROOT, None, color)
    if mdc_path:
        print(_c(GREEN, f"  ✓ wrote user-level rules · {mdc_path}", color))
        print(_c(GREEN, f"     RULE 00 + 5-mode table now alwaysApply across all projects", color))

    GLOBAL_MANIFEST_PATH.write_text(json.dumps({
        "version": 1,
        "scope": "global",
        "mode": "shared",
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "central_aether": str(WORKSPACE_ROOT.resolve()),
        "central_python": sys.executable,
        "hooks_backup": backup_name,
        "cli_wrapper": str(wrapper_path) if wrapper_path else None,
        "mdc_path": str(mdc_path) if mdc_path else None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(_c(GREEN, f"  ✓ wrote {GLOBAL_MANIFEST_PATH.name}", color))

    print()
    print(_c(BOLD, "next steps · 真实测试:", color))
    print(_c(GRAY, "  1. 完全关闭 Cursor (File → Exit · 重新加载 ~/.cursor/hooks.json)", color))
    print(_c(GRAY, "  2. 重新打开 Cursor · 任意打开一个之前没装过 Aether 的项目", color))
    print(_c(GRAY, "  3. 新建 chat · 输入 \"你好\"", color))
    print(_c(GRAY, "  4. AI 第一行应贴 \"⟁ Aether · Day N/30 · ...\" 状态行", color))
    print(_c(GRAY, "  5. 看那个项目根 · 应出现 .aether/events.jsonl(数据隔离的证据)", color))
    if wrapper_path and wrapper_in_path:
        print()
        print(_c(BOLD, "CLI 全局可用 · 任何终端目录直接打:", color))
        print(_c(CYAN, "  aether daily --short", color))
        print(_c(CYAN, "  aether tasks add P0 \"做什么\" --day 9", color))
        print(_c(CYAN, "  aether doctor --apply", color))
        print(_c(CYAN, "  aether install --global --check", color))
        print(_c(GRAY, "  (cmd 找不到时:open new shell · PATH 才生效)", color))
    elif wrapper_path:
        print()
        print(_c(BOLD, "CLI wrapper 已装但需要加 PATH:", color))
        print(_c(CYAN, f"  Windows · 通常已在 PATH(WindowsApps 文件夹)· 如果不在请重启 shell", color))
        print(_c(CYAN, f"  POSIX   · 加这一行到 ~/.bashrc 或 ~/.zshrc:", color))
        print(_c(CYAN, f"            export PATH=\"$HOME/.local/bin:$PATH\"", color))
    print()
    print(_c(GRAY, "  撤销: python aether/bin/aether_install.py --global --uninstall --apply", color))
    return 0


def cmd_uninstall_global(apply: bool, color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_install · uninstall · GLOBAL (~/.cursor/)", color))
    print()

    manifest = None
    if GLOBAL_MANIFEST_PATH.exists():
        manifest, _ = _read_json_tolerant(GLOBAL_MANIFEST_PATH)

    if not GLOBAL_HOOKS_PATH.exists() and not manifest:
        print(_c(YELLOW, "  · no global Aether install detected", color))
        return 0

    backup = manifest.get("hooks_backup") if manifest else None
    cli_wrapper = manifest.get("cli_wrapper") if manifest else None
    mdc_path = manifest.get("mdc_path") if manifest else None
    if not cli_wrapper:
        default_wrapper = _cli_wrapper_path()
        if default_wrapper.exists():
            cli_wrapper = str(default_wrapper)
    if not mdc_path:
        default_mdc = Path.home() / ".cursor" / "rules" / "aether.mdc"
        if default_mdc.exists():
            mdc_path = str(default_mdc)

    actions = ["remove ~/.cursor/hooks.json"]
    if backup:
        actions.append(f"restore from ~/.cursor/{backup}")
    if GLOBAL_MANIFEST_PATH.exists():
        actions.append(f"remove ~/.cursor/{INSTALL_MANIFEST_NAME}")
    if cli_wrapper and Path(cli_wrapper).exists():
        actions.append(f"remove CLI wrapper {cli_wrapper}")
    if mdc_path and Path(mdc_path).exists():
        actions.append(f"remove user-level rules {mdc_path}")

    for a in actions:
        print(_c(GRAY, f"  · would {a}", color))

    if not apply:
        print()
        print(_c(YELLOW, "  (dry-run · pass --apply to actually uninstall)", color))
        return 0

    print()
    print(_c(BOLD, "applying...", color))

    if GLOBAL_HOOKS_PATH.exists():
        GLOBAL_HOOKS_PATH.unlink()
        print(_c(GREEN, "  ✓ removed ~/.cursor/hooks.json", color))

    if backup:
        bak_path = USER_CURSOR_DIR / backup
        if bak_path.exists():
            bak_path.rename(GLOBAL_HOOKS_PATH)
            print(_c(GREEN, f"  ✓ restored hooks.json from {backup}", color))

    if GLOBAL_MANIFEST_PATH.exists():
        GLOBAL_MANIFEST_PATH.unlink()
        print(_c(GREEN, f"  ✓ removed {INSTALL_MANIFEST_NAME}", color))

    if cli_wrapper:
        wrapper_path = Path(cli_wrapper)
        if wrapper_path.exists():
            try:
                wrapper_path.unlink()
                print(_c(GREEN, f"  ✓ removed CLI wrapper {wrapper_path.name}", color))
            except OSError as e:
                print(_c(YELLOW, f"  ⚠ could not remove {wrapper_path}: {e}", color))

    if mdc_path:
        mdc_p = Path(mdc_path)
        if mdc_p.exists():
            try:
                mdc_p.unlink()
                print(_c(GREEN, f"  ✓ removed user-level rules {mdc_p.name}", color))
            except OSError as e:
                print(_c(YELLOW, f"  ⚠ could not remove {mdc_p}: {e}", color))

    print()
    print(_c(GREEN, "  uninstall complete · restart Cursor for change to take effect", color))
    return 0


def cmd_check(target: Path, color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_install · check · {target}", color))
    print()
    if not target.exists():
        print(_c(RED, f"  ✕ target does not exist", color))
        return 1
    manifest = read_manifest(target)
    if not manifest:
        # Maybe hooks.json exists but not from us
        h = target / ".cursor" / "hooks.json"
        if h.exists():
            print(_c(YELLOW, "  ⚠ .cursor/hooks.json exists but no install manifest "
                            f"({INSTALL_MANIFEST_NAME})", color))
            print(_c(GRAY, f"     not installed by aether_install · won't touch it", color))
        else:
            print(_c(GRAY, "  · no Aether install detected", color))
        return 0
    print(_c(GREEN, f"  ✓ Aether installed · mode={manifest.get('mode')}", color))
    print(_c(GRAY, f"     installed_at: {manifest.get('installed_at')}", color))
    if manifest.get("mode") == "shared":
        central = manifest.get("central_aether")
        central_path = Path(central) if central else None
        if central_path and central_path.exists():
            print(_c(GREEN, f"     central aether: {central}", color))
        else:
            print(_c(RED, f"     ✕ BROKEN · central aether missing: {central}", color))
            print(_c(YELLOW, "     hooks will fail · re-install or remove .cursor/hooks.json", color))
    elif manifest.get("mode") == "copy":
        files = manifest.get("installed_files", [])
        print(_c(GRAY, f"     files installed: {len(files)}", color))
    h = target / ".cursor" / "hooks.json"
    if h.exists():
        print(_c(GREEN, f"     hooks.json present · {h.stat().st_size} bytes", color))
    else:
        print(_c(RED, "     ✕ hooks.json missing · install incomplete", color))
    return 0


def cmd_install(target: Path, mode: str, apply: bool, color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_install · {mode} mode · target={target}", color))
    print()

    ok, reason = validate_target(target)
    if not ok:
        print(_c(RED, f"  ✕ {reason}", color))
        return 2

    existing = read_manifest(target)
    if existing:
        print(_c(YELLOW, f"  ⚠ Aether already installed (mode={existing.get('mode')}) "
                        f"· will overwrite", color))

    cursor_dir = target / ".cursor"
    hooks_path = cursor_dir / "hooks.json"
    hooks_existing_text: str | None = None
    if hooks_path.exists():
        # utf-8-sig tolerates BOM (Windows Notepad / VSCode add it sometimes)
        hooks_existing_text = hooks_path.read_text(encoding="utf-8-sig")
        # Detect if it's our install (vs user's own hooks)
        try:
            j = json.loads(hooks_existing_text)
            if "_install_mode" in j:
                print(_c(GRAY, f"  · existing hooks.json is from us · will replace", color))
            else:
                print(_c(YELLOW, f"  ⚠ existing hooks.json is NOT from us · "
                               f"will back up to hooks.json.bak", color))
        except Exception:
            print(_c(YELLOW, f"  ⚠ existing hooks.json malformed · will back up", color))

    actions: list[str] = []
    if mode == "shared":
        actions.append(f"create {hooks_path.relative_to(target)} (shared mode · "
                       f"absolute paths to {WORKSPACE_ROOT})")
    elif mode == "copy":
        n = sum(1 for rel in COPY_INCLUDE if (ROOT / rel).exists())
        actions.append(f"copy aether/ subset → {target / 'aether'} ({n} top entries)")
        actions.append(f"create {hooks_path.relative_to(target)} (copy mode · relative paths)")
    actions.append(f"write {INSTALL_MANIFEST_NAME} (uninstall manifest)")
    if hooks_existing_text and "_install_mode" not in (hooks_existing_text or ""):
        actions.append(f"back up existing hooks.json → hooks.json.bak")

    for a in actions:
        print(_c(GRAY, f"  · would {a}", color))

    if not apply:
        print()
        print(_c(YELLOW, "  (dry-run · pass --apply to actually install)", color))
        return 0

    print()
    print(_c(BOLD, "applying...", color))

    cursor_dir.mkdir(parents=True, exist_ok=True)

    # Back up existing if foreign
    backup_name: str | None = None
    if hooks_existing_text and "_install_mode" not in hooks_existing_text:
        bak = hooks_path.with_suffix(".json.bak")
        if bak.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            bak = cursor_dir / f"hooks.json.bak.{stamp}"
        bak.write_text(hooks_existing_text, encoding="utf-8")
        backup_name = bak.name
        print(_c(GREEN, f"  ✓ backed up existing hooks.json → {backup_name}", color))

    files: list[str] = []
    if mode == "copy":
        dst_aether = target / "aether"
        copied = copy_subset(ROOT, dst_aether)
        files.extend(f"aether/{p}" for p in copied)
        print(_c(GREEN, f"  ✓ copied aether/ subset · {len(copied)} entries", color))
        # Write hooks.json (copy mode · relative paths)
        cfg = hooks_json_copy(target, sys.executable)
    else:
        cfg = hooks_json_shared(ROOT / "bin", sys.executable)

    hooks_path.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    files.append(".cursor/hooks.json")
    print(_c(GREEN, f"  ✓ wrote {hooks_path.relative_to(target)}", color))

    # Project-level mdc · belt-and-suspenders even when global mdc is set
    # IMPORTANT: central mdc lives at <WORKSPACE_ROOT>/.cursor/rules/aether.mdc
    # NOT under aether/ subdir · pass WORKSPACE_ROOT not ROOT.
    mdc_path = _install_mdc("project", WORKSPACE_ROOT, target, color)
    if mdc_path:
        files.append(".cursor/rules/aether.mdc")
        print(_c(GREEN, f"  ✓ wrote {mdc_path.relative_to(target)}", color))
        print(_c(GREEN, f"     RULE 00 + 5-mode now alwaysApply for this project", color))

    write_manifest(target, mode, files, backup_name)
    print(_c(GREEN, f"  ✓ wrote {INSTALL_MANIFEST_NAME}", color))

    print()
    print(_c(BOLD, "next steps · 真实测试:", color))
    print(_c(GRAY, "  1. 关闭并重启 Cursor (重新加载 hooks)", color))
    print(_c(GRAY, f"  2. 在 Cursor 里打开 {target}", color))
    print(_c(GRAY, "  3. 新建 chat · 输入 \"你好\"", color))
    print(_c(GRAY, "  4. AI 第一行应该贴 \"⟁ Aether · Day N/30 · ...\" 状态行", color))
    print(_c(GRAY, "  5. 如果没出 → 看 Cursor Settings → Hooks tab 的 OUTPUT log", color))
    print()
    print(_c(GRAY, f"  撤销: python {Path(__file__).relative_to(WORKSPACE_ROOT)} "
                   f"\"{target}\" --uninstall --apply", color))
    return 0


def cmd_uninstall(target: Path, apply: bool, color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_install · uninstall · target={target}", color))
    print()

    manifest = read_manifest(target)
    if not manifest:
        print(_c(YELLOW, f"  · no install manifest at {target} · nothing to uninstall", color))
        print(_c(GRAY, "    if you have a stray hooks.json, delete it manually", color))
        return 0

    mode = manifest.get("mode", "?")
    files = manifest.get("installed_files", [])
    backup = manifest.get("hooks_backup")

    actions: list[str] = []
    actions.append(f"remove .cursor/hooks.json")
    if mode == "copy":
        # Just remove target/aether/ if it was created by us
        actions.append(f"remove aether/ subtree ({len(files) - 1} files)")
    if backup:
        actions.append(f"restore .cursor/hooks.json from .cursor/{backup}")
    actions.append(f"remove {INSTALL_MANIFEST_NAME}")

    for a in actions:
        print(_c(GRAY, f"  · would {a}", color))

    if not apply:
        print()
        print(_c(YELLOW, "  (dry-run · pass --apply to actually uninstall)", color))
        return 0

    print()
    print(_c(BOLD, "applying...", color))

    hooks_path = target / ".cursor" / "hooks.json"
    if hooks_path.exists():
        hooks_path.unlink()
        print(_c(GREEN, "  ✓ removed .cursor/hooks.json", color))

    if mode == "copy":
        dst_aether = target / "aether"
        if dst_aether.exists():
            shutil.rmtree(dst_aether)
            print(_c(GREEN, f"  ✓ removed aether/ subtree", color))

    if backup:
        bak = target / ".cursor" / backup
        if bak.exists():
            bak.rename(hooks_path)
            print(_c(GREEN, f"  ✓ restored hooks.json from {backup}", color))

    manifest_path = target / INSTALL_MANIFEST_NAME
    if manifest_path.exists():
        manifest_path.unlink()
        print(_c(GREEN, f"  ✓ removed {INSTALL_MANIFEST_NAME}", color))

    print()
    print(_c(GREEN, "  uninstall complete · restart Cursor for hooks change to take effect", color))
    return 0


# ─── main ───────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Install Aether hooks · project (default) or --global (~/.cursor/) · "
                    "supports shared / copy / uninstall / check")
    ap.add_argument("target", nargs="?",
                    help="path to target project root (omit when using --global)")
    ap.add_argument("--global", dest="global_install", action="store_true",
                    help="install to ~/.cursor/hooks.json (USER scope · all projects)")
    mode_g = ap.add_mutually_exclusive_group()
    mode_g.add_argument("--copy", action="store_true",
                       help="copy aether/ subset into target (project scope only)")
    mode_g.add_argument("--uninstall", action="store_true",
                       help="remove our install from target (or --global)")
    mode_g.add_argument("--check", action="store_true",
                       help="report install status (target or --global)")
    ap.add_argument("--apply", action="store_true",
                    help="actually do it (default is dry-run)")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    color = not args.no_color and sys.stdout.isatty()

    if args.global_install:
        if args.copy:
            print(_c(RED, "✕ --global doesn't support --copy mode (always shared)", color))
            return 2
        if args.target:
            print(_c(YELLOW, f"⚠ --global ignores positional target ({args.target})", color))
        if args.check:
            return cmd_check_global(color)
        if args.uninstall:
            return cmd_uninstall_global(args.apply, color)
        return cmd_install_global(args.apply, color)

    if not args.target:
        print(_c(RED, "✕ either provide a target path or use --global", color))
        ap.print_help()
        return 2

    target = Path(args.target).expanduser().resolve()
    if args.check:
        return cmd_check(target, color)
    if args.uninstall:
        return cmd_uninstall(target, args.apply, color)
    mode = "copy" if args.copy else "shared"
    return cmd_install(target, mode, args.apply, color)


if __name__ == "__main__":
    sys.exit(main())
