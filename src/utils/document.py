# src/utils/document.py
import logging
import os
import re
from ebooklib import epub
from bs4 import BeautifulSoup
import ebooklib
import pymupdf4llm
from typing import List, Tuple

logger = logging.getLogger(__name__)


class TextExtractor:
    """Utility for reading and chunking raw text files."""

    @staticmethod
    def extract(filepath: str) -> str:
        with open(filepath, encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def extract_and_split(
        filepath: str, delimiter_pattern: str = r"^%%%\s+(.+)$"
    ) -> List[Tuple[str, str]]:
        content = TextExtractor.extract(filepath)
        pattern = re.compile(delimiter_pattern, flags=re.MULTILINE)

        lines = content.splitlines()
        sections: List[Tuple[str, str]] = []
        current_filename = None
        current_buffer = []

        for line in lines:
            match = pattern.match(line)
            if match:
                if current_filename:
                    sections.append(
                        (current_filename, "\n".join(current_buffer).strip())
                    )
                current_filename = match.group(1).strip()
                current_buffer = []
            else:
                if current_filename is not None:
                    current_buffer.append(line)

        if current_filename and current_buffer:
            sections.append((current_filename, "\n".join(current_buffer).strip()))

        if not sections:
            base_name = os.path.basename(filepath)
            sections = [(base_name, content)]

        return sections


class PDFExtractor:
    """Utility for converting PDFs to Markdown and optionally splitting by chapter."""

    @staticmethod
    def extract(
        filepath: str,
        split_chapters: bool = True,
        split_pattern: str = r"(?i)(?=Chapter|^# )",
    ) -> List[str]:
        logger.info(f"Converting PDF to Markdown: {filepath}")
        markdown_text = pymupdf4llm.to_markdown(filepath)

        if not split_chapters:
            return [markdown_text]

        logger.info(f"Splitting PDF content using pattern: '{split_pattern}'")
        return re.split(split_pattern, markdown_text, flags=re.MULTILINE)


class EpubExtractor:
    """Utility for parsing EPUBs into raw text and optionally splitting by chapter."""

    @staticmethod
    def extract(filepath: str, split_chapters: bool = True) -> List[str]:
        logger.info(f"Parsing EPUB: {filepath}")
        book = epub.read_epub(filepath)
        chapters, full_text_buffer = [], []

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                text = BeautifulSoup(item.get_content(), "html.parser").get_text(
                    separator="\n\n"
                )

                if split_chapters:
                    chapters.append(text)
                else:
                    full_text_buffer.append(text)

        return chapters if split_chapters else ["\n\n".join(full_text_buffer)]
