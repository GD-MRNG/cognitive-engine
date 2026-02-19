import logging
import re
import os
from typing import Dict, Any, List, Tuple
import textwrap

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task

logger = logging.getLogger(__name__)


@register_task("TextFileSplitterTask")
class TextFileSplitterTask(PipelineTask):
    """
    Reads a single large text file, splits it by a delimiter (e.g., '%%% filename'),
    and populates the context with a list of documents.
    """

    # Regex to match "%%% filename"
    DELIMITER_PATTERN = re.compile(r"^%%%\s+(.+)$")

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_file = config.get("input_file")
        output_key = config.get("output_key", "split_docs")
        save_to_disk = config.get("save_to_disk", False)
        output_dir = self.get_workspace_path(
            context, config.get("output_dir", "split_files")
        )

        if not input_file or not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        logger.info(f"Splitting file: {input_file}")

        with open(input_file, encoding="utf-8") as f:
            content = f.read()

        sections = self._parse_content(content)

        if not sections:
            logger.warning(
                "No sections found using '%%%' delimiter. treating file as single doc."
            )
            base_name = os.path.basename(input_file)
            sections = [(base_name, content)]

        # Convert to standard document format for the pipeline
        # Structure: [{'filename': '...', 'content': '...'}]
        doc_list = []
        for filename, text in sections:
            # Ensure .txt extension for consistency
            if not filename.endswith(".txt"):
                safe_filename = f"{self._sanitize_filename(filename)}.txt"
            else:
                safe_filename = self._sanitize_filename(filename)

            doc_list.append(
                {
                    "filename": safe_filename,
                    "content": text,
                    "filepath": f"virtual/{safe_filename}",  # Virtual path since it exists in memory
                }
            )

            # Optional: Write to disk (mimicking your original script)
            if save_to_disk:
                self._save_file(output_dir, safe_filename, text)

        # Store in context
        context.set(output_key, doc_list)
        logger.info(
            f"Splitter produced {len(doc_list)} documents into key '{output_key}'."
        )

        return context

    def _parse_content(self, content: str) -> List[Tuple[str, str]]:
        lines = content.splitlines()
        sections: List[Tuple[str, str]] = []

        current_filename = None
        current_buffer = []

        for line in lines:
            match = self.DELIMITER_PATTERN.match(line)
            if match:
                # Close previous section
                if current_filename:
                    sections.append(
                        (current_filename, "\n".join(current_buffer).strip())
                    )

                # Start new section
                current_filename = match.group(1).strip()
                current_buffer = []
            else:
                if current_filename is not None:
                    current_buffer.append(line)

        # Append final section
        if current_filename and current_buffer:
            sections.append((current_filename, "\n".join(current_buffer).strip()))

        return sections

    def _sanitize_filename(self, name: str) -> str:
        return "".join(c for c in name if c.isalnum() or c in ("_", "-", " "))

    def _save_file(self, folder: str, filename: str, content: str):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug(f"Saved split file: {path}")


@register_task("BookDigestTask")
class BookDigestTask(PipelineTask):
    """
    Ingests binary book formats (PDF, EPUB), intelligently splits them into chapters,
    and converts them to clean text.

    Includes 'Source: [Filename]' header in every output chunk.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_file = config.get("input_file")
        output_key = config.get("output_key", "digested_chapters")
        save_to_disk = config.get("save_to_disk", False)
        output_dir = self.get_workspace_path(
            context, config.get("output_dir", "digested_books")
        )
        split_pattern = config.get("split_pattern", r"(?i)(?=Chapter|^# )")

        wrap_text = config.get("wrap_text", True)
        line_width = config.get("line_width", 80)

        if not input_file or not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        # Get just the filename (e.g., "The_Title.pdf")
        filename_only = os.path.basename(input_file)
        base_name = os.path.splitext(filename_only)[0]
        ext = os.path.splitext(input_file)[1].lower()

        logger.info(f"Digesting book: {filename_only}")

        chapters = []

        # 1. Routing
        if ext == ".pdf":
            chapters = self._process_pdf(input_file, split_pattern)
        elif ext == ".epub":
            chapters = self._process_epub(input_file)
        else:
            raise ValueError(
                f"Unsupported book format: {ext}. Only .pdf and .epub are supported."
            )

        # 2. Processing & Formatting
        processed_docs = []
        for i, raw_content in enumerate(chapters):
            if not raw_content.strip():
                continue

            # Text Wrapping
            body_text = ""
            if wrap_text:
                wrapped_lines = []
                for line in raw_content.strip().splitlines():
                    if line.strip():
                        wrapped_lines.append(textwrap.fill(line, width=line_width))
                    else:
                        wrapped_lines.append("")
                body_text = "\n".join(wrapped_lines)
            else:
                body_text = raw_content.strip()

            # Prepend source context to the actual content string
            final_content = f"Source: {filename_only}\n\n{body_text}"

            doc_filename = f"{base_name}_ch{i+1:03}.txt"

            doc = {
                "filename": doc_filename,
                "content": final_content,
                "source": base_name,
                "chapter_index": i + 1,
                "file_path": input_file,
            }
            processed_docs.append(doc)

            # 3. Disk Persistence
            if save_to_disk:
                self._save_to_disk(output_dir, base_name, doc_filename, final_content)

        context.set(output_key, processed_docs)
        logger.info(f"Book Digest Complete. {len(processed_docs)} chapters extracted.")
        return context

    def _process_pdf(self, filepath: str, split_pattern: str) -> List[str]:
        try:
            import pymupdf4llm
        except ImportError:
            raise ImportError("Please install 'pymupdf4llm'")

        logger.info("Converting PDF to Markdown...")
        markdown_text = pymupdf4llm.to_markdown(filepath)

        logger.info(f"Splitting content using pattern: '{split_pattern}'")
        chapters = re.split(split_pattern, markdown_text, flags=re.MULTILINE)
        return chapters

    def _process_epub(self, filepath: str) -> List[str]:
        try:
            from ebooklib import epub
            from bs4 import BeautifulSoup
            import ebooklib
        except ImportError:
            raise ImportError("Please install 'ebooklib' and 'beautifulsoup4'")

        book = epub.read_epub(filepath)
        chapters = []

        logger.info("Parsing EPUB items...")
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), "html.parser")
                text = soup.get_text(separator="\n\n")

                if len(text.strip()) > 100:
                    chapters.append(text)

        return chapters

    def _save_to_disk(self, base_dir: str, book_name: str, filename: str, content: str):
        target_dir = os.path.join(base_dir, book_name)
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
