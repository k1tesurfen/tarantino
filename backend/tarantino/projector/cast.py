"""Wake the projector from network standby with a Chromecast app launch.

In standby the projector drops ADB and ping but keeps its Cast receiver
listening; launching an app over Cast turns the projector on.
"""

import asyncio
import time
import uuid

import pychromecast
from pychromecast.models import CastInfo, HostServiceInfo

CAST_PORT = 8009
DEFAULT_MEDIA_RECEIVER = "CC1AD845"


class CastError(Exception):
    pass


def _wake_blocking(host: str, timeout: float) -> bool:
    """Return True if the projector was in standby and has been woken."""
    info = CastInfo(
        services={HostServiceInfo(host, CAST_PORT)}, uuid=uuid.uuid5(uuid.NAMESPACE_DNS, host),
        model_name=None, friendly_name="projector", host=host, port=CAST_PORT,
        cast_type="cast", manufacturer=None,
    )  # fmt: skip
    try:
        cast = pychromecast.get_chromecast_from_cast_info(info, zconf=None, tries=1, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - pychromecast raises assorted errors
        raise CastError(f"Cast connection failed: {exc}") from exc
    try:
        cast.wait(timeout=timeout)
        if not cast.status.is_stand_by:
            return False
        cast.start_app(DEFAULT_MEDIA_RECEIVER, timeout=timeout)
        deadline = time.monotonic() + timeout
        while cast.status.is_stand_by and time.monotonic() < deadline:
            time.sleep(0.5)
        # Leave the receiver again; the caller opens the app it actually wants.
        cast.quit_app(timeout=timeout)
        return True
    except Exception as exc:  # noqa: BLE001
        raise CastError(f"Cast wake failed: {exc}") from exc
    finally:
        cast.disconnect(timeout=5)


async def cast_wake(host: str, timeout: float = 10) -> bool:
    return await asyncio.to_thread(_wake_blocking, host, timeout)
