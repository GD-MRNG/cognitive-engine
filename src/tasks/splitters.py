import logging
import re
import os
from typing import Dict, Any
import textwrap

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.utils.io import FileManager
from src.utils.document import TextExtractor, PDFExtractor, EpubExtractor

logger = logging.getLogger(__name__)


@register_task("TextFileSplitterTask")
class TextFileSplitterTask(PipelineTask):
    """
    Reads a single large text file, splits it by a delimiter,
    and populates the context with a list of documents.
    """

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
        delimiter = config.get("delimiter_pattern", r"^%%%\s+(.+)$")

        if not input_file or not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        logger.info(f"Splitting file: {input_file}")
        sections = TextExtractor.extract_and_split(input_file, delimiter)

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
                    "filepath": f"virtual/{safe_filename}",  # Virtual path since it exists in memory
                    "source": safe_filename,
                    "content": text,
                }
            )

            if save_to_disk:
                out_path = os.path.join(output_dir, safe_filename)
                FileManager.save_text(out_path, text)

        context.set(output_key, doc_list)
        logger.info(
            f"Splitter produced {len(doc_list)} documents into key '{output_key}'."
        )

        return context

    def _sanitize_filename(self, name: str) -> str:
        return "".join(c for c in name if c.isalnum() or c in ("_", "-", " "))


@register_task("BookDigestTask")
class BookDigestTask(PipelineTask):
    """
    Ingests binary book formats (PDF, EPUB), intelligently splits them into chapters,
    and converts them to clean text.
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
        split_chapters = config.get("split_chapters", True)

        wrap_text = config.get("wrap_text", True)
        line_width = config.get("line_width", 80)

        if not input_file or not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        filename_only = os.path.basename(input_file)
        base_name = os.path.splitext(filename_only)[0]
        ext = os.path.splitext(input_file)[1].lower()

        logger.info(f"Digesting book: {filename_only}")

        chapters = []

        if ext == ".pdf":
            chapters = PDFExtractor.extract(input_file, split_chapters, split_pattern)
        elif ext == ".epub":
            chapters = EpubExtractor.extract(input_file, split_chapters)
        else:
            raise ValueError(f"Unsupported format: {ext}")

        processed_docs = []
        for i, raw_content in enumerate(chapters):
            if not raw_content.strip():
                continue

            body_text = raw_content.strip()
            if wrap_text:
                wrapped_lines = [
                    textwrap.fill(line, width=line_width) if line.strip() else ""
                    for line in body_text.splitlines()
                ]
                body_text = "\n".join(wrapped_lines)

            final_content = f"Source: {filename_only}\n\n{body_text}"
            doc_filename = f"{base_name}_ch{i+1:03}.txt"

            if save_to_disk:
                out_path = os.path.join(output_dir, base_name, doc_filename)
                FileManager.save_text(out_path, final_content)

        context.set(output_key, processed_docs)
        logger.info("Book Digest Complete.")
        return context
