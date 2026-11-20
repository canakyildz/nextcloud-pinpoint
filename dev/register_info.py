"""Print the --json-info AppAPI needs to register Pinpoint as a manual-install ExApp, built from
appinfo/info.xml so routes and version are never duplicated by hand."""

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

LEVELS = {"PUBLIC": 0, "USER": 1, "ADMIN": 2}

info = ET.parse(Path(__file__).resolve().parents[1] / "appinfo" / "info.xml").getroot()  # noqa: S314
routes = [
    {
        "url": route.findtext("url"),
        "verb": route.findtext("verb"),
        "access_level": LEVELS[route.findtext("access_level", "USER")],
        "headers_to_exclude": route.findtext("headers_to_exclude", "[]"),
    }
    for route in info.iter("route")
]
json.dump(
    {
        "id": info.findtext("id"),
        "name": info.findtext("name"),
        "daemon_config_name": os.environ.get("DAEMON", "manual_install"),
        "version": info.findtext("version"),
        "secret": os.environ.get("APP_SECRET", "dev-secret-change-me-0123456789"),
        "port": int(os.environ.get("APP_PORT", "23000")),
        "routes": routes,
    },
    sys.stdout,
)
