"""Rendering for ai-recommends-you: style.json, the three motif skins, and the PNG share card.

One function, render_receipt(), draws the same receipt data in three motif families:
  analog     the blush guest check (paper you could hold)
  cyberpunk  a plum CRT terminal printout (the girly terminal)
  y2k-blog   a 2003 blog window with sidebar, hit counter and guestbook
Motif is structure; style.json palette and fonts are colour and type, so every family re-tones.
"""
from __future__ import annotations

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
ASSETS = HERE / "assets"
CSS_FILES = {"analog": ["receipt.css"], "cyberpunk": ["receipt.css", "motif-cyberpunk.css"],
             "y2k-blog": ["receipt.css", "motif-y2k.css"]}
CARD_W, CARD_H = 1080, 1350
STYLE_EXAMPLE = HERE / "examples" / "style.rocha-coded.json"
REPO_ISSUES = "https://github.com/RochaStone/ai-recommends-you/issues"
MOTIFS = ("analog", "cyberpunk", "y2k-blog")
# Older motif names from the shared schema map to the nearest family.
MOTIF_ALIASES = {"guest-check": "analog", "front-page": "analog", "magazine-scrawl": "analog",
                 "pink-paper": "analog", "rotary": "analog", "leopard": "analog", "neutral": "analog",
                 "retro-tv": "cyberpunk", "sticker-collage": "y2k-blog", "y2k": "y2k-blog", "blog": "y2k-blog"}
COLOUR = re.compile(r"^#[0-9A-Fa-f]{3,8}$")
FONT_NAME = re.compile(r"^[A-Za-z0-9 ]{1,40}$")
# style.json palette key -> CSS variable. hero is the GROUND (page behind the card), never a fill.
PALETTE_VARS = {"hero": "--ground", "wine": "--wine", "accent": "--candy", "paper_pink": "--paper",
                "paper": "--cream", "ink": "--ink", "marker": "--marker", "plum": "--plum", "gold": "--gold"}
# style.json font key -> (CSS variable, system fallback stack, Google Fonts axes or "")
FONT_VARS = {
    "masthead": ("--serif", 'Georgia, "Times New Roman", serif', "ital,wght@0,400;0,900;1,400;1,900"),
    "label": ("--label", 'system-ui, "Helvetica Neue", Arial, sans-serif', "wght@400;600;800"),
    "mono": ("--mono", "ui-monospace, Menlo, Consolas, monospace", "wght@400;500"),
    "scrawl": ("--scrawl", '"Marker Felt", "Comic Sans MS", cursive', ""),
    "pixel": ("--pixel", '"Pixelify Sans", ui-monospace, monospace', "wght@400;700"),
}
HOUSE_PIXEL_FONT = "Silkscreen"  # chrome labels in cyberpunk and y2k-blog unless fonts.pixel says otherwise

# Card only: once fonts load, shrink the question list until the whole frame fits 1080x1350.
FIT_SCRIPT = """<script>
(function () {
  function fit() {
    var f = document.querySelector(".fit"), l = document.querySelector(".lines"), z = 1;
    while (f && l && f.scrollHeight > f.clientHeight + 1 && z > 0.55) { z -= 0.02; l.style.zoom = z; }
  }
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(fit);
})();
</script>"""

PIXEL_HEART = ('<svg class="pix" viewBox="0 0 7 6" width="21" height="18" aria-hidden="true" shape-rendering="crispEdges">'
               '<path fill="currentColor" d="M1 0h2v1h1V0h2v1h1v2H6v1H5v1H4v1H3V5H2V4H1V3H0V1h1z"/></svg>')
PIXEL_STAR = ('<svg class="pix" viewBox="0 0 5 5" width="15" height="15" aria-hidden="true" shape-rendering="crispEdges">'
              '<path fill="currentColor" d="M2 0h1v2h2v1H3v2H2V3H0V2h2z"/></svg>')


def _e(s: object) -> str:
    return html.escape(str(s), quote=True)


def _short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ---------- style.json ----------

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


def resolve_motif(requested: str | None, style: dict) -> str:
    """--motif wins, then style.json motif, then analog. Old names map to the nearest family."""
    raw = str(requested or style.get("motif") or "analog").strip().lower()
    raw = MOTIF_ALIASES.get(raw, raw)
    return raw if raw in MOTIFS else "analog"


def style_head(style: dict, motif: str = "analog") -> str:
    """Font links plus a :root block that overrides the colours and fonts. Values are validated."""
    palette = style.get("palette") if isinstance(style.get("palette"), dict) else {}
    fonts = dict(style.get("fonts")) if isinstance(style.get("fonts"), dict) else {}
    if motif != "analog" and not str(fonts.get("pixel") or "").strip():
        fonts["pixel"] = HOUSE_PIXEL_FONT
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


# ---------- the receipt, three skins ----------

def _data(result: dict, meta: dict, name: str, style: dict, delta: str = "") -> dict:
    lines_cfg = style.get("lines") if isinstance(style.get("lines"), dict) else {}
    date = meta.get("date") or dt.date.today().isoformat()
    return {
        "name": name, "niche": meta.get("niche") or "", "location": meta.get("location") or "",
        "date": date, "servers": " · ".join(result["sources"].keys()) or "None yet",
        "check_no": int(hashlib.sha1(f"{name}{date}".encode()).hexdigest()[:6], 16) % 900000 + 100000,
        "scrawl": str(lines_cfg.get("scrawl") or "").strip(),
        "credit": " · ".join(str(x).strip() for x in (style.get("owner"), style.get("handle"),
                                                      "made with Rocha Coded") if x and str(x).strip()),
        "instead": ", ".join(x["name"] for x in result["sent_instead"][:3]) or "nobody, yet",
        "questions": result["questions"], "sources": result["sources"],
        "named": result["named"], "total": result["total"], "delta": str(delta or "").strip(),
    }


def _who(q: dict) -> str:
    return (", ".join(q["named"][:3]) + (" +more" if len(q["named"]) > 3 else "")) or "nobody named"


def _analog(d: dict, qlen: int, nlen: int, frame: bool) -> str:
    lines = "".join(
        f'<li class="line{" hit" if q["you_named"] else ""}"><span class="n">{i:02d}</span>'
        f'<span class="q">{_e(_short(q["question"], qlen))}<small>{_e(_short(_who(q), nlen))}</small></span>'
        f'<span class="you">YOU: {"NAMED" if q["you_named"] else "NOT NAMED"}</span></li>'
        for i, q in enumerate(d["questions"], 1))
    subs = "".join(f'<div class="sub"><span>{_e(s)}</span><span>{v["named"]}/{v["asked"]}</span></div>'
                   for s, v in d["sources"].items())
    where = "".join(f" · {_e(d[k])}" for k in ("niche", "location") if d[k])
    scrawl = (f'<p class="scrawl">{_e(d["scrawl"])}<svg viewBox="0 0 300 20" aria-hidden="true">'
              f'<path d="M4 14 C 80 4, 160 18, 296 6" /></svg></p>') if d["scrawl"] else ""
    return f"""<main class="check{" frame fit" if frame else ""}" aria-label="AI receipt">
  <header class="mast">
    <div class="kicker">GUEST CHECK · IS AI RECOMMENDING YOU?</div>
    <h1>AI RECEIPT</h1>
    <div class="for">for <b>{_e(d["name"])}</b>{where}</div>
  </header>
  <div class="boxes">
    <div><label>TABLE NO</label><span>{_e(d["date"])}</span></div>
    <div><label>SERVER</label><span>{_e(d["servers"])}</span></div>
    <div><label>GUESTS</label><span>{d["total"]} Qs</span></div>
    <div><label>CHECK NO</label><span>{d["check_no"]}</span></div>
  </div>
  <ol class="lines">{lines}</ol>
  <section class="foot">
    <div class="subs">{subs}
      <div class="sub tax"><span>SENT TO INSTEAD</span><span>{_e(_short(d["instead"], nlen))}</span></div>{
      f'<div class="sub delta"><span>SINCE LAST TIME</span><span>{_e(d["delta"])}</span></div>' if d["delta"] else ""}
    </div>
    <div class="total"><span>TOTAL</span><span>recommended <b>{d["named"]}/{d["total"]}</b></span></div>
    {scrawl}
    <div class="thanks">THANK YOU!</div>
    <div class="credit">{_e(d["credit"])}</div>
  </section>
</main>"""


def _blocks(n: int, total: int, width: int = 10) -> str:
    filled = round(width * n / total) if total else 0
    return f'<code class="blocks"><b>{"█" * filled}</b>{"░" * (width - filled)}</code>'


def _cyberpunk(d: dict, qlen: int, nlen: int) -> str:
    args = "".join(f' --{flag} "{_e(d[k])}"' for flag, k in (("niche", "niche"), ("place", "location")) if d[k])
    lines = "".join(
        f'<li class="line{" hit" if q["you_named"] else ""}"><span class="n">[{i:02d}]</span>'
        f'<span class="q">{_e(_short(q["question"], qlen))}<small>→ named: {_e(_short(_who(q), nlen))}</small></span>'
        f'<span class="you">{"NAMED" if q["you_named"] else "NOT NAMED"}</span></li>'
        for i, q in enumerate(d["questions"], 1))
    bars = "".join(f'<div class="bar"><span class="px">{_e(s)}</span>{_blocks(v["named"], v["asked"])}'
                   f'<span>{v["named"]}/{v["asked"]}</span></div>' for s, v in d["sources"].items())
    echo = f' echo "{_e(d["scrawl"])}"' if d["scrawl"] else ""
    return f"""<main class="crt frame" aria-label="AI receipt">
  <div class="bezel"><span class="led candy"></span><span class="led gold"></span>
    <span class="px">ai-receipt · rocheverse</span><span class="screws"><i></i><i></i></span></div>
  <div class="screen fit">
    <p class="prompt"><span class="ps">rocheverse:~$</span> ask --for "{_e(d["name"])}"{args}</p>
    <p class="sys">› asked {_e(d["servers"])} · {d["total"]} questions · {_e(d["date"])} · job {d["check_no"]}</p>
    <ol class="lines">{lines}</ol>
    <div class="bars">{bars}
      <div class="bar total"><span class="px">recommended</span>{_blocks(d["named"], d["total"])}<b>{d["named"]}/{d["total"]}</b></div>
    </div>
    <p class="sys">› sent to instead: {_e(_short(d["instead"], nlen))}</p>{
    f'<p class="sys delta">› {_e(d["delta"])}</p>' if d["delta"] else ""}
    <p class="prompt last"><span class="ps">rocheverse:~$</span>{echo}<span class="cursor" aria-hidden="true"></span></p>
    <p class="credit px">{_e(d["credit"])}</p>
  </div>
</main>"""


def _y2k(d: dict, inner: str) -> str:
    about = "<br>".join(_e(x) for x in (d["name"], d["niche"], d["location"]) if x)
    return f"""<main class="win frame fit" aria-label="AI receipt">
  <div class="titlebar"><span class="btns"><i></i><i></i><i></i></span><span class="title px">ai-receipt.exe</span></div>
  <div class="marquee"><span>{PIXEL_STAR} ai receipt for {_e(d["name"])} {PIXEL_STAR} recommended {d["named"]}/{d["total"]} {PIXEL_STAR} last updated {_e(d["date"])} {PIXEL_STAR}</span></div>
  <div class="winbody">
    <div class="post">{inner}</div>
    <aside class="side">
      <section><h3 class="px">about me</h3><p>{about}</p></section>
      <section><h3 class="px">mood</h3><p>delulu ✧</p></section>
      <section><h3 class="px">currently reading</h3><p>my fix list, three things to publish</p></section>
      <section class="counter"><h3 class="px">hit counter</h3><p>you are visitor no.<br><b>000,777</b></p></section>
      <section class="guest"><h3 class="px">guestbook</h3><p><a href="{REPO_ISSUES}">sign my guestbook</a> {PIXEL_HEART}</p></section>
      <p class="sparkle">{PIXEL_HEART}{PIXEL_STAR}{PIXEL_HEART}</p>
      <p class="updated">last updated {_e(d["date"])}</p>
    </aside>
  </div>
</main>"""


def render_receipt(result: dict, meta: dict, name: str, card: bool = False,
                   style: dict | None = None, motif: str | None = None, delta: str = "") -> str:
    style = load_style() if style is None else style
    motif = resolve_motif(motif, style)
    d = _data(result, meta, name, style, delta)
    if motif == "cyberpunk":
        body = _cyberpunk(d, *((46, 58) if card else (90, 80)))
    elif motif == "y2k-blog":
        body = _y2k(d, _analog(d, *((42, 44) if card else (80, 70)), frame=False))
    else:
        body = _analog(d, *((52, 60) if card else (90, 80)), frame=True)
    css = "\n".join((ASSETS / f).read_text(encoding="utf-8") for f in CSS_FILES[motif] if (ASSETS / f).exists())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Receipt for {_e(name)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<style>{css}</style>
{style_head(style, motif)}</head>
<body class="{"card" if card else "page"} m-{motif}">
{body}{FIT_SCRIPT if card else ""}</body></html>"""


# ---------- PNG ----------

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


def render_png(page_html: Path, png: Path, width: int = CARD_W, height: int = CARD_H) -> tuple[bool, str]:
    chrome = find_chrome()
    if not chrome:
        return False, ("No Chrome or Chromium found, so no PNG this time. The receipt HTML is ready. "
                       "Install Chrome, or set CHROME_PATH, then run again for the share card.")
    with tempfile.TemporaryDirectory() as profile:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--no-default-browser-check", f"--user-data-dir={profile}",
               f"--window-size={width},{height}", "--force-device-scale-factor=1",
               "--virtual-time-budget=6000", f"--screenshot={png}", page_html.resolve().as_uri()]
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
