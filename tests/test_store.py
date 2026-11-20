import time

from pinpoint.store import JobStatus, JobStore


async def test_jobs_are_private_to_their_user(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    job = await store.create("alice", 1, "a.pdf", "application/pdf", {"id": "table:1", "name": "T"}, 1)
    assert (await store.get(job.id, "alice")).file_name == "a.pdf"
    assert await store.get(job.id, "bob") is None
    assert not await store.delete(job.id, "bob")
    assert [j.id for j in await store.list_for_user("alice")] == [job.id]
    assert await store.list_for_user("bob") == []


async def test_update_and_reopen(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    job = await store.create("alice", 1, "a.pdf", "application/pdf", {"id": "s", "name": "S"}, None)
    await store.update(job.id, status=JobStatus.DONE, result={"summary": {"verified": 3}})
    reopened = JobStore(path)  # migrations are idempotent
    loaded = await reopened.get(job.id)
    assert loaded.status == JobStatus.DONE
    assert loaded.result == {"summary": {"verified": 3}}
    assert loaded.to_dict(include_result=False)["summary"] == {"verified": 3}


async def test_retention_keeps_running_jobs(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    old = await store.create("alice", 1, "old.pdf", "application/pdf", {"id": "s", "name": "S"}, None)
    running = await store.create("alice", 2, "run.pdf", "application/pdf", {"id": "s", "name": "S"}, None)
    await store.update(old.id, status=JobStatus.DONE)
    await store.update(running.id, status=JobStatus.RUNNING)
    time.sleep(0.01)
    assert await store.delete_older_than(0.0000001) == 1
    assert await store.get(old.id) is None
    assert await store.get(running.id) is not None
    assert [j.id for j in await store.unfinished()] == [running.id]
