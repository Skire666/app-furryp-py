"""Display of paths in messages (SPEC §5.1, rule 10)."""

from pathlib import Path


def display_path(path: Path, cwd: Path) -> str:
    """Return ``path`` relative to ``cwd`` when it lies below it, else absolute.

    Both paths are expected absolute and resolved. Separators are the native
    ones (``os.sep``), as ``str(Path)`` produces them.
    """
    if path.is_relative_to(cwd):
        return str(path.relative_to(cwd))
    return str(path)
