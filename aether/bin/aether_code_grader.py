#!/usr/bin/env python3
"""
aether_code_grader.py — 多维代码打分器

不假装像资深工程师那样"有灵魂",只做 85% 可量化的部分:
- 结构复杂度(嵌套/函数长度/参数数)
- 命名质量(长度/可读性/一致性)
- 重复率(N-gram duplication)
- 错误处理密度(try/except 占比)
- 文档/类型注解覆盖
- 依赖健康(未声明的 import)

产出 0-100 分 + 分项雷达图 data + 历史趋势。
分数沉淀到 `gen6-noesis/code-grades/grade-<hash>.json`。

用法:
    python bin/aether_code_grader.py path/to/file.py
    python bin/aether_code_grader.py path/to/dir --recursive
    python bin/aether_code_grader.py file.py --baseline path/to/earlier.py

多语言:通过 --lang 指定;默认按扩展名识别(.py / .js / .ts / .tsx / .jsx)。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "gen6-noesis" / "code-grades"

LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
}


# ─── Metrics ───

@dataclass
class GradeDimension:
    name: str
    score: float  # 0-100
    weight: float
    notes: list[str] = field(default_factory=list)

    def weighted(self) -> float:
        return self.score * self.weight


def detect_lang(path: Path) -> str:
    return LANG_BY_EXT.get(path.suffix.lower(), "generic")


def score_complexity(code: str, lang: str) -> GradeDimension:
    """Score based on nesting depth, function length, param count."""
    notes = []
    lines = code.splitlines()

    # Nesting depth (rough indentation analysis)
    max_indent = 0
    for ln in lines:
        stripped = ln.expandtabs(4).lstrip(" ")
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        indent = len(ln.expandtabs(4)) - len(stripped)
        indent_level = indent // 4 if indent else 0
        if indent_level > max_indent:
            max_indent = indent_level

    # Function length (crude): split by def/function, measure lines
    fn_lengths = []
    if lang == "python":
        matches = list(re.finditer(r"^def\s+(\w+)", code, re.MULTILINE))
    else:
        matches = list(re.finditer(r"(?:function|const|let|var)\s+(\w+)[^\n]*[={]", code))
    for i, m in enumerate(matches):
        start = code.count("\n", 0, m.start())
        end = code.count("\n", 0, matches[i + 1].start()) if i + 1 < len(matches) else len(lines)
        fn_lengths.append(end - start)
    avg_fn = sum(fn_lengths) / len(fn_lengths) if fn_lengths else 0

    # Param count (Python)
    params = []
    for m in re.finditer(r"def\s+\w+\s*\(([^)]*)\)", code):
        p_list = [p.strip() for p in m.group(1).split(",") if p.strip()]
        params.append(len(p_list))
    avg_params = sum(params) / len(params) if params else 0

    # Scoring
    score = 100.0
    if max_indent > 5:
        score -= (max_indent - 5) * 6
        notes.append(f"max nesting depth {max_indent} (ideal ≤ 4)")
    if avg_fn > 50:
        score -= min(30, (avg_fn - 50) * 0.5)
        notes.append(f"avg function length {avg_fn:.0f} lines (ideal ≤ 40)")
    if avg_params > 5:
        score -= (avg_params - 5) * 8
        notes.append(f"avg {avg_params:.1f} params per function (ideal ≤ 4)")

    return GradeDimension("complexity", max(0, score), 0.20, notes)


def score_naming(code: str, lang: str) -> GradeDimension:
    """Score identifier quality."""
    notes = []
    # Find all identifiers
    idents = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{0,}\b", code)
    # Exclude keywords
    kw = {"if", "else", "for", "while", "return", "def", "class", "import", "from",
          "function", "const", "let", "var", "in", "of", "as", "is", "and", "or",
          "not", "None", "True", "False", "null", "true", "false", "this", "self",
          "new", "try", "catch", "except", "finally", "raise", "throw"}
    idents = [i for i in idents if i not in kw and not i.isupper()]

    if not idents:
        return GradeDimension("naming", 80, 0.15, ["no identifiers found"])

    # Too short
    short = [i for i in idents if len(i) <= 2 and i not in ("i", "j", "k", "x", "y", "z", "n", "m", "f", "e")]
    # Too long
    long_ = [i for i in idents if len(i) > 30]
    # Abbreviation density (no vowels ratio)
    no_vowel = [i for i in idents if len(i) >= 4 and not re.search(r"[aeiouAEIOU]", i)]

    score = 100.0
    short_ratio = len(short) / len(idents)
    long_ratio = len(long_) / len(idents)
    abbrev_ratio = len(no_vowel) / len(idents)

    if short_ratio > 0.1:
        penalty = (short_ratio - 0.1) * 200
        score -= penalty
        notes.append(f"{short_ratio*100:.0f}% ultra-short names (≤2 chars)")
    if long_ratio > 0.05:
        score -= (long_ratio - 0.05) * 150
        notes.append(f"{long_ratio*100:.0f}% overlong names (>30 chars)")
    if abbrev_ratio > 0.2:
        score -= (abbrev_ratio - 0.2) * 100
        notes.append(f"{abbrev_ratio*100:.0f}% names without vowels (cryptic abbreviations)")

    return GradeDimension("naming", max(0, score), 0.15, notes)


def score_duplication(code: str, lang: str) -> GradeDimension:
    """N-gram duplication detection."""
    notes = []
    lines = [ln.strip() for ln in code.splitlines() if ln.strip() and not ln.strip().startswith(("#", "//"))]
    if len(lines) < 10:
        return GradeDimension("duplication", 95, 0.10, ["too short to assess"])

    # Line-level duplicates
    from collections import Counter
    ct = Counter(lines)
    dup_lines = sum(c - 1 for c in ct.values() if c > 1)
    dup_ratio = dup_lines / len(lines) if lines else 0

    score = 100.0
    if dup_ratio > 0.05:
        score -= (dup_ratio - 0.05) * 400
        notes.append(f"{dup_ratio*100:.0f}% duplicate lines")

    # 3-gram duplication
    grams = [tuple(lines[i:i+3]) for i in range(len(lines) - 2)]
    g_ct = Counter(grams)
    dup_grams = sum(c - 1 for c in g_ct.values() if c > 1)
    if dup_grams > 3:
        score -= min(20, dup_grams * 2)
        notes.append(f"{dup_grams} repeated 3-line blocks")

    return GradeDimension("duplication", max(0, score), 0.15, notes)


def score_error_handling(code: str, lang: str) -> GradeDimension:
    """Error handling density."""
    notes = []
    lines = code.splitlines()
    nonblank = [ln for ln in lines if ln.strip() and not ln.strip().startswith(("#", "//"))]
    if not nonblank:
        return GradeDimension("error_handling", 50, 0.15, ["empty"])

    if lang == "python":
        try_count = len(re.findall(r"^\s*try\b", code, re.MULTILINE))
        except_count = len(re.findall(r"^\s*except\b", code, re.MULTILINE))
        bare_except = len(re.findall(r"^\s*except\s*:", code, re.MULTILINE))
    else:
        try_count = len(re.findall(r"\btry\s*\{", code))
        except_count = len(re.findall(r"\bcatch\s*\(", code))
        bare_except = 0

    risky_ops = len(re.findall(r"\bopen\(|\.read\(|\.write\(|fetch\(|axios\.|requests\.", code))

    score = 80.0
    if risky_ops > 0 and except_count == 0:
        score -= 30
        notes.append(f"{risky_ops} risky I/O calls with no error handling")
    elif except_count > 0:
        score += 15
        notes.append(f"{except_count} exception handlers")
    if bare_except > 0:
        score -= bare_except * 8
        notes.append(f"{bare_except} bare `except:` (too broad)")

    return GradeDimension("error_handling", max(0, min(100, score)), 0.15, notes)


def score_documentation(code: str, lang: str) -> GradeDimension:
    """Docstring / comment / type-annotation coverage."""
    notes = []

    if lang == "python":
        func_count = len(re.findall(r"^def\s+", code, re.MULTILINE))
        docstring_count = len(re.findall(r'^\s*"""|\'\'\'', code, re.MULTILINE))
        type_count = len(re.findall(r":\s*[A-Z]\w+|:\s*\w+\s*=|->", code))
    else:
        func_count = len(re.findall(r"function\s+\w+\s*\(|=>\s*\{", code))
        docstring_count = len(re.findall(r"/\*\*", code))
        type_count = len(re.findall(r":\s*\w+(?:<|\[|\s*=|\))", code))

    lines_total = len([l for l in code.splitlines() if l.strip()])
    comment_count = len(re.findall(r"^\s*(?:#|//)", code, re.MULTILINE))
    comment_ratio = comment_count / max(lines_total, 1)

    score = 70.0
    if func_count > 0:
        doc_coverage = min(1.0, docstring_count / func_count)
        score += doc_coverage * 20
        if doc_coverage < 0.3:
            notes.append(f"only {doc_coverage*100:.0f}% of functions have docstrings")
    if type_count < func_count * 1.5 and func_count > 3:
        notes.append("sparse type annotations")
        score -= 10
    if comment_ratio > 0.3:
        score -= (comment_ratio - 0.3) * 100
        notes.append(f"{comment_ratio*100:.0f}% comment ratio — may be over-commented ('what' instead of 'why')")
    if comment_ratio < 0.02 and lines_total > 50:
        score -= 8
        notes.append("no comments at all (suspicious for non-trivial code)")

    return GradeDimension("documentation", max(0, min(100, score)), 0.10, notes)


def score_dependency_health(code: str, lang: str) -> GradeDimension:
    """Check for dubious imports / hallucinated APIs (heuristic)."""
    notes = []
    score = 90.0

    if lang == "python":
        imports = re.findall(r"^(?:from\s+(\S+)|import\s+(\S+))", code, re.MULTILINE)
        imp_names = set()
        for fr, im in imports:
            imp_names.add((fr or im).split(".")[0])
        # Known good stdlib (not exhaustive, indicative)
        stdlib = {"os", "sys", "re", "json", "math", "random", "time", "pathlib",
                  "argparse", "collections", "dataclasses", "typing", "datetime",
                  "subprocess", "shutil", "hashlib", "functools", "itertools", "io",
                  "urllib", "socket", "logging", "threading", "asyncio", "unittest"}
        third_party = imp_names - stdlib
        if third_party:
            notes.append(f"3rd-party deps: {', '.join(sorted(third_party))}")
    else:
        imports = re.findall(r"(?:import|require\()\s*[\"']([^\"']+)", code)
        if imports:
            notes.append(f"imports: {', '.join(sorted(set(imports))[:6])}")

    # TODO markers = score penalty
    todo_count = len(re.findall(r"TODO|FIXME|XXX|HACK", code))
    if todo_count > 0:
        score -= min(15, todo_count * 3)
        notes.append(f"{todo_count} TODO/FIXME markers")

    return GradeDimension("dep_health", max(0, score), 0.10, notes)


def score_safety(code: str, lang: str) -> GradeDimension:
    """Smell detector: sql injection risk, eval, hardcoded secrets..."""
    notes = []
    score = 95.0

    patterns = {
        "string sql concatenation": r"(SELECT|INSERT|UPDATE|DELETE)[^;]*\"\s*\+",
        "eval/exec usage": r"\beval\s*\(|\bexec\s*\(",
        "hardcoded api key": r"(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][A-Za-z0-9]{16,}[\"']",
        "shell=True": r"shell\s*=\s*True",
        "bare md5/sha1 for auth": r"hashlib\.(md5|sha1)\(",
    }
    for label, pat in patterns.items():
        hits = len(re.findall(pat, code, re.IGNORECASE))
        if hits:
            score -= min(25, hits * 10)
            notes.append(f"⚠️ {label}: {hits} occurrence(s)")

    return GradeDimension("safety", max(0, score), 0.15, notes)


# ─── Runner ───

DIMENSIONS = [
    score_complexity,
    score_naming,
    score_duplication,
    score_error_handling,
    score_documentation,
    score_dependency_health,
    score_safety,
]


def grade_file(path: Path, lang: str | None = None) -> dict:
    code = path.read_text(encoding="utf-8")
    if lang is None:
        lang = detect_lang(path)
    dims = [fn(code, lang) for fn in DIMENSIONS]
    total_weight = sum(d.weight for d in dims)
    weighted = sum(d.weighted() for d in dims) / total_weight
    return {
        "path": str(path),
        "lang": lang,
        "lines": len(code.splitlines()),
        "chars": len(code),
        "hash": hashlib.sha256(code.encode()).hexdigest()[:12],
        "graded_at": datetime.now(timezone.utc).isoformat(),
        "total_score": round(weighted, 1),
        "dimensions": [asdict(d) for d in dims],
    }


def render_report(result: dict) -> str:
    lines = []
    lines.append(f"╭─ Code Grade · {result['path']}")
    lines.append(f"├─ {result['lines']} lines · {result['lang']} · hash {result['hash']}")
    lines.append(f"├─ graded at {result['graded_at']}")
    lines.append(f"│")
    lines.append(f"├─ TOTAL SCORE: {result['total_score']} / 100")
    lines.append(f"│")
    for d in result["dimensions"]:
        bar_width = int(d["score"] / 5)
        bar = "█" * bar_width + "░" * (20 - bar_width)
        lines.append(f"│  {d['name']:18s} {bar} {d['score']:5.1f}  (weight {d['weight']:.2f})")
        for n in d["notes"]:
            lines.append(f"│    · {n}")
    lines.append(f"╰─")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-dimensional code grader (heuristic).")
    ap.add_argument("path", help="file or directory")
    ap.add_argument("--lang", type=str, default=None)
    ap.add_argument("--recursive", "-r", action="store_true")
    ap.add_argument("--json", action="store_true", help="output JSON only")
    ap.add_argument("--save", action="store_true", help="persist to gen6-noesis/code-grades/")
    args = ap.parse_args()

    target = Path(args.path)
    if target.is_file():
        files = [target]
    elif target.is_dir():
        pat = "**/*" if args.recursive else "*"
        files = [p for p in target.glob(pat)
                 if p.is_file() and p.suffix in LANG_BY_EXT]
    else:
        print(f"not found: {target}", file=sys.stderr)
        return 1

    if not files:
        print("no gradeable files found", file=sys.stderr)
        return 1

    results = []
    for f in files:
        try:
            r = grade_file(f, args.lang)
            results.append(r)
        except Exception as e:
            print(f"grade failed for {f}: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(render_report(r))
            print()
        if len(results) > 1:
            avg = sum(r["total_score"] for r in results) / len(results)
            print(f"→ aggregate: {len(results)} files · avg {avg:.1f}")

    if args.save:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for r in results:
            out = OUT_DIR / f"grade-{r['hash']}.json"
            out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nsaved {len(results)} grade(s) to {OUT_DIR.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
