"""Turn uploaded artifact bytes into structured document content.

Images stay on the vision path. This module never returns binary, host paths,
or decoded PDF/Office bytes as if they were UTF-8 documents.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from contextlib import suppress
from pathlib import PurePosixPath
from xml.etree import ElementTree

from veyra_agent_platform.contracts.document import DocumentContent, DocumentTable

MAX_EXTRACTED_CHARS = 24_000
_MAX_ZIP_MEMBERS = 64
_MAX_MEMBER_BYTES = 1_000_000
_MAX_TABLE_ROWS = 200
_MAX_TABLE_COLS = 32
_PDF_STRING = re.compile(r"\((?:\\.|[^\\)])*\)")
_WHITESPACE = re.compile(r"[ \t]+\n")
_CELL_REF = re.compile(r"^([A-Z]+)([0-9]+)$")


def artifact_plain_text(filename: str, media_type: str, contents: bytes) -> str:
    return extract_document(filename, media_type, contents, "").plaintext()


def extract_document(
    filename: str,
    media_type: str,
    contents: bytes,
    artifact_id: str,
) -> DocumentContent:
    suffix = PurePosixPath(filename.lower()).suffix
    media = media_type.casefold()
    tables: tuple[DocumentTable, ...] = ()
    blocks: tuple[str, ...]
    metadata: dict[str, str] = {"filename": filename, "media_type": media_type}
    if suffix == ".json" or media == "application/json":
        blocks = (_json_blocks(contents),)
    elif suffix in {".txt", ".md", ".markdown", ".csv"} or media.startswith("text/"):
        text = _utf8_text(contents)
        if suffix == ".csv" or media == "text/csv":
            tables = (_csv_table(text),)
            blocks = ()
        else:
            blocks = (text,)
    elif suffix == ".docx" or media.endswith("wordprocessingml.document"):
        blocks = (_docx_text(contents),)
    elif suffix == ".xlsx" or "spreadsheetml.sheet" in media:
        tables = _xlsx_tables(contents)
        if tables:
            blocks = ()
        else:
            try:
                shared = _shared_strings(_zip_member(contents, "xl/sharedStrings.xml"))
            except (zipfile.BadZipFile, zipfile.LargeZipFile):
                shared = ()
            blocks = ("\n".join(item for item in shared if item),)
    elif suffix == ".pdf" or media == "application/pdf":
        blocks = (_pdf_text(contents),)
    elif suffix == ".rtf" or media == "application/rtf":
        blocks = (_rtf_text(contents),)
    else:
        blocks = (_utf8_text(contents) if _looks_like_text(contents) else "",)
    clipped = tuple(
        block
        if len(block) <= MAX_EXTRACTED_CHARS
        else block[: MAX_EXTRACTED_CHARS - 1] + "…"
        for block in blocks
        if block
    )
    return DocumentContent(
        source_artifact_id=artifact_id,
        filename=filename,
        media_type=media_type,
        text_blocks=clipped,
        tables=tables,
        metadata=metadata,
    )


def _clip(text: str) -> str:
    compact = _WHITESPACE.sub("\n", text).strip()
    if len(compact) <= MAX_EXTRACTED_CHARS:
        return compact
    return compact[: MAX_EXTRACTED_CHARS - 1] + "…"


def _looks_like_text(contents: bytes) -> bool:
    if not contents or b"\x00" in contents[:4096]:
        return False
    sample = contents[:4096]
    return sample.count(b"\x00") == 0 and sum(1 for byte in sample if byte < 9) < 8


def _utf8_text(contents: bytes) -> str:
    if not _looks_like_text(contents):
        return ""
    return contents.decode("utf-8", errors="replace")


def _pdf_text(contents: bytes) -> str:
    if not contents.startswith(b"%PDF"):
        return ""
    decoded = contents.decode("latin-1", errors="replace")
    chunks: list[str] = []
    for match in _PDF_STRING.finditer(decoded):
        raw = match.group(0)[1:-1]
        raw = raw.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
        raw = raw.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
        if raw.strip():
            chunks.append(raw)
    return "\n".join(chunks)


def _rtf_text(contents: bytes) -> str:
    if not contents.lstrip().startswith(b"{\\rtf"):
        return ""
    text = contents.decode("latin-1", errors="replace")
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text)


def _docx_text(contents: bytes) -> str:
    try:
        return _xml_text(_zip_member(contents, "word/document.xml"))
    except (zipfile.BadZipFile, zipfile.LargeZipFile):
        return ""


def _xlsx_text(contents: bytes) -> str:
    return extract_document(
        "book.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        contents,
        "",
    ).plaintext()


def _xlsx_tables(contents: bytes) -> tuple[DocumentTable, ...]:
    try:
        shared = _shared_strings(_zip_member(contents, "xl/sharedStrings.xml"))
        tables: list[DocumentTable] = []
        with _open_zip(contents) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            ]
            for index, name in enumerate(names[:12], start=1):
                table = _xlsx_sheet(
                    _read_zip_member(archive, name),
                    shared,
                    PurePosixPath(name).stem or f"sheet{index}",
                )
                if table is not None:
                    tables.append(table)
        return tuple(tables)
    except (zipfile.BadZipFile, zipfile.LargeZipFile):
        return ()


def _shared_strings(payload: bytes) -> tuple[str, ...]:
    if not payload:
        return ()
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return ()
    values: list[str] = []
    for item in root.findall(
        ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"
    ):
        values.append("".join(item.itertext()).strip())
    return tuple(values)


def _xlsx_sheet(
    payload: bytes, shared: tuple[str, ...], sheet: str
) -> DocumentTable | None:
    if not payload:
        return None
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return None
    grid: dict[tuple[int, int], str] = {}
    max_row = 0
    max_col = 0
    for cell in root.findall(
        ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"
    ):
        ref = cell.get("r") or ""
        match = _CELL_REF.fullmatch(ref)
        if match is None:
            continue
        col = _column_index(match.group(1))
        row = int(match.group(2))
        if col > _MAX_TABLE_COLS or row > _MAX_TABLE_ROWS:
            continue
        value_el = cell.find(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v"
        )
        raw = value_el.text if value_el is not None and value_el.text else ""
        if cell.get("t") == "s":
            with suppress(ValueError, IndexError):
                raw = shared[int(raw)]
        grid[(row, col)] = raw
        max_row = max(max_row, row)
        max_col = max(max_col, col)
    if max_row == 0 or max_col == 0:
        return None
    rows = []
    for row in range(1, max_row + 1):
        rows.append(tuple(grid.get((row, col), "") for col in range(1, max_col + 1)))
    headers = rows[0] if rows else ()
    body = tuple(rows[1:]) if len(rows) > 1 else ()
    return DocumentTable(sheet=sheet, headers=headers, rows=body)


def _column_index(label: str) -> int:
    total = 0
    for char in label:
        total = total * 26 + (ord(char) - 64)
    return total


def _csv_table(text: str) -> DocumentTable:
    rows = [
        tuple(part.strip() for part in line.split(","))
        for line in text.splitlines()
        if line.strip()
    ]
    headers = rows[0] if rows else ()
    body = tuple(rows[1:]) if len(rows) > 1 else ()
    return DocumentTable(sheet="sheet", headers=headers, rows=body)


def _json_blocks(contents: bytes) -> str:
    text = _utf8_text(contents)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def _xml_text(payload: bytes) -> str:
    if not payload:
        return ""
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return re.sub(r"<[^>]+>", " ", payload.decode("utf-8", errors="replace"))
    chunks = [text.strip() for text in root.itertext() if text and text.strip()]
    return "\n".join(chunks)


def _open_zip(contents: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(contents))


def _zip_member(contents: bytes, name: str) -> bytes:
    with _open_zip(contents) as archive:
        return _read_zip_member(archive, name)


def _read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    if len(archive.namelist()) > _MAX_ZIP_MEMBERS:
        return b""
    target = name.replace("\\", "/")
    if target.startswith("/") or ".." in PurePosixPath(target).parts:
        return b""
    try:
        info = archive.getinfo(name)
    except KeyError:
        return b""
    if info.file_size > _MAX_MEMBER_BYTES:
        return b""
    return archive.read(name)
