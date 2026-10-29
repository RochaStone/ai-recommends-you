#!/usr/bin/env python3
"""ai-recommends-you: turn AI answers into a receipt.

Reads answers.json (from browser, API, self or paste mode), works out who got
named for each buyer question, scores how often YOU were named, and writes:
  out/receipt.html   the Guest Check receipt
  out/receipt.png    a 1080x1350 share card (needs Chrome or Chromium)
  out/fix-list.md    the three things to publish next
  out/summary.json   the numbers, for the agent to read back

Stdlib only. Python 3.10+.
Every run also keeps a dated copy in out/history/summary-YYYY-MM-DD.json for the 30-day re-run.
Usage: python3 recommend.py out/answers.json --name "Her Brand" --out out/ [--motif analog|cyberpunk|y2k-blog]
       [--compare out/history/summary-2026-09-28.json]   prints and stamps "last month 3/10, today 5/10"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from receipt_render import (  # noqa: F401  (re-exported for tests and callers)
    CARD_H, CARD_W, MOTIFS, STYLE_EXAMPLE, find_chrome, find_style, inherit_style, load_style, png_size,
    render_png, render_receipt, resolve_motif, style_head,
)

# Words that start capitalised phrases without being part of a name.
LEAD_STOP = {
    "the", "a", "an", "and", "or", "but", "if", "here", "there", "some", "best", "top",
    "for", "in", "on", "at", "of", "to", "with", "by", "from", "you", "your", "they",
    "their", "this", "that", "these", "those", "it", "its", "she", "he", "we", "i",
    "yes", "no", "also", "many", "most", "other", "others", "consider", "look", "try",
    "check", "when", "what", "who", "why", "how", "which", "where", "overall", "finally",
    "first", "second", "third", "next", "then", "however", "based", "known", "great",
    "popular", "highly", "recommended", "option", "options", "pros", "cons", "note",
    "summary", "verdict", "tip", "tips", "my", "our", "is", "are", "was", "were", "be",
    "sure", "both", "each", "every", "all", "any", "one", "two", "three", "while",
}
# Phrases that are never a business or person.
NOT_ENTITY = {
    "google", "google maps", "google reviews", "yelp", "instagram", "facebook", "tiktok",
    "linkedin", "youtube", "reddit", "chatgpt", "perplexity", "claude", "openai", "ai",
    "faq", "faqs", "usa", "uk", "us", "eu", "new year", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday", "january", "february", "march", "april",
    "may", "june", "july", "august", "september", "october", "november", "december",
}
CONNECTORS = {"&", "and", "of", "the", "de", "la", "le", "du", "von", "van", "+", "x"}
CAP_WORD = r"(?:[A-Z][\w'’.-]*|[A-Z]{2,})"
CAP_PHRASE = re.compile(
    rf"{CAP_WORD}(?:\s+(?:&|\+|of|the|de|la|le|du|von|van)?\s*{CAP_WORD}){{0,5}}"
)
LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")
BOLD = re.compile(r"\*\*([^*]{2,80})\*\*")


def _clean(phrase: str, keep_the: bool = False) -> str:
    phrase = phrase.strip(" \t*_:;,.!?\"'()[]-\u2013\u2014")
    words = phrase.split()
    while words and words[0].lower() in LEAD_STOP and not (keep_the and words[0] == "The"):
        words.pop(0)
    while words and words[-1].lower() in CONNECTORS:
        words.pop()
    return " ".join(words)


def _is_entity(phrase: str, ignore: set[str]) -> bool:
    low = phrase.lower()
    if not phrase or low in NOT_ENTITY or low in ignore or len(phrase) > 60:
        return False
    if not re.search(r"[A-Za-z]", phrase):
        return False
    words = phrase.split()
    if len(words) == 1:
        # single words only count if they look like a brand (InnerCaps or ALLCAPS of 3+)
        w = words[0]
        return bool(re.search(r"[a-z][A-Z]", w) or (w.isupper() and len(w) >= 3))
    return True


def extract_entities(text: str, ignore: list[str] | None = None) -> list[str]:
    """Pull likely business and people names out of an AI answer.

    Heuristics, in order: bold text, the lead of each list item, then runs of
    capitalised words. Generic words, platforms and the ignore list are dropped.
    """
    ignore_set = {i.lower().strip() for i in (ignore or []) if i}
    found: list[str] = []

    def add(raw: str, keep_the: bool = False) -> None:
        name = _clean(raw, keep_the)
        low = name.lower()
        # skip duplicates and fragments of a name already found ("Clay Hours" inside "The Clay Hours")
        if _is_entity(name, ignore_set) and not any(low in f.lower() for f in found):
            found.append(name)

    for m in BOLD.finditer(text):
        add(m.group(1), keep_the=True)
    for line in text.splitlines():
        m = LIST_ITEM.match(line)
        if not m:
            continue
        lead = re.split(r"\s[-\u2013\u2014:]\s|:\s|\s\(|,\s", m.group(1).replace("**", ""), maxsplit=1)[0]
        for cm in CAP_PHRASE.finditer(lead):
            add(cm.group(0), keep_the=True)
    plain = text.replace("**", "")
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", plain):
        for cm in CAP_PHRASE.finditer(sentence):
            add(cm.group(0), keep_the=cm.start() > 0)  # "The" mid-sentence is part of a name
    return found


_DENIALS = ("nothing found", "no review found", "no reviews found", "not found", "no results", "unrelated",
            "didn't turn up", "did not turn up", "turned up nothing", "no mention", "none mention", "nothing about",
            "doesn't appear", "does not appear", "couldn't find anything", "could not find anything",
            "didn't find anything", "did not find anything", "no information about", "not recognise", "not recognize")


def _denied(hay: str, pos: int) -> bool:
    """True when the name sits in a sentence that says it was NOT found. A denial is not a recommendation."""
    start = max(hay.rfind(". ", 0, pos), hay.rfind("\n", 0, pos), 0)
    end_candidates = [i for i in (hay.find(". ", pos), hay.find("\n", pos)) if i != -1]
    end = min(end_candidates) if end_candidates else len(hay)
    sentence = hay[start:end]
    return any(d in sentence for d in _DENIALS)


def name_matches(name: str, aliases: list[str], text: str, named: list[str]) -> bool:
    """True if her name (or an alias) appears in the answer text or the named list."""
    targets = [t.strip().lower() for t in [name, *aliases] if t and t.strip()]
    hay = text.lower()
    pool = [n.lower() for n in named]
    for t in targets:
        for m in re.finditer(rf"(?<![\w]){re.escape(t)}(?![\w])", hay):
            if not _denied(hay, m.start()):
                return True
        for n in pool:
            if len(n) >= 4 and (t == n or t in n):
                i = hay.find(n)
                if i == -1 or not _denied(hay, i):
                    return True
    return False


def load_answers(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {}, data
    if isinstance(data, dict) and isinstance(data.get("answers"), list):
        return data.get("meta", {}) or {}, data["answers"]
    raise ValueError("answers.json must be a list of answers or {\"meta\":{}, \"answers\":[]}")


def score(answers: list[dict], name: str, aliases: list[str], ignore: list[str]) -> dict:
    """Score every answer and roll them up per question and per source."""
    rows: list[dict] = []
    for a in answers:
        q = str(a.get("question", "")).strip()
        if not q:
            continue
        text = str(a.get("answer", ""))
        named = [str(n).strip() for n in (a.get("named") or []) if str(n).strip()]
        if not named:
            named = extract_entities(text, ignore=ignore)
        you = name_matches(name, aliases, text, named) or a.get("you_named") is True
        others = [n for n in named if not name_matches(name, aliases, n, [])]
        rows.append({"question": q, "source": str(a.get("source") or "Unknown").strip(),
                     "answer": text, "named": named, "others": others, "you_named": you})

    questions: list[dict] = []
    for r in rows:
        q = next((x for x in questions if x["question"].lower() == r["question"].lower()), None)
        if q is None:
            q = {"question": r["question"], "sources": [], "named": [], "you_named": False}
            questions.append(q)
        if r["source"] not in q["sources"]:
            q["sources"].append(r["source"])
        for n in r["others"]:
            if n.lower() not in {x.lower() for x in q["named"]}:
                q["named"].append(n)
        q["you_named"] = q["you_named"] or r["you_named"]

    sources: dict[str, dict] = {}
    for r in rows:
        s = sources.setdefault(r["source"], {"asked": 0, "named": 0})
        s["asked"] += 1
        s["named"] += int(r["you_named"])

    tally: dict[str, int] = {}
    for q in questions:
        for n in q["named"]:
            low = n.lower()
            key = next((k for k in tally if low in k.lower() or k.lower() in low), n)
            tally[key] = tally.get(key, 0) + 1
    top = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:5]

    return {
        "questions": questions,
        "rows": rows,
        "total": len(questions),
        "named": sum(1 for q in questions if q["you_named"]),
        "sources": sources,
        "sent_instead": [{"name": n, "questions": c} for n, c in top],
        "lost": [q["question"] for q in questions if not q["you_named"]],
    }


# ---------- the 30-day re-run ----------

def load_previous(path: Path, name: str, aliases: list[str], ignore: list[str]) -> dict:
    """A previous summary.json, or a previous answers.json scored the same way as today."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "named" in data and "total" in data:
        return {"named": int(data["named"]), "total": int(data["total"]), "date": str(data.get("date") or ""),
                "questions": data.get("questions") or []}
    meta, answers = load_answers(Path(path))
    r = score(answers, name, aliases, ignore)
    return {"named": r["named"], "total": r["total"], "date": str(meta.get("date") or ""),
            "questions": [{"question": q["question"], "you_named": q["you_named"]} for q in r["questions"]]}


def compare(prev: dict, result: dict, today: str) -> dict:
    """The delta between two runs: the totals, a plain line for the receipt, and which questions moved."""
    days = None
    try:
        days = (dt.date.fromisoformat(today) - dt.date.fromisoformat(prev["date"])).days
    except (ValueError, TypeError, KeyError):
        days = None
    label = "last month" if days is not None and 20 <= days <= 45 else (
        f"on {prev['date']}" if prev.get("date") else "last time")
    before = {str(q.get("question", "")).lower(): bool(q.get("you_named")) for q in prev.get("questions", [])}
    now = {q["question"].lower(): (q["question"], q["you_named"]) for q in result["questions"]}
    won = [orig for low, (orig, hit) in now.items() if hit and before.get(low) is False]
    lost = [orig for low, (orig, hit) in now.items() if not hit and before.get(low) is True]
    change = result["named"] - prev["named"]
    return {"before": prev["named"], "before_total": prev["total"], "before_date": prev.get("date", ""),
            "after": result["named"], "after_total": result["total"], "today": today, "days": days,
            "change": change, "newly_named": won, "newly_lost": lost,
            "line": f"{label} {prev['named']}/{prev['total']}, today {result['named']}/{result['total']}"}


# ---------- fix list ----------

def render_fix_list(result: dict, meta: dict, name: str) -> str:
    niche = meta.get("niche") or "your niche"
    place = meta.get("location") or "your area"
    place_phrase = "online" if place.strip().lower() in ("online", "remote") else f"in {place}"
    offer = meta.get("offer") or "what you sell"
    winners = [x["name"] for x in result["sent_instead"][:3]]
    lost = result["lost"] or ["(you were named every time, so publish to keep it that way)"]
    lost_md = "\n".join(f"- {q}" for q in lost)
    win_line = (f"The names it picked instead: {', '.join(winners)}. Search each one and note where "
                f"they are mentioned. Those pages are where the assistants learned their names."
                if winners else "Search your buyer questions yourself and note which sites come up.")
    return f"""# Your fix list

**{name}** was recommended **{result['named']} out of {result['total']}** times.
AI assistants name the businesses they can describe with confidence and find confirmed
in more than one place. Here is what to publish so they can do that for you.

## 1. One clear page that says exactly who you are
A single page on your own site (your home or About page is fine) that says, in plain words:
what you do, who it is for, and where. The assistants lift sentences like this almost word for word.

Start with this line and make it yours:

> {name}: {niche}, {place_phrase}. We offer {offer}.

Use the same name everywhere, the same way, every time. Add your location, your prices or
packages, and how to book. Keep it on a page that loads without a login.

## 2. Get mentioned on other people's pages
Assistants trust what other sites say about you more than what you say about yourself.
Aim for three new mentions this month in places your buyers already read:
- a directory or "best of" list for {niche}, {place_phrase}
- a podcast guest spot or a newsletter feature in your niche
- a local press piece, a partner's site, or a client's public review that names you

{win_line}

## 3. Answer the exact questions you lost, in your own words
Write a short FAQ answer (three to five sentences each) for every question below.
Use the buyer's words as the heading. Put them on your site, not only on social media.

{lost_md}

Run the receipt again in four to six weeks. Same questions, same assistants. Watch the total.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the AI receipt from answers.json")
    ap.add_argument("answers", type=Path)
    ap.add_argument("--name", help="her brand or name, as buyers would say it")
    ap.add_argument("--alias", action="append", default=[], help="another spelling of her name")
    ap.add_argument("--ignore", action="append", default=[], help="a word to never count as a name")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--no-png", action="store_true", help="skip the PNG share card")
    ap.add_argument("--motif", choices=MOTIFS, help="analog, cyberpunk or y2k-blog (default: style.json motif)")
    ap.add_argument("--style", type=Path, help="a style.json (default: ./style.json, then "
                    "~/.rocha-coded/style.json, then the bundled Rocha Coded example)")
    ap.add_argument("--compare", type=Path, help="a previous summary.json or answers.json, for the 30-day delta")
    args = ap.parse_args(argv)

    try:
        meta, answers = load_answers(args.answers)
    except (OSError, ValueError) as exc:
        print(f"Could not read {args.answers}: {exc}", file=sys.stderr)
        return 2
    name = args.name or meta.get("name")
    if not name:
        print("Tell me her brand name with --name \"Her Brand\".", file=sys.stderr)
        return 2
    aliases = args.alias + list(meta.get("aliases") or [])
    ignore = args.ignore + [meta.get("location") or "", meta.get("niche") or ""]

    result = score(answers, name, aliases, ignore)
    if result["total"] == 0:
        print("No answers with a question in them. Nothing to score.", file=sys.stderr)
        return 2

    if args.style and not args.style.is_file():
        print(f"No style file at {args.style}.", file=sys.stderr)
        return 2
    style_path = find_style(args.style)
    style = load_style(style_path)
    today = str(meta.get("date") or dt.date.today().isoformat())
    delta = None
    if args.compare:
        try:
            delta = compare(load_previous(args.compare, name, aliases, ignore), result, today)
        except (OSError, ValueError, KeyError) as exc:
            print(f"Could not read the previous run {args.compare} ({exc}). Making today's receipt without it.",
                  file=sys.stderr)
    line = delta["line"] if delta else ""
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "receipt.html").write_text(render_receipt(result, meta, name, style=style, motif=args.motif, delta=line),
                                      encoding="utf-8")
    card = out / "receipt-card.html"
    card.write_text(render_receipt(result, meta, name, card=True, style=style, motif=args.motif, delta=line),
                    encoding="utf-8")
    (out / "fix-list.md").write_text(render_fix_list(result, meta, name), encoding="utf-8")
    summary = {k: result[k] for k in ("total", "named", "sources", "sent_instead", "lost")}
    summary["questions"] = [{k: q[k] for k in ("question", "sources", "named", "you_named")}
                            for q in result["questions"]]
    summary["date"] = today
    if delta:
        summary["compare"] = delta
        (out / "delta.json").write_text(json.dumps(delta, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "history").mkdir(exist_ok=True)
    (out / "history" / f"summary-{today}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Recommended {result['named']} out of {result['total']}.")
    if delta:
        print(delta["line"].capitalize() + ".")
        for q in delta["newly_named"]:
            print(f"  now named: {q}")
        for q in delta["newly_lost"]:
            print(f"  slipped: {q}")
    look = "the bundled Rocha Coded example" if style_path == STYLE_EXAMPLE else str(style_path).replace(str(Path.home()), "~", 1)
    print(f"Style: {look} · motif: {resolve_motif(args.motif, style)}")
    print(f"Receipt: {out / 'receipt.html'}")
    print(f"Fix list: {out / 'fix-list.md'}")
    if args.no_png:
        print("PNG skipped (--no-png).")
    else:
        _, msg = render_png(card, out / "receipt.png")
        print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
