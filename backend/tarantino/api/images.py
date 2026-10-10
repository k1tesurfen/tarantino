"""Image proxy, so browsers only ever talk to tarantino (no Jellyfin URL or key in the page)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from tarantino.jellyfin.client import JellyfinError
from tarantino.services import Services, get_services

router = APIRouter(prefix="/api/img", tags=["images"])

ImageType = Literal["Primary", "Backdrop", "Logo", "Thumb"]


@router.get("/{item_id}/{image_type}")
async def image(
    services: Annotated[Services, Depends(get_services)],
    item_id: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    image_type: ImageType,
    w: Annotated[int | None, Query(ge=16, le=3840)] = None,
    tag: Annotated[str | None, Query(pattern=r"^[0-9a-zA-Z]{1,64}$")] = None,
) -> Response:
    if services.jellyfin is None:
        raise HTTPException(status_code=503, detail="Jellyfin is not configured")
    params: dict = {"quality": 90}
    if w:
        params["maxWidth"] = w
    if tag:
        params["tag"] = tag
    try:
        upstream = await services.jellyfin.get_image(item_id, image_type, params)
    except JellyfinError:
        raise HTTPException(status_code=404, detail="Image not available")
    # A tag identifies one version of an image, so tagged URLs can be cached forever.
    cache = "public, max-age=31536000, immutable" if tag else "public, max-age=3600"
    return Response(
        upstream.content,
        media_type=upstream.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": cache},
    )
