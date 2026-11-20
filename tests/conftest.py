from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from pinpoint.model import Schema
from pinpoint.nextcloud import FileInfo, NextcloudError
from pinpoint.schemas import INVOICE
from pinpoint.tables import column_requests

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "dataset"

requires_ocr = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is not installed")


def dataset_file(name: str) -> bytes:
    return (DATASET / name).read_bytes()


def truth(name: str) -> dict[str, Any]:
    return json.loads((DATASET / f"{name}.json").read_text())


class ScriptedModel:
    """Returns prepared answers in order and records the prompts it was given."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def truth_answer(name: str, schema: Schema | None = None) -> str:
    """The ground truth of a dataset document as the model would ideally answer it. With `schema`,
    field keys are mapped by label (for schemas built from a table)."""
    fields = truth(name)["fields"]
    if schema is not None:
        template_key = {spec.label: spec.key for spec in INVOICE.fields}
        fields = {spec.key: fields[template_key[spec.label]] for spec in schema.fields if spec.label in template_key}
    return json.dumps({"fields": fields}, ensure_ascii=False)


class FakeGateway:
    """In-memory stand-in for Nextcloud: files, Tables with columns and rows, notifications."""

    def __init__(self) -> None:
        self.files: dict[int, tuple[str, str, bytes, set[str]]] = {}
        self.tables: dict[int, dict[str, Any]] = {}
        self.columns: dict[int, list[dict[str, Any]]] = {}
        self.rows: dict[int, list[dict[int, Any]]] = {}
        self.notifications: list[tuple[str, str, str, str]] = []
        self.model: Any = ScriptedModel("{}")
        self.model_requests: list[tuple[str, str]] = []
        self.text_generation = True
        self._next_id = 100

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    def add_file(self, name: str, mime: str, data: bytes, owners: set[str]) -> int:
        file_id = self._id()
        self.files[file_id] = (name, mime, data, owners)
        return file_id

    def add_table(self, title: str, owner: str, schema: Schema = INVOICE) -> int:
        table_id = self._id()
        self.tables[table_id] = {"id": table_id, "title": title, "ownership": owner, "emoji": "", "description": ""}
        columns = []
        for kind, body in column_requests(schema):
            column = {
                "id": self._id(),
                "title": body["title"],
                "type": kind,
                "subtype": body.get("subtype", ""),
                "description": body.get("description", ""),
                "mandatory": False,
                "selectionOptions": json.loads(body["selectionOptions"]) if "selectionOptions" in body else [],
            }
            columns.append(column)
        self.columns[table_id] = columns
        self.rows[table_id] = []
        return table_id

    def _file(self, user_id: str, file_id: int) -> tuple[str, str, bytes, set[str]]:
        entry = self.files.get(file_id)
        if entry is None or user_id not in entry[3]:
            raise NextcloudError("The file does not exist or you have no access to it.")
        return entry

    def _table(self, user_id: str, table_id: int) -> dict[str, Any]:
        table = self.tables.get(table_id)
        if table is None or table["ownership"] != user_id:
            raise NextcloudError("The table does not exist or you have no access to it.")
        return table

    async def public_url(self) -> str:
        return "https://cloud.example.com"

    async def file_info(self, user_id: str, file_id: int) -> FileInfo:
        name, mime, data, _ = self._file(user_id, file_id)
        return FileInfo(file_id, name, mime, len(data))

    async def download(self, user_id: str, file_id: int) -> bytes:
        return self._file(user_id, file_id)[2]

    async def list_tables(self, user_id: str) -> list[dict[str, Any]]:
        return [t for t in self.tables.values() if t["ownership"] == user_id]

    async def get_table(self, user_id: str, table_id: int) -> dict[str, Any]:
        return self._table(user_id, table_id)

    async def table_columns(self, user_id: str, table_id: int) -> list[dict[str, Any]]:
        self._table(user_id, table_id)
        return self.columns[table_id]

    async def create_table(self, user_id: str, schema: Schema, title: str) -> dict[str, Any]:
        return self.tables[self.add_table(title, user_id, schema)]

    async def create_row(self, user_id: str, table_id: int, data: dict[int, Any]) -> int:
        self._table(user_id, table_id)
        self.rows[table_id].append(data)
        return len(self.rows[table_id])

    async def text_model(self, user_id: str, custom_id: str, time_limit: float) -> Any:
        self.model_requests.append((user_id, custom_id))
        return self.model

    async def text_generation_available(self, user_id: str) -> bool:
        return self.text_generation

    async def notify(self, user_id: str, subject: str, message: str, link: str) -> None:
        self.notifications.append((user_id, subject, message, link))


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()
