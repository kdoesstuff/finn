"""Check that every key in .env works, with one tiny request per service.

Prints a table of service, set or missing, working or failing, and a short note.
Never prints a key. Run from the repo root or pipeline/:

    python pipeline/scripts/check_setup.py            # test every key
    python pipeline/scripts/check_setup.py --models   # also list the models each key can use
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


GEMINI_ROLES = ("GEMINI_MODEL", "GEMINI_OVERFLOW_MODEL", "GEMINI_QUALITY_MODEL", "GEMINI_QUALITY_FALLBACK_MODEL",
                "GEMINI_VOLUME_MODEL", "GEMINI_EMBED_MODEL")


def gemini():
    key = config.get("GEMINI_API_KEY")
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=TIMEOUT)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {_redact(r.text)}"
    names = {m["name"].split("/")[-1] for m in r.json().get("models", [])}
    wanted = [config.get(n) for n in GEMINI_ROLES]
    missing = [w for w in wanted if w not in names]
    if missing:
        return False, f"key works, but not offered: {missing} (run with --models for the list)"
    return True, f"all {len(wanted)} Gemini models offered: " + ", ".join(wanted)


def available_models(base, key) -> list[str]:
    try:
        r = requests.get(f"{base.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
        return sorted(m.get("id", "") for m in r.json().get("data", [])) if r.status_code == 200 else []
    except Exception:
        return []


def openai_compatible(base, key, model, label):
    r = requests.post(f"{base.rstrip('/')}/chat/completions",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": model, "max_tokens": 5,
                            "messages": [{"role": "user", "content": "Reply with the word ok."}]},
                      timeout=TIMEOUT)
    if r.status_code != 200:
        offered = available_models(base, key)
        hint = f"; models this key can use: {offered[:12]}" if offered else ""
        return False, f"{label} HTTP {r.status_code}: {_redact(r.text)}{hint}"
    return True, f"{label} replied with model {model}"


def groq():
    base, key = "https://api.groq.com/openai/v1", config.get("GROQ_API_KEY")
    ok, note = openai_compatible(base, key, config.get("GROQ_MODEL"), "Groq")
    if not ok:
        return ok, note
    offered = set(available_models(base, key))
    missing = [config.get(n) for n in ("GROQ_FALLBACK_MODEL", "GUARD_MODEL") if config.get(n) not in offered]
    if missing:
        return False, f"{note}; but not offered: {missing}"
    return True, f"{note}; fallback and guard models offered"


def glm():
    return openai_compatible(config.get("GLM_BASE_URL"), config.get("GLM_API_KEY"), config.get("GLM_MODEL"), "GLM")


def openrouter():
    r = requests.get("https://openrouter.ai/api/v1/key",
                     headers={"Authorization": f"Bearer {config.get('OPENROUTER_API_KEY')}"}, timeout=TIMEOUT)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {_redact(r.text)}"
    d = r.json().get("data", {})
    model = config.get("OPENROUTER_MODEL")
    offered = available_models("https://openrouter.ai/api/v1", config.get("OPENROUTER_API_KEY"))
    if offered and model not in offered:
        return False, f"model {model} not offered (run with --models)"
    return True, f"{model} offered; credit limit {d.get('limit')} (free models only)"


def supabase(key_name):
    """Supabase's new keys (sb_publishable_/sb_secret_) are not JWTs: they go in the `apikey`
    header only. The auth settings endpoint accepts any valid project key."""
    url, key = config.get("SUPABASE_URL").rstrip("/"), config.get(key_name)
    prefix = "sb_secret_" if "SECRET" in key_name else "sb_publishable_"
    if not key.startswith(prefix):
        return False, f"expected a key starting with {prefix}"
    r = requests.get(f"{url}/auth/v1/settings", headers={"apikey": key}, timeout=TIMEOUT)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {_redact(r.text)}"
    return True, f"project reachable with the {'secret' if 'SECRET' in key_name else 'publishable'} key"


def sentry(name):
    dsn = config.get(name)
    ok = dsn.startswith("https://") and "@" in dsn and ".sentry.io/" in dsn
    return ok, "DSN format looks right" if ok else "does not look like a Sentry DSN"


CHECKS = [
    ("Gemini", ["GEMINI_API_KEY"], gemini),
    ("Groq", ["GROQ_API_KEY"], groq),
    ("GLM (gateway)", ["GLM_API_KEY", "GLM_BASE_URL", "GLM_MODEL"], glm),
    ("OpenRouter", ["OPENROUTER_API_KEY"], openrouter),
    ("Supabase publishable", ["SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"], lambda: supabase("SUPABASE_PUBLISHABLE_KEY")),
    ("Supabase secret", ["SUPABASE_URL", "SUPABASE_SECRET_KEY"], lambda: supabase("SUPABASE_SECRET_KEY")),
    ("Sentry (API)", ["SENTRY_DSN_API"], lambda: sentry("SENTRY_DSN_API")),
    ("Sentry (web)", ["SENTRY_DSN_WEB"], lambda: sentry("SENTRY_DSN_WEB")),
]


def list_models() -> None:
    """Every model each configured key can use, so .env can name one that exists."""
    print("\nModels available to your keys (the one set in .env is marked *):")
    key = config.get("GEMINI_API_KEY", required=False)
    if key:
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                             headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=TIMEOUT)
            names = sorted(m["name"].split("/")[-1] for m in r.json().get("models", [])
                           if "generateContent" in m.get("supportedGenerationMethods", []))
            embeds = sorted(m["name"].split("/")[-1] for m in r.json().get("models", [])
                            if "embedContent" in m.get("supportedGenerationMethods", []))
            marks = {config.get(n) for n in GEMINI_ROLES}
            print("  Gemini (text):", ", ".join(n + ("*" if n in marks else "") for n in names))
            print("  Gemini (embeddings):", ", ".join(n + ("*" if n in marks else "") for n in embeds))
        except Exception as exc:
            print(f"  Gemini: could not list ({type(exc).__name__})")
    for label, base, key_name, model_name in [
        ("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "GROQ_MODEL"),
        ("GLM gateway", config.get("GLM_BASE_URL", required=False), "GLM_API_KEY", "GLM_MODEL"),
        ("OpenRouter (free only)", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "OPENROUTER_MODEL"),
    ]:
        key = config.get(key_name, required=False)
        if not (key and base):
            continue
        names = available_models(base, key)
        if label.startswith("OpenRouter"):
            names = [n for n in names if n.endswith(":free")]
        marks = {config.get(model_name, required=False)} if model_name else set()
        if label == "Groq":
            marks |= {config.get("GROQ_FALLBACK_MODEL", required=False), config.get("GUARD_MODEL", required=False)}
        print(f"  {label}:", ", ".join(n + ("*" if n in marks else "") for n in names) or "(none listed)")


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
    if "--models" in sys.argv:
        list_models()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
