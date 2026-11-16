"""
Regression coverage for a real production bug: pdfplumber's find_tables()
misdetected a stylized, letter-spaced resume header ("H A S N A I N  ARIF")
as a sparse table, and _table_to_markdown() joined its mostly-empty cells
with " | ", garbling the name in the indexed text. See
src/ingestion/parsers/pdf.py's MIN_TABLE_FILLED_CELL_RATIO/
_looks_like_real_table()/_drop_lines_inside_bboxes() for the fix: a
detected "table" region is only treated as real (and only then excluded
from the plain-text pass) once enough of its cells are actually filled.
"""

from src.ingestion.parsers.pdf import PDFDocumentParser


def test_looks_like_real_table_rejects_a_mostly_empty_header_misdetection():
    # Mirrors what find_tables() produced for the letter-spaced header:
    # each "column" holds one letter/word, everything else empty.
    sparse_rows = [
        ["H", "", "", "A", "", "", "ARIF"],
        ["", "", "", "", "", "", ""],
    ]
    assert PDFDocumentParser._looks_like_real_table(sparse_rows) is False


def test_looks_like_real_table_accepts_a_genuinely_filled_table():
    filled_rows = [
        ["Skill", "Years"],
        ["Python", "5"],
        ["TypeScript", "3"],
    ]
    assert PDFDocumentParser._looks_like_real_table(filled_rows) is True


def test_looks_like_real_table_rejects_completely_empty_rows():
    assert PDFDocumentParser._looks_like_real_table([["", ""], ["", ""]]) is False
    assert PDFDocumentParser._looks_like_real_table([]) is False


def test_drop_lines_inside_bboxes_is_a_no_op_when_no_tables_were_confirmed():
    lines = [("Hasnain Arif", 12.0, True, (0, 0, 100, 10)), ("Software Engineer", 10.0, False, (0, 15, 100, 25))]
    result = PDFDocumentParser._drop_lines_inside_bboxes(lines, [])
    assert result == [("Hasnain Arif", 12.0, True), ("Software Engineer", 10.0, False)]


def test_drop_lines_inside_bboxes_drops_only_lines_inside_a_confirmed_table():
    lines = [
        ("inside the table", 10.0, False, (10, 10, 90, 20)),
        ("outside the table", 10.0, False, (10, 100, 90, 110)),
    ]
    table_bboxes = [(0, 0, 100, 50)]
    result = PDFDocumentParser._drop_lines_inside_bboxes(lines, table_bboxes)
    assert result == [("outside the table", 10.0, False)]
