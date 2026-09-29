from __future__ import annotations

import io
import zipfile

from veyra_agent_platform.local.artifacts.extract import artifact_plain_text
from veyra_agent_platform.local.artifacts.media import inspect_artifact


def _docx(paragraph: str) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p></w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _xlsx(value: str) -> bytes:
    shared = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<si><t>{value}</t></si></sst>"
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData></sheetData></worksheet>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def test_plain_text_and_markdown_extract() -> None:
    assert (
        artifact_plain_text("notes.txt", "text/plain", b"hello brief") == "hello brief"
    )
    assert "包装" in artifact_plain_text(
        "brief.md", "text/markdown", "圣诞包装要点".encode()
    )


def test_docx_and_xlsx_extract_without_host_paths() -> None:
    docx = artifact_plain_text(
        "brief.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        _docx("彩绘风格"),
    )
    xlsx = artifact_plain_text(
        "budget.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        _xlsx("预算 120"),
    )
    assert docx == "彩绘风格"
    assert "预算 120" in xlsx
    assert "/Users" not in docx
    assert "/Users" not in xlsx


def test_pdf_extracts_literal_strings_not_raw_bytes() -> None:
    pdf = (
        b"%PDF-1.4\n1 0 obj\n<< /Length 40 >>\nstream\n"
        b"BT (Santa candy box) Tj ET\nendstream\nendobj\n"
    )
    text = artifact_plain_text("box.pdf", "application/pdf", pdf)
    assert "Santa candy box" in text
    assert "%PDF" not in text


def test_binary_file_does_not_decode_as_utf8() -> None:
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    assert artifact_plain_text("photo.png", "image/png", png) == ""


def test_office_suffixes_are_documents() -> None:
    assert inspect_artifact("brief.docx", _docx("ok"))[1] == "document"
    assert inspect_artifact("budget.xlsx", _xlsx("1"))[1] == "document"
    assert inspect_artifact("table.csv", b"a,b\n1,2")[1] == "document"


def test_invalid_office_bytes_do_not_raise() -> None:
    assert (
        artifact_plain_text(
            "broken.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"not-a-zip",
        )
        == ""
    )
