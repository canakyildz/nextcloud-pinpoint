"""Pinpoint ExApp entry point: lifecycle, registration with Nextcloud and the HTTP app."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from nc_py_api import AsyncNextcloudApp
from nc_py_api.ex_app import AppAPIAuthMiddleware, LogLvl, persistent_storage, run_app, set_handlers

from pinpoint import __version__
from pinpoint.api import router
from pinpoint.nextcloud import NextcloudGateway
from pinpoint.provider import ProviderWorker, provider, task_type
from pinpoint.service import PinpointService
from pinpoint.settings import FORM, SettingsReader
from pinpoint.store import JobStore

logging.basicConfig(level=os.environ.get("PINPOINT_LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s: %(message)s")
LOG = logging.getLogger("pinpoint")

APP_ID = os.environ.get("APP_ID", "pinpoint")
MENU_ENTRY = "main"
FILE_ACTION = "extract_fields"
FILE_MIMES = "application/pdf, image/png, image/jpeg, image/tiff, image/webp"

SETTINGS = SettingsReader()
PROVIDER_WORKER = ProviderWorker(APP_ID, SETTINGS)


async def enabled_handler(enabled: bool, nc: AsyncNextcloudApp) -> str:
    """Called by AppAPI when the app is enabled or disabled. Registers everything Pinpoint adds to
    Nextcloud; on disable, removes it again."""
    if enabled:
        await nc.ui.top_menu.register(MENU_ENTRY, "Pinpoint", "img/app.svg", admin_required=False)
        await nc.ui.resources.set_script("top_menu", MENU_ENTRY, "js/pinpoint-main")
        await nc.ui.resources.set_style("top_menu", MENU_ENTRY, "js/pinpoint-main")
        await nc.ui.files_dropdown_menu.register_ex(
            FILE_ACTION, "Extract fields", "/api/file-action", mime=FILE_MIMES, icon="img/app-dark.svg"
        )
        await nc.ui.settings.register_form(FORM)
        await nc.providers.task_processing.register(provider(APP_ID), task_type(APP_ID))
        await nc.log(LogLvl.INFO, f"Pinpoint {__version__} enabled")
    else:
        await nc.ui.top_menu.unregister(MENU_ENTRY)
        await nc.ui.resources.delete_script("top_menu", MENU_ENTRY, "js/pinpoint-main")
        await nc.ui.resources.delete_style("top_menu", MENU_ENTRY, "js/pinpoint-main")
        await nc.ui.files_dropdown_menu.unregister(FILE_ACTION)
        await nc.ui.settings.unregister_form(FORM.id)
        await nc.providers.task_processing.unregister(f"{APP_ID}:extract_fields")
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    set_handlers(app, enabled_handler, trigger_handler=PROVIDER_WORKER.trigger)
    store = JobStore(Path(persistent_storage()) / "pinpoint.sqlite3")
    service = PinpointService(store, NextcloudGateway(), SETTINGS, app_id=APP_ID)
    app.state.service = service
    await service.start()
    PROVIDER_WORKER.start()
    LOG.info("Pinpoint %s started", __version__)
    yield
    await PROVIDER_WORKER.stop()
    await service.stop()


APP = FastAPI(lifespan=lifespan, title="Pinpoint", version=__version__)
APP.add_middleware(AppAPIAuthMiddleware)
APP.include_router(router)


if __name__ == "__main__":
    run_app("main:APP", log_level="info")
