"""Command line in process: options, combinations, exit codes (SPEC §4)."""

import unittest
from unittest import mock

import furryp
from furryp.cli.app import ExitCode, compute_exit_code
from tests.support import (
    PYPROJECT,
    TempDirTestCase,
    run_main,
    write_files,
)


class CliTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: "", "pkg/a.py": "x = 1\n"})

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        return run_main(args, self.root)

    def test_version(self) -> None:
        self.assertEqual(
            self.run_cli("--version"), (0, f"furryp {furryp.__version__}\n", "")
        )

    def test_check_clean_files(self) -> None:
        self.assertEqual(self.run_cli("check"), (0, "All checks passed!\n", ""))
        self.assertEqual(
            self.run_cli("check", "pkg", "--exit-zero"), (0, "All checks passed!\n", "")
        )

    def test_fix_with_diff_is_allowed(self) -> None:
        """``--fix --diff`` is ``--diff``: nothing to fix prints nothing (ruff)."""
        self.assertEqual(self.run_cli("check", "--fix", "--diff"), (0, "", ""))
        write_files(self.root, {"pkg/b.py": "x = 1  # foqa:FUR102\n"})
        code, out, err = self.run_cli("check", "--fix", "--diff")
        self.assertEqual((code, err), (1, ""))
        self.assertTrue(out.endswith("\nWould fix 1 error.\n"))
        self.assertEqual(
            (self.root / "pkg" / "b.py").read_bytes(), b"x = 1  # foqa:FUR102\n"
        )

    def test_rule_documentation(self) -> None:
        for args in (["FUR403"], ["demeter-chain"]):
            with self.subTest(args=args):
                code, out, err = self.run_cli("rule", *args)
                self.assertEqual((code, err), (0, ""))
                self.assertTrue(out.startswith("# demeter-chain (FUR403)\n"))

    def test_unknown_rule_documentation(self) -> None:
        self.assertEqual(
            self.run_cli("rule", "FUR40"),
            (2, "", 'error: unknown rule "FUR40" (did you mean "FUR404"?)\n'),
        )

    def test_rule_needs_a_target(self) -> None:
        code, _, err = self.run_cli("rule")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: one of the arguments"), err)

    def test_command_is_required(self) -> None:
        code, _, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertTrue(
            err.startswith("error: a command is required\nusage: furryp"), err
        )

    def test_unknown_option(self) -> None:
        code, _, err = self.run_cli("check", "--bogus")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: unrecognized arguments: --bogus\n"), err)

    def test_abbreviated_options_are_refused(self) -> None:
        # Like ruff 0.17.3 (clap): an option is written in full or not at all.
        for arguments in (
            ("check", "--stat"),
            ("check", "--sel", "FUR403"),
            ("check", "--exit"),
            ("check", "--report", "out.html"),
            ("rule", "--al"),
            ("rule", "FUR403", "--conf", "x.json"),
            ("--vers",),
        ):
            with self.subTest(arguments=arguments):
                code, out, err = self.run_cli(*arguments)
                self.assertEqual((code, out), (2, ""), err)
                self.assertTrue(err.startswith("error: "), err)

    def test_unknown_cli_selector(self) -> None:
        code, _, err = self.run_cli("check", "--select", "FUR,XYZ")
        self.assertEqual(code, 2)
        self.assertEqual(err, 'error: --select: unknown rule or prefix "XYZ"\n')

    def test_empty_or_spaced_selectors_are_refused(self) -> None:
        # Like ruff 0.17.3: otherwise `--select "$RULES"` with an empty variable
        # would select nothing and pass.
        for option in ("--select", "--extend-select", "--ignore"):
            for value, selector in (
                ("", ""),
                (",", ""),
                ("FUR403,", ""),
                (",FUR403", ""),
                ("FUR403,,FUR401", ""),
                ("FUR403, FUR401", " FUR401"),
                (" FUR403", " FUR403"),
            ):
                with self.subTest(option=option, value=value):
                    code, out, err = self.run_cli("check", option, value)
                    self.assertEqual((code, out), (2, ""), err)
                    self.assertTrue(
                        err.startswith(
                            f'error: {option}: unknown rule or prefix "{selector}"'
                        ),
                        err,
                    )

    def test_lowercase_all_rules_prefix_is_suggested(self) -> None:
        code, _, err = self.run_cli("check", "--select", "fur")
        self.assertEqual(code, 2)
        self.assertEqual(
            err, 'error: --select: unknown rule or prefix "fur" (did you mean "FUR"?)\n'
        )

    def test_invalid_configuration(self) -> None:
        write_files(self.root, {"furryp.json": '{"exclud": []}'})
        code, out, err = self.run_cli("check")
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(
            err, 'error: furryp.json: exclud: unknown key (did you mean "exclude"?)\n'
        )

    def test_internal_error_exits_with_2(self) -> None:
        with mock.patch(
            "furryp.cli.app.discover_files", side_effect=RuntimeError("boom")
        ):
            code, _, err = self.run_cli("check", "--exit-zero")
        self.assertEqual(code, 2)
        self.assertEqual(err, "error: internal error: RuntimeError: boom\n")


class ExitCodeTest(unittest.TestCase):
    def test_priorities(self) -> None:
        cases = [
            ((0, 0, False), ExitCode.SUCCESS),
            ((3, 0, False), ExitCode.VIOLATIONS),
            ((3, 0, True), ExitCode.SUCCESS),
            ((0, 1, False), ExitCode.ERROR),
            ((3, 1, False), ExitCode.ERROR),
            ((3, 1, True), ExitCode.ERROR),
        ]
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(compute_exit_code(*arguments), expected)


if __name__ == "__main__":
    unittest.main()
