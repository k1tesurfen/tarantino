from fastapi.testclient import TestClient

from tarantino.config import Settings
from tarantino.main import create_app


def make_client(tmp_path, with_frontend: bool) -> TestClient:
    build = tmp_path / "build"
    build.mkdir()
    if with_frontend:
        (build / "index.html").write_text("<html>spa</html>")
        (build / "favicon.png").write_bytes(b"png")
    app = create_app(Settings(frontend_dir=build, data_dir=tmp_path / "data"), run_jobs=False)
    return TestClient(app)


def test_health(tmp_path):
    with make_client(tmp_path, with_frontend=False) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_placeholder_without_frontend(tmp_path):
    with make_client(tmp_path, with_frontend=False) as client:
        assert "frontend has not been built" in client.get("/").text


def test_spa_fallback_and_static_files(tmp_path):
    with make_client(tmp_path, with_frontend=True) as client:
        assert client.get("/admin/rooms").text == "<html>spa</html>"
        assert client.get("/favicon.png").content == b"png"


def test_unknown_api_route_is_404(tmp_path):
    with make_client(tmp_path, with_frontend=True) as client:
        assert client.get("/api/nope").status_code == 404


def test_no_path_traversal(tmp_path):
    with make_client(tmp_path, with_frontend=True) as client:
        assert client.get("/..%2F..%2Fetc%2Fpasswd").text == "<html>spa</html>"


def test_status_without_jellyfin_key(tmp_path):
    with make_client(tmp_path, with_frontend=False) as client:
        assert client.get("/api/admin/status").json()["jellyfin"]["state"] == "unconfigured"
