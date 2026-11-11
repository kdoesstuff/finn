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

ROOT = Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional in the cloud, where env vars are already set
    pass
else:
    load_dotenv(ROOT / ".env", override=False)

# name -> what it is for. Keep in step with .env.example.
SETTINGS = {
    # Model routing: each role names one model; the code asks for a role, never a model name.
    "GEMINI_API_KEY": "Google AI Studio key (AQ. format), used natively, never via the OpenAI-compatible route",
    "GEMINI_MODEL": "Reads documents in volume: results PDFs, transcripts, annual reports",
    "GEMINI_OVERFLOW_MODEL": "Second document reader with its own daily quota, used when the first runs out",
    "GEMINI_QUALITY_MODEL": "Rescue tier for documents the volume models get wrong (small daily quota)",
    "GEMINI_QUALITY_FALLBACK_MODEL": "Second rescue model with its own small quota",
    "GEMINI_VOLUME_MODEL": "Short jobs only (16K tokens/min): backup for the fast Groq jobs",
    "GEMINI_EMBED_MODEL": "Embeddings for retrieval over transcripts and reports",
    "GEMINI_EMBED_DIM": "Embedding size (Matryoshka truncation keeps the vector index small)",
    "GROQ_API_KEY": "Groq key: fast jobs and the injection guard",
    "GROQ_MODEL": "Fast jobs: classifying leftover filings, one-line summaries",
    "GROQ_FALLBACK_MODEL": "Second fast model with its own daily quota",
    "GUARD_MODEL": "Prompt-injection screen for untrusted filing text (on Groq)",
    "GLM_API_KEY": "GLM through an OpenAI-compatible gateway (Hyde)",
    "GLM_BASE_URL": "The gateway's OpenAI-compatible base URL, ending in /v1",
    "GLM_MODEL": "Reasoning: promise vs delivery, narrative vs numbers, bull and bear",
    "OPENROUTER_API_KEY": "OpenRouter key, capped at $0 so only free models can run",
    "OPENROUTER_MODEL": "Last-resort fallback model",
    "SUPABASE_URL": "Supabase project URL (Mumbai region)",
    "SUPABASE_PUBLISHABLE_KEY": "Supabase publishable key (sb_publishable_...); safe in the browser only because "
                                "every table has row-level security",
    "SUPABASE_SECRET_KEY": "Supabase secret key (sb_secret_...); pipeline and API only, never the frontend",
    "SENTRY_DSN_API": "Sentry error tracking for the Python API",
    "SENTRY_DSN_WEB": "Sentry error tracking for the web app",
}

# Fallbacks only. The real choice of model lives in .env, so changing a model is a
# one-line change there, never a code change. check_setup.py confirms each one exists.
DEFAULTS = {
    "GEMINI_MODEL": "gemini-3.5-flash-lite",
    "GEMINI_OVERFLOW_MODEL": "gemini-3.1-flash-lite",
    "GEMINI_QUALITY_MODEL": "gemini-3.8-flash",
    "GEMINI_QUALITY_FALLBACK_MODEL": "gemini-3.6-flash",
    "GEMINI_VOLUME_MODEL": "gemma-4-31b-it",
    "GEMINI_EMBED_MODEL": "gemini-embedding-2",
    "GEMINI_EMBED_DIM": "768",
    "GROQ_MODEL": "openai/gpt-oss-120b",
    "GROQ_FALLBACK_MODEL": "openai/gpt-oss-20b",
    "GUARD_MODEL": "meta-llama/llama-prompt-guard-2-86m",
    "OPENROUTER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b:free",
}


class MissingSetting(RuntimeError):
    pass


def get(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name) or DEFAULTS.get(name)
    if required and not value:
        raise MissingSetting(f"{name} is not set. Add it to .env (local) or the platform's secrets. Used for: "
                             f"{SETTINGS.get(name, 'unknown')}")
    return value


def require(name: str) -> str:
    """A setting that must be present (from the environment, .env or the defaults above)."""
    value = get(name, required=False)
    if not value:
        raise MissingSetting(f"{name} is not set. Add it to .env (local) or the platform's secrets. Used for: "
                             f"{SETTINGS.get(name, 'unknown')}")
    return value


def describe() -> list[tuple[str, bool, str]]:
    """(name, is set, purpose) for every setting. Never returns values."""
    return [(n, bool(os.environ.get(n) or DEFAULTS.get(n)), purpose) for n, purpose in SETTINGS.items()]
