#!/usr/bin/env python3
"""Fix 1: one clear page that says exactly who she is.

Reads out/entity.json (her interview, in her words) and writes:
  out/entity/index.html   the page, in her motif, with Organization/Person + Service + FAQPage JSON-LD
  out/entity/index.md     the same words as plain Markdown, to paste into Substack About or any site
  out/entity/DEPLOY.md    where to put it, three beginner paths

Direct answer first, then short quotable lines that each carry her name, then proof, how to work with
her, and the FAQ. Method credit: audit-website-aeo and improve-aeo-geo in onvoyage-ai/gtm-engineer-skills (MIT).

Usage: python3 solutions/entity_page.py out/entity.json --out out/ [--motif analog|cyberpunk|y2k-blog] [--style style.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from receipt_render import MOTIFS  # noqa: E402
from solutions.common import EntityError, entity_graph, ld_script, load_entity, one_line, quotables  # noqa: E402
from solutions.page_render import e, get_style, render_page  # noqa: E402


def faqs_for(ent: dict) -> list[dict]:
    """Her own FAQ, plus every lost-question answer she wrote in her words."""
    faqs = list(ent["faq"])
    have = {f["q"].lower() for f in faqs}
    faqs += [{"q": q, "a": a} for q, a in ent["answers"].items() if q.lower() not in have]
    return faqs


def body_html(ent: dict, faqs: list[dict]) -> str:
    n = ent["name"]
    quote = "".join(f"<li>{e(s)}</li>" for s in quotables(ent, lead=False, proof=False))
    proof = ("<h2>Proof</h2><ul>" + "".join(f"<li>{e(p)}</li>" for p in ent["proof"]) + "</ul>") if ent["proof"] else ""
    book = f' <a href="{e(ent["book_url"])}">Book here.</a>' if ent["book_url"] else ""
    work = (f"<h2>How to work with {e(n)}</h2><p>{e(ent['work_with'])}{book}</p>"
            if ent["work_with"] or book else "")
    faq = ("<h2>Questions people ask</h2>" + "".join(
        f"<h3>{e(f['q'])}</h3><p>{e(f['a'])}</p>" for f in faqs)) if faqs else ""
    links = ("<h2>Find " + e(n) + "</h2><ul>" + "".join(
        f'<li><a href="{e(u)}">{e(u)}</a></li>' for u in ([ent["site"]] if ent["site"] else []) + ent["same_as"])
        + "</ul>") if ent["site"] or ent["same_as"] else ""
    return (f"<h1>{e(n)}</h1><p class=\"answer\">{e(one_line(ent))}</p>"
            f"<h2>In short</h2><ul class=\"quote\">{quote}</ul>{proof}{work}{faq}{links}")


def markdown(ent: dict, faqs: list[dict]) -> str:
    n = ent["name"]
    out = [f"# {n}", "", one_line(ent), "", "## In short", ""]
    out += [f"- {s}" for s in quotables(ent, lead=False, proof=False)]
    if ent["proof"]:
        out += ["", "## Proof", ""] + [f"- {p}" for p in ent["proof"]]
    if ent["work_with"] or ent["book_url"]:
        out += ["", f"## How to work with {n}", "", (ent["work_with"] + (f" [Book here]({ent['book_url']})." if ent["book_url"] else "")).strip()]
    if faqs:
        out += ["", "## Questions people ask"]
        for f in faqs:
            out += ["", f"### {f['q']}", "", f["a"]]
    links = ([ent["site"]] if ent["site"] else []) + ent["same_as"]
    if links:
        out += ["", f"## Find {n}", ""] + [f"- {u}" for u in links]
    return "\n".join(out) + "\n"


DEPLOY = """# Where to put your page

Pick the one that matches where you already live online. Any one of them works.

1. **Your own website.** Open your About page in your site editor. Paste the words from `index.md`.
   Then find "custom code" or "header code" in your site settings and paste the block that starts with
   `<script type="application/ld+json">` from `index.html`. That block is the label the assistants read.
2. **Substack.** Open Settings, then About. Paste the words from `index.md`. Substack does not take the code
   block, and the words alone still help.
3. **GitHub Pages (free hosting).** Make a new public repository, upload `index.html`, then open Settings,
   Pages, and choose the main branch. Your page goes live at the address GitHub shows you in a minute or two.

Use the same name, the same one line, and the same links everywhere. Consistency across every surface is
what makes the assistants confident enough to say your name.
"""


def build(ent: dict, out: Path, style: dict, motif: str | None, date: str) -> Path:
    faqs = faqs_for(ent)
    folder = out / "entity"
    folder.mkdir(parents=True, exist_ok=True)
    side = [("about me", one_line(ent)), ("mood", "certain ✧")]
    page = render_page(ent["name"], body_html(ent, faqs), style=style, motif=motif,
                       jsonld=ld_script(entity_graph(ent, faqs)), window="about-me.exe",
                       sidebar=side, date=date, description=one_line(ent),
                       credit=f"{ent['name']} · made with Rocha Coded")
    (folder / "index.html").write_text(page, encoding="utf-8")
    (folder / "index.md").write_text(markdown(ent, faqs), encoding="utf-8")
    (folder / "DEPLOY.md").write_text(DEPLOY, encoding="utf-8")
    return folder


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write her one clear entity page")
    ap.add_argument("entity", type=Path, help="out/entity.json from the interview")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--motif", choices=MOTIFS)
    ap.add_argument("--style", type=Path)
    args = ap.parse_args(argv)
    try:
        ent = load_entity(args.entity)
    except EntityError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.style and not args.style.is_file():
        print(f"No style file at {args.style}.", file=sys.stderr)
        return 2
    folder = build(ent, args.out, get_style(args.style), args.motif, dt.date.today().isoformat())
    print(f"Your page: {folder / 'index.html'}")
    print(f"The words to paste: {folder / 'index.md'}")
    print(f"Where to put it: {folder / 'DEPLOY.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
