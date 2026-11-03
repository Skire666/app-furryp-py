"""Default values of the global and ``report`` options (SPEC §8.4)."""

CONFIG_FILE_NAME = "furryp.json"
PYPROJECT_FILE_NAME = "pyproject.toml"
CONFIG_ENCODING = "utf-8-sig"

DEFAULT_INCLUDE = ("**/*.py",)
DEFAULT_EXCLUDE = (
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "*.egg-info",
)
DEFAULT_SELECT = ("FUR",)

DEFAULT_TOP_N = 10
DEFAULT_REPORT_TITLE = "furryp — audit"
DEFAULT_RATING_THRESHOLDS = (0.20, 0.40, 0.60, 0.80)
RATING_THRESHOLD_COUNT = 4
RATING_MIN = 0.0
RATING_MAX = 1.0
