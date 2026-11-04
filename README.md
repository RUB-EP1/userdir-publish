<!-- cspell:ignore pipx -->

# userdir-publish

[![Spelling checked](https://img.shields.io/badge/cspell-checked-brightgreen.svg)](https://github.com/streetsidesoftware/cspell/tree/main/packages/cspell)
[![code style: prettier](https://img.shields.io/badge/code_style-prettier-ff69b4.svg?style=flat-square)](https://github.com/prettier/prettier)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/RUB-EP1/userdir-publish/main.svg)](https://results.pre-commit.ci/latest/github/RUB-EP1/userdir-publish/main)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

`userdir-publish` copies a built static website to a personal web directory, such as `https://web.example.edu/~jdoe/`, that Apache serves with [`mod_userdir`](https://httpd.apache.org/docs/current/mod/mod_userdir.html). It uses [`rsync`](https://rsync.samba.org), either over [SSH](https://www.openssh.org) or to a local path when the web directory is mounted or you are logged in on the server. It removes stale files, sets permissions the web server can read, and refuses to publish a build that lacks `index.html` or the current `.htaccess` rules.

## Installation

The tool requires `rsync` on your machine and on the server. Install it from [PyPI](https://pypi.org/project/userdir-publish):

```bash
uv tool install userdir-publish
```

or with `pipx install userdir-publish`. Then run `userdir-publish --help`.

## Documentation

See [rub-ep1.github.io/userdir-publish](https://rub-ep1.github.io/userdir-publish) for other installation methods, configuration, group pages, and task runner integration.
