from sphinx_api_relink.helpers import (
    get_branch_name,
    get_git_revision,
    get_package_version,
)

BRANCH = get_branch_name()
REVISION = get_git_revision()
ORGANIZATION = "RUB-EP1"
REPO_NAME = "userdir-publish"
PACKAGE_NAME = REPO_NAME.replace("-", "_")

add_module_names = False
api_github_repo = f"{ORGANIZATION}/{REPO_NAME}"
api_linkcode_rev = REVISION
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "undoc-members": True,
}
autodoc_member_order = "bysource"
autodoc_typehints_format = "short"
copyright = f"2026, {ORGANIZATION}"
default_role = "py:obj"
extensions = [
    "myst_parser",
    "sphinx_api_relink",
    "sphinx_config_schema",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinxcontrib.typer",
]
generate_apidoc_excludes = ["cli.py"]
generate_apidoc_package_path = f"../src/{PACKAGE_NAME}"
html_context = {
    "doc_path": "docs",
    "github_repo": REPO_NAME,
    "github_user": ORGANIZATION,
    "github_version": BRANCH,
    "github_view_rev": REVISION,
}
html_favicon = "_static/favicon.svg"
html_last_updated_fmt = "%-d %B %Y"
html_logo = "_static/favicon.svg"
html_sidebars = {"**": []}
html_show_copyright = False
html_show_sourcelink = False
html_show_sphinx = False
html_theme = "pydata_sphinx_theme"
html_theme_options = {
    "icon_links": [
        {
            "name": "GitHub",
            "url": f"https://github.com/{ORGANIZATION}/{REPO_NAME}",
            "icon": "fa-brands fa-github",
        },
    ],
    "footer_end": [],
    "logo": {"text": REPO_NAME},
    "navbar_align": "right",
    "navigation_with_keys": False,
    "secondary_sidebar_items": [
        "page-toc",
        "edit-this-page",
        "view-on-github",
    ],
    "show_prev_next": False,
    "show_toc_level": 2,
    "use_edit_page_button": True,
}
html_title = REPO_NAME
intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
}
myst_heading_anchors = 3
myst_colon_fence_exact_match = True
myst_enable_extensions = [
    "alert",
    "colon_fence",
]
nitpicky = True
project = REPO_NAME
release = get_package_version(PACKAGE_NAME)
templates_path = ["_templates"]
toc_object_entries = False
version = get_package_version(PACKAGE_NAME)
