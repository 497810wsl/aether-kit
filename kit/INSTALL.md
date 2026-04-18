# Install Aether Kit

30 seconds, zero dependencies, any OS with Python 3.8+.

---

## Prerequisites

- Python 3.8 or newer (`python3 --version`)
- Git
- A project where you want AI to behave consistently (Cursor / Claude Code recommended)

Nothing else. No Node. No Docker. No account.

---

## Install

### macOS / Linux

```bash
# Clone once to your home directory
git clone https://github.com/497810wsl/aether-kit ~/aether

# Wire it into any project
cd your-project/
~/aether/bin/aether init
```

### Windows (PowerShell)

```powershell
git clone https://github.com/497810wsl/aether-kit $HOME\aether

cd your-project
& "$HOME\aether\bin\aether.cmd" init
```

### Behind a firewall / slow GitHub?

Use a proxy or Gitee mirror. Set `core_repo` in `.aether/config.json`:

```json
{
  "core_repo": "https://ghproxy.com/https://raw.githubusercontent.com/497810wsl/aether-kit/main"
}
```

---

## What `aether init` does

1. Creates `.aether/` in your project (`.aether/fields/`, `.aether/config.json`)
2. Writes `.cursor/rules/aether.mdc` — tells Cursor how to read fields on activation
3. Fetches 3 starter fields: `linus-torvalds`, `engineering-rigor`, `jony-ive`
4. Prints next steps

Existing `.cursorrules` is left alone. The new file is separate.

---

## First use

Open Cursor (or Claude Code · or any LLM tool that reads `.cursor/rules/*.mdc`). In a chat, paste one line from a preset file:

```
activate linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2
```

Then ask your question. AI responds in that profile.

Try the `code-reviewer` preset first — it's the easiest to tell apart from default AI output.

---

## Fetch more fields

```bash
~/aether/bin/aether fetch nolan          # cinematic / time-gradient style
~/aether/bin/aether fetch brainstorm     # divergent / 10+ ideas mode
~/aether/bin/aether fetch deep-thinking  # recursive why · question premises
~/aether/bin/aether fetch research       # fact-backed · source-cited
~/aether/bin/aether fetch code-generator # style-matching code output
~/aether/bin/aether fetch cold-to-warm   # tone dial
```

All 9 starter fields are MIT. Listed in [README.md](./README.md#what-you-get).

---

## Troubleshooting

### Symptom 1 · `aether: command not found`

You didn't clone into `~/aether`. Either use the full path to the script:

```bash
python3 /full/path/to/aether-kit/bin/aether.py init
```

Or add to your shell rc:

```bash
alias aether="python3 ~/aether/bin/aether.py"
```

### Symptom 2 · `aether fetch` fails with "Network error"

You're behind a firewall. See "Behind a firewall" section above.

### Symptom 3 · Cursor doesn't react to `activate linus=0.9`

Check `.cursor/rules/aether.mdc` exists in your project root. If not, `aether init` wasn't run from the project root. Run it again from the right directory.

### Symptom 4 · AI just says "ok, I understand" but output looks the same

1. Open a new chat (existing context may override the rule)
2. Raise the weight: `activate linus=0.9` (not 0.3)
3. Verify with `python tools/fingerprint.py before.txt after.txt` — if the math distance is > 0.3, the field did fire; the issue is your expectation of how visible the shift is.

### Still stuck?

Open an issue: [github.com/497810wsl/aether-kit/issues](https://github.com/497810wsl/aether-kit/issues)

---

## Uninstall

The kit is fully local. To remove from a project:

```bash
rm -rf your-project/.aether
rm your-project/.cursor/rules/aether.mdc
```

To remove the kit itself:

```bash
rm -rf ~/aether
```

Starter fields, your activation history, and any AI output you produced stay yours forever.
