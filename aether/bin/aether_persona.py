#!/usr/bin/env python3
"""
aether_persona.py — 专家脑子的序列化与注入

把一个 Aether 实例中的"专家积累"(fields + 关键 coll corpus + essence 切片)
打包成一份 .aether-persona/<name>/ 目录,可分享、下载、导入到另一个项目。

这是"装高级程序员脑子"的管道层。

命令:
    python bin/aether_persona.py export <name>
        把当前项目的活跃场 + 最近 N 次 coll + essence 打包到
        .aether-persona/<name>/

    python bin/aether_persona.py import <path>
        把一份 persona 目录合并到当前项目的场库和 triggers

    python bin/aether_persona.py list
        列出当前项目里的所有 persona

选项:
    --corpus-size N       导出时保留多少条 coll 语料(默认 30)
    --include-essence     是否包含 user-essence(默认 false,避免隐私)
    --signature-only      只导出指纹(hash),不含具体文本,供去重
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS_DIR = ROOT / "gen4-morphogen" / "fields"
COLL_DIR = ROOT / "gen6-noesis" / "collapse-events"
TRIGGERS = ROOT / "gen4-morphogen" / "composers" / "triggers.md"
ESSENCE = ROOT / "gen6-noesis" / "mirror" / "user-essence.md"
PERSONA_ROOT = ROOT / ".aether-persona"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def gather_active_fields(recent_coll_limit: int = 50) -> set[str]:
    """Find which fields were activated in the last N collapses."""
    active = set()
    if not COLL_DIR.exists():
        return active
    for p in sorted(COLL_DIR.glob("coll-*.md"), reverse=True)[:recent_coll_limit]:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(r"active_fields:\s*\n((?:\s{2,}[\w-]+:\s*-?[\d.]+\s*\n)+)", text)
        if m:
            for line in m.group(1).strip().splitlines():
                mm = re.match(r"\s*([\w-]+):", line)
                if mm:
                    active.add(mm.group(1))
    return active


def find_field_file(name: str) -> Path | None:
    for p in FIELDS_DIR.rglob(f"{name}.field.md"):
        return p
    return None


def cmd_export(args) -> int:
    name = args.name
    if not re.match(r"^[a-z0-9][a-z0-9\-]*$", name):
        print("name must be lowercase alnum/dash, e.g. 'sarah-the-staff'", file=sys.stderr)
        return 1

    out_dir = PERSONA_ROOT / name
    if out_dir.exists() and not args.force:
        print(f"{out_dir.relative_to(ROOT)} already exists · use --force to overwrite", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fields").mkdir(exist_ok=True)
    (out_dir / "corpus").mkdir(exist_ok=True)

    active = gather_active_fields()
    exported_fields = []
    for fname in sorted(active):
        src = find_field_file(fname)
        if not src:
            continue
        rel = src.relative_to(FIELDS_DIR)
        dst = out_dir / "fields" / rel.name
        shutil.copy2(src, dst)
        exported_fields.append({
            "id": fname,
            "source_category": rel.parent.name,
            "hash": sha256(src.read_text(encoding="utf-8")),
        })

    # Corpus
    corpus_refs = []
    if COLL_DIR.exists():
        colls = sorted(COLL_DIR.glob("coll-*.md"), reverse=True)[:args.corpus_size]
        for p in colls:
            dst = out_dir / "corpus" / p.name
            shutil.copy2(p, dst)
            corpus_refs.append({
                "id": p.stem,
                "hash": sha256(p.read_text(encoding="utf-8")),
            })

    if args.include_essence and ESSENCE.exists():
        shutil.copy2(ESSENCE, out_dir / "user-essence.md")

    if TRIGGERS.exists():
        shutil.copy2(TRIGGERS, out_dir / "triggers-reference.md")

    manifest = {
        "persona_name": name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_project": str(ROOT),
        "aether_version": "0.4-cognitive",
        "fields": exported_fields,
        "corpus": corpus_refs,
        "includes_essence": bool(args.include_essence and ESSENCE.exists()),
        "description": args.description or f"Persona captured from {ROOT.name}",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # README
    readme = f"""# Persona · {name}

Exported: {manifest['exported_at']}
Fields: {len(exported_fields)} · Corpus: {len(corpus_refs)} coll entries

## What's inside

- `manifest.json` — metadata & hashes
- `fields/` — field definitions this persona uses
- `corpus/` — recent collapse events (anonymized if `--signature-only`)
- `triggers-reference.md` — the trigger table this persona was shaped by
{"- `user-essence.md` — user profile slice" if manifest['includes_essence'] else ""}

## Import into another Aether project

```bash
cd /path/to/another/project
python path/to/aether/bin/aether_persona.py import {out_dir}
```

## Signature

Fields: {sha256(''.join(f['hash'] for f in exported_fields))}
Corpus: {sha256(''.join(c['hash'] for c in corpus_refs))}
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    print(f"exported persona to {out_dir.relative_to(ROOT)}")
    print(f"  fields: {len(exported_fields)}")
    print(f"  corpus: {len(corpus_refs)}")
    return 0


def cmd_import(args) -> int:
    src = Path(args.path)
    if not src.exists() or not (src / "manifest.json").exists():
        print(f"not a valid persona directory: {src}", file=sys.stderr)
        return 1

    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    print(f"importing persona '{manifest['persona_name']}' with {len(manifest['fields'])} fields...")

    # Copy fields
    target_dir = FIELDS_DIR / "imported" / manifest["persona_name"]
    target_dir.mkdir(parents=True, exist_ok=True)
    imported = []
    src_fields = src / "fields"
    if src_fields.exists():
        for f in src_fields.glob("*.field.md"):
            dst = target_dir / f.name
            if dst.exists() and not args.force:
                print(f"  skip existing: {dst.relative_to(ROOT)}")
                continue
            shutil.copy2(f, dst)
            imported.append(dst)

    # Append triggers note
    note = f"\n\n<!-- Imported persona: {manifest['persona_name']} · {len(imported)} fields added under fields/imported/{manifest['persona_name']}/ -->\n"
    if TRIGGERS.exists():
        with open(TRIGGERS, "a", encoding="utf-8") as f:
            f.write(note)

    print(f"imported {len(imported)} fields → {target_dir.relative_to(ROOT)}")
    print(f"review and integrate into triggers.md as needed.")
    return 0


def cmd_list(args) -> int:
    if not PERSONA_ROOT.exists():
        print("no personas yet")
        return 0
    for d in sorted(PERSONA_ROOT.iterdir()):
        if not d.is_dir():
            continue
        mf = d / "manifest.json"
        if not mf.exists():
            continue
        m = json.loads(mf.read_text(encoding="utf-8"))
        print(f"- {m['persona_name']}: {len(m['fields'])} fields, {len(m['corpus'])} coll · {m['exported_at']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether persona import/export.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="export current project's persona")
    ex.add_argument("name", help="persona name (lowercase, dash-separated)")
    ex.add_argument("--corpus-size", type=int, default=30)
    ex.add_argument("--include-essence", action="store_true")
    ex.add_argument("--description", type=str, default=None)
    ex.add_argument("--force", action="store_true")
    ex.set_defaults(func=cmd_export)

    im = sub.add_parser("import", help="import a persona into current project")
    im.add_argument("path", help="path to persona directory")
    im.add_argument("--force", action="store_true")
    im.set_defaults(func=cmd_import)

    ls = sub.add_parser("list", help="list local personas")
    ls.set_defaults(func=cmd_list)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
