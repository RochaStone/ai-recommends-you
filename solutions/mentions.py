#!/usr/bin/env python3
"""Fix 3: get mentioned on other people's pages.

Assistants trust what other sites say about her more than what she says about herself.
Method credit: build-backlinks in onvoyage-ai/gtm-engineer-skills (MIT), cited, not copied.

Two ways in:
  With web search: the agent searches her niche, then saves out/mentions.json with REAL places only:
    {"niche": "...", "places": [{"name": "...", "url": "https://...", "kind": "directory|podcast|community|press",
                                 "why": "one line", "found_via": "the search or page it came from"}]}
    Places with no working-looking URL or no found_via are dropped. Nothing is ever invented.
  Without web search: run with --niche and no places file, and you get a checklist of categories and the
    exact searches to type, so she finds the places herself.

Writes out/mentions-plan.md: up to 10 places, a three-line pitch in her words for each kind, and the
hand-off to the Podcast Outreach Engine kit for the podcast ones.

Usage: python3 solutions/mentions.py out/entity.json [--places out/mentions.json] [--niche "..."] --out out/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solutions.common import EntityError, load_entity, one_line  # noqa: E402

KINDS = ("directory", "podcast", "community", "press")
ASK = {
    "directory": "Could {name} be listed with you? Everything you need is on {link}.",
    "podcast": "Could I come on as a guest and talk about {topic}? I would bring one story your listeners can use the same day.",
    "community": "Could I share a free resource with your members? No pitch, only something useful for {who}.",
    "press": "Could I send you a short story idea about {topic}? I can share details and photos within a day.",
}
PODCAST_KIT = "https://github.com/RochaStone/podcast-outreach-engine"
SEARCHES = {
    "directory": ["best {niche} directory", "{niche} near {where} list", "top {niche} {where}"],
    "podcast": ["{niche} podcast", "podcast for {who}", "podcast guest application {niche}"],
    "community": ["{niche} community", "{who} newsletter", "{who} group"],
    "press": ["{where} local news features small business", "{niche} magazine contributor", "{niche} roundup"],
}


def clean_places(raw: list) -> tuple[list[dict], int]:
    """Keep only real-looking places (a URL and where it was found). Returns (places, dropped)."""
    keep, dropped, seen = [], 0, set()
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict):
            dropped += 1
            continue
        url = str(p.get("url") or "").strip()
        name = str(p.get("name") or "").strip()
        via = str(p.get("found_via") or "").strip()
        kind = str(p.get("kind") or "").strip().lower()
        if not (name and via and re.match(r"^https?://[^\s<>\"]+\.[^\s<>\"]+", url)) or url.lower() in seen:
            dropped += 1
            continue
        seen.add(url.lower())
        keep.append({"name": name, "url": url, "kind": kind if kind in KINDS else "community",
                     "why": str(p.get("why") or "").strip(), "found_via": via})
    return keep[:10], dropped + max(0, len(keep) - 10)


def pitch(kind: str, ent: dict) -> list[str]:
    me = ent["person"] or ent["name"]
    first = f"Hi, I'm {me}. {one_line(ent)}"
    second = ent["proof"][0] if ent["proof"] else (
        f"Your audience is who I serve: {ent['for_whom']}." if ent["for_whom"] else "I think your audience would like this.")
    topic = ent["what"] or ent["offer"] or "my work"
    third = ASK[kind].format(name=ent["name"], link=ent["site"] or "my page", topic=topic.rstrip("."),
                             who=ent["for_whom"] or "your members")
    return [first, second, third]


def checklist(niche: str, ent: dict) -> str:
    fill = {"niche": niche, "where": ent["where"] or "your city", "who": ent["for_whom"] or "your buyers"}
    out = ["No web search this time, so here are the places to look and the exact searches to type.",
           "Pick three. Real places only, ones your buyers already read.", ""]
    for kind in KINDS:
        out.append(f"### {kind.title()}")
        out += [f"- [ ] search: `{s.format(**fill)}`" for s in SEARCHES[kind]]
        out.append("")
    return "\n".join(out)


def render_plan(ent: dict, niche: str, places: list[dict], dropped: int) -> str:
    out = [f"# Your mentions plan: {ent['name']}", "",
           "Assistants trust what other sites say about you more than what you say about yourself.",
           "Aim for three new mentions this month. Use the same name, the same one line and the same link every time.", ""]
    if places:
        out += [f"## Ten places for {niche}" if len(places) >= 10 else f"## {len(places)} places for {niche}", ""]
        for i, p in enumerate(places, 1):
            why = f" {p['why']}" if p["why"] else ""
            out.append(f"{i}. **{p['name']}** ({p['kind']}) {p['url']}{why}  \n   found via: {p['found_via']}")
        if dropped:
            out += ["", f"{dropped} more were left out because they had no link or no source. Nothing here is guessed."]
        out.append("")
    else:
        out += ["## Where to look", "", checklist(niche, ent)]
    out += ["## Your three-line pitches", "", "Copy the one that fits. Change any word that is not yours.", ""]
    kinds = [k for k in KINDS if not places or any(p["kind"] == k for p in places)]
    for k in kinds:
        out += [f"### For a {k}", ""] + [f"> {line}  " for line in pitch(k, ent)] + [""]
    out += ["## Podcasts, properly",
            f"For the podcasts, the sibling kit Podcast Outreach Engine finds shows that fit and drafts each pitch: {PODCAST_KIT}", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write her third-party mentions plan")
    ap.add_argument("entity", type=Path)
    ap.add_argument("--places", type=Path, help="out/mentions.json from a web search (real places only)")
    ap.add_argument("--niche", help="her niche, in her words (defaults to the places file, then 'your niche')")
    ap.add_argument("--out", type=Path, default=Path("out"))
    args = ap.parse_args(argv)
    try:
        ent = load_entity(args.entity)
    except EntityError as exc:
        print(exc, file=sys.stderr)
        return 2
    places, dropped, niche = [], 0, args.niche or ""
    if args.places:
        try:
            data = json.loads(args.places.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"Could not read {args.places} ({exc}).", file=sys.stderr)
            return 2
        places, dropped = clean_places(data.get("places") if isinstance(data, dict) else data)
        niche = niche or (str(data.get("niche") or "") if isinstance(data, dict) else "")
    niche = niche or ent["what"] or "your niche"
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "mentions-plan.md"
    path.write_text(render_plan(ent, niche, places, dropped), encoding="utf-8")
    print(f"Mentions plan: {path} ({len(places)} places" + (f", {dropped} left out" if dropped else "") + ")"
          if places else f"Mentions plan: {path} (a checklist to search yourself)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
