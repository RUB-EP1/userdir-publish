"""Validate a built website and copy it to the web directory with rsync."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

if TYPE_CHECKING:
    from userdir_publish.config import Settings


_SYMLINK_EXIT = 3


class PublishError(RuntimeError):
    """Raised when the website cannot be published safely."""


def validate_build(settings: Settings) -> None:
    """Check that the build can be published.

    The build must contain an ``index.html``. If `~.Settings.htaccess_source` is set,
    every ``.htaccess`` file under it must appear unchanged at the same relative path in
    the build. Hidden directories, the build itself, and files ignored by Git are not
    searched.

    Raises:
        PublishError: If a check fails.
    """
    source = settings.source_dir
    if not (source / "index.html").is_file():
        msg = f"The build in {source} has no index.html"
        raise PublishError(msg)
    rules_dir = settings.htaccess_dir
    if rules_dir is None:
        return
    for rules in _access_rules(rules_dir):
        if rules.is_relative_to(source):
            continue
        built = source / rules.relative_to(rules_dir)
        if not built.is_file() or built.read_bytes() != rules.read_bytes():
            msg = f"The build is missing the current access rules: {built}"
            raise PublishError(msg)


def _access_rules(directory: Path) -> Iterator[Path]:
    """Find the ``.htaccess`` files under *directory*, skipping hidden directories.

    In a Git work tree, files that Git ignores are skipped as well.
    """
    tracked = _git_access_rules(directory)
    if tracked is not None:
        yield from tracked
        return
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if ".htaccess" in files:
            yield Path(root, ".htaccess")


def _git_access_rules(directory: Path) -> list[Path] | None:
    """List the ``.htaccess`` files that Git does not ignore.

    Returns `None` outside a Git work tree, or if Git ignores *directory* itself, such
    as a project inside a home directory that is tracked with Git.
    """
    git = shutil.which("git")
    if git is None:
        return None
    ignored = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [git, "check-ignore", "--quiet", "."],
        cwd=directory,
        capture_output=True,
        check=False,
    )
    if ignored.returncode != 1:
        return None
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [
            git,
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            ":(glob)**/.htaccess",
        ],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return [
        directory / name
        for name in result.stdout.split("\0")
        if name and not any(part.startswith(".") for part in Path(name).parent.parts)
    ]


def use_ssh(settings: Settings) -> bool:
    """Decide whether to publish over SSH.

    With ``transport = "auto"``, SSH is used when a host is set and the target directory
    does not exist on this machine.
    """
    if settings.transport == "auto":
        if settings.host is None:
            return False
        return not Path(settings.target).expanduser().is_dir()
    return settings.transport == "ssh"


def rsync_command(
    settings: Settings, *, ssh: bool, dry_run: bool = False, progress: bool = False
) -> list[str]:
    """Build the rsync command that mirrors the build to the target.

    The command passes ``--delete``, so files in the target that are not in the build
    are removed, except those matched by `~.Settings.keep`. Unless *dry_run* is set, a
    local target directory is created, and over SSH the remote target is created by the
    command itself. With *progress*, rsync reports the overall transfer progress.
    """
    command = [_executable("rsync"), "--recursive", "--links", "--times", "--delete"]
    command.extend(_mkpath_arguments(settings, ssh=ssh, dry_run=dry_run))
    if settings.chmod is not None:
        command.extend(["--perms", f"--chmod={settings.chmod}"])
    command.extend(f"--filter=P {pattern}" for pattern in settings.keep)
    if dry_run:
        command.extend(["--dry-run", "--itemize-changes"])
    elif progress:
        command.append("--info=progress2")
    command.append(f"{settings.source_dir}/")
    if ssh:
        command.append(f"{settings.login}@{settings.host}:{settings.remote_target}/")
    else:
        command.append(f"{Path(settings.target).expanduser()}/")
    return command


def _refuse_symlink(settings: Settings, *, ssh: bool) -> None:
    """Refuse a symlinked target, because it may point outside the web root."""
    if ssh:
        target = shlex.quote(settings.remote_target)
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [
                _executable("ssh"),
                f"{settings.login}@{settings.host}",
                f"if [ -L {target} ]; then exit {_SYMLINK_EXIT}; fi",
            ],
            check=False,
        )
        if result.returncode not in {0, _SYMLINK_EXIT}:
            msg = f"Could not inspect {settings.remote_target} on {settings.host}"
            raise PublishError(msg)
        is_symlink = result.returncode == _SYMLINK_EXIT
    else:
        is_symlink = Path(settings.target).expanduser().is_symlink()
    if is_symlink:
        msg = f"Refusing to publish to a symlink: {settings.target}"
        raise PublishError(msg)


def _mkpath_arguments(settings: Settings, *, ssh: bool, dry_run: bool) -> list[str]:
    """Create the parent directories of the target, like ``rsync --mkpath``.

    ``--mkpath`` requires rsync 3.2.3 or newer on both ends, which older servers lack.
    Over SSH, the directories are therefore created by the remote command that starts
    rsync. Once all servers run rsync 3.2.3 or newer, return ``["--mkpath"]`` instead.
    """
    if dry_run:
        return []
    if ssh:
        target = shlex.quote(settings.remote_target)
        return [f"--rsync-path=mkdir -p -- {target} && rsync"]
    Path(settings.target).expanduser().mkdir(parents=True, exist_ok=True)
    return []


def publish(
    settings: Settings, *, dry_run: bool = False, progress: bool = False
) -> list[str]:
    """Copy the build to the target and return the rsync command that was run.

    A dry run still validates the build and refuses a symlinked target, but copies
    nothing and creates no directories.

    Raises:
        PublishError: If the build is invalid or the target is a symlink.
        subprocess.CalledProcessError: If rsync fails.
    """
    validate_build(settings)
    ssh = use_ssh(settings)
    _refuse_symlink(settings, ssh=ssh)
    command = rsync_command(settings, ssh=ssh, dry_run=dry_run, progress=progress)
    subprocess.run(command, check=True)  # ruff: ignore[subprocess-without-shell-equals-true]
    return command


def _executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        msg = f"{name} executable not found in PATH"
        raise PublishError(msg)
    return path
