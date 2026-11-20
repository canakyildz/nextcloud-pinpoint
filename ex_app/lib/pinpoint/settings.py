"""Admin settings, shown under Administration → Artificial intelligence and rendered by Nextcloud
from a declarative schema (no settings page code in Pinpoint)."""

from __future__ import annotations

import time
from dataclasses import fields

from nc_py_api import AsyncNextcloudApp
from nc_py_api.ex_app import SettingsField, SettingsFieldType, SettingsForm

from .service import Settings

DEFAULTS = Settings()

FORM = SettingsForm(
    id="pinpoint_admin",
    section_type="admin",
    section_id="ai_integration_team",
    title="Pinpoint",
    description=(
        "Pinpoint sends document text to the text generation provider configured above "
        "(Administration → Artificial intelligence). Use a local provider such as llm2 to keep documents on "
        "your server."
    ),
    fields=[
        SettingsField(
            id="max_pages",
            title="Pages read per document",
            type=SettingsFieldType.NUMBER,
            default=DEFAULTS.max_pages,
            description="Longer documents are cut after this many pages.",
        ),
        SettingsField(
            id="max_file_mb",
            title="Largest file (MB)",
            type=SettingsFieldType.NUMBER,
            default=DEFAULTS.max_file_mb,
        ),
        SettingsField(
            id="ocr_languages",
            title="OCR languages",
            type=SettingsFieldType.TEXT,
            default=DEFAULTS.ocr_languages,
            description="Tesseract language codes joined by +, used for scans and photos. "
            "Installed: eng, deu, fra, spa, ita, nld, por, tur.",
        ),
        SettingsField(
            id="model_timeout_minutes",
            title="Wait for the language model (minutes)",
            type=SettingsFieldType.NUMBER,
            default=DEFAULTS.model_timeout_minutes,
            description="Local models on a CPU can take several minutes per document.",
        ),
        SettingsField(
            id="keep_days",
            title="Keep review history (days)",
            type=SettingsFieldType.NUMBER,
            default=DEFAULTS.keep_days,
            description="Extracted values waiting for review are deleted after this many days. "
            "Rows saved to Tables are not affected.",
        ),
    ],
)


class SettingsReader:
    """Reads the admin settings, cached for a minute so a busy queue does not hit Nextcloud per job."""

    def __init__(self, ttl: float = 60.0) -> None:
        self.ttl = ttl
        self._cached: Settings | None = None
        self._read_at = 0.0

    async def __call__(self) -> Settings:
        if self._cached is not None and time.monotonic() - self._read_at < self.ttl:
            return self._cached
        nc = AsyncNextcloudApp()
        keys = [f.name for f in fields(Settings)]
        stored = {r.key: r.value for r in await nc.appconfig_ex.get_values(keys)}
        values: dict[str, object] = {}
        for f in fields(Settings):
            raw = stored.get(f.name)
            default = getattr(DEFAULTS, f.name)
            if raw in (None, ""):
                values[f.name] = default
                continue
            try:
                values[f.name] = type(default)(float(raw)) if isinstance(default, int | float) else str(raw)
            except ValueError:
                values[f.name] = default
        settings = Settings(**values)  # type: ignore[arg-type]
        if settings.max_pages < 1 or settings.keep_days <= 0 or settings.model_timeout_minutes <= 0:
            settings = DEFAULTS
        self._cached, self._read_at = settings, time.monotonic()
        return settings
