"""Settings and secrets, read the same way everywhere.

On a laptop, values come from a `.env` file at the repo root (git-ignored).
In GitHub Actions, Render or Vercel, the same names come from the platform's
encrypted environment variables. Real environment variables win over `.env`,
so a cloud run never picks up a stale local file.

Values are never printed or logged; `describe()` reports only whether each one is set.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional in the cloud, where env vars are already set
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[2]

if load_dotenv is not None:
    load_dotenv(ROOT / ".env", override=False)

# name -> what it is for. Keep in step with .env.example.
SETTINGS = {
    "GEMINI_API_KEY": "Google AI Studio: reading long documents (results PDFs, transcripts) and embeddings",
    "GEMINI_MODEL": "Gemini model for bulk extraction (default gemini-2.5-flash)",
    "GROQ_API_KEY": "Groq: fast, cheap classification of leftover filings and one-line summaries",
    "GROQ_MODEL": "Groq model (default openai/gpt-oss-20b)",
    "ZAI_API_KEY": "Z.AI GLM: promise-vs-delivery reasoning, and backup for Gemini",
    "ZAI_BASE_URL": "Z.AI OpenAI-compatible base URL (default https://api.z.ai/api/paas/v4)",
    "ZAI_MODEL": "GLM model (default glm-4.5-flash)",
    "OPENROUTER_API_KEY": "OpenRouter: last-resort fallback across free models",
    "SUPABASE_URL": "Supabase project URL (Mumbai region)",
    "SUPABASE_ANON_KEY": "Supabase public key; safe in the browser only because every table has row-level security",
    "SUPABASE_SERVICE_ROLE_KEY": "Supabase admin key; pipeline and API only, never the frontend",
    "SENTRY_DSN_API": "Sentry error tracking for the Python API",
    "SENTRY_DSN_WEB": "Sentry error tracking for the web app",
}

DEFAULTS = {
    "GEMINI_MODEL": "gemini-2.5-flash",
    "GROQ_MODEL": "openai/gpt-oss-20b",
    "ZAI_BASE_URL": "https://api.z.ai/api/paas/v4",
    "ZAI_MODEL": "glm-4.5-flash",
}


class MissingSetting(RuntimeError):
    pass


def get(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name) or DEFAULTS.get(name)
    if required and not value:
        raise MissingSetting(f"{name} is not set. Add it to .env (local) or the platform's secrets. Used for: "
                             f"{SETTINGS.get(name, 'unknown')}")
    return value


def describe() -> list[tuple[str, bool, str]]:
    """(name, is set, purpose) for every setting. Never returns values."""
    return [(n, bool(os.environ.get(n) or DEFAULTS.get(n)), purpose) for n, purpose in SETTINGS.items()]
