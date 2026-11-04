# cspell:ignore delenv
from __future__ import annotations

from dataclasses import replace
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from userdir_publish.config import ConfigError, load_settings, user_config_path

if TYPE_CHECKING:
    from pathlib import Path


def _write(project: Path, user_config: Path, *, tool: str, user: str = "") -> None:
    (project / "pyproject.toml").write_text(
        "[tool.userdir-publish]\n" + dedent(tool).lstrip("\n")
    )
    user_config.write_text(dedent(user))


def describe_load_settings():
    def it_layers_cli_project_and_user_config(project: Path, user_config: Path):
        _write(
            project,
            user_config,
            tool="""
                host = "web.example.edu"
                subdirectory = "notes"
                permissions = "none"
            """,
            user="""
                permissions = "group-writable"
                web-root = "/srv/{user}/www"

                [hosts."web.example.edu"]
                user = "jdoe"
            """,
        )
        settings = load_settings(
            cli={"subdirectory": "talks", "host": None},
            project_root=project,
            user_config=user_config,
        )
        assert settings.host == "web.example.edu"
        assert settings.permissions == "none"
        assert settings.login == "jdoe"
        assert settings.target == "/srv/jdoe/www/talks"

    def it_lets_cli_user_override_host_table(project: Path, user_config: Path):
        _write(
            project,
            user_config,
            tool='host = "web.example.edu"\n',
            user="""
                [hosts."web.example.edu"]
                user = "jdoe"
            """,
        )
        settings = load_settings(
            cli={"user": "alice"}, project_root=project, user_config=user_config
        )
        assert settings.login == "alice"

    def it_rejects_unknown_options(project: Path, user_config: Path):
        _write(project, user_config, tool='sub-directory = "notes"\n')
        with pytest.raises(ConfigError, match="sub_directory"):
            load_settings(project_root=project, user_config=user_config)

    @pytest.mark.parametrize("name", ["project_root", "_project_root"])
    def it_keeps_project_root_internal(project: Path, user_config: Path, name):
        _write(project, user_config, tool=f'{name} = "/other"\n')
        with pytest.raises(
            ConfigError, match=f"Unknown userdir-publish options: {name}"
        ):
            load_settings(project_root=project, user_config=user_config)

    @pytest.mark.parametrize("subdirectory", ["/etc", "../other", "a/../../b"])
    def it_rejects_unsafe_subdirectories(
        project: Path, user_config: Path, subdirectory: str
    ):
        with pytest.raises(ConfigError, match="relative"):
            load_settings(
                cli={"subdirectory": subdirectory},
                project_root=project,
                user_config=user_config,
            )

    @pytest.mark.parametrize(
        ("permissions", "valid"),
        [
            ("group-writable", True),
            ("D2775,F664", True),
            ("Dg-rwx,Do=x,Fg-rwx,Fo=r", True),
            ("u+rw-x,go=", True),
            ("everyone", False),
            ("D2775,", False),
            ("F999", False),
        ],
    )
    def it_validates_permissions(
        project: Path, user_config: Path, permissions: str, valid: bool
    ):
        def load():
            return load_settings(
                cli={"permissions": permissions},
                project_root=project,
                user_config=user_config,
            )

        if valid:
            assert load().permissions == permissions
        else:
            with pytest.raises(ConfigError, match="rsync --chmod"):
                load()

    def describe_host_patterns():
        @pytest.mark.parametrize(
            ("host", "cli", "expected"),
            [
                ("web.example.edu", {}, "exact"),
                ("www.example.edu", {}, "domain"),
                ("web1.example.org", {}, "numbered"),
                ("web2.example.org", {}, "numbered"),
                ("web3.example.org", {}, "catchall"),
                ("other.example.org", {}, "catchall"),
                ("WWW.EXAMPLE.EDU", {}, "catchall"),
                (None, {}, "default"),
                ("www.example.edu", {"user": "cli"}, "cli"),
                ("web.example.edu", {"host": "www.example.edu"}, "domain"),
            ],
        )
        def it_selects_the_matching_user(
            project: Path, user_config: Path, host, cli, expected
        ):
            _write(
                project,
                user_config,
                tool=f'host = "{host}"\n' if host is not None else "",
                user="""
                    user = "default"

                    [hosts."*.example.edu"]
                    user = "domain"

                    [hosts."w??.example.edu"]
                    user = "later"

                    [hosts."web[12].example.org"]
                    user = "numbered"

                    [hosts."*"]
                    user = "catchall"

                    [hosts."web.example.edu"]
                    user = "exact"
                """,
            )
            settings = load_settings(cli, project_root=project, user_config=user_config)
            assert settings.login == expected

        @pytest.mark.parametrize("host", ["web1.example.edu", "web12.example.edu"])
        def it_falls_back_to_the_default_user(project: Path, user_config: Path, host):
            _write(
                project,
                user_config,
                tool=f'host = "{host}"\n',
                user="""
                    user = "default"

                    [hosts."web?.example.edu"]
                    user = "matched"
                """,
            )
            settings = load_settings(project_root=project, user_config=user_config)
            expected = "matched" if host == "web1.example.edu" else "default"
            assert settings.login == expected

        @pytest.mark.parametrize(
            ("user", "cli", "expected"),
            [
                ('user = "default"\n', {}, "shared"),
                (
                    """
                    [hosts."web.example.edu"]
                    user = "personal"
                    """,
                    {},
                    "personal",
                ),
                (
                    """
                    [hosts."*.example.edu"]
                    user = "personal"
                    """,
                    {},
                    "personal",
                ),
                (
                    """
                    [hosts."*"]
                    user = "personal"
                    """,
                    {"user": "cli"},
                    "cli",
                ),
            ],
        )
        def it_ranks_project_user_below_host_tables(
            project: Path, user_config: Path, user, cli, expected
        ):
            _write(
                project,
                user_config,
                tool="""
                    host = "web.example.edu"
                    user = "shared"
                """,
                user=user,
            )
            settings = load_settings(cli, project_root=project, user_config=user_config)
            assert settings.login == expected

        def it_ranks_host_tables_below_cli(project: Path, user_config: Path):
            _write(
                project,
                user_config,
                tool='host = "web.example.edu"\n',
                user="""
                    [hosts."*"]
                    web-root = "/profile"
                """,
            )
            settings = load_settings(
                cli={"web_root": "/cli"}, project_root=project, user_config=user_config
            )
            assert settings.web_root == "/cli"


def describe_user_config_path():
    @pytest.mark.parametrize(
        "name", ["userdir-publish/config.toml", "userdir-publish.toml"]
    )
    def it_finds_the_config_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
    ):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        assert user_config_path() == path

    def it_refuses_ambiguous_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        (tmp_path / "userdir-publish").mkdir()
        (tmp_path / "userdir-publish" / "config.toml").touch()
        (tmp_path / "userdir-publish.toml").touch()
        with pytest.raises(ConfigError, match="keep only one"):
            user_config_path()


def describe_validation():
    @pytest.mark.parametrize(
        ("cli", "match"),
        [
            ({"transport": "pigeon"}, "transport must be one of"),
            ({"transport": "ssh"}, "requires a host"),
            ({"user": "j doe"}, "Invalid login name"),
            ({"user": "jdoe@host"}, "Invalid login name"),
        ],
    )
    def it_rejects_invalid_values(
        project: Path, user_config: Path, cli: dict, match: str
    ):
        with pytest.raises(ConfigError, match=match):
            load_settings(
                cli={"user": "jdoe", **cli},
                project_root=project,
                user_config=user_config,
            )

    def it_requires_a_login(
        project: Path, user_config: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("USER", raising=False)
        with pytest.raises(ConfigError, match="login name"):
            load_settings(project_root=project, user_config=user_config)

    def it_rejects_an_empty_web_root(project: Path, user_config: Path):
        with pytest.raises(ConfigError, match="may not be empty"):
            load_settings(
                cli={"user": "jdoe", "web_root": "/"},
                project_root=project,
                user_config=user_config,
            )


def describe_resolved_url():
    def it_fills_in_placeholders(project: Path, user_config: Path):
        settings = load_settings(
            cli={"user": "jdoe", "subdirectory": "tips"},
            project_root=project,
            user_config=user_config,
        )
        assert settings.resolved_url() is None
        settings = replace(settings, url="https://example.edu/~{user}/{subdirectory}/")
        assert settings.resolved_url() == "https://example.edu/~jdoe/tips/"

    def it_derives_the_address_from_the_host(project: Path, user_config: Path):
        settings = load_settings(
            cli={
                "user": "jdoe",
                "host": "web.example.edu",
                "subdirectory": "tips",
            },
            project_root=project,
            user_config=user_config,
        )
        assert settings.resolved_url() == "https://web.example.edu/~jdoe/tips/"
        settings = replace(settings, subdirectory="")
        assert settings.resolved_url() == "https://web.example.edu/~jdoe/"


def describe_project_root():
    def it_searches_parent_directories(
        project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.chdir(project / "docs" / "_build")
        settings = load_settings(cli={"user": "jdoe"})
        assert settings.source_dir == project / "docs" / "_build" / "html"

    def it_falls_back_to_the_working_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        settings = load_settings(cli={"user": "jdoe", "source": "site"})
        assert settings.source_dir == empty / "site"
