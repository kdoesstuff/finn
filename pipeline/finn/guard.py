"""The prompt-injection screen in front of every model call that reads untrusted document text (task C2).

Llama Prompt Guard 2 (GUARD_MODEL, served by Groq) classifies short texts as benign or malicious.
Its context is small (512 tokens), so a document is screened in overlapping windows of about
WINDOW_WORDS words. A long document is not screened whole: at most MAX_WINDOWS windows per call,
always the first and the last, then every window containing phrases typical of injections
(SUSPICIOUS), then evenly spaced ones. One flagged window stops the call before any model sees the
document (InjectionDetected).

Fail-closed: if the guard is configured but cannot answer, the call fails (ModelError) and the
document waits for the next run, rather than reaching a model unscreened. Without GROQ_API_KEY the
screen is skipped with a warning (a laptop without the key); the other defences still hold: the
document sits between markers it cannot contain, the model is told it is data, no tools exist, the
answer must match a schema, and callers check every quote against the source.
"""

from __future__ import annotations

import logging
import re
import time

import psycopg

from . import config, llm

log = logging.getLogger("finn.guard")

WINDOW_WORDS = 300   # Prompt Guard 2 reads 512 tokens; ~300 English words stays inside that
OVERLAP_WORDS = 50   # an instruction split across two windows still lands whole in one of them
MAX_WINDOWS = 48     # per call: about 14,000 words screened in full, longer documents sampled
THRESHOLD = 0.8      # a score at or above this is an injection
PROMPT_VERSION = "guard-v1"
SUSPICIOUS = re.compile(
    r"ignore (all |any |the )?(previous|prior|above)|disregard|system prompt|you are (now )?(an?|the) |"
    r"as an ai|new instructions|instead,? (output|reply|respond|return)|jailbreak|do not follow|"
    r"assistant:|<\|im_start\|>|\[inst\]|override", re.IGNORECASE)


def windows(document: str) -> list[str]:
    words = document.split()
    if not words:
        return []
    step = WINDOW_WORDS - OVERLAP_WORDS
    out = []
    for start in range(0, len(words), step):
        out.append(" ".join(words[start:start + WINDOW_WORDS]))
        if start + WINDOW_WORDS >= len(words):
            break
    return out


def choose(all_windows: list[str], limit: int = MAX_WINDOWS) -> list[int]:
    """Indexes of the windows to screen, in document order."""
    n = len(all_windows)
    if n <= limit:
        return list(range(n))
    chosen = {0, n - 1}
    for i, w in enumerate(all_windows):
        if len(chosen) >= limit:
            break
        if SUSPICIOUS.search(w):
            chosen.add(i)
    spare = limit - len(chosen)
    if spare > 0:
        step = n / (spare + 1)
        for k in range(1, spare + 1):
            chosen.add(min(n - 1, int(k * step)))
    return sorted(chosen)


def score(text: str) -> float:
    """The guard's probability that `text` is an injection or jailbreak. Raises llm._Fail."""
    key = config.get("GROQ_API_KEY", required=False) or ""
    model = llm.Model("groq", config.require("GUARD_MODEL"), key)
    data = llm._post(model, f"{llm.GROQ_URL}/chat/completions", {"Authorization": f"Bearer {key}"},
                     {"model": model.name, "messages": [{"role": "user", "content": text}]})
    choices = data.get("choices") or []
    content = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    try:
        return float(content)
    except ValueError:
        label = content.upper()
        if any(w in label for w in ("MALICIOUS", "INJECTION", "JAILBREAK", "UNSAFE")):
            return 1.0
        if "BENIGN" in label or "SAFE" in label:
            return 0.0
        raise llm._Fail("refused", f"groq:{model.name} gave an answer that is not a score") from None


def screen(conn: psycopg.Connection | None, document: str, *, h: str, prompt_version: str = PROMPT_VERSION,
           db_role: str = "finn_ingest") -> None:
    """Raise InjectionDetected if any screened window is flagged; ModelError if the guard cannot answer."""
    if not config.get("GROQ_API_KEY", required=False):
        log.warning("guard: GROQ_API_KEY is not set; the injection screen is skipped for this call")
        return
    model_name = config.require("GUARD_MODEL")
    all_windows = windows(document)
    picked = choose(all_windows)
    started = time.monotonic()
    for i in picked:
        try:
            s = score(all_windows[i])
        except llm._Fail as fail:
            llm.log_call(conn, role="guard", model=model_name, prompt_version=PROMPT_VERSION, h=h, ok=False,
                         latency_ms=int((time.monotonic() - started) * 1000), error=f"guard unavailable: {fail}",
                         db_role=db_role)
            raise llm.ModelError(f"the injection screen could not run ({fail}); the document was not sent") from None
        if s >= THRESHOLD:
            llm.log_call(conn, role="guard", model=model_name, prompt_version=PROMPT_VERSION, h=h, ok=False,
                         latency_ms=int((time.monotonic() - started) * 1000),
                         error=f"flagged window {i + 1} of {len(all_windows)} (score {s:.2f})", db_role=db_role)
            raise llm.InjectionDetected(f"the injection screen flagged window {i + 1} of {len(all_windows)} "
                                        f"(score {s:.2f}) for {prompt_version}; no model was asked")
    if len(picked) < len(all_windows):
        log.info("guard: screened %d of %d windows (first, last, suspicious, evenly spaced)",
                 len(picked), len(all_windows))
    llm.log_call(conn, role="guard", model=model_name, prompt_version=PROMPT_VERSION, h=h, ok=True,
                 latency_ms=int((time.monotonic() - started) * 1000), db_role=db_role)
