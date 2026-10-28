#!/usr/bin/env python3
"""Convert out/answers.json into the generic gaps file egeo's `fix-gaps` reads.

egeo (PyPI package from mverab/eGEOagents, MIT) documents a generic gaps file as "a JSON array or CSV
with `query` and `cited`", plus an optional `sources` list of the URLs an engine cited instead of you
(egeoagents.com/docs/cli, egeo fix-gaps). We write exactly those three keys, one row per buyer question:
  {"query": "...", "cited": false, "sources": ["https://..."]}
`cited` is true if any assistant named her for that question, matching the receipt. `sources` holds the
links found in the answers that did not name her, and is left out when there are none.

fix-gaps also needs her own project.yaml (egeo's examples/project.yaml shows the shape) whose
queries[].text match these queries and whose pages point at her page files. We do not write that file.

Usage: python3 solutions/to_gaps.py out/answers.json --out out/gaps.json [--name "Her Brand"]
Then, only if egeo is installed:  egeo fix-gaps out/gaps.json --project project.yaml --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import recommend  # noqa: E402

URL = re.compile(r"https?://[^\s)\]>\"'<,]+")


def to_gaps(meta: dict, answers: list[dict], name: str | None = None) -> list[dict]:
    name = name or meta.get("name") or ""
    if not name:
        raise ValueError("I need her brand name (meta.name in answers.json, or --name).")
    result = recommend.score(answers, name, list(meta.get("aliases") or []),
                             [meta.get("location") or "", meta.get("niche") or ""])
    rows = []
    for q in result["questions"]:
        urls: list[str] = []
        for r in result["rows"]:
            if r["question"].lower() == q["question"].lower() and not r["you_named"]:
                for u in URL.findall(r["answer"]):
                    u = u.rstrip(".;:")
                    if u not in urls:
                        urls.append(u)
        row = {"query": q["question"], "cited": bool(q["you_named"])}
        if urls and not q["you_named"]:
            row["sources"] = urls
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="answers.json -> egeo generic gaps.json")
    ap.add_argument("answers", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/gaps.json"))
    ap.add_argument("--name")
    args = ap.parse_args(argv)
    try:
        meta, answers = recommend.load_answers(args.answers)
        rows = to_gaps(meta, answers, args.name)
    except (OSError, ValueError) as exc:
        print(f"Could not convert {args.answers}: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    lost = sum(1 for r in rows if not r["cited"])
    print(f"gaps.json: {args.out} ({lost} of {len(rows)} questions are gaps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
