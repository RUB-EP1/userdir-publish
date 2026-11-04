from __future__ import annotations

import shutil
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from userdir_publish.publish import is_openrsync

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    build = root / "docs" / "_build" / "html"
    build.mkdir(parents=True)
    (build / "index.html").write_text("<p>Hello</p>")
    (root / "pyproject.toml").write_text(
        dedent("""
            [tool.userdir-publish]
            source = "docs/_build/html"
        """)
    )
    return root


@pytest.fixture
def user_config(tmp_path: Path) -> Path:
    return tmp_path / "config.toml"


@pytest.fixture
def gnu_rsync() -> None:
    """Skip tests that run rsync with ``--chmod`` when only openrsync is available."""
    if shutil.which("rsync") is None or is_openrsync():
        pytest.skip("requires GNU rsync")
