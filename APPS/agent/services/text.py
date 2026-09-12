"""文本归一化、Token 估算、分块与文件内容提取。"""
from __future__ import annotations

import csv
import html
import json
import math
import re
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from ._compat import _LANGCHAIN_AVAILABLE
from .env import env_int_strip

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:
    RecursiveCharacterTextSplitter = None


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        return " ".join(self.parts)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 2))


def _legacy_split_text(text: str, chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[str]:
    chunk_size = chunk_size or env_int_strip("AGENT_CHUNK_SIZE", 900)
    chunk_overlap = chunk_overlap or env_int_strip("AGENT_CHUNK_OVERLAP", 120)
    text = normalize_text(text)
    if not text:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", ";", "，", ",", " "],
    )
    return [normalize_text(chunk) for chunk in splitter.split_text(text) if normalize_text(chunk)]


def _text_from_html(raw: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    return normalize_text(html.unescape(parser.get_text()))


def _text_from_docx(path: Path) -> str:
    namespace = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    }
    parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
        if text.strip():
            parts.append(text)
    return normalize_text("\n\n".join(parts))


def _text_from_xlsx(path: Path) -> str:
    namespace = {
        "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    }
    rows: list[str] = []
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(".//a:si", namespace):
                shared_strings.append(
                    "".join(node.text or "" for node in item.findall(".//a:t", namespace))
                )
        sheet_names = sorted(
            name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        for sheet_name in sheet_names:
            sheet_root = ET.fromstring(archive.read(sheet_name))
            for row in sheet_root.findall(".//a:sheetData/a:row", namespace):
                values: list[str] = []
                for cell in row.findall("a:c", namespace):
                    cell_type = cell.attrib.get("t")
                    value = ""
                    if cell_type == "s":
                        index_text = cell.findtext("a:v", default="0", namespaces=namespace)
                        try:
                            index = int(index_text or 0)
                            value = shared_strings[index] if index < len(shared_strings) else ""
                        except ValueError:
                            value = ""
                    elif cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.findall(".//a:t", namespace))
                    else:
                        value = cell.findtext("a:v", default="", namespaces=namespace) or ""
                    if value.strip():
                        values.append(value.strip())
                if values:
                    rows.append("\t".join(values))
    return normalize_text("\n".join(rows))


def extract_text_from_file(path: str | Path) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    raw = file_path.read_text(encoding="utf-8", errors="ignore")

    if suffix in {".txt", ".md", ".log", ".csv", ".json"}:
        if suffix == ".csv":
            rows: list[str] = []
            with file_path.open("r", encoding="utf-8", errors="ignore", newline="") as fp:
                reader = csv.reader(fp)
                for row in reader:
                    if row:
                        rows.append("\t".join(cell.strip() for cell in row if cell.strip()))
            return normalize_text("\n".join(rows))
        if suffix == ".json":
            try:
                return normalize_text(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
            except json.JSONDecodeError:
                return normalize_text(raw)
        return normalize_text(raw)

    if suffix in {".html", ".htm"}:
        return _text_from_html(raw)

    if suffix == ".xml":
        return normalize_text(re.sub(r"<[^>]+>", " ", raw))

    if suffix == ".docx":
        return _text_from_docx(file_path)

    if suffix == ".xlsx":
        return _text_from_xlsx(file_path)

    return normalize_text(raw)


def split_text(text: str, chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[str]:
    if not _LANGCHAIN_AVAILABLE or RecursiveCharacterTextSplitter is None:
        return _legacy_split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunk_size = chunk_size or env_int_strip("AGENT_CHUNK_SIZE", 900)
    chunk_overlap = chunk_overlap or env_int_strip("AGENT_CHUNK_OVERLAP", 120)
    text = normalize_text(text)
    if not text:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", ";", "，", ",", " "],
    )
    chunks = splitter.split_text(text)
    return [normalize_text(chunk) for chunk in chunks if normalize_text(chunk)]
