"""Settings: the service refuses to start without a database URL or with a weak session secret,
and maps each allow-listed origin to its deployment. Messages name the setting, never its value."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from api.settings import ConfigError, Settings, parse_origins, short_version
from api.tests.helpers import ROOT

GOOD = {"SUPABASE_DB_URL": "postgresql://user:not-a-real-password@db.invalid:5432/postgres",
        "SESSION_SECRET": "x" * 32,
        "ALLOWED_ORIGINS_CORE": "https://finn-core.test.invalid",
        "ALLOWED_ORIGINS_FULL": "https://finn.test.invalid, https://finn-alt.test.invalid/"}


def test_settings_from_the_environment():
    s = Settings.from_env(GOOD)
    assert s.origins_core == ("https://finn-core.test.invalid",)
    assert s.origins_full == ("https://finn.test.invalid", "https://finn-alt.test.invalid")
    assert s.deployment_for("https://finn-core.test.invalid") == "core"
    assert s.deployment_for("https://finn-alt.test.invalid") == "full"
    assert s.deployment_for("https://other.test.invalid") is None and s.deployment_for(None) is None
    assert (s.version, s.environment, s.client_ip_header, s.docs, s.sentry_dsn) == \
        ("unknown", "development", None, False, None)
    assert str(s.demo_investor_id) == "d3e0d3e0-0000-4000-8000-000000000001"


def test_on_render_the_commit_environment_and_client_header_are_used():
    s = Settings.from_env({**GOOD, "RENDER": "true", "RENDER_GIT_COMMIT": "bf56e5f0c3d9a1b2c3d4e5f6a7b8c9d0e1f2a3b4"})
    assert (s.version, s.environment, s.client_ip_header) == ("bf56e5f", "production", "true-client-ip")
    s = Settings.from_env({**GOOD, "RENDER": "true", "CLIENT_IP_HEADER": "CF-Connecting-IP", "API_DOCS": "1",
                           "SENTRY_ENVIRONMENT": "review"})
    assert (s.client_ip_header, s.docs, s.environment) == ("cf-connecting-ip", True, "review")


@pytest.mark.parametrize("commit,shown", [(None, "unknown"), ("", "unknown"), ("main", "unknown"),
                                          ("ABCDEF0", "unknown"), ("abc1234", "abc1234")])
def test_version_is_a_short_commit_or_unknown(commit, shown):
    assert short_version(commit) == shown


@pytest.mark.parametrize("secret", ["", "x" * 31])
def test_a_missing_or_short_session_secret_stops_start_up(secret):
    with pytest.raises(ConfigError, match="SESSION_SECRET must be at least 32 bytes"):
        Settings.from_env({**GOOD, "SESSION_SECRET": secret})


def test_a_missing_database_url_stops_start_up():
    with pytest.raises(ConfigError, match="SUPABASE_DB_URL is not set"):
        Settings.from_env({k: v for k, v in GOOD.items() if k != "SUPABASE_DB_URL"})


@pytest.mark.parametrize("raw", ["*", "https://*.vercel.app", "http://finn.test.invalid", "finn.test.invalid",
                                 "https://finn.test.invalid/app", "https://finn.test.invalid?x=1",
                                 "https://user:pw@finn.test.invalid", "https://finn.test.invalid:99999", "ftp://x.test"])
def test_origins_must_be_exact_https_origins(raw):
    with pytest.raises(ConfigError, match="ALLOWED_ORIGINS_CORE"):
        parse_origins("ALLOWED_ORIGINS_CORE", raw)


def test_local_development_origins_and_empty_lists_are_allowed():
    assert parse_origins("X", "http://localhost:5173, http://127.0.0.1:4173,http://[::1]:5173") == \
        ("http://localhost:5173", "http://127.0.0.1:4173", "http://[::1]:5173")
    assert parse_origins("X", " , ") == ()
    assert parse_origins("X", "HTTPS://FINN.Test.Invalid") == ("https://finn.test.invalid",)


def test_an_origin_cannot_belong_to_both_deployments():
    with pytest.raises(ConfigError, match="both deployments"):
        Settings.from_env({**GOOD, "ALLOWED_ORIGINS_FULL": GOOD["ALLOWED_ORIGINS_CORE"]})


def test_secrets_never_appear_in_the_settings_repr():
    text = repr(Settings.from_env({**GOOD, "SENTRY_DSN_API": "https://key@o0.ingest.invalid/0"}))
    assert "not-a-real-password" not in text and "xxxxxxxx" not in text and "ingest.invalid" not in text


def run_main(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    clean = {k: v for k, v in os.environ.items() if k not in GOOD and not k.startswith(("RENDER", "SENTRY"))}
    return subprocess.run([sys.executable, "-c", "import api.main"], cwd=ROOT, capture_output=True, text=True,
                          env={**clean, "PYTHONPATH": f"{ROOT}{os.pathsep}{ROOT / 'pipeline'}", **env},
                          timeout=60, check=False)


def test_the_service_refuses_to_start_on_a_weak_secret_without_printing_secrets():
    out = run_main({**GOOD, "SESSION_SECRET": "short"})
    assert out.returncode != 0
    assert "SESSION_SECRET must be at least 32 bytes" in out.stderr
    assert "not-a-real-password" not in out.stderr + out.stdout


def test_the_service_starts_with_good_settings_and_no_database_reachable():
    out = run_main(GOOD)  # db.invalid does not resolve; the pool is opened only on first use
    assert out.returncode == 0, out.stderr
