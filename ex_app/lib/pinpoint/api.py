"""HTTP API used by Pinpoint's own pages and by the Files action.

Every route is reached through AppAPI's proxy, which authenticates the Nextcloud user and passes their
id to the ExApp. A job is only ever visible to the user who created it.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from nc_py_api import AsyncNextcloudApp
from nc_py_api.ex_app import anc_app
from pydantic import BaseModel, Field

from .document import ocr_available
from .nextcloud import NextcloudError
from .service import PinpointService, UserError


async def current_user(nc: Annotated[AsyncNextcloudApp, Depends(anc_app)]) -> str:
    user = await nc.user
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to Nextcloud to use Pinpoint.")
    return user


def get_service(request: Request) -> PinpointService:
    service: PinpointService = request.app.state.service
    return service


User = Annotated[str, Depends(current_user)]
Service = Annotated[PinpointService, Depends(get_service)]

router = APIRouter(prefix="/api")


class CreateTable(BaseModel):
    template: str
    title: str | None = Field(default=None, max_length=200)


class CreateJob(BaseModel):
    fileId: int  # noqa: N815 (matches the frontend's JSON)
    tableId: int  # noqa: N815


class SaveJob(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class FileActionFile(BaseModel):
    fileId: int  # noqa: N815
    name: str = ""
    mime: str = ""


class FileAction(BaseModel):
    files: list[FileActionFile]


def _errors(exc: Exception) -> JSONResponse:
    if isinstance(exc, UserError):
        return JSONResponse({"error": str(exc)}, status_code=exc.status)
    if isinstance(exc, NextcloudError):
        return JSONResponse({"error": str(exc)}, status_code=502)
    raise exc


@router.get("/state")
async def state(user: User, service: Service) -> Any:
    try:
        tables = await service.tables(user)
        tables_error = None
    except NextcloudError as exc:
        tables, tables_error = [], str(exc)
    return {
        "templates": service.templates(),
        "tables": tables,
        "tablesError": tables_error,
        "textGenerationAvailable": await service.gateway.text_generation_available(user),
        "ocrAvailable": ocr_available(),
    }


@router.post("/tables")
async def create_table(body: CreateTable, user: User, service: Service) -> Any:
    try:
        return await service.create_table(user, body.template, body.title)
    except (UserError, NextcloudError) as exc:
        return _errors(exc)


@router.get("/tables/{table_id}/schema")
async def table_schema(table_id: int, user: User, service: Service) -> Any:
    try:
        return (await service.table_schema(user, table_id)).to_dict()
    except (UserError, NextcloudError) as exc:
        return _errors(exc)


@router.get("/files")
async def file_names(ids: str, user: User, service: Service) -> Any:
    """Names of the files the Files action passed in (?fileIds=…), read with the user's permissions."""
    files = []
    for raw in ids.split(",")[:20]:
        try:
            info = await service.gateway.file_info(user, int(raw))
        except (ValueError, NextcloudError):
            continue
        files.append({"id": info.id, "name": info.name, "mime": info.mime, "size": info.size})
    return {"files": files}


@router.get("/jobs")
async def list_jobs(user: User, service: Service) -> Any:
    return {"jobs": [j.to_dict(include_result=False) for j in await service.list_jobs(user)]}


@router.post("/jobs")
async def create_job(body: CreateJob, user: User, service: Service) -> Any:
    try:
        job = await service.submit(user, body.fileId, body.tableId)
    except (UserError, NextcloudError) as exc:
        return _errors(exc)
    return job.to_dict()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: User, service: Service) -> Any:
    try:
        return (await service.get(user, job_id)).to_dict()
    except UserError as exc:
        return _errors(exc)


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, user: User, service: Service) -> Any:
    try:
        return (await service.retry(user, job_id)).to_dict()
    except UserError as exc:
        return _errors(exc)


@router.post("/jobs/{job_id}/save")
async def save_job(job_id: str, body: SaveJob, user: User, service: Service) -> Any:
    try:
        return (await service.save(user, job_id, body.values)).to_dict()
    except (UserError, NextcloudError) as exc:
        return _errors(exc)


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, user: User, service: Service) -> Any:
    try:
        await service.delete(user, job_id)
    except UserError as exc:
        return _errors(exc)
    return {"deleted": job_id}


@router.get("/jobs/{job_id}/pages/{page}")
async def page_image(job_id: str, page: int, user: User, service: Service) -> Response:
    try:
        png = await service.page_png(user, job_id, page)
    except (UserError, NextcloudError) as exc:
        return _errors(exc)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/file-action")
async def file_action(body: FileAction, user: User) -> Any:
    """Called by the Files app's "Extract fields" action. Opens Pinpoint with the chosen files;
    AppAPI appends ?fileIds=… to the redirect."""
    return {"redirect_handler": "main/new"}
