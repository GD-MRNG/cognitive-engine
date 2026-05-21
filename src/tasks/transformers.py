import os
import logging
import datetime
from typing import Dict, Any

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.core.llm import get_llm_client
from src.utils.io import CheckpointManager, FileManager

logger = logging.getLogger(__name__)


@register_task("LLMTransformTask")
class LLMTransformTask(PipelineTask):
    """
    Applies an LLM prompt to a single string input.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_key = config.get("input_key")
        output_key = config.get("output_key")
        prompt_file = config.get("prompt_file")
        model_name = config.get("model", "default")

        if not input_key or not output_key or not prompt_file:
            raise ValueError("LLMTransformTask config missing required keys.")

        # Load Data
        input_text = context.require(input_key)

        # Load Prompt
        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        with open(prompt_file, encoding="utf-8") as f:
            template = f.read()

        # Execute
        llm_client = get_llm_client(config)
        final_prompt = template.format(content=input_text)

        logger.info(f"Generating transformation for key '{input_key}'...")
        result = llm_client.query(final_prompt, model=model_name)

        # Add Metadata (No Source field for single transform)
        current_date = datetime.datetime.now().strftime("%d-%m-%Y")
        metadata_section = (
            f"## Metadata\n"
            f"- **Date:** {current_date}\n"
            f"- **Model:** {model_name}\n"
            f"- **Prompt:** {prompt_file}\n\n"
        )

        # Combine
        final_output = f"{metadata_section}## LLM Processed Content\n\n{result}"

        context.set(output_key, final_output)
        return context


@register_task("BatchLLMTask")
class BatchLLMTask(PipelineTask):
    """
    Iterates over a list of items in the Context, applies an LLM prompt,
    and optionally saves the result to disk immediately.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_key = config.get("input_key")
        output_key = config.get("output_key")
        prompt_file = config.get("prompt_file")
        save_intermediate = config.get("save_intermediate_files", False)
        output_dir = self.get_workspace_path(
            context, config.get("output_dir", "processed_files")
        )
        suffix = config.get("filename_suffix", "_processed")
        model_name = config.get("model", "default")
        include_original = config.get("include_original_content", True)

        if not input_key or not output_key or not prompt_file:
            raise ValueError(
                "BatchLLMTask requires 'input_key', 'output_key', and 'prompt_file'."
            )

        inputs = context.require(input_key)  # Expecting List[Dict] from DirectoryLoader

        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        with open(prompt_file, encoding="utf-8") as f:
            prompt_template = f.read()

        llm_client = get_llm_client(config)
        results = []

        logger.info(f"BatchLLMTask starting processing for {len(inputs)} items...")

        os.makedirs(output_dir, exist_ok=True)

        current_date = datetime.datetime.now().strftime("%d-%m-%Y")

        for item in inputs:
            original_source = item.get("source", "unknown_source")
            content = item.get("content", "")

            final_prompt = prompt_template.format(content=content)

            llm_output = llm_client.query(final_prompt, model=model_name)

            metadata_section = (
                f"## Metadata\n"
                f"- **Date:** {current_date}\n"
                f"- **Source:** {original_source}\n"
                f"- **Model:** {model_name}\n"
                f"- **Prompt:** {prompt_file}\n\n"
            )

            processed_content = (
                f"{metadata_section}## LLM Processed Content\n\n{llm_output}"
            )
            if include_original:
                processed_content += f"\n\n---\n\n## Original Content\n\n{content}"

            if save_intermediate:
                safe_base = "".join(
                    c for c in original_source if c.isalnum() or c in ("_", "-")
                ).strip()
                out_path = os.path.join(output_dir, f"{safe_base}{suffix}.md")
                FileManager.save_text(out_path, processed_content)

            results.append(processed_content)

        context.set(output_key, results)
        return context


class LLMEnrichmentTask(PipelineTask):
    """
    Base Class: Generic engine for LLM-based enrichment.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        target_key = config.get("target_key", "research_data")
        output_key = config.get("output_key", "enrichment_result")
        checkpoint_file = self.get_workspace_path(
            context, config.get("checkpoint_file", "research.json")
        )

        target_types = config.get("target_types", [])
        input_fields = config.get("input_fields", ["title", "content"])

        max_chars = config.get("max_chars", 3000)

        prompt_file = config.get("prompt_file")
        model_name = config.get("model", "default")

        try:
            llm_client = get_llm_client(config)
        except Exception as e:
            logger.error(f"Failed to initialize LLM Client: {e}")
            return context

        artifact = CheckpointManager.load(checkpoint_file)
        items = artifact.get(target_key, [])

        if not items:
            items = context.get(target_key, [])
            if not items:
                logger.warning(
                    f"{self.__class__.__name__}: No items found in '{target_key}'"
                )
                return context

        if not prompt_file or not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

        with open(prompt_file, encoding="utf-8") as f:
            prompt_template = f.read()

        updated = False
        logger.info(
            f"{self.__class__.__name__}: Processing {len(items)} items with model '{model_name}'."
        )

        limit_per_field = None
        if max_chars and isinstance(max_chars, int) and max_chars > 0:
            limit_per_field = int(max_chars / len(input_fields))

        for item in items:
            if target_types and item.get("type") not in target_types:
                continue

            if item.get(output_key):
                continue

            # Build Context
            combined_parts = []

            for field in input_fields:
                val = item.get(field, "") or ""

                if limit_per_field and len(val) > limit_per_field:
                    val = val[:limit_per_field] + "...(truncated)"

                if val:
                    # We add the field name as a label to preserve semantics
                    # e.g., "Title: Some Headline"
                    combined_parts.append(f"{field.capitalize()}: {val}")

            if not combined_parts:
                continue

            merged_context = "\n\n".join(combined_parts)

            final_prompt = prompt_template.format(content=merged_context)

            response = llm_client.query(final_prompt, model=model_name)

            cleaned_response = self._post_process_response(response)

            item[output_key] = cleaned_response
            updated = True

            artifact[target_key] = items
            CheckpointManager.save(checkpoint_file, artifact)

        if updated:
            context.set(target_key, items)

        return context

    def _post_process_response(self, response: str) -> str:
        """Hook for validation logic."""
        return response.strip()


@register_task("RegionCategorizationTask")
class RegionCategorizationTask(LLMEnrichmentTask):
    """
    Specific implementation for Region Categorization.
    """

    CATEGORIES = [
        "Global",
        "China",
        "East Asia",
        "Singapore",
        "Southeast Asia",
        "South Asia",
        "Central Asia",
        "Russia",
        "West Asia (Middle East)",
        "Africa",
        "Europe",
        "Latin America & Caribbean",
        "North America",
        "Oceania",
    ]

    CATEGORY_ALIASES = {
        "us": "North America",
        "usa": "North America",
        "united states": "North America",
        "america": "North America",
        "canada": "North America",
        "washington": "North America",
        "white house": "North America",
        "uk": "Europe",
        "britain": "Europe",
        "eu": "Europe",
        "european union": "Europe",
        "brussels": "Europe",
        "ukraine": "Europe",
        "germany": "Europe",
        "france": "Europe",
        "beijing": "China",
        "prc": "China",
        "middle east": "West Asia (Middle East)",
        "nz": "Oceania",
        "new zealand": "Oceania",
        "australia": "Oceania",
        "latin america": "Latin America & Caribbean",
        "caribbean": "Latin America & Caribbean",
        "south america": "Latin America & Caribbean",
        "the americas": "North America",
        "asia": "East Asia",
        "unknown": "Global",
        "global": "Global",
        "russia & former soviet union": "Russia",
    }

    def _post_process_response(self, text: str) -> str:
        cleaned = text.strip().strip('"').strip("'").split("\n")[0].strip()
        cleaned_lower = cleaned.lower()

        if cleaned_lower in self.CATEGORY_ALIASES:
            return self.CATEGORY_ALIASES[cleaned_lower]

        for cat in self.CATEGORIES:
            if cat.lower() == cleaned_lower:
                return cat

        logger.warning(
            f"RegionCategorizationTask: Invalid category '{cleaned}' returned."
        )
        # Default to 'Global' if unrecognized, as it's the most inclusive category
        return "Global"


@register_task("SummarizationTask")
class SummarizationTask(LLMEnrichmentTask):
    """
    Specific implementation for Content Summarization.
    """

    def _post_process_response(self, text: str) -> str:
        """
        Cleans the LLM output by removing blockquotes and meta-commentary.
        """
        if not text:
            return ""

        lines = text.splitlines()
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()

            # Filter out blockquotes (often used for 'thinking' or pre-amble)
            if stripped.startswith(">"):
                continue

            # Filter out italicized thinking markers (e.g. *Thinking...*)
            if stripped.lower().startswith("*thinking"):
                continue

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()
