"""Source files: encodings, line breaks, tokens, logical lines, AST (§3.1, §9.2)."""

import tokenize
import unittest
import warnings
from pathlib import Path

from furryp.core.diagnostic import Position
from furryp.core.source import (
    SourceDecodeError,
    SourceReadError,
    decode_source,
    read_source,
)
from tests.support import TempDirTestCase, write_files

PATH = Path("example.py")


class EncodingTest(unittest.TestCase):
    def test_utf8_by_default(self) -> None:
        source = decode_source(PATH, "example.py", 'name = "é"\n'.encode())
        self.assertEqual(source.encoding, "utf-8")
        self.assertEqual(source.lines, ('name = "é"',))

    def test_bom(self) -> None:
        source = decode_source(PATH, "example.py", b'\xef\xbb\xbfx = "\xc3\xa9"\n')
        self.assertEqual(source.encoding, "utf-8-sig")
        self.assertEqual(source.text, 'x = "é"\n')

    def test_coding_declaration(self) -> None:
        data = '# -*- coding: latin-1 -*-\nname = "é"\n'.encode("latin-1")
        source = decode_source(PATH, "example.py", data)
        self.assertEqual(source.encoding, "iso-8859-1")
        self.assertEqual(source.lines[1], 'name = "é"')
        self.assertIsNone(source.syntax_error)

    def test_undecodable(self) -> None:
        for data in (b'name = "\xe9"\n', b"# ok\n# ok\nx = '\xe9'\n"):
            with self.subTest(data=data), self.assertRaises(SourceDecodeError):
                decode_source(PATH, "example.py", data)

    def test_unknown_encoding(self) -> None:
        with self.assertRaises(SourceDecodeError):
            decode_source(PATH, "example.py", b"# -*- coding: nope -*-\nx = 1\n")

    def test_codec_that_is_not_a_text_encoding(self) -> None:
        with self.assertRaises(SourceDecodeError):
            decode_source(PATH, "example.py", b"# -*- coding: rot13 -*-\nx = 1\n")


class LineBreakTest(unittest.TestCase):
    def test_line_breaks_are_kept(self) -> None:
        source = decode_source(PATH, "example.py", b"x = 1\r\ny = 2\nz = 3\r\n")
        self.assertEqual(source.text, "x = 1\r\ny = 2\nz = 3\r\n")
        self.assertEqual(source.newline, "\r\n")
        self.assertEqual(source.lines, ("x = 1", "y = 2", "z = 3"))

    def test_default_newline(self) -> None:
        self.assertEqual(decode_source(PATH, "example.py", b"x = 1").newline, "\n")

    def test_line_bounds(self) -> None:
        source = decode_source(PATH, "example.py", b"x = 1\r\ny = 2\nz")
        self.assertEqual(
            [source.line_bounds(line) for line in (1, 2, 3)],
            [(0, 7), (7, 13), (13, 14)],
        )
        source = decode_source(PATH, "example.py", b"x\n")
        self.assertEqual(source.line_bounds(1), (0, 2))


class SyntaxTest(unittest.TestCase):
    def test_valid_source(self) -> None:
        source = decode_source(PATH, "example.py", b"x = 1\n")
        self.assertIsNone(source.syntax_error)
        self.assertIsNotNone(source.tree)
        self.assertEqual(source.tokens[0].type, tokenize.NAME)

    def test_syntax_error_position_in_characters(self) -> None:
        source = decode_source(PATH, "example.py", "é = 'é' +* 2\n".encode())
        self.assertIsNone(source.tree)
        self.assertEqual(source.syntax_error.message, "invalid syntax")
        self.assertEqual(source.syntax_error.span.start, Position(1, 10))

    def test_error_past_the_end_is_kept_in_the_file(self) -> None:
        source = decode_source(PATH, "example.py", b"def f(\n    a,\n")
        self.assertEqual(source.syntax_error.span.start, Position(1, 6))

    def test_null_byte(self) -> None:
        source = decode_source(PATH, "example.py", b"# a\n# b\nx = 1\x00\n")
        self.assertEqual(source.syntax_error.span.start, Position(1, 1))
        with self.assertRaises(SourceDecodeError):
            decode_source(PATH, "example.py", b"x = 1\x00\n")

    def test_no_syntax_warning(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            decode_source(PATH, "example.py", b'x = "\\d"\n')
        self.assertEqual(caught, [])

    def test_logical_lines(self) -> None:
        text = b"x = (\n    1,\n)  # end\n# alone\n\ndef f(\n    a,\n):\n    pass\n"
        logical = decode_source(PATH, "example.py", text).logical
        self.assertEqual(logical.ranges, ((1, 3), (6, 8), (9, 9)))
        expected = {
            1: (1, 3),
            2: (1, 3),
            3: (1, 3),
            4: (4, 4),
            5: (5, 5),
            6: (6, 8),
            7: (6, 8),
            8: (6, 8),
            9: (9, 9),
            10: (10, 10),
        }
        for line, lines in expected.items():
            with self.subTest(line=line):
                self.assertEqual(logical.range_of(line), lines)


class ReadTest(TempDirTestCase):
    def test_missing_file(self) -> None:
        with self.assertRaises(SourceReadError) as caught:
            read_source(self.root / "missing.py", "missing.py")
        self.assertEqual(str(caught.exception), "No such file or directory")

    def test_read_bytes(self) -> None:
        write_files(self.root, {"a.py": "x = 1\r\n"})
        source = read_source(self.root / "a.py", "a.py")
        self.assertEqual((source.text, source.display), ("x = 1\r\n", "a.py"))


if __name__ == "__main__":
    unittest.main()
