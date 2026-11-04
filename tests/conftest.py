from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

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
