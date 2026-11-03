"""The version of pyproject.toml is the one exposed by the package (SPEC §3)."""

import tomllib
import unittest

import furryp
from tests.support import REPO_ROOT


class VersionTest(unittest.TestCase):
    def test_pyproject_version_matches_package(self) -> None:
        with (REPO_ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]
        self.assertEqual(project["version"], furryp.__version__)

    def test_no_dependency_declared(self) -> None:
        with (REPO_ROOT / "pyproject.toml").open("rb") as stream:
            data = tomllib.load(stream)
        self.assertNotIn("dependencies", data["project"])
        self.assertNotIn("dependency-groups", data)
        self.assertEqual(data["project"]["scripts"]["furryp"], "furryp.cli.app:main")


if __name__ == "__main__":
    unittest.main()
