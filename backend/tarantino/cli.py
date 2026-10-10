"""The `tarantino` command line tool.

Talks to a running tarantino instance over HTTP, so it works for any user on
the mini-PC (or from another machine) without touching the database.

Admin commands authenticate with the installation's signing key when it is
readable (the deploy user is in the service group), otherwise with a password
(--password or TARANTINO_ADMIN_PASSWORD).
"""

import json
import sys
from pathlib import Path

import httpx
import typer

from tarantino.auth import COOKIE, make_token
from tarantino.config import SECRET_FILE

app = typer.Typer(help="tarantino home cinema CLI", no_args_is_help=True)
config_app = typer.Typer(help="Export and import the admin configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")

DEFAULT_URL = "http://localhost"
DEFAULT_DATA_DIR = Path("/var/lib/tarantino")


class Context:
    def __init__(self, url: str, data_dir: Path, password: str | None):
        self.url = url.rstrip("/")
        self.data_dir = data_dir
        self.password = password
        self._client: httpx.Client | None = None

    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.url, timeout=60)
            self._authenticate(self._client)
        return self._client

    def _authenticate(self, client: httpx.Client) -> None:
        secret_path = self.data_dir / SECRET_FILE
        try:
            secret = bytes.fromhex(secret_path.read_text().strip())
        except OSError:
            secret = None
        if secret:
            client.cookies.set(COOKIE, make_token(secret))
            return
        if self.password:
            response = client.post("/api/admin/login", json={"password": self.password})
            if response.status_code == 401:
                fail("Wrong admin password")
            response.raise_for_status()


def fail(message: str) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(1)


def check(response: httpx.Response) -> httpx.Response:
    if response.status_code == 401:
        fail("Not authorised: run as the deploy user (service group) or pass --password")
    if response.is_error:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text
        fail(f"HTTP {response.status_code}: {detail}")
    return response


@app.callback()
def main(
    ctx: typer.Context,
    url: str = typer.Option(DEFAULT_URL, "--url", envvar="TARANTINO_URL", help="Base URL of the tarantino server."),
    data_dir: Path = typer.Option(
        DEFAULT_DATA_DIR, "--data-dir", envvar="TARANTINO_DATA_DIR", help="Where to find the signing key."
    ),
    password: str | None = typer.Option(None, "--password", envvar="TARANTINO_ADMIN_PASSWORD", help="Admin password."),
) -> None:
    ctx.obj = Context(url, data_dir, password)


@app.command()
def health(ctx: typer.Context) -> None:
    """Check that the tarantino server is up."""
    data = check(httpx.get(f"{ctx.obj.url}/api/health", timeout=5)).json()
    typer.echo(f"{data['status']} (version {data['version']})")


@app.command()
def backup(
    ctx: typer.Context,
    reason: str = typer.Option("manual", help="manual, pre-update, nightly or pre-import"),
) -> None:
    """Write a config backup on the server."""
    data = check(ctx.obj.client().post("/api/admin/backups", params={"reason": reason})).json()
    typer.echo(f"backup written: {data['name']}")


@config_app.command("export")
def config_export(
    ctx: typer.Context,
    output: Path | None = typer.Argument(None, help="File to write (default: stdout)."),
    state: bool = typer.Option(True, help="Include sticky series and programme history."),
) -> None:
    """Export the configuration (never contains secrets)."""
    data = check(ctx.obj.client().get("/api/admin/config/export", params={"state": state})).json()
    text = json.dumps(data, indent=2)
    if output:
        output.write_text(text)
        typer.echo(f"written: {output}", err=True)
    else:
        sys.stdout.write(text + "\n")


@config_app.command("import")
def config_import(
    ctx: typer.Context,
    file: Path = typer.Argument(..., exists=True, readable=True, help="An export file."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply without asking."),
) -> None:
    """Show what an import would change, then apply it."""
    document = json.loads(file.read_text())
    client = ctx.obj.client()
    preview = check(client.post("/api/admin/config/import/preview", json=document)).json()
    typer.echo(f"Export from {preview['exported_at']} (tarantino {preview['tarantino_version']})")
    for key, change in preview["settings_changed"].items():
        typer.echo(f"  setting {key}: {change['from']!r} -> {change['to']!r}")
    for label, rooms in (("added", "rooms_added"), ("changed", "rooms_changed"), ("removed", "rooms_removed")):
        for room in preview[rooms]:
            typer.echo(f"  room {label}: {room}")
    if preview["state_included"]:
        typer.echo(f"  state: {preview['series_assignments']} series assignments, "
                   f"{preview['programme_entries']} programme entries, {preview['remapped_titles']} remapped")  # fmt: skip
        for title in preview["unresolved_titles"]:
            typer.echo(f"  not in library (skipped): {title}")
    if not yes and not typer.confirm("Apply this import?"):
        raise typer.Exit(1)
    result = check(client.post("/api/admin/config/import", json=document)).json()
    typer.echo(f"imported (previous configuration saved as {result['backup']})")
