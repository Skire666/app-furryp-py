"""``--diff`` output, as ruff 0.17.3 prints it (SPEC §5.3)."""

import unittest

from furryp.fix.diff import render_diff_footer, render_file_diff


class FileDiffTest(unittest.TestCase):
    def test_unified_diff_followed_by_a_blank_line(self) -> None:
        self.assertEqual(
            render_file_diff("a.py", "x = 1\ny = 2\n", "x = 1\n\n# end\n"),
            "--- a.py\n+++ a.py\n@@ -1,2 +1,3 @@\n x = 1\n-y = 2\n+\n+# end\n\n",
        )

    def test_last_line_without_line_break(self) -> None:
        self.assertEqual(
            render_file_diff("a.py", "x = 1", "x = 1\n\n# end\n"),
            "--- a.py\n"
            "+++ a.py\n"
            "@@ -1 +1,3 @@\n"
            "-x = 1\n"
            "\\ No newline at end of file\n"
            "+x = 1\n"
            "+\n"
            "+# end\n"
            "\n",
        )

    def test_lines_keep_their_line_breaks(self) -> None:
        self.assertEqual(
            render_file_diff("a.py", "x = 1\r\n# end \r\n", "x = 1\r\n# end\r\n"),
            "--- a.py\n+++ a.py\n@@ -1,2 +1,2 @@\n x = 1\r\n-# end \r\n+# end\r\n\n",
        )

    def test_three_lines_of_context(self) -> None:
        before = "".join(f"x{n} = {n}\n" for n in range(10))
        after = before.replace("x5 = 5\n", "")
        diff = render_file_diff("a.py", before, after)
        self.assertIn("@@ -3,7 +3,6 @@\n x2 = 2\n", diff)
        self.assertTrue(diff.endswith(" x8 = 8\n\n"))


class FooterTest(unittest.TestCase):
    def test_footer(self) -> None:
        self.assertIsNone(render_diff_footer(0))
        self.assertEqual(render_diff_footer(1), "Would fix 1 error.")
        self.assertEqual(render_diff_footer(3), "Would fix 3 errors.")


if __name__ == "__main__":
    unittest.main()
