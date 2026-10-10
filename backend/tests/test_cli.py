import httpx

from tarantino.auth import COOKIE, token_valid
from tarantino.cli import Context
from tarantino.config import load_secret


def test_cli_signs_a_session_with_the_installation_key(tmp_path):
    secret = load_secret(tmp_path)
    assert (tmp_path / "secret.key").stat().st_mode & 0o777 == 0o640
    client = httpx.Client(base_url="http://example.invalid")
    Context("http://example.invalid", tmp_path, None)._authenticate(client)
    assert token_valid(secret, client.cookies.get(COOKIE))


def test_cli_without_key_or_password_sends_no_cookie(tmp_path):
    client = httpx.Client(base_url="http://example.invalid")
    Context("http://example.invalid", tmp_path / "missing", None)._authenticate(client)
    assert client.cookies.get(COOKIE) is None
