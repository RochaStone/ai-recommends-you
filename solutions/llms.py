#!/usr/bin/env python3
"""Fix 4: llms.txt, llms-full.txt and a plain note on AI crawlers.

llms.txt follows the proposal at https://llmstxt.org: an H1 with her name (the only required part), a
blockquote summary, a plain detail paragraph, then H2 sections that are lists of `[name](url): notes`,
with a final "## Optional" section for links an assistant may skip.
llms-full.txt is a common companion convention (not part of the llmstxt.org page): the full text of her
page and answers in one file, so an assistant can read everything in one go.

Reads out/entity.json and, if present, out/answers/faq.json. Writes out/llms/llms.txt, out/llms/llms-full.txt
and out/llms/AI-CRAWLERS.md.

Usage: python3 solutions/llms.py out/entity.json --out out/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solutions.common import EntityError, load_entity, one_line, quotables, slugify  # noqa: E402

# User-agent names the big assistants publish for their crawlers. Names change; the note says to check.
AI_CRAWLERS = [("GPTBot", "OpenAI, collects pages for training"),
               ("OAI-SearchBot", "OpenAI, finds pages for ChatGPT search answers"),
               ("ChatGPT-User", "OpenAI, fetches a page when a person asks ChatGPT about it"),
               ("PerplexityBot", "Perplexity, finds pages for its answers"),
               ("ClaudeBot", "Anthropic, collects pages for training"),
               ("Claude-SearchBot", "Anthropic, finds pages for Claude's search answers"),
               ("Claude-User", "Anthropic, fetches a page when a person asks Claude about it"),
               ("Google-Extended", "Google, controls use in Gemini; normal Google search is separate")]


def _first_sentence(text: str) -> str:
    s = text.strip().split(". ")[0].strip()
    return s if s.endswith(".") else s + "."


def load_faqs(out: Path) -> list[dict]:
    path = out / "answers" / "faq.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"Could not read {path}, so llms.txt has no answers section.", file=sys.stderr)
        return []
    return [{"q": q.get("name", ""), "a": q.get("acceptedAnswer", {}).get("text", "")}
            for q in data.get("mainEntity", []) if q.get("name")]


def llms_txt(ent: dict, faqs: list[dict]) -> str:
    base = ent["site"].rstrip("/")
    home = ent["site"] or "/"
    lines = [f"# {ent['name']}", "", f"> {one_line(ent)}", ""]
    detail = " ".join(x for x in (
        f"{ent['name']} offers {ent['offer'].rstrip('.')}." if ent["offer"] else "",
        f"It is for {ent['for_whom'].rstrip('.')}." if ent["for_whom"] else "",
        f"Based in {ent['where'].rstrip('.')}." if ent["where"] else "") if x)
    if detail:
        lines += [detail, ""]
    lines += ["## About", "", f"- [{ent['name']}]({home}): {one_line(ent)}"]
    if ent["book_url"] or ent["work_with"]:
        lines.append(f"- [How to work with {ent['name']}]({ent['book_url'] or home}): "
                     f"{ent['work_with'] or 'Booking and contact.'}")
    if faqs:
        lines += ["", "## Answers", ""]
        lines += [f"- [{f['q']}]({base}/faq#{slugify(f['q'])}): {_first_sentence(f['a'])}" for f in faqs]
    if ent["same_as"]:
        lines += ["", "## Optional", ""] + [f"- [{u}]({u})" for u in ent["same_as"]]
    return "\n".join(lines) + "\n"


def llms_full(ent: dict, faqs: list[dict]) -> str:
    out = [f"# {ent['name']}", "", f"> {one_line(ent)}", ""] + [f"- {s}" for s in quotables(ent)]
    if ent["work_with"]:
        out += ["", f"## How to work with {ent['name']}", "", ent["work_with"]]
        if ent["book_url"]:
            out.append(f"Book: {ent['book_url']}")
    for f in faqs:
        out += ["", f"## {f['q']}", "", f["a"]]
    return "\n".join(out) + "\n"


def crawler_note(ent: dict) -> str:
    rows = "\n".join(f"- `{ua}`: {what}" for ua, what in AI_CRAWLERS)
    allow = "\n".join(f"User-agent: {ua}\nAllow: /\n" for ua, _ in AI_CRAWLERS)
    where = ent["site"] or "your-site"
    return f"""# Let the assistants read your site

Your site has a small file called `robots.txt` (a note to visiting robots about what they may read).
If it blocks the assistants' robots, they cannot read your page, so they cannot recommend you.

1. Open `{where.rstrip('/')}/robots.txt` in your browser.
2. Look for any of these names next to `Disallow: /`. If one is there, that assistant is blocked.

{rows}

3. If you want them to read you, ask whoever runs your site (or your site builder's help page) to allow them.
   The lines look like this:

```
{allow}```

4. Put `llms.txt` and `llms-full.txt` at the top of your site, so they open at
   `{where.rstrip('/')}/llms.txt`. Most site builders call this "upload a file to the root".

These names come from each company's own crawler page and they change. Check them once a year.
Allowing training robots is your choice; the search and user robots are the ones that help you get named.
"""


def build(ent: dict, out: Path) -> Path:
    faqs = load_faqs(out)
    folder = out / "llms"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "llms.txt").write_text(llms_txt(ent, faqs), encoding="utf-8")
    (folder / "llms-full.txt").write_text(llms_full(ent, faqs), encoding="utf-8")
    (folder / "AI-CRAWLERS.md").write_text(crawler_note(ent), encoding="utf-8")
    return folder


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write llms.txt, llms-full.txt and the AI crawler note")
    ap.add_argument("entity", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out"))
    args = ap.parse_args(argv)
    try:
        ent = load_entity(args.entity)
    except EntityError as exc:
        print(exc, file=sys.stderr)
        return 2
    folder = build(ent, args.out)
    print(f"llms.txt and llms-full.txt: {folder}")
    print(f"The robot note: {folder / 'AI-CRAWLERS.md'}")
    if not ent["site"]:
        print("No site address in entity.json, so the links start with /. Add \"site\" and run it again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
