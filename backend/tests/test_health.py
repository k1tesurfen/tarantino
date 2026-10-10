from fastapi.testclient import TestClient

from tarantino.config import Settings
from tarantino.main import create_app


def make_client(tmp_path, with_frontend: bool) -> TestClient:
    if with_frontend:
        (tmp_path / "index.html").write_text("<html>spa</html>")
        (tmp_path / "favicon.png").write_bytes(b"png")
    return TestClient(create_app(Settings(frontend_dir=tmp_path, data_dir=tmp_path / "data")))


def test_health(tmp_path):
    response = make_client(tmp_path, with_frontend=False).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_placeholder_without_frontend(tmp_path):
    response = make_client(tmp_path, with_frontend=False).get("/")
    assert "frontend has not been built" in response.text


def test_spa_fallback_and_static_files(tmp_path):
    client = make_client(tmp_path, with_frontend=True)
    assert client.get("/admin/rooms").text == "<html>spa</html>"
    assert client.get("/favicon.png").content == b"png"


def test_unknown_api_route_is_404(tmp_path):
    assert make_client(tmp_path, with_frontend=True).get("/api/nope").status_code == 404


def test_no_path_traversal(tmp_path):
    client = make_client(tmp_path, with_frontend=True)
    assert client.get("/..%2F..%2Fetc%2Fpasswd").text == "<html>spa</html>"
