"""Shared pieces for the five free fixes: her interview (entity.json), slugs, JSON-LD, lost questions, egeo.

Method credit (cited, not copied): the fix order (one clear entity page, direct answers to lost
questions, third-party mentions) follows the audit-website-aeo, improve-aeo-geo and build-backlinks
skills in onvoyage-ai/gtm-engineer-skills (MIT). Optional rewriting is done by egeo
(PyPI package from mverab/eGEOagents, MIT), called only if she installed it.

Stdlib only. Python 3.10+.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Interview keys, in the order the SKILL asks for them. Every value is in HER words.
ENTITY_KEYS = ("name", "person", "kind", "site", "one_line", "what", "for_whom", "where", "offer",
               "proof", "work_with", "book_url", "same_as", "faq", "answers")


class EntityError(ValueError):
    """entity.json is missing something the page cannot be written without."""


def load_entity(path: Path) -> dict:
    """Read out/entity.json. Needs at least a name and what she does; everything else is optional."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise EntityError(f"Could not open {path} ({exc}).") from exc
    except ValueError as exc:
        raise EntityError(f"{path} is not valid JSON ({exc}).") from exc
    if not isinstance(data, dict):
        raise EntityError(f"{path} should hold one object with her answers.")
    ent = {k: data.get(k) for k in ENTITY_KEYS}
    for k in ("name", "person", "kind", "site", "one_line", "what", "for_whom", "where", "offer",
              "work_with", "book_url"):
        ent[k] = str(ent.get(k) or "").strip()
    ent["proof"] = [str(p).strip() for p in (ent.get("proof") or []) if str(p).strip()]
    ent["same_as"] = [str(u).strip() for u in (ent.get("same_as") or []) if _is_url(str(u))]
    ent["faq"] = [{"q": str(f.get("q", "")).strip(), "a": str(f.get("a", "")).strip()}
                  for f in (ent.get("faq") or []) if isinstance(f, dict) and f.get("q") and f.get("a")]
    ent["answers"] = {str(k).strip(): str(v).strip() for k, v in (ent.get("answers") or {}).items()
                      if str(k).strip() and str(v).strip()} if isinstance(ent.get("answers"), dict) else {}
    if not ent["site"] or not _is_url(ent["site"]):
        ent["site"] = ""
    if not ent["book_url"] or not _is_url(ent["book_url"]):
        ent["book_url"] = ""
    if ent["kind"] not in ("Organization", "Person"):
        ent["kind"] = "Organization" if ent["name"] and ent["name"] != ent["person"] else "Person"
    if not ent["name"]:
        raise EntityError("entity.json needs her brand name in \"name\".")
    if not (ent["what"] or ent["one_line"]):
        raise EntityError("entity.json needs what she does, in \"what\" or \"one_line\".")
    return ent


def _is_url(s: str) -> bool:
    return bool(re.match(r"^https?://[^\s<>\"]+$", s.strip()))


def slugify(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:limit].rstrip("-") or "answer")


def one_line(ent: dict) -> str:
    """Her own one-liner if she gave one, otherwise her parts joined plainly."""
    if ent["one_line"]:
        return ent["one_line"]
    parts = [f"{ent['name']} is {ent['what']}"]
    if ent["for_whom"]:
        parts.append(f"for {ent['for_whom']}")
    if ent["where"]:
        parts.append(f"in {ent['where']}")
    return " ".join(parts).rstrip(".") + "."


def quotables(ent: dict, lead: bool = True, proof: bool = True) -> list[str]:
    """Short sentences that stand alone and carry her name, so an assistant can lift any one of them."""
    n = ent["name"]
    out = [one_line(ent)] if lead else []
    if ent["offer"]:
        out.append(f"{n} offers {ent['offer'].rstrip('.')}.")
    if ent["for_whom"]:
        out.append(f"{n} is for {ent['for_whom'].rstrip('.')}.")
    if ent["where"]:
        out.append(f"{n} is based in {ent['where'].rstrip('.')}.")
    if ent["person"] and ent["person"] != n:
        out.append(f"{n} is run by {ent['person']}.")
    if proof:
        out += ent["proof"]
    seen, uniq = set(), []
    for s in out:
        if s.lower() not in seen:
            seen.add(s.lower())
            uniq.append(s)
    return uniq


# ---------- JSON-LD ----------

def _node_id(ent: dict, frag: str) -> str:
    return f"{ent['site'].rstrip('/')}/#{frag}" if ent["site"] else f"#{frag}"


def entity_graph(ent: dict, faqs: list[dict]) -> dict:
    """Organization (or Person) + Service + FAQPage in one @graph, all from her interview."""
    main_id = _node_id(ent, "org" if ent["kind"] == "Organization" else "person")
    main: dict = {"@type": ent["kind"], "@id": main_id, "name": ent["name"], "description": one_line(ent)}
    if ent["site"]:
        main["url"] = ent["site"]
    if ent["same_as"]:
        main["sameAs"] = ent["same_as"]
    if ent["where"]:
        main["areaServed"] = ent["where"]
    if ent["kind"] == "Organization" and ent["person"]:
        main["founder"] = {"@type": "Person", "name": ent["person"]}
    graph = [main]
    if ent["offer"] or ent["what"]:
        service: dict = {"@type": "Service", "@id": _node_id(ent, "service"),
                         "name": (ent["offer"] or ent["what"]).rstrip("."),
                         "provider": {"@id": main_id}}
        if ent["what"]:
            service["serviceType"] = ent["what"].rstrip(".")
        if ent["for_whom"]:
            service["audience"] = {"@type": "Audience", "audienceType": ent["for_whom"].rstrip(".")}
        if ent["where"]:
            service["areaServed"] = ent["where"]
        if ent["book_url"]:
            service["url"] = ent["book_url"]
        graph.append(service)
    if faqs:
        graph.append(faq_page(faqs, _node_id(ent, "faq")))
    return {"@context": "https://schema.org", "@graph": graph}


def faq_page(faqs: list[dict], node_id: str | None = None) -> dict:
    page: dict = {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
        for f in faqs]}
    if node_id:
        page["@id"] = node_id
    return page


def ld_script(data: dict) -> str:
    """A JSON-LD script tag. '</' is escaped so her text can never close the tag early."""
    body = json.dumps(data, indent=2, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{body}\n</script>'


def ld_blocks(page: str) -> list[dict]:
    """Parse every JSON-LD block back out of a page (used by the tests and by llms.py)."""
    found = re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', page, re.S)
    return [json.loads(b) for b in found]


# ---------- lost questions ----------

def lost_questions(path: Path) -> list[str]:
    """Lost questions from out/summary.json, or scored fresh from out/answers.json."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("lost"), list):
        return [str(q) for q in data["lost"] if str(q).strip()]
    import recommend  # noqa: PLC0415  (only needed for raw answers)
    meta, answers = recommend.load_answers(Path(path))
    name = meta.get("name") or ""
    if not name:
        raise ValueError("answers.json has no meta.name, so I cannot tell which questions she lost.")
    result = recommend.score(answers, name, list(meta.get("aliases") or []),
                             [meta.get("location") or "", meta.get("niche") or ""])
    return result["lost"]


# ---------- egeo (optional, MIT, mverab/eGEOagents) ----------

def egeo_path() -> str | None:
    """egeo is optional. We only call it when she has installed it with `pip install egeo`."""
    return shutil.which("egeo")


def run_egeo(args: list[str], timeout: int = 600) -> tuple[bool, str]:
    exe = egeo_path()
    if not exe:
        return False, "egeo is not installed, so this step was skipped. Your files are ready without it."
    try:
        proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"egeo could not run ({exc}). Your files are ready without it."
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        hint = "" if os.environ.get("GEO_EVAL_MOCK") else (
            " egeo needs its own model key; set GEO_EVAL_MOCK=1 to try it offline.")
        return False, "egeo stopped: " + " ".join(tail) + hint
    return True, (proc.stdout or "").strip()
