#!/usr/bin/env python3
"""ai-recommends-you: turn AI answers into a receipt.

Reads answers.json (from browser, API, self or paste mode), works out who got
named for each buyer question, scores how often YOU were named, and writes:
  out/receipt.html   the Guest Check receipt
  out/receipt.png    a 1080x1350 share card (needs Chrome or Chromium)
  out/fix-list.md    the three things to publish next
  out/summary.json   the numbers, for the agent to read back

Stdlib only. Python 3.10+.
Usage: python3 recommend.py out/answers.json --name "Her Brand" --out out/
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSS_PATH = HERE / "assets" / "receipt.css"
CARD_W, CARD_H = 1080, 1350
STYLE_EXAMPLE = HERE / "examples" / "style.rocha-coded.json"
COLOUR = re.compile(r"^#[0-9A-Fa-f]{3,8}$")
FONT_NAME = re.compile(r"^[A-Za-z0-9 ]{1,40}$")
# style.json palette key -> CSS variable in assets/receipt.css. hero is the GROUND (page behind the card), never a fill.
PALETTE_VARS = {"hero": "--ground", "wine": "--wine", "accent": "--candy", "paper_pink": "--paper",
                "paper": "--cream", "ink": "--ink", "marker": "--marker", "plum": "--plum", "gold": "--gold"}
# style.json font key -> (CSS variable, system fallback stack, Google Fonts axes or "")
FONT_VARS = {
    "masthead": ("--serif", 'Georgia, "Times New Roman", serif', "ital,wght@0,400;0,900;1,400;1,900"),
    "label": ("--label", 'system-ui, "Helvetica Neue", Arial, sans-serif', "wght@400;600;800"),
    "mono": ("--mono", "ui-monospace, Menlo, Consolas, monospace", "wght@400;500"),
    "scrawl": ("--scrawl", '"Marker Felt", "Comic Sans MS", cursive', ""),
}

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


def name_matches(name: str, aliases: list[str], text: str, named: list[str]) -> bool:
    """True if her name (or an alias) appears in the answer text or the named list."""
    targets = [t.strip().lower() for t in [name, *aliases] if t and t.strip()]
    hay = text.lower()
    pool = [n.lower() for n in named]
    for t in targets:
        if re.search(rf"(?<![\w]){re.escape(t)}(?![\w])", hay):
            return True
        if any(t == n or t in n or n in t for n in pool if len(n) >= 4):
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


# ---------- rendering ----------

def _e(s: object) -> str:
    return html.escape(str(s), quote=True)


def _short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# Card only: once fonts load, shrink the question list until the whole receipt fits 1080x1350.
FIT_SCRIPT = """<script>
(function () {
  function fit() {
    var c = document.querySelector(".check"), l = document.querySelector(".lines"), z = 1;
    while (c.scrollHeight > c.clientHeight + 1 && z > 0.6) { z -= 0.02; l.style.zoom = z; }
  }
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(fit);
})();
</script>"""


def find_style(explicit: Path | None = None, cwd: Path | None = None, home: Path | None = None) -> Path:
    """The shared Rocha Coded fallback order: --style, ./style.json, ~/.rocha-coded/style.json, bundled example."""
    candidates = [explicit] if explicit else []
    candidates += [Path(cwd or Path.cwd()) / "style.json",
                   Path(home or Path.home()) / ".rocha-coded" / "style.json", STYLE_EXAMPLE]
    return next((Path(c) for c in candidates if c and Path(c).is_file()), STYLE_EXAMPLE)


def load_style(path: Path | None = None) -> dict:
    path = path or STYLE_EXAMPLE
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Could not read style file {path} ({exc}). Using the bundled example look.", file=sys.stderr)
        try:
            data = json.loads(STYLE_EXAMPLE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    data = data if isinstance(data, dict) else {}
    return data if Path(path) == STYLE_EXAMPLE else inherit_style(data)


def inherit_style(user: dict) -> dict:
    """A user's style borrows ONLY missing palette and font entries from the bundled example.
    Lines, owner, handle, name, references and notes never fall back to Rocha's."""
    try:
        example = json.loads(STYLE_EXAMPLE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        example = {}
    merged = dict(user)
    for key in ("palette", "fonts"):
        mine = user.get(key) if isinstance(user.get(key), dict) else {}
        base = example.get(key) if isinstance(example.get(key), dict) else {}
        merged[key] = {**base, **{k: v for k, v in mine.items() if str(v or "").strip()}}
    return merged


def style_head(style: dict) -> str:
    """Font links plus a :root block that overrides the receipt colours and fonts. Values are validated."""
    palette = style.get("palette") if isinstance(style.get("palette"), dict) else {}
    fonts = style.get("fonts") if isinstance(style.get("fonts"), dict) else {}
    css_vars, links = [], []
    for key, var in PALETTE_VARS.items():
        val = str(palette.get(key) or "").strip()
        if COLOUR.match(val):
            css_vars.append(f"{var}: {val};")
    for key, (var, fallback, axes) in FONT_VARS.items():
        fam = str(fonts.get(key) or "").strip()
        if not FONT_NAME.match(fam):
            continue
        css_vars.append(f'{var}: "{fam}", {fallback};')
        q = fam.replace(" ", "+")
        if axes:  # weighted request first; if the family lacks a weight, the plain link below still loads it
            links.append(f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={q}:{axes}&display=swap">')
        links.append(f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={q}&display=swap">')
    return "\n".join(links) + f"\n<style>:root {{ {' '.join(css_vars)} }}</style>"


def render_receipt(result: dict, meta: dict, name: str, card: bool = False, style: dict | None = None) -> str:
    css = CSS_PATH.read_text(encoding="utf-8") if CSS_PATH.exists() else ""
    style = load_style() if style is None else style
    lines_cfg = style.get("lines") if isinstance(style.get("lines"), dict) else {}
    scrawl = str(lines_cfg.get("scrawl") or "").strip()
    credit = " · ".join(str(x).strip() for x in (style.get("owner"), style.get("handle"), "made with Rocha Coded")
                        if x and str(x).strip())
    date = meta.get("date") or dt.date.today().isoformat()
    servers = " · ".join(result["sources"].keys()) or "None yet"
    check_no = int(hashlib.sha1(f"{name}{date}".encode()).hexdigest()[:6], 16) % 900000 + 100000
    qlen, nlen = (52, 60) if card else (90, 80)
    lines = []
    for i, q in enumerate(result["questions"], 1):
        who = ", ".join(q["named"][:3]) + (" +more" if len(q["named"]) > 3 else "")
        tag = "NAMED" if q["you_named"] else "NOT NAMED"
        lines.append(
            f'<li class="line{" hit" if q["you_named"] else ""}">'
            f'<span class="n">{i:02d}</span>'
            f'<span class="q">{_e(_short(q["question"], qlen))}'
            f'<small>{_e(_short(who or "nobody named", nlen))}</small></span>'
            f'<span class="you">YOU: {tag}</span></li>'
        )
    subtotals = "".join(
        f'<div class="sub"><span>{_e(s)}</span><span>{v["named"]}/{v["asked"]}</span></div>'
        for s, v in result["sources"].items()
    )
    instead = ", ".join(x["name"] for x in result["sent_instead"][:3]) or "nobody, yet"
    scrawl_html = (f'<p class="scrawl">{_e(scrawl)}<svg viewBox="0 0 300 20" aria-hidden="true">'
                   f'<path d="M4 14 C 80 4, 160 18, 296 6" /></svg></p>') if scrawl else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Receipt for {_e(name)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<style>{css}</style>
{style_head(style)}</head>
<body class="{"card" if card else "page"}">
<main class="check" aria-label="AI receipt">
  <header class="mast">
    <div class="kicker">GUEST CHECK · IS AI RECOMMENDING YOU?</div>
    <h1>AI RECEIPT</h1>
    <div class="for">for <b>{_e(name)}</b>{(" · " + _e(meta["niche"])) if meta.get("niche") else ""}{(" · " + _e(meta["location"])) if meta.get("location") else ""}</div>
  </header>
  <div class="boxes">
    <div><label>TABLE NO</label><span>{_e(date)}</span></div>
    <div><label>SERVER</label><span>{_e(servers)}</span></div>
    <div><label>GUESTS</label><span>{result["total"]} Qs</span></div>
    <div><label>CHECK NO</label><span>{check_no}</span></div>
  </div>
  <ol class="lines">{"".join(lines)}</ol>
  <section class="foot">
    <div class="subs">{subtotals}
      <div class="sub tax"><span>SENT TO INSTEAD</span><span>{_e(_short(instead, 52 if card else 80))}</span></div>
    </div>
    <div class="total"><span>TOTAL</span><span>recommended <b>{result["named"]}/{result["total"]}</b></span></div>
    {scrawl_html}
    <div class="thanks">THANK YOU!</div>
    <div class="credit">{_e(credit)}</div>
  </section>
</main>{FIT_SCRIPT if card else ""}</body></html>"""


def render_fix_list(result: dict, meta: dict, name: str) -> str:
    niche = meta.get("niche") or "your niche"
    place = meta.get("location") or "your area"
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

> {name}: {niche} in {place}. We offer {offer}.

Use the same name everywhere, the same way, every time. Add your location, your prices or
packages, and how to book. Keep it on a page that loads without a login.

## 2. Get mentioned on other people's pages
Assistants trust what other sites say about you more than what you say about yourself.
Aim for three new mentions this month in places your buyers already read:
- a directory or "best of" list for {niche} in {place}
- a podcast guest spot or a newsletter feature in your niche
- a local press piece, a partner's site, or a client's public review that names you

{win_line}

## 3. Answer the exact questions you lost, in your own words
Write a short FAQ answer (three to five sentences each) for every question below.
Use the buyer's words as the heading. Put them on your site, not only on social media.

{lost_md}

Run the receipt again in four to six weeks. Same questions, same assistants. Watch the total.
"""


# ---------- PNG share card ----------

def find_chrome() -> str | None:
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    for cmd in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                "chrome", "microsoft-edge"):
        p = shutil.which(cmd)
        if p:
            return p
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if Path(p).exists():
            return p
    return None


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", head[16:24])


def render_png(card_html: Path, png: Path) -> tuple[bool, str]:
    chrome = find_chrome()
    if not chrome:
        return False, ("No Chrome or Chromium found, so no PNG this time. The receipt HTML is ready. "
                       "Install Chrome, or set CHROME_PATH, then run again for the share card.")
    with tempfile.TemporaryDirectory() as profile:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--no-default-browser-check", f"--user-data-dir={profile}",
               f"--window-size={CARD_W},{CARD_H}", "--force-device-scale-factor=1",
               "--virtual-time-budget=6000", f"--screenshot={png}", card_html.resolve().as_uri()]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        try:
            subprocess.run(cmd, capture_output=True, timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"Chrome could not render the PNG ({exc}). The receipt HTML is ready."
    if not png.exists():
        return False, "Chrome ran but wrote no PNG. The receipt HTML is ready."
    w, h = png_size(png)
    return True, f"Share card: {png} ({w}x{h})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the AI receipt from answers.json")
    ap.add_argument("answers", type=Path)
    ap.add_argument("--name", help="her brand or name, as buyers would say it")
    ap.add_argument("--alias", action="append", default=[], help="another spelling of her name")
    ap.add_argument("--ignore", action="append", default=[], help="a word to never count as a name")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--no-png", action="store_true", help="skip the PNG share card")
    ap.add_argument("--style", type=Path, help="a style.json (default: ./style.json, then "
                    "~/.rocha-coded/style.json, then the bundled Rocha Coded example)")
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
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "receipt.html").write_text(render_receipt(result, meta, name, style=style), encoding="utf-8")
    card = out / "receipt-card.html"
    card.write_text(render_receipt(result, meta, name, card=True, style=style), encoding="utf-8")
    (out / "fix-list.md").write_text(render_fix_list(result, meta, name), encoding="utf-8")
    summary = {k: result[k] for k in ("total", "named", "sources", "sent_instead", "lost")}
    summary["questions"] = [{k: q[k] for k in ("question", "sources", "named", "you_named")}
                            for q in result["questions"]]
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Recommended {result['named']} out of {result['total']}.")
    look = "the bundled Rocha Coded example" if style_path == STYLE_EXAMPLE else str(style_path)
    print(f"Style: {look}")
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
