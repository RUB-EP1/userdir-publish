"""Layered configuration: defaults, user config, project config, and CLI flags.

Each layer overrides the one before it. For the login name, a matching host entry in the
user config overrides the project config, while the CLI takes precedence over both. The
``USER`` environment variable supplies the fallback. Exact host entries take precedence
over patterns; otherwise the first matching pattern in file order applies.
"""

# cspell:ignore rwxs
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field, fields
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any, Literal, get_args

TOOL_NAME = "userdir-publish"

Transport = Literal["auto", "local", "ssh"]
"""How to reach the web directory, see `Settings.transport`."""
TRANSPORTS: tuple[Transport, ...] = get_args(Transport)

PermissionPreset = Literal["private", "group-writable", "none"]
"""Named permission settings, see `Settings.permissions`."""

PERMISSION_PRESETS: dict[PermissionPreset, str | None] = {
    "private": "Dg-rwx,Do=x,Fg-rwx,Fo=r",
    "group-writable": "Dg=rwxs,Do=x,Fg=rw,Fo=r",
    "none": None,
}
"""Named arguments for ``rsync --chmod``, see `Settings.permissions`."""

_CHMOD_CLAUSE = r"[DF]?(?:[0-7]{3,4}|[ugoa]*(?:[-+=][rwxXst]*)+)"
CHMOD_PATTERN = rf"^{_CHMOD_CLAUSE}(?:,{_CHMOD_CLAUSE})*$"
"""Comma-separated clauses accepted by ``rsync --chmod``, such as ``D2775,Fg-w``.

`Settings.permissions` must be a key of `PERMISSION_PRESETS` or match this pattern.
"""


class ConfigError(ValueError):
    """Raised when a configuration value is invalid."""


@dataclass(frozen=True)
class Settings:
    """Merged and validated configuration for one publication.

    Create it with `load_settings` rather than directly, so that all configuration
    layers are applied and the values are validated.
    """

    source: str | None = field(
        default=None,
        metadata={"examples": ["docs/_build/html"]},
    )
    """Directory of the built website, relative to the directory with ``pyproject.toml``.

    The first command-line argument overrides it.
    """
    host: str | None = field(default=None, metadata={"examples": ["web.example.edu"]})
    """SSH host that serves the pages. Without it, only local publishing is possible."""
    web_root: str = "~/public_html"
    """Web directory on the server. ``{user}`` is replaced by the login name.

    A leading ``~`` means the home directory of the login on the server.
    """
    subdirectory: str = ""
    """Subdirectory of the web root that this project owns. Empty means the web root.

    Files in it that are not in the build are deleted.
    """
    keep: tuple[str, ...] = ()
    """``rsync`` filter patterns, relative to the target, for files that are never deleted.

    For example, ``/*/`` keeps all top-level directories.
    """
    permissions: PermissionPreset | str = field(
        default="private",
        metadata={"pattern": CHMOD_PATTERN},
    )
    """Permissions of the published files, as a preset or a raw ``rsync --chmod`` spec.

    ``private`` hides the files from group members, ``group-writable`` lets the group
    maintain a shared page, and ``none`` keeps the local modes.
    """
    transport: Transport = "auto"
    """How to reach the web directory.

    ``auto`` uses SSH if `host` is set and the target does not exist on this machine.
    """
    htaccess_source: str | None = field(default=None, metadata={"examples": ["docs"]})
    """Directory, relative to the project root, whose ``.htaccess`` files the build must contain.

    Publishing is refused if a build lacks one of them or contains an outdated copy.
    """
    url: str | None = field(
        default=None,
        metadata={"examples": ["https://web.example.edu/~{user}/{subdirectory}/"]},
    )
    """Address printed after publishing. ``{user}`` and ``{subdirectory}`` are replaced.

    Defaults to ``https://{host}/~{user}/{subdirectory}/`` if `host` is set.
    """
    user: str | None = field(default=None, metadata={"examples": ["jdoe"]})
    """Login name on the host. Defaults to the ``USER`` environment variable."""
    _project_root: Path = field(default=Path(), repr=False)

    @property
    def login(self) -> str:
        """`user`, or the ``USER`` environment variable if it is not set.

        Raises:
            ConfigError: If neither is set.
        """
        user = self.user or os.getenv("USER")
        if not user:
            msg = "Could not determine the login name, set it with --user"
            raise ConfigError(msg)
        return user

    @property
    def chmod(self) -> str | None:
        """`permissions` as ``rsync --chmod`` spec, or `None` to leave them as is."""
        return PERMISSION_PRESETS.get(self.permissions, self.permissions)

    @property
    def source_dir(self) -> Path:
        """`source` resolved against the project root.

        Raises:
            ConfigError: If `source` is not set.
        """
        if self.source is None:
            msg = "No source directory given, pass it as argument or set source"
            raise ConfigError(msg)
        return self._project_root / self.source

    @property
    def htaccess_dir(self) -> Path | None:
        """`htaccess_source` resolved against the project root."""
        if self.htaccess_source is None:
            return None
        return self._project_root / self.htaccess_source

    @property
    def target(self) -> str:
        """`web_root` with ``{user}`` replaced, followed by `subdirectory`.

        A leading ``~`` is kept, so the path is valid on the host and on this machine.

        Raises:
            ConfigError: If the web root is empty.
        """
        root = self.web_root.format(user=self.login).rstrip("/")
        if not root:
            msg = "The web root may not be empty"
            raise ConfigError(msg)
        if not self.subdirectory:
            return root
        return f"{root}/{self.subdirectory}"

    @property
    def remote_target(self) -> str:
        """Target path for SSH, where a leading ``~/`` means the login's home."""
        return self.target.removeprefix("~/")

    def resolved_url(self) -> str | None:
        """`url` with ``{user}`` and ``{subdirectory}`` replaced.

        Without `url`, the address is derived from `host`, or `None` if that is unset.
        """
        if self.url is not None:
            return self.url.format(user=self.login, subdirectory=self.subdirectory)
        if self.host is None:
            return None
        path = "/".join(part for part in (f"~{self.login}", self.subdirectory) if part)
        return f"https://{self.host}/{path}/"


def load_settings(
    cli: dict[str, Any] | None = None,
    *,
    project_root: Path | None = None,
    user_config: Path | None = None,
) -> Settings:
    """Merge all configuration layers into one `Settings` object.

    Entries of *cli* that are `None` count as not given. *project_root* is the directory
    with the ``pyproject.toml`` that holds the project configuration and defaults to the
    nearest such directory at or above the working directory. *user_config* defaults to
    `user_config_path`.

    Raises:
        ConfigError: If an option is unknown or a value is invalid.
    """
    if project_root is None:
        project_root = _find_project_root(Path.cwd())
    if user_config is None:
        user_config = user_config_path()
    user_table = _read_table(user_config, key=None)
    project_table = _read_table(project_root / "pyproject.toml", key=TOOL_NAME)
    cli = {k: v for k, v in (cli or {}).items() if v is not None}
    hosts = user_table.pop("hosts", {})
    merged = {**user_table, **project_table}
    host = cli.get("host", merged.get("host"))
    if host is not None:
        if host in hosts:
            merged.update(hosts[host])
        else:
            for pattern, options in hosts.items():
                if fnmatchcase(host, pattern):
                    merged.update(options)
                    break
    merged.update(cli)
    settings = _to_settings(merged, project_root)
    _validate(settings)
    return settings


def _find_project_root(start: Path) -> Path:
    for directory in (start, *start.parents):
        if (directory / "pyproject.toml").is_file():
            return directory
    return start


def user_config_path() -> Path:
    """Locate the user configuration file.

    This is :file:`$XDG_CONFIG_HOME/userdir-publish.toml` if it exists, otherwise
    :file:`$XDG_CONFIG_HOME/userdir-publish/config.toml`. ``XDG_CONFIG_HOME`` defaults
    to :file:`~/.config`.

    Raises:
        ConfigError: If both files exist.
    """
    config_home = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    nested = config_home / TOOL_NAME / "config.toml"
    flat = config_home / f"{TOOL_NAME}.toml"
    if nested.is_file() and flat.is_file():
        msg = f"Found both {nested} and {flat}; keep only one"
        raise ConfigError(msg)
    return flat if flat.is_file() else nested


def _read_table(path: Path, key: str | None) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as stream:
        table = tomllib.load(stream)
    if key is not None:
        table = table.get("tool", {}).get(key, {})
    normalized = _normalize_keys(table)
    if "hosts" in normalized:
        normalized["hosts"] = {
            host: _normalize_keys(options)
            for host, options in normalized["hosts"].items()
        }
    return normalized


def _normalize_keys(table: dict[str, Any]) -> dict[str, Any]:
    return {k.replace("-", "_"): v for k, v in table.items()}


def _to_settings(table: dict[str, Any], project_root: Path) -> Settings:
    known = {f.name for f in fields(Settings) if not f.name.startswith("_")}
    unknown = sorted(set(table) - known)
    if unknown:
        msg = f"Unknown {TOOL_NAME} options: {', '.join(unknown)}"
        raise ConfigError(msg)
    if "keep" in table:
        table["keep"] = tuple(table["keep"])
    return Settings(**table, _project_root=project_root)


def _validate(settings: Settings) -> None:
    if settings.transport not in TRANSPORTS:
        msg = f"transport must be one of {', '.join(TRANSPORTS)}"
        raise ConfigError(msg)
    if settings.transport == "ssh" and not settings.host:
        msg = "Publishing over SSH requires a host"
        raise ConfigError(msg)
    subdirectory = PurePosixPath(settings.subdirectory)
    if subdirectory.is_absolute() or ".." in subdirectory.parts:
        msg = f"subdirectory must be relative to the web root: {settings.subdirectory}"
        raise ConfigError(msg)
    if settings.permissions not in PERMISSION_PRESETS and not re.match(
        CHMOD_PATTERN, settings.permissions
    ):
        msg = f"permissions is neither a preset nor an rsync --chmod spec: {settings.permissions!r}"
        raise ConfigError(msg)
    if any(c.isspace() for c in settings.login) or "@" in settings.login:
        msg = f"Invalid login name: {settings.login!r}"
        raise ConfigError(msg)
    _ = settings.target  # raises if the web root is empty
