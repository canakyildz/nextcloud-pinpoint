"""The HTTP API end to end against an in-memory Nextcloud: submit, extract, review, save to Tables."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, Request

from conftest import FakeGateway, ScriptedModel, dataset_file, truth_answer
from pinpoint.api import current_user, router
from pinpoint.schemas import schema_from_table
from pinpoint.service import PinpointService, Settings
from pinpoint.store import JobStore


async def _settings() -> Settings:
    return Settings(max_file_mb=1)


@pytest.fixture
async def app(tmp_path, gateway: FakeGateway) -> AsyncIterator[FastAPI]:
    service = PinpointService(JobStore(tmp_path / "jobs.sqlite3"), gateway, _settings)
    app = FastAPI()
    app.include_router(router)
    app.state.service = service

    async def user_from_header(request: Request) -> str:
        return request.headers["x-user"]

    app.dependency_overrides[current_user] = user_from_header
    await service.start()
    yield app
    await service.stop()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers={"x-user": "alice"}) as c:
        yield c


async def _finished(client: httpx.AsyncClient, job_id: str) -> dict:
    for _ in range(200):
        job = (await client.get(f"/api/jobs/{job_id}")).json()
        if job["status"] not in ("queued", "running"):
            return job
        await asyncio.sleep(0.01)
    raise AssertionError("job did not finish")


async def _setup_invoice(gateway: FakeGateway) -> tuple[int, int]:
    file_id = gateway.add_file("invoice-03.pdf", "application/pdf", dataset_file("invoice-03.pdf"), {"alice"})
    table_id = gateway.add_table("Invoices", "alice")
    schema = schema_from_table(gateway.tables[table_id], gateway.columns[table_id])
    gateway.model = ScriptedModel(truth_answer("invoice-03", schema))
    return file_id, table_id


async def test_extract_review_and_save_to_tables(client, gateway):
    file_id, table_id = await _setup_invoice(gateway)

    state = (await client.get("/api/state")).json()
    assert [t["id"] for t in state["tables"]] == [table_id]
    assert {t["id"] for t in state["templates"]} == {"template:invoice", "template:receipt"}

    job = (await client.post("/api/jobs", json={"fileId": file_id, "tableId": table_id})).json()
    job = await _finished(client, job["id"])
    assert job["status"] == "done", job
    assert job["summary"]["verified"] >= 8
    total = next(f for f in job["result"]["fields"] if f["key"] == "total_amount")
    assert total["status"] == "verified"
    assert total["anchor"]["boxes"]

    # The model ran as alice, through a task tagged with this job.
    assert gateway.model_requests == [("alice", f"pinpoint:{job['id']}")]
    # Alice was told, with a link back to the review page.
    assert gateway.notifications[-1][3].endswith(f"/embedded/pinpoint/main/jobs/{job['id']}")

    page = await client.get(f"/api/jobs/{job['id']}/pages/0")
    assert page.headers["content-type"] == "image/png"

    saved = (await client.post(f"/api/jobs/{job['id']}/save", json={"values": {"supplier": "Atelier Verte"}})).json()
    assert saved["status"] == "saved"
    row = gateway.rows[table_id][0]
    columns = {c["title"]: c["id"] for c in gateway.columns[table_id]}
    assert row[columns["Supplier"]] == "Atelier Verte"
    assert row[columns["Total amount"]] == total["value"]
    assert "invoice-03.pdf" in row[columns["Source"]]
    assert "/index.php/f/" in row[columns["Source"]]
    assert "**Supplier**: Atelier Verte · entered by a person" in row[columns["Evidence"]]
    assert "**Total amount**:" in row[columns["Evidence"]] and "· verified" in row[columns["Evidence"]]

    again = await client.post(f"/api/jobs/{job['id']}/save", json={"values": {}})
    assert again.status_code == 409  # never two rows for one review


async def test_other_users_cannot_see_or_touch_a_job(client, gateway):
    file_id, table_id = await _setup_invoice(gateway)
    job = (await client.post("/api/jobs", json={"fileId": file_id, "tableId": table_id})).json()
    await _finished(client, job["id"])
    bob = {"x-user": "bob"}
    assert (await client.get(f"/api/jobs/{job['id']}", headers=bob)).status_code == 404
    assert (await client.get(f"/api/jobs/{job['id']}/pages/0", headers=bob)).status_code == 404
    assert (await client.post(f"/api/jobs/{job['id']}/save", json={"values": {}}, headers=bob)).status_code == 404
    assert (await client.delete(f"/api/jobs/{job['id']}", headers=bob)).status_code == 404
    assert (await client.get("/api/jobs", headers=bob)).json() == {"jobs": []}


async def test_files_and_tables_are_read_with_the_users_permissions(client, gateway):
    file_id, table_id = await _setup_invoice(gateway)
    bob = {"x-user": "bob"}
    response = await client.post("/api/jobs", json={"fileId": file_id, "tableId": table_id}, headers=bob)
    assert response.status_code == 502
    assert "no access" in response.json()["error"]


async def test_invalid_edit_is_refused_with_the_field_name(client, gateway):
    file_id, table_id = await _setup_invoice(gateway)
    job = (await client.post("/api/jobs", json={"fileId": file_id, "tableId": table_id})).json()
    await _finished(client, job["id"])
    response = await client.post(f"/api/jobs/{job['id']}/save", json={"values": {"total_amount": "a lot"}})
    assert response.status_code == 400
    assert "Total amount" in response.json()["error"]
    assert gateway.rows[table_id] == []


async def test_unsupported_and_oversized_files_are_refused_before_any_work(client, gateway):
    table_id = gateway.add_table("Invoices", "alice")
    docx = gateway.add_file("letter.docx", "application/vnd.openxmlformats", b"PK..", {"alice"})
    big = gateway.add_file("big.pdf", "application/pdf", b"%PDF-" + b"0" * 2_000_000, {"alice"})
    for file_id, message in ((docx, "not a PDF"), (big, "1 MB limit")):
        response = await client.post("/api/jobs", json={"fileId": file_id, "tableId": table_id})
        assert response.status_code == 400
        assert message in response.json()["error"]
    assert gateway.model_requests == []


async def test_a_model_that_never_returns_json_fails_the_job_readably(client, gateway):
    file_id, table_id = await _setup_invoice(gateway)
    gateway.model = ScriptedModel("Sorry, I can't help with that.")
    job = (await client.post("/api/jobs", json={"fileId": file_id, "tableId": table_id})).json()
    job = await _finished(client, job["id"])
    assert job["status"] == "failed"
    assert "JSON" in job["error"]
    assert "could not read" in gateway.notifications[-1][1]

    gateway.model = ScriptedModel(
        truth_answer("invoice-03", schema_from_table(gateway.tables[table_id], gateway.columns[table_id]))
    )
    retried = (await client.post(f"/api/jobs/{job['id']}/retry")).json()
    assert retried["status"] == "queued"
    assert (await _finished(client, job["id"]))["status"] == "done"


async def test_create_table_from_template(client, gateway):
    table = (await client.post("/api/tables", json={"template": "receipt", "title": "Receipts 2026"})).json()
    assert table["title"] == "Receipts 2026"
    titles = [c["title"] for c in gateway.columns[table["id"]]]
    assert titles[-2:] == ["Source", "Evidence"]
    schema = (await client.get(f"/api/tables/{table['id']}/schema")).json()
    assert [f["label"] for f in schema["fields"]] == titles[:-2]


async def test_table_without_fillable_columns(client, gateway):
    table_id = gateway.add_table("Empty", "alice")
    gateway.columns[table_id] = [{"id": 1, "title": "Owner", "type": "usergroup", "subtype": ""}]
    response = await client.get(f"/api/tables/{table_id}/schema")
    assert response.status_code == 400
    assert "no columns" in response.json()["error"]


async def test_file_action_redirects_to_the_new_extraction_page(client):
    response = await client.post("/api/file-action", json={"files": [{"fileId": 5, "name": "a.pdf"}]})
    assert response.json() == {"redirect_handler": "main/new"}


async def test_delete_job(client, gateway):
    file_id, table_id = await _setup_invoice(gateway)
    job = (await client.post("/api/jobs", json={"fileId": file_id, "tableId": table_id})).json()
    await _finished(client, job["id"])
    assert (await client.delete(f"/api/jobs/{job['id']}")).status_code == 200
    assert (await client.get(f"/api/jobs/{job['id']}")).status_code == 404
