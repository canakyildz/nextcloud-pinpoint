"""Pinpoint inside a real Nextcloud, through AppAPI, Tables and TaskProcessing.

Runs against the stack in dev/docker-compose.yml (CI adds tests/integration/docker-compose.ci.yml, which
points the OpenAI integration at mock_llm.py). Nothing is mocked inside Nextcloud.

    docker compose -f dev/docker-compose.yml -f tests/integration/docker-compose.ci.yml up -d --build --wait
    LLM_URL=http://mockllm:8000/v1 LLM_MODEL=mock-model WITH_ASSISTANT=0 dev/setup.sh
    pytest -m integration tests/integration
"""

from __future__ import annotations

import base64
import os
import re
import secrets
import time
import uuid
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

NC = os.environ.get("NC_URL", "http://localhost:8080")
EXAPP = os.environ.get("EXAPP_URL", "http://localhost:23000")
ADMIN = (os.environ.get("NC_USER", "admin"), os.environ.get("NC_PASSWORD", "admin"))
DATASET = Path(__file__).resolve().parents[2] / "evals" / "dataset"
PROXY = f"{NC}/index.php/apps/app_api/proxy/pinpoint/api"
OCS = {"OCS-APIRequest": "true", "Accept": "application/json"}


def _client(auth: tuple[str, str]) -> httpx.Client:
    # Nextcloud answers with a session cookie; a later cookie-authenticated WebDAV call would need a CSRF
    # token. The OCS-APIRequest header marks these as API calls, which is what they are.
    return httpx.Client(auth=auth, timeout=60, headers={"OCS-APIRequest": "true"})


@pytest.fixture(scope="module")
def admin() -> httpx.Client:
    with _client(ADMIN) as client:
        yield client


def _upload(client: httpx.Client, user: str, name: str) -> int:
    folder = f"pinpoint-it-{uuid.uuid4().hex[:8]}"
    client.request("MKCOL", f"{NC}/remote.php/dav/files/{user}/{folder}").raise_for_status()
    url = f"{NC}/remote.php/dav/files/{user}/{folder}/{name}"
    client.put(url, content=(DATASET / name).read_bytes()).raise_for_status()
    body = (
        '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
        "<d:prop><oc:fileid/></d:prop></d:propfind>"
    )
    response = client.request("PROPFIND", url, headers={"Depth": "0"}, content=body)
    return int(re.search(r"<oc:fileid>(\d+)</oc:fileid>", response.text).group(1))


def _wait_for_job(client: httpx.Client, job_id: str, timeout: float = 180) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"{PROXY}/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(2)
    raise AssertionError(f"job {job_id} did not finish")


@pytest.fixture(scope="module")
def invoice_table(admin: httpx.Client) -> dict:
    response = admin.post(f"{PROXY}/tables", json={"template": "invoice", "title": f"IT {uuid.uuid4().hex[:6]}"})
    response.raise_for_status()
    return response.json()


def test_pinpoint_registers_its_task_type(admin):
    types = admin.get(f"{NC}/ocs/v2.php/taskprocessing/tasktypes", headers=OCS).json()["ocs"]["data"]["types"]
    assert "pinpoint:extract_fields" in types
    assert "core:text2text" in types  # the provider Pinpoint relies on


def test_extract_review_and_save_through_appapi(admin, invoice_table):
    file_id = _upload(admin, ADMIN[0], "invoice-02.pdf")
    job = admin.post(f"{PROXY}/jobs", json={"fileId": file_id, "tableId": invoice_table["id"]}).json()
    job = _wait_for_job(admin, job["id"])
    assert job["status"] == "done", job.get("error")

    fields = {f["key"]: f for f in job["result"]["fields"]}
    assert fields["total_amount"]["status"] == "verified"
    assert fields["total_amount"]["anchor"]["boxes"]
    assert all(c["passed"] for c in job["result"]["checks"])

    page = admin.get(f"{PROXY}/jobs/{job['id']}/pages/0")
    assert page.headers["content-type"] == "image/png"

    saved = admin.post(f"{PROXY}/jobs/{job['id']}/save", json={"values": {}}).json()
    assert saved["status"] == "saved"
    rows = admin.get(f"{NC}/index.php/apps/tables/api/1/tables/{invoice_table['id']}/rows").json()
    row = next(r for r in rows if r["id"] == saved["rowId"])
    columns = {
        c["id"]: c["title"]
        for c in admin.get(f"{NC}/index.php/apps/tables/api/1/tables/{invoice_table['id']}/columns").json()
    }
    cells = {columns[c["columnId"]]: c["value"] for c in row["data"]}
    assert cells["Total amount"] == fields["total_amount"]["value"]
    assert f"/f/{file_id}" in cells["Source"]
    assert "· verified" in cells["Evidence"]


def test_assistant_task_runs_through_the_provider(admin):
    file_id = _upload(admin, ADMIN[0], "invoice-03.pdf")
    response = admin.post(
        f"{NC}/ocs/v2.php/taskprocessing/schedule",
        headers=OCS,
        json={
            "input": {"Document": file_id, "Document type": "invoice"},
            "type": "pinpoint:extract_fields",
            "appId": "pinpoint-it",
            "customId": "",
        },
    )
    response.raise_for_status()
    task_id = response.json()["ocs"]["data"]["task"]["id"]
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        task = admin.get(f"{NC}/ocs/v2.php/taskprocessing/task/{task_id}", headers=OCS).json()["ocs"]["data"]["task"]
        if task["status"] in ("STATUS_SUCCESSFUL", "STATUS_FAILED"):
            break
        time.sleep(2)
    assert task["status"] == "STATUS_SUCCESSFUL", task.get("errorMessage")
    assert "✓ Supplier: Atelier Verte SARL" in task["output"]["Evidence"]
    assert '"status": "verified"' in task["output"]["Fields (JSON)"]


def test_jobs_are_invisible_to_other_users(admin, invoice_table):
    password = secrets.token_urlsafe(16) + "aA1!"
    user = f"bob{uuid.uuid4().hex[:6]}"
    admin.post(f"{NC}/ocs/v1.php/cloud/users", headers=OCS, data={"userid": user, "password": password})
    file_id = _upload(admin, ADMIN[0], "invoice-05.pdf")
    job = admin.post(f"{PROXY}/jobs", json={"fileId": file_id, "tableId": invoice_table["id"]}).json()
    with _client((user, password)) as bob:
        assert bob.get(f"{PROXY}/jobs/{job['id']}").status_code == 404
        assert bob.get(f"{PROXY}/jobs/{job['id']}/pages/0").status_code == 404
        # Nor can bob start a job on a file or table he cannot see.
        refused = bob.post(f"{PROXY}/jobs", json={"fileId": file_id, "tableId": invoice_table["id"]})
        assert refused.status_code >= 400
    _wait_for_job(admin, job["id"])


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"EX-APP-ID": "pinpoint"},
        {"EX-APP-ID": "pinpoint", "AUTHORIZATION-APP-API": base64.b64encode(b"admin:wrong-secret").decode()},
        {
            "EX-APP-ID": "other",
            "AUTHORIZATION-APP-API": base64.b64encode(b"admin:dev-secret-change-me-0123456789").decode(),
        },
    ],
)
def test_the_exapp_refuses_requests_that_did_not_come_through_appapi(headers):
    response = httpx.get(f"{EXAPP}/api/jobs", headers={**headers, "AA-VERSION": "3.0.0", "EX-APP-VERSION": "0.1.0"})
    assert response.status_code == 401


def test_heartbeat_is_public():
    assert httpx.get(f"{EXAPP}/heartbeat").json() == {"status": "ok"}
