"""Lines, columns and indexes (SPEC §10.1, §10.4) and the diagnostic model."""

import unittest
from pathlib import Path

from furryp.core.diagnostic import Diagnostic, Position, line_span
from furryp.core.positions import (
    byte_to_char_column,
    char_to_byte_column,
    first_line_break,
    split_lines,
    split_lines_with_breaks,
    text_index,
)


class SplitLinesTest(unittest.TestCase):
    def test_line_breaks(self) -> None:
        cases = [
            ("", ()),
            ("\n", ("",)),
            ("a", ("a",)),
            ("a\n", ("a",)),
            ("a\n\n", ("a", "")),
            ("a\r\nb\rc\nd", ("a", "b", "c", "d")),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(split_lines(text), expected)

    def test_lines_with_their_line_breaks(self) -> None:
        cases = [
            ("", ()),
            ("\n", ("\n",)),
            ("a", ("a",)),
            ("a\r\nb\rc\nd", ("a\r\n", "b\r", "c\n", "d")),
            ("a\fb\n\n", ("a\fb\n", "\n")),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(split_lines_with_breaks(text), expected)

    def test_other_separators_do_not_split(self) -> None:
        self.assertEqual(split_lines("a\fb\vc\x1cd\x85e f\n"), ("a\fb\vc\x1cd\x85e f",))

    def test_first_line_break(self) -> None:
        self.assertEqual(first_line_break("a\r\nb\n"), "\r\n")
        self.assertEqual(first_line_break("a\rb\r\n"), "\r")
        self.assertIsNone(first_line_break("a"))


class ColumnTest(unittest.TestCase):
    def test_bytes_to_characters(self) -> None:
        line = "é = '日本'"
        self.assertEqual(byte_to_char_column(line, 0), 0)
        self.assertEqual(byte_to_char_column(line, 2), 1)
        self.assertEqual(
            byte_to_char_column(line, len(line.encode("utf-8"))), len(line)
        )

    def test_characters_to_bytes(self) -> None:
        line = "é = '日本'"
        self.assertEqual(char_to_byte_column(line, 1), 2)
        self.assertEqual(char_to_byte_column(line, 6), 9)


class TextIndexTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        text = "ab\r\ncé\rd\n"
        index = text_index(text)
        for offset in range(len(text) + 1):
            with self.subTest(offset=offset):
                self.assertEqual(index.index(index.position(offset)), offset)

    def test_positions(self) -> None:
        index = text_index("ab\r\ncé\rd\n")
        self.assertEqual(index.position(0), Position(1, 1))
        self.assertEqual(index.position(4), Position(2, 1))
        self.assertEqual(index.position(7), Position(3, 1))
        self.assertEqual(index.index(Position(2, 2)), 5)
        self.assertEqual(index.position(9), Position(4, 1))


class DiagnosticTest(unittest.TestCase):
    def make(self, help_text: str) -> Diagnostic:
        return Diagnostic(
            "FUR999", "x", "m", Path("a.py"), line_span(1, 1, 2), help_text
        )

    def test_help_is_mandatory(self) -> None:
        for help_text in ("", "   ", "Do this\nthen that", "Do this\rthen"):
            with self.subTest(help_text=help_text), self.assertRaises(ValueError):
                self.make(help_text)

    def test_long_help_is_truncated(self) -> None:
        self.assertEqual(self.make("x" * 160).help, "x" * 160)
        truncated = self.make("x" * 200).help
        self.assertEqual(len(truncated), 160)
        self.assertTrue(truncated.endswith("x…"))


if __name__ == "__main__":
    unittest.main()
