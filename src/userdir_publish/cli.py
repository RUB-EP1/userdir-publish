"""Command-line interface for ``userdir-publish``."""

import shlex
import subprocess
import sys
from dataclasses import asdict
from typing import Annotated

import typer
from rich.console import Console

from userdir_publish.config import ConfigError, load_settings
from userdir_publish.publish import PublishError, publish, use_ssh

app = typer.Typer()
console = Console(soft_wrap=True)
"""Prints long paths on one line, so that they can be copied."""

RESUME_HINT = "Rerun to resume: files that were already copied are not sent again."


@app.command()
def main(  # ruff: ignore[too-many-arguments]
    source: Annotated[
        str | None,
        typer.Argument(help="Directory with the built website.", show_default=False),
    ] = None,
    *,
    host: Annotated[
        str | None, typer.Option(help="SSH host that serves the pages.")
    ] = None,
    user: Annotated[
        str | None, typer.Option(help="Login name on the host.", show_default=False)
    ] = None,
    web_root: Annotated[
        str | None,
        typer.Option(help="Web directory, may contain {user}.", show_default=False),
    ] = None,
    subdirectory: Annotated[
        str | None,
        typer.Option(help="Subdirectory of the web root.", show_default=False),
    ] = None,
    keep: Annotated[
        list[str] | None,
        typer.Option(help="rsync pattern under the target that is never deleted."),
    ] = None,
    permissions: Annotated[
        str | None,
        typer.Option(
            help="private, group-writable, none, or an rsync --chmod spec.",
            show_default=False,
        ),
    ] = None,
    transport: Annotated[
        str | None,
        typer.Option(help="auto, local, or ssh.", show_default=False),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option(help="Show what would change without copying.")
    ] = False,
    progress: Annotated[
        bool | None,
        typer.Option(
            help="Show the transfer progress. Default: if the output is a terminal.",
            show_default=False,
        ),
    ] = None,
    show_config: Annotated[
        bool, typer.Option(help="Print the merged configuration and exit.")
    ] = False,
) -> None:
    r"""Publish a built website to a web directory served by Apache's mod_userdir.

    Options are read from the user config, then \[tool.userdir-publish] in
    pyproject.toml, then these flags, each overriding the previous.
    """
    cli = {
        "source": source,
        "host": host,
        "user": user,
        "web_root": web_root,
        "subdirectory": subdirectory,
        "keep": keep or None,
        "permissions": permissions,
        "transport": transport,
    }
    if progress is None:
        progress = sys.stdout.isatty()
    try:
        settings = load_settings(cli)
        if show_config:
            for key, value in asdict(settings).items():
                console.print(f"{key} = {value!r}")
            console.print(f"target = {settings.target!r}")
            return
        command = publish(settings, dry_run=dry_run, progress=progress)
    except (ConfigError, PublishError) as exc:
        console.print(f"[red]{exc}")
        raise typer.Exit(code=1) from exc
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]rsync failed: {shlex.join(command_of(exc))}")
        console.print(f"[yellow]{RESUME_HINT}")
        raise typer.Exit(code=exc.returncode) from exc
    except KeyboardInterrupt as exc:
        console.print(f"[red]Interrupted. {RESUME_HINT}")
        raise typer.Exit(code=130) from exc
    if dry_run:
        console.print(f"[yellow]Dry run: {shlex.join(command)}")
        return
    destination = f"{settings.host}:" if use_ssh(settings) else ""
    console.print(f"[green]Published to {destination}{settings.target}")
    url = settings.resolved_url()
    if url is not None:
        console.print(f"[green]{url}")


def command_of(exc: subprocess.CalledProcessError) -> list[str]:
    return [str(arg) for arg in exc.cmd]
