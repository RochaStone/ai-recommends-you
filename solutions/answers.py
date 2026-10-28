#!/usr/bin/env python3
"""Fix 2: a direct answer, in her words, for every question she lost on the receipt.

Reads the lost questions from out/summary.json (or scores out/answers.json) and her interview from
out/entity.json. Writes, per lost question:
  out/answers/<slug>.md       the answer, buyer's words as the heading, her name in the first sentence,
                              with its FAQPage JSON-LD block at the bottom (paste-ready)
and once:
  out/answers/faq.json        one FAQPage JSON-LD for all of them
  out/answers/index.html      every answer on one page, in her motif

If she wrote an answer in the interview (entity.json "answers"), it is used word for word. If not, a draft
is built only from facts she gave, marked DRAFT, for her to read aloud and make hers.

If egeo is installed (`pip install egeo`, MIT, mverab/eGEOagents), each answer also runs through
`egeo optimize` and its report is kept in out/answers/egeo/<slug>/. Without egeo nothing changes.

Usage: python3 solutions/answers.py out/summary.json out/entity.json --out out/ [--motif ...] [--style ...] [--no-egeo]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from receipt_render import MOTIFS  # noqa: E402
from solutions.common import (EntityError, egeo_path, faq_page, ld_script, load_entity, lost_questions,  # noqa: E402
                              one_line, run_egeo, slugify)
from solutions.page_render import e, get_style, render_page  # noqa: E402

DRAFT_NOTE = "DRAFT from your interview. Read it aloud and change any word that is not yours."


def answer_for(question: str, ent: dict) -> tuple[str, bool]:
    """(answer text, is_draft). Her own words win; a draft uses only facts she gave."""
    for q, a in ent["answers"].items():
        if q.lower() == question.lower():
            return a, False
    parts = [one_line(ent)]
    if ent["offer"]:
        parts.append(f"{ent['name']} offers {ent['offer'].rstrip('.')}.")
    if ent["proof"]:
        parts.append(ent["proof"][0].rstrip(".") + ".")
    if ent["work_with"]:
        parts.append(ent["work_with"].rstrip(".") + ".")
    return " ".join(parts), True


def answer_md(question: str, text: str, draft: bool) -> str:
    block = ld_script({"@context": "https://schema.org", **faq_page([{"q": question, "a": text}])})
    note = f"> {DRAFT_NOTE}\n\n" if draft else ""
    return f"# {question}\n\n{note}{text}\n\n<!-- paste the block below into your page's custom code -->\n{block}\n"


def build(lost: list[str], ent: dict, out: Path, style: dict, motif: str | None, date: str,
          use_egeo: bool = True) -> dict:
    folder = out / "answers"
    folder.mkdir(parents=True, exist_ok=True)
    items, used = [], set()
    for q in lost:
        slug = slugify(q)
        base, i = slug, 2
        while slug in used:
            slug, i = f"{base}-{i}", i + 1
        used.add(slug)
        text, draft = answer_for(q, ent)
        path = folder / f"{slug}.md"
        path.write_text(answer_md(q, text, draft), encoding="utf-8")
        items.append({"question": q, "slug": slug, "answer": text, "draft": draft, "file": path.name})
    faq = {"@context": "https://schema.org", **faq_page([{"q": x["question"], "a": x["answer"]} for x in items])}
    (folder / "faq.json").write_text(json.dumps(faq, indent=2, ensure_ascii=False), encoding="utf-8")
    body = f"<h1>Questions about {e(ent['name'])}</h1>" + "".join(
        f'<h2 id="{e(x["slug"])}">{e(x["question"])}</h2>'
        + (f'<p class="kicker">{e(DRAFT_NOTE)}</p>' if x["draft"] else "")
        + f'<p class="answer">{e(x["answer"])}</p>' for x in items)
    page = render_page(f"{ent['name']} FAQ", body, style=style, motif=motif, jsonld=ld_script(faq),
                       window="faq.exe", sidebar=[("about me", one_line(ent))], date=date,
                       credit=f"{ent['name']} · made with Rocha Coded")
    (folder / "index.html").write_text(page, encoding="utf-8")

    egeo_notes = []
    if use_egeo and egeo_path() and items:
        for x in items:
            ok, msg = run_egeo(["optimize", str(folder / x["file"]), "--out-dir",
                                str(folder / "egeo" / x["slug"]), "--schema-type", "FAQPage",
                                "--query", x["question"]])
            egeo_notes.append({"slug": x["slug"], "ok": ok, "message": msg[-400:]})
            if not ok:
                break  # the same reason will stop every one; say it once
        (folder / "egeo-report.json").write_text(json.dumps(egeo_notes, indent=2), encoding="utf-8")
    return {"items": items, "egeo": egeo_notes, "folder": folder}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write a direct answer for every lost question")
    ap.add_argument("summary", type=Path, help="out/summary.json (or out/answers.json)")
    ap.add_argument("entity", type=Path, help="out/entity.json from the interview")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--motif", choices=MOTIFS)
    ap.add_argument("--style", type=Path)
    ap.add_argument("--no-egeo", action="store_true", help="skip egeo even if it is installed")
    args = ap.parse_args(argv)
    try:
        ent = load_entity(args.entity)
        lost = lost_questions(args.summary)
    except (EntityError, OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    if not lost:
        print("You were named on every question. Nothing lost, so no answers to write. Keep publishing.")
        return 0
    res = build(lost, ent, args.out, get_style(args.style), args.motif, dt.date.today().isoformat(),
                use_egeo=not args.no_egeo)
    drafts = sum(1 for x in res["items"] if x["draft"])
    print(f"Wrote {len(res['items'])} answers in {res['folder']}.")
    if drafts:
        print(f"{drafts} are drafts from your interview. Read each one aloud and make it yours.")
    if res["egeo"]:
        print("egeo: " + ("ran on every answer, reports in answers/egeo/." if all(n["ok"] for n in res["egeo"])
                          else res["egeo"][-1]["message"]))
    elif not args.no_egeo and not egeo_path():
        print("egeo is not installed, so the extra rewrite was skipped. That is fine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
