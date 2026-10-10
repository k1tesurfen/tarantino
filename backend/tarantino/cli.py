"""The `tarantino` command line tool.

Talks to a running tarantino instance over HTTP, so it works for any user on
the mini-PC (or from another machine) without touching the database.
"""

import httpx
import typer

app = typer.Typer(help="tarantino home cinema CLI", no_args_is_help=True)

DEFAULT_URL = "http://localhost"


@app.callback()
def main(
    ctx: typer.Context,
    url: str = typer.Option(DEFAULT_URL, "--url", envvar="TARANTINO_URL", help="Base URL of the tarantino server."),
) -> None:
    ctx.obj = {"url": url.rstrip("/")}


@app.command()
def health(ctx: typer.Context) -> None:
    """Check that the tarantino server is up."""
    response = httpx.get(f"{ctx.obj['url']}/api/health", timeout=5)
    response.raise_for_status()
    data = response.json()
    typer.echo(f"{data['status']} (version {data['version']})")
