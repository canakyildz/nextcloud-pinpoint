"""Everything Pinpoint asks of Nextcloud, behind one small interface.

All calls are made *as the user* the work is for (AppAPI lets an ExApp act for a user), so Nextcloud
enforces that user's file and table permissions. Pinpoint never reads a file the user cannot read.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from nc_py_api import AsyncNextcloudApp, NextcloudException, NextcloudExceptionNotFound

from . import tables as tables_mod
from .model import Schema
from .pipeline import TextModel

LOG = logging.getLogger(__name__)

TEXT_TASK_TYPE = "core:text2text"


class NextcloudError(RuntimeError):
    """A Nextcloud call failed. The message is safe to show to the user."""


@dataclass(frozen=True, slots=True)
class FileInfo:
    id: int
    name: str
    mime: str
    size: int


class Gateway(Protocol):
    """What the service needs from Nextcloud. The tests provide an in-memory fake."""

    async def public_url(self) -> str: ...

    async def file_info(self, user_id: str, file_id: int) -> FileInfo: ...

    async def download(self, user_id: str, file_id: int) -> bytes: ...

    async def list_tables(self, user_id: str) -> list[dict[str, Any]]: ...

    async def get_table(self, user_id: str, table_id: int) -> dict[str, Any]: ...

    async def table_columns(self, user_id: str, table_id: int) -> list[dict[str, Any]]: ...

    async def create_table(self, user_id: str, schema: Schema, title: str) -> dict[str, Any]: ...

    async def create_row(self, user_id: str, table_id: int, data: dict[int, Any]) -> int: ...

    async def text_model(self, user_id: str, custom_id: str, time_limit: float) -> TextModel: ...

    async def text_generation_available(self, user_id: str) -> bool: ...

    async def notify(self, user_id: str, subject: str, message: str, link: str) -> None: ...


class TaskProcessingModel:
    """Runs a prompt through Nextcloud's TaskProcessing, i.e. through whichever text-generation provider
    the admin configured: llm2 on the server, LocalAI, Ollama, OpenAI or any other.

    The prompt contains document text, so the task is deleted from Nextcloud once its result is read.
    """

    def __init__(self, nc: AsyncNextcloudApp, custom_id: str, timeout: float, poll_interval: float = 1.0) -> None:
        self.nc = nc
        self.custom_id = custom_id
        self.timeout = timeout
        self.poll_interval = poll_interval

    async def complete(self, prompt: str) -> str:
        try:
            scheduled = await self.nc.ocs(
                "POST",
                "/ocs/v2.php/taskprocessing/schedule",
                json={
                    "input": {"input": prompt},
                    "type": TEXT_TASK_TYPE,
                    "appId": self.nc.app_cfg.app_name,
                    "customId": self.custom_id,
                },
            )
        except NextcloudException as exc:
            raise NextcloudError(
                "Could not start the text generation task. Is a text generation provider installed?"
            ) from exc
        task_id = scheduled["task"]["id"]
        try:
            return await self._wait(task_id)
        finally:
            try:
                await self.nc.ocs("DELETE", f"/ocs/v2.php/taskprocessing/task/{task_id}")
            except NextcloudException:
                LOG.warning("Could not delete TaskProcessing task %s", task_id)

    async def _wait(self, task_id: int) -> str:
        deadline = time.monotonic() + self.timeout
        delay = self.poll_interval
        while True:
            task = (await self.nc.ocs("GET", f"/ocs/v2.php/taskprocessing/task/{task_id}"))["task"]
            status = task["status"]
            if status == "STATUS_SUCCESSFUL":
                output = task.get("output") or {}
                return str(output.get("output", ""))
            if status in ("STATUS_FAILED", "STATUS_CANCELLED"):
                message = task.get("userFacingErrorMessage") or task.get("errorMessage") or status
                raise NextcloudError(f"The text generation task failed: {message}")
            if time.monotonic() > deadline:
                with contextlib.suppress(NextcloudException):
                    await self.nc.ocs("POST", f"/ocs/v2.php/taskprocessing/tasks/{task_id}/cancel")
                raise NextcloudError("The text generation task took too long and was cancelled.")
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 5.0)


class NextcloudGateway:
    def __init__(self) -> None:
        self._public_url: str | None = None

    async def public_url(self) -> str:
        """The address users reach Nextcloud at (overwrite.cli.url), for links in Tables and notifications.
        It can differ from NEXTCLOUD_URL, which is how this container reaches Nextcloud."""
        if self._public_url is None:
            nc = AsyncNextcloudApp()
            data = await nc.ocs(
                "GET", "/ocs/v1.php/apps/app_api/api/v1/info/nextcloud_url/absolute", params={"url": ""}
            )
            self._public_url = str(data["absolute_url"]).rstrip("/")
        return self._public_url

    @staticmethod
    async def _as(user_id: str) -> AsyncNextcloudApp:
        nc = AsyncNextcloudApp()
        await nc.set_user(user_id)
        return nc

    async def file_info(self, user_id: str, file_id: int) -> FileInfo:
        nc = await self._as(user_id)
        node = await nc.files.by_id(file_id)
        if node is None or node.is_dir:
            raise NextcloudError("The file does not exist or you have no access to it.")
        return FileInfo(id=node.info.fileid, name=node.name, mime=node.info.mimetype, size=node.info.size)

    async def download(self, user_id: str, file_id: int) -> bytes:
        nc = await self._as(user_id)
        node = await nc.files.by_id(file_id)
        if node is None or node.is_dir:
            raise NextcloudError("The file does not exist or you have no access to it.")
        return await nc.files.download(node)

    async def list_tables(self, user_id: str) -> list[dict[str, Any]]:
        nc = await self._as(user_id)
        try:
            tables = await nc.ocs("GET", "/ocs/v2.php/apps/tables/api/2/tables")
        except NextcloudExceptionNotFound:
            raise NextcloudError("The Tables app is not installed or not enabled.") from None
        return [t for t in tables if _can_add_rows(t, user_id)]

    async def get_table(self, user_id: str, table_id: int) -> dict[str, Any]:
        nc = await self._as(user_id)
        try:
            return await nc.ocs("GET", f"/ocs/v2.php/apps/tables/api/2/tables/{table_id}")
        except NextcloudException as exc:
            raise NextcloudError("The table does not exist or you have no access to it.") from exc

    async def table_columns(self, user_id: str, table_id: int) -> list[dict[str, Any]]:
        nc = await self._as(user_id)
        try:
            return await nc.ocs("GET", f"/index.php/apps/tables/api/1/tables/{table_id}/columns", response_type="json")
        except NextcloudException as exc:
            raise NextcloudError("Could not read the table's columns.") from exc

    async def create_table(self, user_id: str, schema: Schema, title: str) -> dict[str, Any]:
        nc = await self._as(user_id)
        table = await nc.ocs(
            "POST",
            "/ocs/v2.php/apps/tables/api/2/tables",
            json={"title": title, "emoji": "🧾", "description": schema.instructions, "template": "custom"},
        )
        for kind, body in tables_mod.column_requests(schema):
            await nc.ocs(
                "POST",
                f"/ocs/v2.php/apps/tables/api/2/columns/{kind}",
                json={**body, "baseNodeId": table["id"], "baseNodeType": "table"},
            )
        return table

    async def create_row(self, user_id: str, table_id: int, data: dict[int, Any]) -> int:
        nc = await self._as(user_id)
        try:
            row = await nc.ocs(
                "POST",
                f"/index.php/apps/tables/api/1/tables/{table_id}/rows",
                json={"data": {str(k): v for k, v in data.items()}},
                response_type="json",
            )
        except NextcloudException as exc:
            raise NextcloudError(f"Tables refused the row: {exc.reason or exc}") from exc
        return int(row["id"])

    async def text_model(self, user_id: str, custom_id: str, time_limit: float) -> TextModel:
        return TaskProcessingModel(await self._as(user_id), custom_id, time_limit)

    async def text_generation_available(self, user_id: str) -> bool:
        nc = await self._as(user_id)
        types = (await nc.ocs("GET", "/ocs/v2.php/taskprocessing/tasktypes"))["types"]
        return TEXT_TASK_TYPE in types

    async def notify(self, user_id: str, subject: str, message: str, link: str) -> None:
        nc = await self._as(user_id)
        try:
            await nc.notifications.create(subject, message, link=link)
        except Exception as exc:  # notifications are a convenience; never fail a job over them
            LOG.info("Notification not sent: %s", exc)


def _can_add_rows(table: dict[str, Any], user_id: str) -> bool:
    if table.get("ownership") == user_id:
        return True
    permissions = table.get("onSharePermissions") or {}
    return bool(permissions.get("create") or permissions.get("manage"))
