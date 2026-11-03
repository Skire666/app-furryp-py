"""``--report-html`` from end to end: output, exit codes, contents (SPEC §5.6, §12)."""

import re
from pathlib import Path
from unittest import mock

from furryp.core.diagnostic import Diagnostic
from furryp.core.registry import Rule, Scope
from tests.report_support import (
    FIXED_TIME,
    SECTION_TITLES,
    cards_of,
    check_html,
    rows_of,
    section_of,
    tables_of,
)
from tests.support import (
    CONFIG,
    PYPROJECT,
    REPO_ROOT,
    TempDirTestCase,
    run_furryp,
    run_furryp_raw,
    run_main,
    write_files,
)

CLEAN = '"""Doc."""\n\nX = 1\n'
TOO_LONG = "def f():\n" + "".join(f"    a{i} = {i}\n" for i in range(30))
FLAGGED_FILE = "x = a.b.c.d.e\n"
BROKEN = "def broken(:\n"
REPORT = "audit.html"
VARIABLE_PARTS = re.compile(r'<time datetime="[^"]*">[^<]*</time>|\d+\.\d+ s<')


class ReportE2eTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: ""})

    def project(self, files: dict[str, str | bytes], config: str = "{}") -> None:
        write_files(self.root, {CONFIG: config, **files})

    def run_report(self, *args: str, target: str = REPORT):
        return run_furryp(["check", *args, "--report-html", target], self.root)

    def report_text(self, target: str = REPORT) -> str:
        return (self.root / target).read_bytes().decode("utf-8")

    def test_nothing_on_stdout_and_code_0_without_violation(self) -> None:
        self.project({"a.py": CLEAN})
        result = self.run_report()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        check_html(self, self.report_text())

    def test_violations_give_code_1_and_nothing_on_stdout(self) -> None:
        self.project({"a.py": FLAGGED_FILE})
        result = self.run_report()
        self.assertEqual((result.returncode, result.stdout), (1, ""))

    def test_exit_zero(self) -> None:
        self.project({"a.py": FLAGGED_FILE})
        self.assertEqual(self.run_report("--exit-zero").returncode, 0)

    def test_an_error_on_a_file_counts_for_the_exit_code(self) -> None:
        """Left out of the aggregates, but still code 1 as ``check``."""
        self.project({"a.py": BROKEN})
        self.assertEqual(self.run_report().returncode, 1)
        self.assertEqual(run_furryp(["check"], self.root).returncode, 1)

    def test_same_exit_code_as_check_with_the_same_selection(self) -> None:
        self.project({"a.py": FLAGGED_FILE})
        for args in (["--select", "FUR4"], ["--select", "FUR101"], []):
            with self.subTest(args=args):
                check = run_furryp(["check", *args], self.root)
                self.assertEqual(self.run_report(*args).returncode, check.returncode)

    def test_report_that_cannot_be_written_gives_code_2(self) -> None:
        self.project({"a.py": CLEAN, "folder/keep.txt": "x"})
        result = self.run_report(target="folder")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("error: Failed to write report folder: ", result.stderr)

    def test_exit_zero_does_not_hide_a_report_that_cannot_be_written(self) -> None:
        self.project({"a.py": FLAGGED_FILE, "folder/keep.txt": "x"})
        result = self.run_report("--exit-zero", target="folder")
        self.assertEqual(result.returncode, 2)

    def test_missing_parent_directories_are_created(self) -> None:
        """As ruff 0.17.3 does with ``--output-file``."""
        self.project({"a.py": CLEAN})
        result = self.run_report(target=str(Path("out") / "deep" / REPORT))
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.root / "out" / "deep" / REPORT).is_file())

    def test_configuration_error_writes_nothing(self) -> None:
        self.project({"a.py": CLEAN}, '{"report": {"top-n": -1}}')
        result = self.run_report()
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertFalse((self.root / REPORT).exists())

    def test_no_python_file_warns_and_writes_a_report(self) -> None:
        self.project({})
        result = self.run_report()
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertIn("No Python files found", result.stderr)
        text = self.report_text()
        check_html(self, text)
        self.assertIn("* Not rated: no file was analyzed.", text)

    def test_bytes_are_utf8_with_line_feeds_only(self) -> None:
        self.project(
            {"é.py": FLAGGED_FILE}, '{"report": {"title": "Audit — équipe ☃"}}'
        )
        result = run_furryp_raw(["check", "--report-html", REPORT], self.root)
        self.assertEqual(result.stdout, b"")
        data = (self.root / REPORT).read_bytes()
        self.assertNotIn(b"\r", data)
        text = data.decode("utf-8")
        self.assertIn("Audit — équipe ☃", text)
        self.assertIn("é.py", text)

    def test_measures_do_not_depend_on_the_selection(self) -> None:
        self.project({"a.py": TOO_LONG})
        self.run_report("--select", "FUR403")
        selected = self.report_text()
        self.assertIn("* Not rated: no rule of this category is selected.", selected)
        self.assertNotIn("function-too-long", selected.split("Appendix")[0])
        self.run_report()
        everything = self.report_text()
        for label, value in (
            ("Lines per file", "31.00"),
            ("Lines of code per function", "30.00"),
        ):
            for text in (selected, everything):
                row = text[text.index(label) :].split("</tr>")[0]
                self.assertIn(f'<td class="number">{value}</td>', row)

    def test_violations_respect_the_selection_and_foqa(self) -> None:
        self.project(
            {"a.py": "# furryp: foqa:FUR403\n" + FLAGGED_FILE, "b.py": FLAGGED_FILE},
            '{"ignore": ["FUR401"]}',
        )
        self.run_report()
        text = self.report_text()
        row = text[text.index("<td>FUR403</td>") :].split("</tr>")[0]
        numbers = re.findall(r'class="number">([^<]*)<', row)
        self.assertEqual(numbers, ["1", "1", "1", "0"])
        self.assertNotIn("<td>FUR401</td>", text)

    def test_only_the_violations_with_a_fix_are_available_fixes(self) -> None:
        """FUR001 has a fix, FUR101 has none."""
        unused = "x = 1  # foqa:FUR102\n"
        self.project({"a.py": unused + TOO_LONG}, '{"select": ["FUR101", "FUR001"]}')
        self.run_report()
        text = self.report_text()
        self.assertIn("<dt>Violations</dt><dd>2</dd>", text)
        self.assertIn("<dt>Available fixes</dt><dd>1</dd>", text)

    def test_per_file_ignores_are_respected(self) -> None:
        self.project(
            {"a.py": FLAGGED_FILE, "gen/b.py": FLAGGED_FILE},
            '{"select": ["FUR403"], "per-file-ignores": {"gen": ["FUR403"]}}',
        )
        self.run_report()
        text = self.report_text()
        self.assertIn("50.0% (1/2)", text)

    def test_file_in_error_is_listed_with_the_banner(self) -> None:
        self.project({"ok.py": CLEAN, "broken.py": BROKEN})
        self.run_report()
        text = self.report_text()
        self.assertIn('role="alert"', text)
        section = text[text.index('<section id="analysis-errors">') :]
        self.assertIn('<td class="path">broken.py</td>', section)
        self.assertIn("FUR000", section)
        lines_card = re.search(r"<dt>Files analyzed</dt><dd>(\d+)<", text)
        self.assertEqual(lines_card.group(1), "1")

    def test_every_file_in_error_is_listed_with_its_message(self) -> None:
        """Not cut to the top N: the list of the errors is complete."""
        files = {f"broken{index:02}.py": BROKEN for index in range(12)}
        self.project({"ok.py": CLEAN, **files})
        self.run_report()
        text = self.report_text()
        section = text[text.index('<section id="analysis-errors">') :]
        rows = rows_of(tables_of(section.split("</section>")[0])[0])
        self.assertEqual([row["File"] for row in rows], sorted(files))
        for row in rows:
            self.assertEqual(row["Code"], "FUR000")
            self.assertRegex(row["Position"], r"^\d+:\d+$")
            self.assertIn("SyntaxError", row["Message"])

    def test_generated_date_has_its_offset(self) -> None:
        """Local date and time, in ISO form (§12.3): the offset says which zone."""
        self.project({"a.py": CLEAN})
        self.run_report()
        self.assertRegex(
            cards_of(self.report_text())["Generated"],
            r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$",
        )

    def test_reasons_of_missing_ratings_do_not_depend_on_the_hash_seed(self) -> None:
        """Two reasons: no file, and no rule of the category."""
        self.project({})
        texts = set()
        for seed in ("1", "2", "3", "4"):
            run_furryp(
                ["check", "--select", "FUR4", "--report-html", REPORT],
                self.root,
                {"PYTHONHASHSEED": seed},
            )
            texts.add(VARIABLE_PARTS.sub("", self.report_text()))
        self.assertEqual(len(texts), 1)

    def test_missing_path_is_listed_and_its_name_escaped(self) -> None:
        """``<`` cannot be in a file name under Windows, but a missing path can."""
        self.project({"ok.py": CLEAN})
        result = run_furryp(
            ["check", "ok.py", "miss<ing>.py", "--report-html", REPORT], self.root
        )
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        text = self.report_text()
        check_html(self, text)
        self.assertIn("miss&lt;ing&gt;.py", text)
        self.assertNotIn("miss<ing>", text)

    def test_top_n_of_the_configuration(self) -> None:
        files = {f"m{index}.py": FLAGGED_FILE for index in range(6)}
        self.project(files, '{"report": {"top-n": 3}}')
        self.run_report()
        text = self.report_text()
        worst = section_of(text, "design")
        worst = worst[worst.index("Worst files") :]
        self.assertEqual(worst.count('<td class="path">'), 3)

    def test_ten_files_at_most_by_default(self) -> None:
        files = {f"m{index:02}.py": FLAGGED_FILE for index in range(14)}
        self.project(files)
        self.run_report()
        text = self.report_text()
        worst = section_of(text, "design")
        worst = worst[worst.index("Worst files") :]
        self.assertEqual(worst.count('<td class="path">'), 10)

    def test_generation_on_the_fixtures_of_every_rule(self) -> None:
        """Syntax errors, foqa and encodings included: no internal error."""
        write_files(self.root, {CONFIG: "{}"})
        fixtures = REPO_ROOT / "tests" / "fixtures"
        result = run_furryp(
            [
                "check",
                str(fixtures),
                "--config",
                str(self.root / CONFIG),
                "--report-html",
                str(self.root / REPORT),
            ],
            REPO_ROOT,
        )
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertEqual(result.stderr, "")
        text = self.report_text().replace(str(self.root), "")
        checker = check_html(self, text)
        self.assertEqual(checker.headings, list(SECTION_TITLES))
        for forbidden in ("<script", "http"):
            self.assertNotIn(forbidden, text)
        self.assertIn("FUR000", text)

    def test_two_runs_differ_only_by_time(self) -> None:
        """Whatever the hash seed: no set decides the order of the report."""
        self.project(
            {
                "a.py": TOO_LONG,
                "b.py": FLAGGED_FILE,
                "c.py": BROKEN,
                "d/e.py": FLAGGED_FILE,
            }
        )
        texts = []
        for seed in ("1", "2"):
            run_furryp(
                ["check", "--report-html", REPORT],
                self.root,
                {"PYTHONHASHSEED": seed},
            )
            texts.append(VARIABLE_PARTS.sub("", self.report_text()))
        self.assertEqual(texts[0], texts[1])


class InProcessTest(TempDirTestCase):
    """The clock and a failing rule are injected in this process."""

    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: "", CONFIG: "{}", "a.py": FLAGGED_FILE})

    def test_fixed_clock_gives_the_same_bytes(self) -> None:
        target = self.root / REPORT
        outputs = []
        with mock.patch("furryp.cli.app.local_now", return_value=FIXED_TIME):
            for _ in range(2):
                code, stdout, _stderr = run_main(
                    ["check", "--report-html", REPORT], self.root
                )
                self.assertEqual((code, stdout), (1, ""))
                outputs.append(target.read_bytes())
        self.assertEqual(outputs[0], outputs[1])
        text = outputs[0].decode("utf-8")
        self.assertIn(FIXED_TIME.isoformat(timespec="seconds"), text)
        self.assertIn("<dd>0.00 s</dd>", text)

    def test_duration_comes_from_the_clock(self) -> None:
        moments = [FIXED_TIME, FIXED_TIME.replace(second=8)]
        with mock.patch("furryp.cli.app.local_now", side_effect=moments):
            run_main(["check", "--report-html", REPORT], self.root)
        self.assertIn(
            "<dd>3.00 s</dd>", (self.root / REPORT).read_text(encoding="utf-8")
        )

    def test_internal_error_is_listed_and_gives_code_2(self) -> None:
        """Stderr does not follow the file: the report says it too."""

        def explode(context: object) -> list[Diagnostic]:
            raise ValueError("boom")

        failing = Rule(
            "FUR999", "explode", "test", "Fake.", None, False, Scope.LINE, explode
        )
        write_files(self.root, {"b.py": "y = 2\n"})
        with mock.patch("furryp.cli.app.ALL_RULES", [failing]):
            code, stdout, stderr = run_main(
                ["check", "--select", "FUR999", "--report-html", REPORT], self.root
            )
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("error: Failed to check a.py: ValueError: boom", stderr)
        text = (self.root / REPORT).read_text(encoding="utf-8")
        check_html(self, text)
        self.assertIn('role="alert"', text)
        self.assertIn("files not analyzed: 2.", text)
        self.assertIn("Internal error: ValueError: boom", text)

    def test_exit_zero_does_not_hide_an_internal_error(self) -> None:
        def explode(context: object) -> list[Diagnostic]:
            raise ValueError("boom")

        failing = Rule(
            "FUR999", "explode", "test", "Fake.", None, False, Scope.LINE, explode
        )
        with mock.patch("furryp.cli.app.ALL_RULES", [failing]):
            code, _stdout, _stderr = run_main(
                ["check", "--select", "FUR999", "--exit-zero", "--report-html", REPORT],
                self.root,
            )
        self.assertEqual(code, 2)

    def test_a_rule_ignored_on_the_command_line_does_not_rate(self) -> None:
        run_main(["check", "--ignore", "FUR4", "--report-html", REPORT], self.root)
        text = (self.root / REPORT).read_text(encoding="utf-8")
        self.assertIn('class="rating rating-none">*</span><h2>Design', text)
