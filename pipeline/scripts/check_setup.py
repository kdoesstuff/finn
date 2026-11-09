"""Check that every key in .env works, with one tiny request per service.

Prints a table of service, set or missing, working or failing, and a short note.
Never prints a key. Run from the repo root or pipeline/:

    python pipeline/scripts/check_setup.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finn import config  # noqa: E402

TIMEOUT = 20


def _redact(text: str) -> str:
    """Error bodies sometimes echo the request; never let a key reach the screen."""
    for name in config.SETTINGS:
        v = config.get(name, required=False)
        if v and len(v) > 8 and "KEY" in name:
            text = text.replace(v, "***")
    return text[:120]


def gemini():
    key, model = config.get("GEMINI_API_KEY"), config.get("GEMINI_MODEL")
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=TIMEOUT)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {_redact(r.text)}"
    names = [m["name"].split("/")[-1] for m in r.json().get("models", [])]
    flash = sorted(n for n in names if "flash" in n)[-4:]
    if model not in names:
        return False, f"key works, but model '{model}' not offered; Flash models available: {flash}"
    embed = [n for n in names if "embedding" in n]
    return True, f"model {model} available; embeddings: {embed[:2]}"


def openai_compatible(base, key, model, label):
    r = requests.post(f"{base.rstrip('/')}/chat/completions",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": model, "max_tokens": 5,
                            "messages": [{"role": "user", "content": "Reply with the word ok."}]},
                      timeout=TIMEOUT)
    if r.status_code != 200:
        return False, f"{label} HTTP {r.status_code}: {_redact(r.text)}"
    return True, f"{label} replied with model {model}"


def groq():
    return openai_compatible("https://api.groq.com/openai/v1", config.get("GROQ_API_KEY"),
                             config.get("GROQ_MODEL"), "Groq")


def zai():
    return openai_compatible(config.get("ZAI_BASE_URL"), config.get("ZAI_API_KEY"), config.get("ZAI_MODEL"), "Z.AI")


def openrouter():
    r = requests.get("https://openrouter.ai/api/v1/key",
                     headers={"Authorization": f"Bearer {config.get('OPENROUTER_API_KEY')}"}, timeout=TIMEOUT)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {_redact(r.text)}"
    d = r.json().get("data", {})
    return True, f"free tier: {d.get('is_free_tier')}, limit: {d.get('limit')}"


def supabase(key_name):
    url, key = config.get("SUPABASE_URL"), config.get(key_name)
    r = requests.get(f"{url.rstrip('/')}/rest/v1/", headers={"apikey": key, "Authorization": f"Bearer {key}"},
                     timeout=TIMEOUT)
    if r.status_code not in (200, 401):
        return False, f"HTTP {r.status_code}: {_redact(r.text)}"
    if r.status_code == 401:
        return False, "key rejected by the project"
    return True, f"project reachable ({'admin' if 'SERVICE' in key_name else 'public'} key)"


def sentry(name):
    dsn = config.get(name)
    ok = dsn.startswith("https://") and "@" in dsn and ".sentry.io/" in dsn
    return ok, "DSN format looks right" if ok else "does not look like a Sentry DSN"


CHECKS = [
    ("Gemini", ["GEMINI_API_KEY"], gemini),
    ("Groq", ["GROQ_API_KEY"], groq),
    ("Z.AI (GLM)", ["ZAI_API_KEY"], zai),
    ("OpenRouter", ["OPENROUTER_API_KEY"], openrouter),
    ("Supabase public key", ["SUPABASE_URL", "SUPABASE_ANON_KEY"], lambda: supabase("SUPABASE_ANON_KEY")),
    ("Supabase admin key", ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"], lambda: supabase("SUPABASE_SERVICE_ROLE_KEY")),
    ("Sentry (API)", ["SENTRY_DSN_API"], lambda: sentry("SENTRY_DSN_API")),
    ("Sentry (web)", ["SENTRY_DSN_WEB"], lambda: sentry("SENTRY_DSN_WEB")),
]


def main() -> int:
    env = config.ROOT / ".env"
    print(f".env file: {'found' if env.exists() else 'NOT FOUND'} at {env}\n")
    rows, failures = [], 0
    for label, needs, fn in CHECKS:
        missing = [n for n in needs if not config.get(n, required=False)]
        if missing:
            rows.append((label, "missing", "-", f"set {', '.join(missing)}"))
            failures += 1
            continue
        try:
            ok, note = fn()
        except Exception as exc:
            ok, note = False, f"{type(exc).__name__}: {_redact(str(exc))}"
        rows.append((label, "set", "OK" if ok else "FAIL", note))
        failures += not ok

    width = max(len(r[0]) for r in rows)
    for label, state, result, note in rows:
        print(f"{label:<{width}}  {state:<7}  {result:<4}  {note}")
    print(f"\n{len(rows) - failures} of {len(rows)} working.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
