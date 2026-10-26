#!/usr/bin/env python3
"""API mode: ask ChatGPT (OpenAI) and Perplexity the buyer questions.

Reads keys from the environment (copy .env.example to .env and fill it, or export them):
  OPENAI_API_KEY, PERPLEXITY_API_KEY
Optional: OPENAI_MODEL, PERPLEXITY_MODEL

Usage:
  python3 ask_api.py out/questions.json --out out/answers.json
questions.json is {"meta": {...}, "questions": ["...", ...]} (the skill writes it).
New answers are added to out/answers.json, keeping anything already there.
Stdlib only. No SDK. Nothing leaves your machine except the questions themselves.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OPENAI_URL = "https://api.openai.com/v1/responses"
PPLX_URL = "https://api.perplexity.ai/chat/completions"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
PPLX_MODEL = os.environ.get("PERPLEXITY_MODEL", "sonar")
SYSTEM = ("Answer the way you would for any member of the public asking this. "
          "Name specific businesses or people where you can.")


def load_dotenv(path: Path) -> None:
    """Read KEY=value lines from .env into the environment, without overriding what is set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def post_json(url: str, key: str, body: dict, timeout: int = 90) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def openai_text(data: dict) -> str:
    """Pull the answer text out of an OpenAI Responses API reply."""
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()
    parts = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for c in item.get("content") or []:
            if c.get("type") in ("output_text", "text") and c.get("text"):
                parts.append(c["text"])
    return "\n".join(parts).strip()


def pplx_text(data: dict) -> str:
    """Pull the answer text (plus cited links) out of a Perplexity reply."""
    choices = data.get("choices") or []
    text = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    cites = data.get("citations") or []
    if cites:
        text += "\n\nSources:\n" + "\n".join(f"- {c}" for c in cites if isinstance(c, str))
    return text


def ask_openai(q: str, key: str) -> str:
    body = {"model": OPENAI_MODEL, "instructions": SYSTEM, "input": q,
            "tools": [{"type": "web_search"}]}
    try:
        return openai_text(post_json(OPENAI_URL, key, body))
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        body.pop("tools")  # model without web search: ask plainly and say so
        return "[answered without web search] " + openai_text(post_json(OPENAI_URL, key, body))


def ask_pplx(q: str, key: str) -> str:
    body = {"model": PPLX_MODEL, "messages": [
        {"role": "system", "content": SYSTEM}, {"role": "user", "content": q}]}
    return pplx_text(post_json(PPLX_URL, key, body))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ask the buyer questions through the APIs")
    ap.add_argument("questions", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/answers.json"))
    ap.add_argument("--env", type=Path, default=Path(__file__).resolve().parent / ".env")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between calls")
    args = ap.parse_args(argv)

    load_dotenv(args.env)
    try:
        qdata = json.loads(args.questions.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Could not read {args.questions}: {exc}", file=sys.stderr)
        return 2
    questions = [q for q in qdata.get("questions", []) if isinstance(q, str) and q.strip()]
    providers = []
    if os.environ.get("OPENAI_API_KEY"):
        providers.append(("ChatGPT", ask_openai, os.environ["OPENAI_API_KEY"]))
    if os.environ.get("PERPLEXITY_API_KEY"):
        providers.append(("Perplexity", ask_pplx, os.environ["PERPLEXITY_API_KEY"]))
    if not providers:
        print("No OPENAI_API_KEY or PERPLEXITY_API_KEY set. Use browser, self or paste mode instead.",
              file=sys.stderr)
        return 3
    if not questions:
        print("No questions found in the questions file.", file=sys.stderr)
        return 2

    existing = {"meta": qdata.get("meta", {}), "answers": []}
    if args.out.exists():
        try:
            prev = json.loads(args.out.read_text(encoding="utf-8"))
            existing["answers"] = prev if isinstance(prev, list) else prev.get("answers", [])
            if isinstance(prev, dict) and prev.get("meta"):
                existing["meta"] = {**prev["meta"], **existing["meta"]}
        except ValueError as exc:
            print(f"Existing {args.out} is not valid JSON ({exc}). Not overwriting it.", file=sys.stderr)
            return 2

    failures = 0
    for source, fn, key in providers:
        for q in questions:
            try:
                text = fn(q, key)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                failures += 1
                detail = getattr(exc, "code", "") or getattr(exc, "reason", "") or exc
                print(f"  {source}: could not ask '{q}' ({detail})", file=sys.stderr)
                continue
            existing["answers"].append({"question": q, "source": f"{source} (API)", "answer": text})
            print(f"  {source}: {q}")
            time.sleep(args.pause)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"Saved {len(existing['answers'])} answers to {args.out} ({failures} failed).")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
