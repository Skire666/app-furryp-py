"""Selection of the files to check (SPEC §8.5).

Patterns are relative to the project root and compared in POSIX form: a
pattern without ``/`` applies to each component of the path, a pattern with
``/`` applies to the whole relative path (``**`` allowed).
"""

import fnmatch
import functools
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PATTERN_SEPARATOR = "/"


def relative_to_root(path: Path, root: Path) -> PurePosixPath:
    """Return ``path`` relative to ``root`` in POSIX form, absolute if outside."""
    if path.is_relative_to(root):
        return PurePosixPath(path.relative_to(root).as_posix())
    return PurePosixPath(path.as_posix())


def pattern_matches(pattern: str, relative: PurePosixPath) -> bool:
    """Match one configuration pattern against a relative path."""
    if PATTERN_SEPARATOR in pattern:
        return relative.full_match(pattern)
    return any(fnmatch.fnmatchcase(part, pattern) for part in relative.parts)


def path_matches(patterns: Iterable[str], relative: PurePosixPath) -> bool:
    """Whether a pattern matches ``relative`` or one of its parent directories."""
    prefixes = (relative, *relative.parents[:-1])
    return any(
        pattern_matches(pattern, prefix) for pattern in patterns for prefix in prefixes
    )


@dataclass(frozen=True, slots=True)
class FileFilter:
    """``include`` and ``exclude`` patterns (``exclude`` ∪ ``extend-exclude``)."""

    include: tuple[str, ...]
    exclude: tuple[str, ...]

    def is_excluded(self, relative: PurePosixPath) -> bool:
        """Whether ``relative`` or one of its parent directories is excluded."""
        return path_matches(self.exclude, relative)

    def accepts(self, relative: PurePosixPath) -> bool:
        """Whether the file is included and not excluded."""
        included = any(pattern_matches(pattern, relative) for pattern in self.include)
        return included and not self.is_excluded(relative)


@dataclass(frozen=True, slots=True)
class WalkError:
    """A directory that cannot be listed (permissions), and the reason."""

    path: Path
    reason: str


def record_walk_error(errors: list[WalkError], top: Path, error: OSError) -> None:
    """Append the ``OSError`` raised while walking ``top`` to ``errors``."""
    path = Path(error.filename) if error.filename else top
    errors.append(WalkError(path, error.strerror or str(error)))


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Files to check, arguments that do not exist (FUR000), and directories
    that cannot be listed (a warning, as ruff does)."""

    files: tuple[Path, ...]
    missing: tuple[Path, ...]
    unreadable: tuple[WalkError, ...] = ()


def _walk(
    top: Path, root: Path, file_filter: FileFilter, errors: list[WalkError]
) -> Iterator[Path]:
    """Yield the accepted files below ``top``, without entering excluded dirs.

    A directory that cannot be listed is appended to ``errors`` and skipped.
    """
    if file_filter.is_excluded(relative_to_root(top, root)):
        return
    on_error = functools.partial(record_walk_error, errors, top)
    for directory, dirnames, filenames in top.walk(on_error=on_error):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not file_filter.is_excluded(relative_to_root(directory / name, root))
        )
        for name in sorted(filenames):
            path = directory / name
            if file_filter.accepts(relative_to_root(path, root)):
                yield path.resolve()


def discover_files(
    paths: Iterable[Path], cwd: Path, root: Path, file_filter: FileFilter
) -> DiscoveryResult:
    """Return the unique files to check under ``paths`` (relative to ``cwd``)."""
    found: dict[Path, None] = {}
    missing: dict[Path, None] = {}
    errors: list[WalkError] = []
    for argument in paths:
        path = (cwd / argument).resolve()
        if path.is_dir():
            found.update(dict.fromkeys(_walk(path, root, file_filter, errors)))
        elif path.is_file():
            if file_filter.accepts(relative_to_root(path, root)):
                found[path] = None
        elif not path.exists():
            missing[path] = None
    return DiscoveryResult(tuple(sorted(found)), tuple(missing), tuple(errors))
