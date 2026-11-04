<!-- cspell:ignore pipx -->

# userdir-publish

:::{title} Welcome
:::

`userdir-publish` copies a built static website to a personal web directory, such as `https://web.example.edu/~jdoe/`, that Apache serves with [`mod_userdir`](https://httpd.apache.org/docs/current/mod/mod_userdir.html). It runs [`rsync`](https://rsync.samba.org) over [SSH](https://www.openssh.org), or to a local path when the web directory is mounted or you are on the server (see {cfg}`.transport`). It removes stale files, sets permissions the web server can read, and refuses a build that lacks `index.html` or the current `.htaccess` rules from {cfg}`.htaccess-source`.

## Installation

`rsync` must be available locally and on the server. Install the tool from [PyPI](https://pypi.org/project/userdir-publish):

::::{tab-set}
:sync-group: installer

:::{tab-item} uv
:sync: uv

```bash
uv tool install userdir-publish
```

:::

:::{tab-item} pipx
:sync: pipx

```bash
pipx install userdir-publish
```

:::

:::{tab-item} pip
:sync: pip

```bash
pip install userdir-publish
```

:::

::::

or pin it in a project, so that everyone publishes with the same version:

::::{tab-set}
:sync-group: installer

:::{tab-item} uv
:sync: uv

```bash
uv add --dev userdir-publish
```

:::

:::{tab-item} Pixi
:sync: pixi

```bash
pixi add --pypi userdir-publish
```

:::

:::{tab-item} pip
:sync: pip

```{code-block} text
:caption: requirements-dev.txt
userdir-publish==<version>
```

:::

::::

## Configuration

Each layer overrides the previous one:

1. built-in defaults,
2. the user config, `$XDG_CONFIG_HOME/userdir-publish/config.toml` or `$XDG_CONFIG_HOME/userdir-publish.toml`,
3. `[tool.userdir-publish]` in the project's [`pyproject.toml`](https://packaging.python.org/en/latest/specifications/pyproject-toml),
4. [command-line flags](#command-line-interface).

`userdir-publish --show-config` prints the merged result. The user config accepts the [project options](#options) at its top level as personal defaults.

(options)=

### Options

Generated from the settings schema; hover over an option for its description.

```{config-schema} /../userdir-publish.schema.json
:caption: pyproject.toml
:table: tool.userdir-publish
```

{cfg}`.source` is required, here or as the first command-line argument. {cfg}`.keep` takes [`rsync` filter patterns](https://download.samba.org/pub/rsync/rsync.1#FILTER_RULES), and {cfg}`.permissions` also accepts a raw [`rsync --chmod`](https://download.samba.org/pub/rsync/rsync.1#opt--chmod) specification. `private` removes all group access; `group-writable` suits [group pages](#group-pages). {cfg}`.htaccess-source` is searched for `.htaccess` files outside hidden directories and, in a Git work tree, outside Git-ignored paths. With a {cfg}`.host`, the printed {cfg}`.url` defaults to `https://<host>/~<user>/<subdirectory>/`, where `<user>` is the [login name](#login-name), so set it only for servers that serve the pages under a different address.

### Login name

The login name is resolved in this order: `--user`, a matching entry under `[hosts]` in the user config, {cfg}`.user` in the project (for a shared account), {cfg}`.user` at the top level of the user config, and finally the local `$USER`.

```{code-block} toml
:caption: ~/.config/userdir-publish/config.toml
user = "jdoe"

[hosts."*.example.edu"]
user = "jdoe-rub"

[hosts."*"]
user = "other-login"
```

Host keys are case-sensitive shell-style patterns (`*`, `?`, `[abc]`) matched against the configured {cfg}`.host`, without resolving SSH aliases. An exact key wins over patterns; otherwise the first matching pattern in file order applies, so put `*` last.

### Homepage with subprojects

A homepage published to the {cfg}`.web-root` would delete the {cfg}`.subdirectory` targets of other projects. Protect every top-level directory with {cfg}`.keep`:

```toml
[tool.userdir-publish]
keep = ["/*/"]
```

### Group pages

`mod_userdir` serves only user directories, so a group page needs one of these server setups:

- A shared account, such as `~research-group`, that has your SSH key: set {cfg}`.user` or pass `--user research-group`.
- A setgid, group-owned directory inside one user's web directory: set {cfg}`.permissions` to `group-writable`.
- An Apache [`Alias`](https://httpd.apache.org/docs/current/mod/mod_alias.html#alias) to a shared directory: set {cfg}`.web-root` to that directory.

## Command-line interface

```{typer} userdir_publish.cli:app
:prog: userdir-publish
:width: 88
```

## Task runners

Publishing is separate from building. Chain them with a [Poe the Poet](https://poethepoet.natn.io) [sequence task](https://poethepoet.natn.io/tasks/task_types/sequence.html):

```toml
[tool.poe.tasks.website]
sequence = ["doc", { cmd = "userdir-publish" }]
```

or with [Pixi](https://pixi.prefix.dev):

```toml
[tasks.website]
cmd = "userdir-publish"
depends-on = ["doc"]
```

```{toctree}
:hidden:
API <api/userdir_publish>
Changelog <https://github.com/RUB-EP1/userdir-publish/releases>
```
