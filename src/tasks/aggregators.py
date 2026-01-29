import logging
import os
from typing import Dict, Any

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task

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
        save_path = config.get(
            "save_to_file"
        )  # Optional: Save the combined text immediately

        if not input_key or not output_key:
            raise ValueError("TextAggregator requires 'input_key' and 'output_key'.")

        # Get the list of strings (produced by BatchLLMTask)
        data_list = context.require(input_key)

        if not isinstance(data_list, list):
            raise TypeError(
                f"Input data at '{input_key}' must be a list, got {type(data_list)}"
            )

        logger.info(f"Aggregating {len(data_list)} items...")

        # Join them
        combined_text = separator.join([str(item) for item in data_list])

        # Save to context
        context.set(output_key, combined_text)

        # Optional: Save to disk (handles the "combined.md" requirement)
        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(combined_text)
            logger.info(f"Saved combined text to {save_path}")

        return context


@register_task("CitationCompilerTask")
class CitationCompilerTask(PipelineTask):
    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        docs = context.require(config.get("input_key"))
        lines = ["## Sources"]

        for i, doc in enumerate(docs):
            title = doc.get("title", "Unknown Title")
            source = doc.get("source", "Unknown Source")
            date = doc.get("date", "Unknown Date")
            url = doc.get("url", "#")

            # Format: 1. [Title](Link), Source, Date
            lines.append(f"{i+1}. [{title}]({url}), {source}, {date}")

        context.set(config.get("output_key"), "\n".join(lines))
        return context
