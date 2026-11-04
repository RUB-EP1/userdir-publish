from __future__ import annotations

import stat
import subprocess
from dataclasses import replace
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from userdir_publish.config import ConfigError, load_settings
from userdir_publish.publish import (
    PublishError,
    publish,
    rsync_command,
    use_ssh,
    validate_build,
)

if TYPE_CHECKING:
    from pathlib import Path


def describe_rsync_command():
    def it_builds_an_ssh_command(project: Path, user_config: Path):
        settings = load_settings(
            cli={
                "host": "web.example.edu",
                "user": "jdoe",
                "web_root": "/home/{user}/WWW",
                "subdirectory": "tips",
                "keep": ["/*/"],
            },
            project_root=project,
            user_config=user_config,
        )
        command = rsync_command(settings, ssh=True)
        assert command[-1] == "jdoe@web.example.edu:/home/jdoe/WWW/tips/"
        assert "--filter=P /*/" in command
        assert "--chmod=Dg-rwx,Do=x,Fg-rwx,Fo=r" in command
        assert "--rsync-path=mkdir -p -- /home/jdoe/WWW/tips && rsync" in command
        assert not any(
            arg.startswith("--rsync-path")
            for arg in rsync_command(settings, ssh=True, dry_run=True)
        )

    def it_reports_progress_on_request(project: Path, user_config: Path):
        settings = load_settings(
            cli={"user": "jdoe", "web_root": "/srv/www"},
            project_root=project,
            user_config=user_config,
        )
        progress = "--info=progress2"
        assert progress not in rsync_command(settings, ssh=False, dry_run=True)
        assert progress in rsync_command(settings, ssh=True, progress=True)
        assert progress not in rsync_command(settings, ssh=True)

    def it_targets_home_relative_paths_remotely(project: Path, user_config: Path):
        settings = load_settings(
            cli={
                "host": "web.example.edu",
                "user": "jdoe",
                "subdirectory": "tips",
            },
            project_root=project,
            user_config=user_config,
        )
        assert (
            rsync_command(settings, ssh=True)[-1]
            == "jdoe@web.example.edu:public_html/tips/"
        )


def describe_publish():
    @pytest.mark.usefixtures("gnu_rsync")
    def it_publishes_locally(project: Path, user_config: Path, tmp_path: Path):
        www = tmp_path / "www"
        (www / "other").mkdir(parents=True)
        (www / "tips").mkdir()
        (www / "tips" / "stale.html").write_text("")
        settings = load_settings(
            cli={
                "web_root": str(www),
                "subdirectory": "tips",
                "user": "jdoe",
            },
            project_root=project,
            user_config=user_config,
        )
        publish(settings)
        index = www / "tips" / "index.html"
        assert index.read_text() == "<p>Hello</p>"
        assert not (www / "tips" / "stale.html").exists()
        assert (www / "other").is_dir()
        mode = index.stat().st_mode
        assert mode & stat.S_IROTH
        assert not mode & (stat.S_IRGRP | stat.S_IWGRP)

    @pytest.mark.usefixtures("gnu_rsync")
    def it_keeps_protected_directories(
        project: Path, user_config: Path, tmp_path: Path
    ):
        www = tmp_path / "www"
        (www / "talks").mkdir(parents=True)
        (www / "old.html").write_text("")
        settings = load_settings(
            cli={
                "web_root": str(www),
                "keep": ["/*/"],
                "user": "jdoe",
            },
            project_root=project,
            user_config=user_config,
        )
        publish(settings)
        assert (www / "index.html").is_file()
        assert (www / "talks").is_dir()
        assert not (www / "old.html").exists()

    @pytest.mark.usefixtures("gnu_rsync")
    def it_creates_missing_parents(project: Path, user_config: Path, tmp_path: Path):
        www = tmp_path / "missing" / "www"
        settings = load_settings(
            cli={
                "web_root": str(www),
                "subdirectory": "a/b",
                "user": "jdoe",
            },
            project_root=project,
            user_config=user_config,
        )
        publish(settings)
        assert (www / "a" / "b" / "index.html").is_file()

    def it_refuses_symlinked_targets(project: Path, user_config: Path, tmp_path: Path):
        www = tmp_path / "www"
        www.mkdir()
        (www / "tips").symlink_to(tmp_path)
        settings = load_settings(
            cli={
                "web_root": str(www),
                "subdirectory": "tips",
                "user": "jdoe",
            },
            project_root=project,
            user_config=user_config,
        )
        with pytest.raises(PublishError, match="symlink"):
            publish(settings)

    def it_requires_built_access_rules(
        project: Path, user_config: Path, tmp_path: Path
    ):
        (project / "docs" / ".htaccess").write_text("Require valid-user\n")
        settings = load_settings(
            cli={
                "web_root": str(tmp_path / "www"),
                "user": "jdoe",
            },
            project_root=project,
            user_config=user_config,
        )
        settings = replace(settings, htaccess_source="docs")
        with pytest.raises(PublishError, match="access rules"):
            publish(settings)

    def it_requires_a_source(project: Path, user_config: Path):
        (project / "pyproject.toml").write_text("")
        settings = load_settings(
            cli={"web_root": "/srv/www"},
            project_root=project,
            user_config=user_config,
        )
        with pytest.raises(ConfigError, match="No source directory"):
            publish(settings, dry_run=True)


@pytest.fixture
def fake_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Replace ``PATH`` with fake ``ssh`` and ``rsync`` that log their arguments."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("ssh", "rsync"):
        script = bin_dir / name
        script.write_text(
            dedent(f"""\
                #!/bin/sh
                printf '%s\\n' "$@" > {tmp_path}/{name}.log
                exit ${{FAKE_{name.upper()}_EXIT:-0}}
            """)
        )
        script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    return tmp_path


def _ssh_settings(project: Path, user_config: Path):
    return load_settings(
        cli={
            "host": "web.example.edu",
            "user": "jdoe",
            "subdirectory": "my tips",
            "transport": "ssh",
        },
        project_root=project,
        user_config=user_config,
    )


def describe_publish_with_openrsync():
    def it_refuses_to_set_permissions(project: Path, user_config: Path, fake_bin: Path):
        (fake_bin / "bin" / "rsync").write_text(
            "#!/bin/sh\necho 'openrsync: protocol version 29'\n"
        )
        settings = load_settings(
            cli={"web_root": str(fake_bin / "www"), "user": "jdoe"},
            project_root=project,
            user_config=user_config,
        )
        with pytest.raises(PublishError, match="openrsync"):
            publish(settings)
        publish(replace(settings, permissions="none"))


def describe_publish_over_ssh():
    def it_runs_rsync_after_checking_the_target(
        project: Path, user_config: Path, fake_bin: Path
    ):
        command = publish(_ssh_settings(project, user_config))
        ssh_args = (fake_bin / "ssh.log").read_text().splitlines()
        assert ssh_args[0] == "jdoe@web.example.edu"
        assert "[ -L '~/public_html/my tips' ]" not in ssh_args[1]
        assert "[ -L 'public_html/my tips' ]" in ssh_args[1]
        rsync_args = (fake_bin / "rsync.log").read_text().splitlines()
        assert rsync_args == command[1:]
        assert "--rsync-path=mkdir -p -- 'public_html/my tips' && rsync" in rsync_args

    def it_refuses_remote_symlinks(
        project: Path,
        user_config: Path,
        fake_bin: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("FAKE_SSH_EXIT", "3")
        with pytest.raises(PublishError, match="symlink"):
            publish(_ssh_settings(project, user_config))
        assert not (fake_bin / "rsync.log").exists()

    def it_fails_when_ssh_fails(
        project: Path,
        user_config: Path,
        fake_bin: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("FAKE_SSH_EXIT", "255")
        with pytest.raises(PublishError, match="Could not inspect"):
            publish(_ssh_settings(project, user_config))
        assert not (fake_bin / "rsync.log").exists()

    def it_requires_the_executables(
        project: Path,
        user_config: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        with pytest.raises(PublishError, match="ssh executable not found"):
            publish(_ssh_settings(project, user_config))


def describe_use_ssh():
    @pytest.mark.parametrize(
        ("transport", "host", "target_exists", "expected"),
        [
            ("auto", None, False, False),
            ("auto", "web.example.edu", True, False),
            ("auto", "web.example.edu", False, True),
            ("local", "web.example.edu", False, False),
            ("ssh", "web.example.edu", True, True),
        ],
    )
    def it_picks_the_transport(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
        project: Path,
        user_config: Path,
        tmp_path: Path,
        transport: str,
        host: str | None,
        target_exists: bool,
        expected: bool,
    ):
        www = tmp_path / "www"
        if target_exists:
            www.mkdir()
        cli = {"web_root": str(www), "user": "jdoe", "transport": transport}
        if host is not None:
            cli["host"] = host
        settings = load_settings(cli=cli, project_root=project, user_config=user_config)
        assert use_ssh(settings) is expected


def describe_validate_build():
    def _settings(project: Path, user_config: Path):
        settings = load_settings(
            cli={"web_root": "/srv/www", "user": "jdoe"},
            project_root=project,
            user_config=user_config,
        )
        return replace(settings, htaccess_source="docs")

    def it_requires_an_index(project: Path, user_config: Path):
        (project / "docs" / "_build" / "html" / "index.html").unlink()
        with pytest.raises(PublishError, match=r"no index\.html"):
            validate_build(_settings(project, user_config))

    def it_rejects_changed_access_rules(project: Path, user_config: Path):
        (project / "docs" / ".htaccess").write_text("Require valid-user\n")
        built = project / "docs" / "_build" / "html" / ".htaccess"
        built.write_text("Require all granted\n")
        with pytest.raises(PublishError, match="access rules"):
            validate_build(_settings(project, user_config))

    def it_accepts_copied_access_rules(project: Path, user_config: Path):
        rules = project / "docs" / "sub" / ".htaccess"
        rules.parent.mkdir()
        rules.write_text("Require valid-user\n")
        built = project / "docs" / "_build" / "html" / "sub" / ".htaccess"
        built.parent.mkdir()
        built.write_bytes(rules.read_bytes())
        validate_build(_settings(project, user_config))

    def it_skips_hidden_directories(project: Path, user_config: Path):
        rules = project / "docs" / ".venv" / ".htaccess"
        rules.parent.mkdir()
        rules.write_text("Require valid-user\n")
        validate_build(_settings(project, user_config))

    def it_skips_files_ignored_by_git(project: Path, user_config: Path):
        subprocess.run(["git", "init", "-q", str(project)], check=True)  # ruff: ignore[subprocess-without-shell-equals-true, start-process-with-partial-path]
        (project / ".gitignore").write_text("/docs/generated/\n")
        ignored = project / "docs" / "generated" / ".htaccess"
        ignored.parent.mkdir()
        ignored.write_text("Require valid-user\n")
        validate_build(_settings(project, user_config))
        rules = project / "docs" / "sub" / ".htaccess"
        rules.parent.mkdir()
        rules.write_text("Require valid-user\n")
        with pytest.raises(PublishError, match="access rules"):
            validate_build(_settings(project, user_config))
