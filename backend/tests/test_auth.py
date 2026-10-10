import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tarantino.auth import SESSION_SECONDS, make_token, token_valid
from tarantino.main import create_app


@pytest.fixture
def locked(settings, fake_jellyfin, fake_projector):
    settings = settings.model_copy(update={"admin_password": SecretStr("s3cret")})
    app = create_app(settings, jellyfin_transport=fake_jellyfin.transport, remote=fake_projector,
                     waker=fake_projector.wake, adb_factory=fake_projector.adb_factory, run_jobs=False)  # fmt: skip
    with TestClient(app) as client:
        yield client


def test_tokens_expire_and_must_be_signed():
    secret = b"k" * 32
    token = make_token(secret, now=1000)
    assert token_valid(secret, token, now=1000 + 60)
    assert not token_valid(secret, token, now=1000 + SESSION_SECONDS + 1)
    assert not token_valid(b"x" * 32, token, now=1000)
    assert not token_valid(secret, "1000.forged", now=1000)
    assert not token_valid(secret, None)


def test_admin_is_open_without_password(client):
    assert client.get("/api/admin/session").json() == {"password_set": False, "authenticated": True}
    assert client.get("/api/admin/rooms").status_code == 200


def test_admin_requires_login_when_password_set(locked):
    assert locked.get("/api/admin/session").json() == {"password_set": True, "authenticated": False}
    for path in ("/api/admin/rooms", "/api/admin/status", "/api/admin/programme", "/api/admin/settings"):
        assert locked.get(path).status_code == 401, path

    assert locked.post("/api/admin/login", json={"password": "wrong"}).status_code == 401
    assert locked.post("/api/admin/login", json={"password": "s3cret"}).status_code == 200
    assert locked.get("/api/admin/session").json()["authenticated"]
    assert locked.get("/api/admin/rooms").status_code == 200

    locked.post("/api/admin/logout")
    assert locked.get("/api/admin/rooms").status_code == 401


def test_public_routes_stay_open(locked):
    assert locked.get("/api/health").status_code == 200


def test_media_status(client, tmp_path):
    good, empty = tmp_path / "movies", tmp_path / "series"
    good.mkdir()
    (good / "Some Film (1999)").mkdir()
    empty.mkdir()
    client.patch("/api/admin/settings", json={"media_paths": [str(good), str(empty), str(tmp_path / "missing")]})
    media = client.get("/api/admin/status").json()["media"]
    assert media["state"] == "error"
    assert [m["ok"] for m in media["mounts"]] == [True, False, False]


def test_home_assistant_unconfigured(client):
    assert client.get("/api/admin/status").json()["home_assistant"]["state"] == "unconfigured"
