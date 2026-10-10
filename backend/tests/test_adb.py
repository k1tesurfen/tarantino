import asyncio

from tarantino.projector.adb import Adb, serial_for

RESUMED = """ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
    mResumedActivity: ActivityRecord{1a2b3c u0 org.jellyfin.androidtv/.ui.browsing.MainActivity t42}
"""


def fake_runner(responses: dict[str, tuple[int, str]]):
    calls = []

    async def run(args, timeout):
        calls.append(args)
        if args[0] == "-s":
            command = args[-1] if args[2] == "shell" else args[2]
        else:
            command = args[0]
        return responses.get(command, (0, ""))

    run.calls = calls
    return run


def test_serial_defaults_to_port_5555():
    assert serial_for("192.0.2.50") == "192.0.2.50:5555"
    assert serial_for("projector.example:5556") == "projector.example:5556"


def test_foreground_from_resumed_activity():
    adb = Adb("192.0.2.50", fake_runner({"dumpsys activity activities": (0, RESUMED)}))
    assert asyncio.run(adb.foreground_package()) == "org.jellyfin.androidtv"


def test_foreground_falls_back_to_window_focus():
    runner = fake_runner({
        "dumpsys activity activities": (0, "mResumedActivity: null\n"),
        "dumpsys window": (0, "  mCurrentFocus=Window{9f u0 com.google.android.tvlauncher/.MainActivity}\n"),
    })  # fmt: skip
    assert asyncio.run(Adb("192.0.2.50", runner).foreground_package()) == "com.google.android.tvlauncher"


def test_foreground_unknown_is_none_not_error():
    assert asyncio.run(Adb("192.0.2.50", fake_runner({})).foreground_package()) is None


def test_screen_state():
    asleep = fake_runner({"dumpsys power": (0, "  mWakefulness=Asleep\n")})
    awake = fake_runner({"dumpsys power": (0, "  mWakefulness=Awake\n")})
    assert asyncio.run(Adb("192.0.2.50", asleep).screen_on()) is False
    assert asyncio.run(Adb("192.0.2.50", awake).screen_on()) is True


def test_connect_states():
    unauthorized = fake_runner({"connect": (0, "connected to 192.0.2.50:5555"),
                                "get-state": (1, "error: device unauthorized.")})  # fmt: skip
    assert asyncio.run(Adb("192.0.2.50", unauthorized).connect()) == "unauthorized"
    refused = fake_runner({"connect": (1, "failed to connect to '192.0.2.50:5555': Connection refused")})
    assert asyncio.run(Adb("192.0.2.50", refused).connect()) == "disconnected"
