import os
import logging
import datetime
from typing import Dict, Any

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.core.llm import get_llm_client
from src.utils.io import CheckpointManager

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
        # 1. Configuration Extraction
        input_key = config.get("input_key")  # Key containing list of file dicts
        output_key = config.get("output_key")  # Key to store results list
        prompt_file = config.get("prompt_file")  # Path to .txt template
        save_intermediate = config.get("save_intermediate_files", False)
        output_dir = config.get("output_dir", "./outputs")
        suffix = config.get("filename_suffix", "_processed")
        model_name = config.get("model", "default")
        include_original = config.get("include_original_content", True)

        # 2. Validation
        if not input_key or not output_key or not prompt_file:
            raise ValueError(
                "BatchLLMTask requires 'input_key', 'output_key', and 'prompt_file'."
            )

        # 3. Load Resources
        inputs = context.require(input_key)  # Expecting List[Dict] from DirectoryLoader

        # Read the prompt template
        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        with open(prompt_file, encoding="utf-8") as f:
            prompt_template = f.read()

        # Initialize LLM
        llm_client = get_llm_client(config)
        results = []

        # 4. Processing Loop
        logger.info(f"BatchLLMTask starting processing for {len(inputs)} items...")

        os.makedirs(output_dir, exist_ok=True)

        current_date = datetime.datetime.now().strftime("%d-%m-%Y")

        for item in inputs:
            original_filename = item.get("filename", "unknown")
            content = item.get("content", "")

            logger.info(f"Processing item: {original_filename}")

            # A. Prepare Prompt
            # We assume the template uses {content} as the placeholder
            final_prompt = prompt_template.format(content=content)

            # B. Call LLM
            try:
                llm_output = llm_client.query(final_prompt, model=model_name)
            except Exception as e:
                logger.error(f"LLM failure for {original_filename}: {e}")
                llm_output = f"[Error processing {original_filename}]"

            # C. Combine for Output
            metadata_section = (
                f"## Metadata\n"
                f"- **Date:** {current_date}\n"
                f"- **Source:** {original_filename}\n"
                f"- **Model:** {model_name}\n"
                f"- **Prompt:** {prompt_file}\n\n"
            )

            if include_original:
                processed_content = f"{metadata_section}## LLM Processed Content\n\n{llm_output}\n\n---\n\n## Original Content\n\n{content}"
            else:
                processed_content = (
                    f"{metadata_section}## LLM Processed Content\n\n{llm_output}"
                )

            # D. Save Intermediate File (optional)
            if save_intermediate:
                base_name = os.path.splitext(original_filename)[0]
                out_filename = f"{base_name}{suffix}.md"
                out_path = os.path.join(output_dir, out_filename)

                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(processed_content)
                logger.info(f"Saved intermediate file: {out_path}")

            # E. Store result in memory
            results.append(processed_content)

        # 5. Update Context
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
        checkpoint_file = config.get("checkpoint_file", "outputs/research.json")

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

            try:
                final_prompt = prompt_template.format(content=merged_context)

                response = llm_client.query(final_prompt, model=model_name)

                cleaned_response = self._post_process_response(response)

                item[output_key] = cleaned_response
                updated = True

                artifact[target_key] = items
                CheckpointManager.save(checkpoint_file, artifact)

            except Exception as e:
                logger.error(f"LLM Enrichment failed for {item.get('url')}: {e}")

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
        "Unknown",
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
            f"RegionCategorizationTask: Invalid category '{cleaned}'. Defaulting to 'Unknown'."
        )
        return "Unknown"


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
