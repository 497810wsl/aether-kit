#!/usr/bin/env python3
"""
aether_stats.py — 聚合真实可公开的 Aether 运营数据

数据来源(全部真实 · 不编造):
- GitHub API: stars / forks / watchers / issues (公开 · 不需 token)
- 本地 Aether 状态: coll 数 / species 数 / seed 数 / 场数(读文件)
- nginx log(可选 · 服务器侧): PV / UV / top pages

输出: site/public/stats.json(前端 LiveStats 组件 fetch)

用法:
    python bin/aether_stats.py
    python bin/aether_stats.py --repo 497810wsl/aether
    python bin/aether_stats.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_PUBLIC = ROOT / "site" / "public"
OUTPUT_PATH = SITE_PUBLIC / "stats.json"

DEFAULT_REPO = "497810wsl/aether-kit"
GITHUB_API = "https://api.github.com/repos"
USER_AGENT = "aether-stats-bot/0.1"


def fetch_github_repo(repo: str) -> dict:
    """Fetch public repo info. No auth needed (rate-limited to 60/hr by IP)."""
    url = f"{GITHUB_API}/{repo}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[warn] github API HTTP {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 404:
            return {"_error": "repo-not-found"}
        if e.code == 403:
            return {"_error": "rate-limit"}
        return {"_error": f"http-{e.code}"}
    except Exception as e:
        print(f"[warn] github fetch failed: {e}", file=sys.stderr)
        return {"_error": str(e)}


def fetch_github_releases(repo: str) -> list[dict]:
    url = f"{GITHUB_API}/{repo}/releases"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []


def count_collapses() -> int:
    """Count all coll-*.md across hot + cold archive."""
    n = 0
    hot = ROOT / "gen6-noesis" / "collapse-events"
    if hot.exists():
        n += len(list(hot.glob("coll-*.md")))
    archive = ROOT / "gen6-noesis" / "archive"
    if archive.exists():
        for q in archive.iterdir():
            if q.is_dir():
                n += len(list(q.glob("coll-*.md")))
    return n


def count_species() -> int:
    reg = ROOT / "gen5-ecoware" / "species-registry.json"
    if not reg.exists():
        return 0
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
        species = data.get("species", {})
        return len([k for k in species if not k.startswith("_")])
    except (json.JSONDecodeError, OSError):
        return 0


def count_seeds() -> int:
    nursery = ROOT / "gen5-ecoware" / "nursery"
    if not nursery.exists():
        return 0
    return len(list(nursery.glob("*.seed.md")))


def count_fields() -> int:
    fields = ROOT / "gen4-morphogen" / "fields"
    if not fields.exists():
        return 0
    return len(list(fields.rglob("*.field.md")))


def count_cli_tools() -> int:
    bin_dir = ROOT / "bin"
    if not bin_dir.exists():
        return 0
    return len([p for p in bin_dir.glob("*.py") if p.stem.startswith(("aether", "aether_"))])


def read_generation() -> int:
    reg = ROOT / "gen5-ecoware" / "species-registry.json"
    if not reg.exists():
        return 0
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
        return int(data.get("generation", 0))
    except (json.JSONDecodeError, OSError, ValueError):
        return 0


def build_stats(repo: str) -> dict:
    print(f"→ fetching GitHub data for {repo}...", file=sys.stderr)
    gh = fetch_github_repo(repo)
    releases = fetch_github_releases(repo)

    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "github": {
            "stars": gh.get("stargazers_count", 0),
            "forks": gh.get("forks_count", 0),
            "watchers": gh.get("subscribers_count", 0),
            "open_issues": gh.get("open_issues_count", 0),
            "releases": len(releases),
            "latest_release": releases[0]["tag_name"] if releases else None,
            "updated_at": gh.get("updated_at"),
            "error": gh.get("_error"),
        },
        "aether": {
            # Day 13 form α · gen5-7 archived · species/generation/seeds_ripening
            # would render as 0 from non-existent registry · misleading on the
            # public site. Dropped from schema. count_species/count_seeds/
            # read_generation helpers kept in this file but no longer published.
            "collapses": count_collapses(),
            "fields": count_fields(),
            "cli_tools": count_cli_tools(),
            "scope": "dev-self",
        },
    }
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether stats aggregator")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/repo")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = ap.parse_args()

    stats = build_stats(args.repo)

    output = json.dumps(stats, ensure_ascii=False, indent=2)
    print(output)

    if args.dry_run:
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"\n✓ wrote {args.output.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
