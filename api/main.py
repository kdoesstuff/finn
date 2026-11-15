"""The service entry point, as Render starts it:

    PYTHONPATH=pipeline uvicorn api.main:app --host 0.0.0.0 --port $PORT --no-proxy-headers

Settings are read and checked here, so a missing or unsafe setting stops the deploy with a message
naming it (never its value). Sentry starts before the app is built, as its integrations require.
"""

from __future__ import annotations

import logging

from . import observability
from .app import create_app
from .settings import Settings

observability.configure_logging()

settings = Settings.from_env()
if observability.init(settings):
    logging.getLogger("finn.api").info("error reporting on (environment %s)", settings.environment)
app = create_app(settings)
