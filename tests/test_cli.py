from __future__ import annotations

import subprocess
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from userdir_publish import cli

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def run(project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(project)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("COLUMNS", "500")
    runner = CliRunner()

    def invoke(*args: str):
        return runner.invoke(cli.app, list(args))

    return invoke


def describe_main():
    def it_shows_the_merged_config(run, tmp_path: Path):
        www = tmp_path / "www"
        result = run("--web-root", str(www), "--user", "jdoe", "--show-config")
        assert result.exit_code == 0, result.output
        assert "source = 'docs/_build/html'" in result.output
        assert f"target = '{www}'" in result.output
        assert not www.exists()

    def it_publishes_locally(run, project: Path, tmp_path: Path):
        www = tmp_path / "www"
        (project / "pyproject.toml").write_text(
            dedent("""
                [tool.userdir-publish]
                source = "docs/_build/html"
                url = "https://example.edu/~{user}/{subdirectory}/"
            """)
        )
        result = run("--web-root", str(www), "--user", "jdoe", "--subdirectory", "tips")
        assert result.exit_code == 0, result.output
        assert f"Published to {www}/tips" in result.output
        assert "https://example.edu/~jdoe/tips/" in result.output
        assert (www / "tips" / "index.html").is_file()

    def it_does_a_dry_run(run, tmp_path: Path):
        www = tmp_path / "www"
        result = run("--web-root", str(www), "--user", "jdoe", "--dry-run")
        assert result.exit_code == 0, result.output
        assert "Dry run:" in result.output
        assert "--dry-run" in result.output
        assert not (www / "index.html").exists()

    def it_reports_config_errors(run):
        result = run("--transport", "carrier-pigeon")
        assert result.exit_code == 1
        assert "transport must be one of" in result.output

    def it_reports_publish_errors(run, project: Path, tmp_path: Path):
        (project / "docs" / "_build" / "html" / "index.html").unlink()
        result = run("--web-root", str(tmp_path / "www"), "--user", "jdoe")
        assert result.exit_code == 1
        assert "has no index.html" in result.output

    def it_forwards_rsync_failures(
        run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def fail(*_args, **_kwargs):
            raise subprocess.CalledProcessError(23, ["rsync", "--delete", "a b"])

        monkeypatch.setattr(cli, "publish", fail)
        result = run("--web-root", str(tmp_path / "www"), "--user", "jdoe")
        assert result.exit_code == 23
        assert "rsync failed: rsync --delete 'a b'" in result.output
        assert "Rerun to resume" in result.output

    def it_reports_interruptions(run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        def interrupt(*_args, **_kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(cli, "publish", interrupt)
        result = run("--web-root", str(tmp_path / "www"), "--user", "jdoe")
        assert result.exit_code == 130
        assert "Interrupted. Rerun to resume" in result.output

    def it_accepts_repeated_keep_flags(run, tmp_path: Path):
        result = run(
            "--web-root",
            str(tmp_path / "www"),
            "--user",
            "jdoe",
            "--keep",
            "/talks/",
            "--keep",
            "/*.pdf",
            "--show-config",
        )
        assert result.exit_code == 0, result.output
        assert "keep = ('/talks/', '/*.pdf')" in result.output


def describe_output():
    def it_does_not_break_long_paths(
        run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(cli.console, "width", 40)
        www = tmp_path / "a-rather-long-directory-name" / "www"
        result = run("--web-root", str(www), "--user", "jdoe")
        assert result.exit_code == 0, result.output
        assert f"Published to {www}" in result.output
