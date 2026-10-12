"""The `tarantino` command line tool.

Talks to a running tarantino instance over HTTP, so it works for any user on
the mini-PC (or from another machine) without touching the database.

Admin commands authenticate with the installation's signing key when it is
readable (the deploy user is in the service group), otherwise with a password
(--password or TARANTINO_ADMIN_PASSWORD).
"""

import json
import sys
import time
from pathlib import Path

import httpx
import typer

from tarantino.auth import COOKIE, make_token
from tarantino.config import SECRET_FILE

app = typer.Typer(help="tarantino home cinema CLI", no_args_is_help=True)
config_app = typer.Typer(help="Export and import the admin configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")
vhs_app = typer.Typer(help="Simulate the VHS recorder.", no_args_is_help=True)
app.add_typer(vhs_app, name="vhs")

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


# -- VHS recorder -------------------------------------------------------------

OUTCOMES = {
    "played": "starting room {room}",
    "learned": "learned for room {room}",
    "unknown": "unknown cassette, ignored (learn it first: tarantino learn <room> --uid <uid>)",
    "ignored": "ignored",
}


def describe_event(event: dict) -> str:
    if event["outcome"] == "learned" and event.get("room") is None:
        return "learned as the franchise cassette"
    text = OUTCOMES.get(event["outcome"], event["outcome"]).format(room=event.get("room"))
    if event["outcome"] == "unknown" or not event.get("message"):
        return text
    return f"{text} ({event['message']})"


def follow_show(client: httpx.Client, show_id: int, timeout: float = 120) -> None:
    """Print a show's steps as they happen until it plays, fails or is replaced."""
    printed = 0
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get("/api/admin/shows")
        if response.status_code == 401:
            typer.echo("(not following the show: no admin access)")
            return
        show = next((s for s in check(response).json() if s["id"] == show_id), None)
        if show is None:
            return
        for step in show["steps"][printed:]:
            if step["status"] == "running":
                break
            typer.echo(f"  {step['step']}: {step['status']}{' - ' + step['message'] if step['message'] else ''}")
            printed += 1
        if show["state"] != "running":
            if show["state"] == "playing":
                typer.echo(f"playing: {show['item_name']}")
                return
            fail(f"show {show['state']}: {show['error']}")
        time.sleep(1)
    fail("gave up waiting for the show (it may still start)")


def insert_uid(ctx: typer.Context, uid: str, wait: bool) -> None:
    event = check(httpx.post(f"{ctx.obj.url}/api/vhs/insert", json={"uid": uid}, timeout=30)).json()
    typer.echo(f"{event['uid']}: {describe_event(event)}")
    if wait and event["outcome"] == "played" and event.get("show_id"):
        follow_show(ctx.obj.client(), event["show_id"])


@vhs_app.command("insert")
def vhs_insert(
    ctx: typer.Context,
    uid: str = typer.Argument(..., help="RFID UID of the cassette."),
    wait: bool = typer.Option(True, help="Follow the show until it plays (needs admin access)."),
) -> None:
    """Insert a cassette, exactly as the VHS recorder would."""
    insert_uid(ctx, uid, wait)


@vhs_app.command("eject")
def vhs_eject(ctx: typer.Context, uid: str | None = typer.Argument(None, help="RFID UID (optional).")) -> None:
    """Eject the cassette (logged only; the show keeps playing)."""
    check(httpx.post(f"{ctx.obj.url}/api/vhs/eject", json={"uid": uid}, timeout=10))
    typer.echo("ejected")


def parse_target(value: str) -> int | None:
    """A room number, or None for "franchise" (the franchise cassette)."""
    if value.casefold() == "franchise":
        return None
    if not value.isdigit():
        fail(f"expected a room number or 'franchise', not {value!r}")
    return int(value)


@app.command()
def learn(
    ctx: typer.Context,
    room: str = typer.Argument(..., help="Room (and cassette) number, or 'franchise' for the franchise cassette."),
    uid: str | None = typer.Option(None, "--uid", help="Simulate this cassette instead of waiting for the recorder."),
    seconds: int = typer.Option(120, help="How long to wait for a cassette."),
) -> None:
    """Bind a cassette to a room (or as the franchise cassette): arms learn mode, then the next insert is learned."""
    number = parse_target(room)
    target = {"room": number} if number is not None else {"franchise": True}
    client = ctx.obj.client()
    state = check(client.post("/api/admin/cassettes/learn", json=target | {"seconds": seconds})).json()
    if uid:
        insert_uid(ctx, uid, wait=False)
        return
    label = f"room {number} ({state['room_name']})" if number is not None else "the franchise run"
    typer.echo(f"Insert the cassette for {label} within {seconds} s ...")
    last_event = (check(client.get("/api/admin/cassettes")).json()["events"] or [{"id": 0}])[0]["id"]
    try:
        while True:
            time.sleep(1)
            overview = check(client.get("/api/admin/cassettes")).json()
            learned = [e for e in overview["events"] if e["id"] > last_event and e["outcome"] == "learned"]
            if learned:
                typer.echo(f"{learned[0]['uid']}: {describe_event(learned[0])}")
                return
            if overview["learn"] is None:
                fail("no cassette was inserted")
    except KeyboardInterrupt:
        client.delete("/api/admin/cassettes/learn")
        fail("cancelled")


@app.command()
def play(
    ctx: typer.Context,
    room: str = typer.Argument(..., help="Room (and cassette) number, or 'franchise'."),
    wait: bool = typer.Option(True, help="Follow the show until it plays."),
) -> None:
    """Insert room N's (or the franchise) learned cassette through the real VHS endpoint."""
    overview = check(ctx.obj.client().get("/api/admin/cassettes")).json()
    number = parse_target(room)
    if number is None:
        if not overview["franchise"]:
            fail("no franchise cassette yet; run: tarantino learn franchise --uid <uid>")
        insert_uid(ctx, overview["franchise"][0]["uid"], wait)
        return
    room = number
    match = next((r for r in overview["rooms"] if r["number"] == room), None)
    if match is None:
        fail(f"no room {room}")
    if not match["cassettes"]:
        fail(f"room {room} has no cassette yet; run: tarantino learn {room} --uid <uid>")
    insert_uid(ctx, match["cassettes"][0]["uid"], wait)


@app.command()
def cassettes(ctx: typer.Context) -> None:
    """List rooms and their cassettes."""
    overview = check(ctx.obj.client().get("/api/admin/cassettes")).json()
    for r in overview["rooms"]:
        uids = ", ".join(c["uid"] for c in r["cassettes"]) or "-"
        typer.echo(f"{r['number']:>3}  {r['name']:<28} {uids}")
    typer.echo(f"{'F':>3}  {'Franchise cassette':<28} {', '.join(c['uid'] for c in overview['franchise']) or '-'}")
    if overview["learn"]:
        typer.echo(f"learn mode: room {overview['learn']['room']} ({overview['learn']['seconds_left']} s left)")
