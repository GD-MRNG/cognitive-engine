import logging
import os
from typing import Dict, Any
import json
from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task

logger = logging.getLogger(__name__)


@register_task("ReportWriterTask")
class ReportWriterTask(PipelineTask):
    """
    Compiles a final Markdown report from multiple context variables.
    Config 'sections' is a list of dicts: {'title': '...', 'content_key': '...'}
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        filename = self.get_workspace_path(context, config.get("filename", "report.md"))
        sections = config.get("sections", [])

        if not filename:
            raise ValueError("ReportWriterTask requires a 'filename'.")

        report_content = []

        for section in sections:
            title = section.get("title")
            key = section.get("content_key")

            content = context.get(key, f"_[Missing content for key: {key}]_")

            if title:
                report_content.append(f"## {title}")

            report_content.append(str(content))
            report_content.append("\n---\n")

        # Write to disk
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n\n".join(report_content))

        logger.info(f"Final Report saved to {filename}")
        return context


@register_task("ArtifactCheckpointTask")
class ArtifactCheckpointTask(PipelineTask):
    """
    Dumps specific context keys to a JSON file on disk.
    Used to persist the 'Golden Artifact' (research.json).
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        keys_to_save = config.get("input_keys", [])  # List of context keys
        output_file = self.get_workspace_path(
            context, config.get("output_file", "research.json")
        )

        if not keys_to_save:
            logger.warning(
                "ArtifactCheckpointTask: No 'input_keys' specified. Saving empty artifact."
            )
            artifact_data = {}
        else:
            artifact_data = {}
            for key in keys_to_save:
                data = context.get(key)
                if data is not None:
                    artifact_data[key] = data
                else:
                    logger.warning(
                        f"ArtifactCheckpointTask: Key '{key}' not found in context."
                    )

        # Ensure directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(artifact_data, f, indent=2, default=str, ensure_ascii=False)
            logger.info(f"Golden Artifact saved to: {output_file}")
        except Exception as e:
            logger.error(f"Failed to save artifact to {output_file}: {e}")
            raise

        return context
