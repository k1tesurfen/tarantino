import asyncio
from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from tarantino.configio.transfer import apply_import, export_config, parse_export, preview_import
from tarantino.services import Services, get_services

router = APIRouter(prefix="/api/admin", tags=["config"])

ServicesDep = Annotated[Services, Depends(get_services)]


def _parse(document: dict):
    try:
        return parse_export(document)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Not a valid tarantino export: {exc}")


@router.get("/config/export")
def export(services: ServicesDep, state: Annotated[bool, Query()] = True) -> JSONResponse:
    data = export_config(services.session_factory, services.settings, include_state=state)
    filename = f"tarantino-config-{datetime.now():%Y%m%d-%H%M}.tarantino.json"
    return JSONResponse(
        data.model_dump(mode="json"), headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/config/import/preview")
def import_preview(services: ServicesDep, document: Annotated[dict, Body()]) -> dict:
    return asdict(preview_import(services.session_factory, services.settings, _parse(document)))


@router.post("/config/import")
async def import_config(services: ServicesDep, document: Annotated[dict, Body()]) -> dict:
    export = _parse(document)
    backup = await asyncio.to_thread(services.backups.create, "pre-import")
    await asyncio.to_thread(apply_import, services.session_factory, export)
    services.projector.connect()  # the projector address may have changed
    await services.ensure_programme()
    services.events.publish("programme", {"date": services.programme.today().isoformat()})
    return {"imported": True, "backup": backup.name}


@router.get("/backups")
def list_backups(services: ServicesDep) -> list[dict]:
    return [asdict(b) for b in services.backups.list()]


@router.post("/backups", status_code=201)
async def create_backup(services: ServicesDep, reason: Annotated[str, Query()] = "manual") -> dict:
    try:
        return asdict(await asyncio.to_thread(services.backups.create, reason))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/backups/{name}")
def download_backup(services: ServicesDep, name: str) -> FileResponse:
    try:
        path = services.backups.path(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No such backup")
    return FileResponse(path, media_type="application/json", filename=name)


@router.post("/backups/{name}/preview")
def preview_backup(services: ServicesDep, name: str) -> dict:
    try:
        document = services.backups.read(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No such backup")
    return import_preview(services, document)


@router.post("/backups/{name}/restore")
async def restore_backup(services: ServicesDep, name: str) -> dict:
    try:
        document = services.backups.read(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No such backup")
    return await import_config(services, document)
