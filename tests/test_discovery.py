"""File selection: patterns, pruning, explicit files, deduplication (SPEC §8.5)."""

import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

from furryp.config.defaults import DEFAULT_EXCLUDE, DEFAULT_INCLUDE
from furryp.core.discovery import (
    FileFilter,
    WalkError,
    discover_files,
    pattern_matches,
)
from tests.support import TempDirTestCase, unreadable_directory, write_files

TREE = {
    "pyproject.toml": "",
    "a.py": "",
    "notes.txt": "",
    "pkg/__init__.py": "",
    "pkg/mod.py": "",
    "pkg/.venv/x.py": "",
    "pkg/thing.egg-info/x.py": "",
    ".venv/lib/site.py": "",
    "build/b.py": "",
    "tests/test_a.py": "",
    "tests/fixtures/ko.py": "",
    "tests/fixtures/deep/ko.py": "",
    "src/gen/out.py": "",
    "src/gen/keep.txt": "",
    "src/main.py": "",
}
FILTER = FileFilter(
    DEFAULT_INCLUDE, DEFAULT_EXCLUDE + ("tests/fixtures", "**/gen/*.py")
)
EXPECTED_ALL = [
    "a.py",
    "pkg/__init__.py",
    "pkg/mod.py",
    "src/main.py",
    "tests/test_a.py",
]


class PatternTest(unittest.TestCase):
    def test_pattern_without_slash_matches_any_component(self) -> None:
        self.assertTrue(pattern_matches(".venv", PurePosixPath("a/.venv/b.py")))
        self.assertTrue(pattern_matches("*.egg-info", PurePosixPath("x.egg-info")))
        self.assertTrue(pattern_matches("b.py", PurePosixPath("a/b.py")))
        self.assertFalse(pattern_matches(".venv", PurePosixPath("a/venv2/b.py")))

    def test_pattern_without_slash_is_case_sensitive(self) -> None:
        self.assertFalse(pattern_matches("build", PurePosixPath("Build/a.py")))

    def test_pattern_with_slash_matches_the_whole_path(self) -> None:
        self.assertTrue(
            pattern_matches("tests/fixtures", PurePosixPath("tests/fixtures"))
        )
        self.assertFalse(
            pattern_matches("tests/fixtures", PurePosixPath("a/tests/fixtures"))
        )
        self.assertTrue(pattern_matches("**/gen/*.py", PurePosixPath("gen/a.py")))
        self.assertTrue(pattern_matches("**/gen/*.py", PurePosixPath("src/gen/a.py")))
        self.assertTrue(pattern_matches("**/*.py", PurePosixPath("a.py")))

    def test_excluded_parent_excludes_the_file(self) -> None:
        self.assertTrue(FILTER.is_excluded(PurePosixPath("tests/fixtures/deep/ko.py")))
        self.assertFalse(FILTER.is_excluded(PurePosixPath("tests/test_a.py")))


class DiscoveryTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, TREE)

    def discover(self, *paths: str, cwd: Path | None = None) -> list[str]:
        result = discover_files(
            [Path(p) for p in paths], cwd or self.root, self.root, FILTER
        )
        return [path.relative_to(self.root).as_posix() for path in result.files]

    def test_walk_applies_include_and_exclude(self) -> None:
        self.assertEqual(self.discover("."), EXPECTED_ALL)

    def test_files_are_absolute_and_resolved(self) -> None:
        result = discover_files([Path("pkg/../a.py")], self.root, self.root, FILTER)
        self.assertEqual(result.files, (self.root / "a.py",))

    def test_excluded_directories_are_pruned(self) -> None:
        visited: list[Path] = []
        original_walk = Path.walk

        def recording_walk(self: Path, *args: object, **kwargs: object):
            for entry in original_walk(self, *args, **kwargs):
                visited.append(entry[0])
                yield entry

        with mock.patch.object(Path, "walk", recording_walk):
            self.discover(".")
        relative = {path.relative_to(self.root).as_posix() for path in visited}
        self.assertEqual(relative, {".", "pkg", "src", "src/gen", "tests"})

    def test_explicit_files_are_excluded_too(self) -> None:
        for path in (
            ".venv/lib/site.py",
            "build/b.py",
            "tests/fixtures/deep/ko.py",
            "src/gen/out.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.discover(path), [])

    def test_explicit_excluded_directory(self) -> None:
        self.assertEqual(self.discover("tests/fixtures"), [])
        self.assertEqual(self.discover(".venv"), [])

    def test_explicit_file_must_match_include(self) -> None:
        result = discover_files([Path("notes.txt")], self.root, self.root, FILTER)
        self.assertEqual((result.files, result.missing), ((), ()))

    def test_duplicates_are_removed(self) -> None:
        self.assertEqual(
            self.discover("a.py", "./a.py", "pkg/../a.py", "."), EXPECTED_ALL
        )

    def test_missing_paths_are_kept_apart(self) -> None:
        result = discover_files(
            [Path("nope.py"), Path("a.py"), Path("no/dir"), Path("nope.py")],
            self.root,
            self.root,
            FILTER,
        )
        self.assertEqual(result.files, (self.root / "a.py",))
        self.assertEqual(
            result.missing, (self.root / "nope.py", self.root / "no" / "dir")
        )

    def test_paths_are_relative_to_cwd_and_patterns_to_root(self) -> None:
        self.assertEqual(
            self.discover(".", cwd=self.root / "tests"), ["tests/test_a.py"]
        )
        self.assertEqual(self.discover("mod.py", cwd=self.root / "pkg"), ["pkg/mod.py"])

    def test_unreadable_directories_are_reported_and_skipped(self) -> None:
        with unreadable_directory(self.root / "pkg"):
            result = discover_files([Path(".")], self.root, self.root, FILTER)
        self.assertEqual(
            [path.relative_to(self.root).as_posix() for path in result.files],
            ["a.py", "src/main.py", "tests/test_a.py"],
        )
        self.assertEqual(
            result.unreadable, (WalkError(self.root / "pkg", "Permission denied"),)
        )
        with unreadable_directory(self.root / "src"):
            result = discover_files([Path("src")], self.root, self.root, FILTER)
        self.assertEqual(result.files, ())
        self.assertEqual(
            result.unreadable, (WalkError(self.root / "src", "Permission denied"),)
        )

    def test_file_outside_the_root_uses_its_components(self) -> None:
        outside = self.root / "outside"
        project = self.root / "pkg"
        result = discover_files([outside], self.root, project, FILTER)
        self.assertEqual(result.files, ())
        write_files(outside, {"ok.py": "", ".venv/no.py": ""})
        result = discover_files([outside], self.root, project, FILTER)
        self.assertEqual(result.files, (outside / "ok.py",))


if __name__ == "__main__":
    unittest.main()
