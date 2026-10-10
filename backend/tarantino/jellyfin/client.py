from collections.abc import AsyncIterator
from typing import Any

import httpx

from tarantino import __version__

PAGE_SIZE = 500


class JellyfinError(Exception):
    pass


class JellyfinClient:
    """Thin async client for the parts of the Jellyfin API tarantino uses."""

    def __init__(self, base_url: str, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None):
        auth = (
            f'MediaBrowser Client="tarantino", Device="tarantino", DeviceId="tarantino-core", '
            f'Version="{__version__}", Token="{api_key}"'
        )
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": auth},
            timeout=httpx.Timeout(20, connect=5),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise JellyfinError(f"Jellyfin unreachable: {exc.__class__.__name__}") from exc
        if response.status_code in (401, 403):
            raise JellyfinError("Jellyfin rejected the API key")
        if response.is_error:
            raise JellyfinError(f"Jellyfin returned HTTP {response.status_code} for {path}")
        return response

    async def _get_json(self, path: str, **params) -> Any:
        return (await self._request("GET", path, params=params)).json()

    async def system_info(self) -> dict:
        return await self._get_json("/System/Info")

    async def find_user(self, name: str) -> dict:
        users = await self._get_json("/Users")
        for user in users:
            if user["Name"].casefold() == name.casefold():
                return user
        raise JellyfinError(f"Jellyfin user '{name}' not found")

    async def iter_items(self, user_id: str, item_types: list[str], fields: list[str]) -> AsyncIterator[dict]:
        start = 0
        while True:
            page = await self._get_json(
                "/Items",
                userId=user_id,
                includeItemTypes=",".join(item_types),
                recursive="true",
                fields=",".join(fields),
                enableUserData="true",
                enableImageTypes="Primary,Backdrop,Logo,Thumb",
                imageTypeLimit=1,
                excludeLocationTypes="Virtual",
                startIndex=start,
                limit=PAGE_SIZE,
                enableTotalRecordCount="true",
            )
            items = page.get("Items", [])
            for item in items:
                yield item
            start += len(items)
            if not items or start >= page.get("TotalRecordCount", 0):
                return

    async def sessions(self, controllable_by_user_id: str | None = None, active_within_seconds: int = 900) -> list[dict]:
        params: dict[str, Any] = {"activeWithinSeconds": active_within_seconds}
        if controllable_by_user_id:
            params["controllableByUserId"] = controllable_by_user_id
        return await self._get_json("/Sessions", **params)

    async def play(self, session_id: str, item_ids: list[str], start_position_ticks: int = 0) -> None:
        await self._request(
            "POST",
            f"/Sessions/{session_id}/Playing",
            params={
                "playCommand": "PlayNow",
                "itemIds": ",".join(item_ids),
                "startPositionTicks": start_position_ticks,
            },
        )

    async def seek(self, session_id: str, position_ticks: int) -> None:
        await self._request(
            "POST", f"/Sessions/{session_id}/Playing/Seek", params={"seekPositionTicks": position_ticks}
        )

    async def next_up(self, user_id: str, series_id: str) -> dict | None:
        page = await self._get_json(
            "/Shows/NextUp", userId=user_id, seriesId=series_id, enableResumable="true",
            enableRewatching="false", limit=1, enableUserData="true",
        )  # fmt: skip
        items = page.get("Items", [])
        return items[0] if items else None

    async def episodes(self, series_id: str, user_id: str, start_item_id: str, limit: int) -> list[dict]:
        page = await self._get_json(
            f"/Shows/{series_id}/Episodes", userId=user_id, startItemId=start_item_id,
            limit=limit, enableUserData="true", isMissing="false",
        )  # fmt: skip
        return page.get("Items", [])

    async def get_image(self, item_id: str, image_type: str, params: dict[str, Any]) -> httpx.Response:
        return await self._request("GET", f"/Items/{item_id}/Images/{image_type}", params=params)
