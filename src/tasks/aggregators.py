import logging
from typing import Dict, Any

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.utils.io import FileManager

logger = logging.getLogger(__name__)


@register_task("TextAggregator")
class TextAggregator(PipelineTask):
    """
    Combines a list of text strings from the context into a single string.
    Useful for merging multiple summaries before a final 'master' summary.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_key = config.get("input_key")
        output_key = config.get("output_key")
        separator = config.get("separator", "\n\n---\n\n")

        save_filename = config.get("save_to_file")

        if not input_key or not output_key:
            raise ValueError("TextAggregator requires 'input_key' and 'output_key'.")

        data_list = context.require(input_key)

        if not isinstance(data_list, list):
            raise TypeError(
                f"Input data at '{input_key}' must be a list, got {type(data_list)}"
            )

        logger.info(f"Aggregating {len(data_list)} items...")

        combined_text = separator.join([str(item) for item in data_list])

        context.set(output_key, combined_text)

        if save_filename:
            out_path = self.get_workspace_path(context, save_filename)
            FileManager.save_text(out_path, combined_text)

        return context


@register_task("CitationCompilerTask")
class CitationCompilerTask(PipelineTask):
    """
    Compiles a bibliography section by iterating through document metadata.
    Only displays fields that actually contain data.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        docs = context.require(config.get("input_key"))
        lines = ["## Sources Referenced\n"]

        for i, doc in enumerate(docs):
            url = doc.get("url", "").strip()
            title = doc.get("title", "").strip()
            source = doc.get("source", "").strip()
            date = doc.get("date", "").strip()

            source_info = []

            if title:
                source_info.append(f"**Title:** {title}")

            # Prevent printing the URL twice if 'source' defaulted to the URL earlier
            if source and source != url:
                source_info.append(f"**Source:** {source}")

            if date:
                source_info.append(f"**Date:** {date}")

            if url:
                source_info.append(f"**URL:** {url}")

            # Join whatever parts we collected with a separator
            entry = f"{i+1}. " + " ".join(source_info)
            lines.append(entry)

        context.set(config.get("output_key"), "\n".join(lines))
        return context
