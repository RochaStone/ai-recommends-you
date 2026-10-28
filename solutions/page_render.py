"""One render path for every page the fixes write, in the three motif families.

Same idea as receipt_render: motif is STRUCTURE (paper sheet, terminal screen, 2003 blog window),
style.json palette and fonts are COLOUR and TYPE, through the same style loader and inheritance rule.
"""
from __future__ import annotations

import html
from pathlib import Path

from solutions.common import ROOT
from receipt_render import (PIXEL_HEART, PIXEL_STAR, REPO_ISSUES, find_style, load_style,  # noqa: F401
                            resolve_motif, style_head)

PAGE_CSS = ROOT / "assets" / "page.css"


def e(s: object) -> str:
    return html.escape(str(s), quote=True)


def get_style(style_path: Path | None) -> dict:
    """--style, then ./style.json, then ~/.rocha-coded/style.json, then the bundled example."""
    return load_style(find_style(style_path))


def render_page(title: str, body: str, *, style: dict, motif: str | None = None, jsonld: str = "",
                window: str = "page.exe", sidebar: list[tuple[str, str]] | None = None,
                date: str = "", card: bool = False, description: str = "", credit: str = "") -> str:
    """Wrap body HTML in the chosen motif. body is already-escaped HTML built by the caller."""
    motif = resolve_motif(motif, style)
    owner = str(style.get("owner") or "").strip()
    handle = str(style.get("handle") or "").strip()
    # Her own pages pass their own credit; otherwise the style owner signs it (never Rocha's on a user style).
    credit = credit or " · ".join(x for x in (owner, handle, "made with Rocha Coded") if x)
    stamp = f'<p class="stamp">last updated {e(date)}</p>' if date else ""
    if motif == "cyberpunk":
        inner = f"""<main class="pg-crt{" frame" if card else ""}">
  <div class="bezel"><span class="led candy"></span><span class="led gold"></span>
    <span class="px">{e(window)} · rocheverse</span><span class="screws"><i></i><i></i></span></div>
  <div class="screen">
    <p class="prompt"><span class="ps">rocheverse:~$</span> cat {e(window.replace('.exe', '.md'))}</p>
    {body}
    {stamp}
    <p class="prompt"><span class="ps">rocheverse:~$</span><span class="cursor" aria-hidden="true"></span></p>
    <p class="credit px">{e(credit)}</p>
  </div>
</main>"""
    elif motif == "y2k-blog":
        side = "".join(f'<section><h3 class="px">{e(h)}</h3><p>{e(t)}</p></section>' for h, t in (sidebar or []))
        inner = f"""<main class="pg-win{" frame" if card else ""}">
  <div class="titlebar"><span class="btns"><i></i><i></i><i></i></span><span class="title px">{e(window)}</span></div>
  <div class="marquee"><span>{PIXEL_STAR} {e(title)} {PIXEL_STAR} {e(date)} {PIXEL_STAR}</span></div>
  <div class="winbody">
    <article class="post">{body}{stamp}</article>
    <aside class="side">{side}
      <section class="counter"><h3 class="px">hit counter</h3><p>you are visitor no.<br><b>000,777</b></p></section>
      <section><h3 class="px">guestbook</h3><p><a href="{REPO_ISSUES}">sign my guestbook</a> {PIXEL_HEART}</p></section>
      <p class="credit">{e(credit)}</p>
    </aside>
  </div>
</main>"""
    else:
        inner = f"""<main class="pg-sheet{" frame" if card else ""}">
  <p class="kicker">{e(title)}</p>
  {body}
  {stamp}
  <p class="credit">{e(credit)}</p>
</main>"""
    css = PAGE_CSS.read_text(encoding="utf-8") if PAGE_CSS.exists() else ""
    desc = f'<meta name="description" content="{e(description)}">\n' if description else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
{desc}<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<style>{css}</style>
{style_head(style, motif)}
{jsonld}
</head>
<body class="{"card" if card else "page"} m-{motif}">
{inner}
</body></html>"""
