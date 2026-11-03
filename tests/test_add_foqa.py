"""``--add-foqa``: freezing the existing violations (SPEC §6.1).

``FUR901`` (``bad``) and ``FUR902`` (``worse``) are fake rules of scope
``line``; FUR102 and FUR201 are the shipped rules of scope ``file``.
"""

from pathlib import Path

from furryp.fix.foqa import add_foqa, preamble_end, render_added
from tests.support import (
    FLAG_BAD,
    FLAG_WORSE,
    TempDirTestCase,
    codes_at,
    linter_with,
    write_files,
)

LINE_RULES = {"select": ["FUR901", "FUR902", "FUR001"]}
FILE_RULES = {
    "select": ["FUR102", "FUR201", "FUR001"],
    "rules": {"file-too-long": {"max-lines": 0}, "halstead-file": {"max": 0}},
}


class AddFoqaTest(TempDirTestCase):
    def freeze(
        self, content: str | bytes, data: dict[str, object] | None = None
    ) -> tuple[int, bytes]:
        """Freeze ``a.py``, check that a second run adds nothing and that the
        file is then clean; return the count and the bytes written."""
        write_files(self.root, {"a.py": content})
        path = self.root / "a.py"
        linter = linter_with((FLAG_BAD, FLAG_WORSE), data or LINE_RULES, self.root)
        count = add_foqa(linter, path)
        written = path.read_bytes()
        self.assertEqual(add_foqa(linter, path), 0)
        self.assertEqual(path.read_bytes(), written)
        self.assertEqual(codes_at(linter.check_path(path)), [])
        return count, written

    def assert_frozen(
        self, content: str, expected: str, data: dict[str, object] | None = None
    ) -> None:
        count, written = self.freeze(content, data)
        self.assertEqual(written.decode("utf-8"), expected)
        self.assertEqual(count, 1)

    def test_compact_format_with_sorted_codes(self) -> None:
        self.assert_frozen("x = bad\n", "x = bad  # foqa:FUR901\n")
        self.assert_frozen(
            "x = worse + bad\n", "x = worse + bad  # foqa:FUR901,FUR902\n"
        )

    def test_end_of_the_logical_line(self) -> None:
        self.assert_frozen(
            "result = call(bad,\n    1,\n    2)\n",
            "result = call(bad,\n    1,\n    2)  # foqa:FUR901\n",
        )
        self.assert_frozen(
            "def f(\n    bad,\n):\n    pass\n",
            "def f(\n    bad,\n):  # foqa:FUR901\n    pass\n",
        )

    def test_trailing_blanks_are_removed(self) -> None:
        self.assert_frozen("x = bad   \n", "x = bad  # foqa:FUR901\n")

    def test_an_edited_last_line_gets_its_line_break(self) -> None:
        # As --add-noqa of ruff 0.17.3, in the style of the file.
        for content, expected in (
            ("x = bad", "x = bad  # foqa:FUR901\n"),
            ("x = bad   ", "x = bad  # foqa:FUR901\n"),
            ("y = 1\nx = bad", "y = 1\nx = bad  # foqa:FUR901\n"),
            ("y = 1\r\nx = bad", "y = 1\r\nx = bad  # foqa:FUR901\r\n"),
            ("x = bad  # why", "x = bad  # why  # foqa:FUR901\n"),
            (
                "x = bad + worse  # foqa:FUR902",
                "x = bad + worse  # foqa:FUR901,FUR902\n",
            ),
            (
                "x = bad + worse  # foqa:FUR902  # why",
                "x = bad + worse  # foqa:FUR901,FUR902  # why\n",
            ),
        ):
            with self.subTest(content=content):
                count, written = self.freeze(content.encode("utf-8"))
                self.assertEqual(count, 1)
                self.assertEqual(written.decode("utf-8"), expected)

    def test_a_last_line_that_is_not_edited_stays_as_it_is(self) -> None:
        self.assertEqual(
            self.freeze(b"x = bad\ny = 1"), (1, b"x = bad  # foqa:FUR901\ny = 1")
        )
        self.assertEqual(self.freeze(b"x = bad  # foqa"), (0, b"x = bad  # foqa"))

    def test_merged_with_an_existing_directive(self) -> None:
        self.assert_frozen(
            "x = (bad,  # foqa:FUR902\n     worse)\n",
            "x = (bad,  # foqa:FUR901,FUR902\n     worse)\n",
        )
        self.assert_frozen(
            "x = bad + worse  # foqa:flag-worse  # why\n",
            "x = bad + worse  # foqa:FUR901,flag-worse  # why\n",
        )

    def test_blanket_directive_is_respected(self) -> None:
        self.assertEqual(self.freeze("x = bad  # foqa\n"), (0, b"x = bad  # foqa\n"))

    def test_existing_comment_is_kept(self) -> None:
        self.assert_frozen("x = bad  # why\n", "x = bad  # why  # foqa:FUR901\n")

    def test_after_an_invalid_directive_it_is_added_at_each_run(self) -> None:
        # As --add-noqa of ruff 0.17.3: the invalid directive hides what follows it.
        for comment in ("# foqa.", "# a bare `# foqa`", "# foqa: FUR901;", "# foqafoo"):
            with self.subTest(comment=comment):
                write_files(self.root, {"a.py": f"x = bad  {comment}\n"})
                path = self.root / "a.py"
                linter = linter_with((FLAG_BAD, FLAG_WORSE), LINE_RULES, self.root)
                for count in (1, 2):
                    self.assertEqual(add_foqa(linter, path), 1)
                    self.assertEqual(
                        path.read_bytes().decode("utf-8"),
                        f"x = bad  {comment}" + "  # foqa:FUR901" * count + "\n",
                    )
                self.assertEqual(codes_at(linter.check_path(path)), ["1:5 FUR901"])

    def test_blanket_directive_with_text_is_respected(self) -> None:
        self.assertEqual(
            self.freeze("x = bad  # foqa bar\n"), (0, b"x = bad  # foqa bar\n")
        )

    def test_one_directive_per_logical_line(self) -> None:
        count, written = self.freeze("x = bad\ny = 1\nz = (worse,\n     bad)\n")
        self.assertEqual(count, 2)
        self.assertEqual(
            written,
            b"x = bad  # foqa:FUR901\ny = 1\nz = (worse,\n     bad)  # foqa:FUR901,FUR902\n",
        )

    def test_file_rules_get_a_single_file_directive(self) -> None:
        self.assert_frozen(
            "x = 1\ny = 2\n", "# furryp: foqa:FUR102,FUR201\nx = 1\ny = 2\n", FILE_RULES
        )
        self.assert_frozen(
            "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\nx = 1\n",
            "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n"
            "# furryp: foqa:FUR102,FUR201\nx = 1\n",
            FILE_RULES,
        )

    def test_file_directive_is_completed(self) -> None:
        self.assert_frozen(
            "x = 1\n# furryp: foqa:FUR102\n",
            "x = 1\n# furryp: foqa:FUR102,FUR201\n",
            FILE_RULES,
        )

    def test_a_file_directive_on_the_last_line_gets_its_line_break(self) -> None:
        count, written = self.freeze(b"x = 1\n# furryp: foqa:FUR102", FILE_RULES)
        self.assertEqual(count, 1)
        self.assertEqual(written, b"x = 1\n# furryp: foqa:FUR102,FUR201\n")

    def test_encoding_bom_and_line_breaks_are_kept(self) -> None:
        data = {"select": ["FUR102"], "rules": {"file-too-long": {"max-lines": 0}}}
        latin_1 = (
            b"#!/usr/bin/env python\r\n# -*- coding: latin-1 -*-\r\nx = '\xe9'\r\n"
        )
        self.assertEqual(
            self.freeze(latin_1, data),
            (
                1,
                b"#!/usr/bin/env python\r\n# -*- coding: latin-1 -*-\r\n"
                b"# furryp: foqa:FUR102\r\nx = '\xe9'\r\n",
            ),
        )
        self.assertEqual(
            self.freeze(b"\xef\xbb\xbfx = '\xc3\xa9'\n", data),
            (1, b"\xef\xbb\xbf# furryp: foqa:FUR102\nx = '\xc3\xa9'\n"),
        )

    def test_unused_foqa_is_never_frozen(self) -> None:
        write_files(self.root, {"a.py": "x = 1  # foqa:FUR102\n"})
        path = self.root / "a.py"
        linter = linter_with(root=self.root)
        self.assertEqual(add_foqa(linter, path), 0)
        self.assertEqual(path.read_bytes(), b"x = 1  # foqa:FUR102\n")
        self.assertEqual(codes_at(linter.check_path(path)), ["1:8 FUR001"])

    def test_files_in_fur000_are_left_alone(self) -> None:
        write_files(self.root, {"a.py": "x = (\n"})
        linter = linter_with(root=self.root)
        self.assertEqual(add_foqa(linter, self.root / "a.py"), 0)
        self.assertEqual((self.root / "a.py").read_bytes(), b"x = (\n")
        self.assertEqual(add_foqa(linter, self.root / "missing.py"), 0)
        self.assertFalse(Path(self.root / "missing.py").exists())

    def test_a_file_in_fur000_is_left_alone_even_with_a_textual_violation(self) -> None:
        # FUR102 still runs on such a file, and would otherwise be frozen.
        linter = linter_with(data=FILE_RULES, root=self.root)
        for content in (b"x = (\n", b"x = 1 +* 2\n"):
            with self.subTest(content=content):
                write_files(self.root, {"a.py": content})
                self.assertEqual(add_foqa(linter, self.root / "a.py"), 0)
                self.assertEqual((self.root / "a.py").read_bytes(), content)


class PreambleTest(TempDirTestCase):
    def test_preamble_end(self) -> None:
        cases = [
            ((), 0),
            (("x = 1",), 0),
            (("#!/usr/bin/env python", "x = 1"), 1),
            (("# -*- coding: latin-1 -*-", "x = 1"), 1),
            (("#!/usr/bin/env python", "# vim: set fileencoding=utf-8 :"), 2),
            (("# a comment", "# coding=latin-1", "x = 1"), 2),
            (("x = 1", "y = 2", "# coding: latin-1"), 0),
        ]
        for lines, expected in cases:
            with self.subTest(lines=lines):
                self.assertEqual(preamble_end(lines), expected)

    def test_message(self) -> None:
        self.assertIsNone(render_added(0))
        self.assertEqual(render_added(1), "Added 1 foqa directive.")
        self.assertEqual(render_added(2), "Added 2 foqa directives.")
