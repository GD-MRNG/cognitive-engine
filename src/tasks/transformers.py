import os
import glob
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
        pass_previous_output = config.get("pass_previous_output", False)

        if not input_key or not output_key or not prompt_file:
            raise ValueError(
                "BatchLLMTask requires 'input_key', 'output_key', and 'prompt_file'."
            )

        inputs = context.require(input_key)  # Expecting List[Dict] from DirectoryLoader

        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        with open(prompt_file, encoding="utf-8") as f:
            prompt_template = f.read()

        initial_context_file = config.get("initial_context_file")

        llm_client = get_llm_client(config)
        results = []

        logger.info(f"BatchLLMTask starting processing for {len(inputs)} items...")

        os.makedirs(output_dir, exist_ok=True)

        current_date = datetime.datetime.now().strftime("%d-%m-%Y")
        previous_output = ""
        if initial_context_file:
            if not os.path.exists(initial_context_file):
                raise FileNotFoundError(f"initial_context_file not found: {initial_context_file}")
            with open(initial_context_file, encoding="utf-8") as f:
                previous_output = f.read()

        for item in inputs:
            original_source = item.get("source", "unknown_source")
            content = item.get("content", "")

            if pass_previous_output:
                final_prompt = prompt_template.format(content=content, previous_output=previous_output)
            else:
                final_prompt = prompt_template.format(content=content)

            llm_output = llm_client.query(final_prompt, model=model_name)

            if pass_previous_output:
                previous_output = llm_output

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
                # Remove file extension from original_source
                source_without_ext = os.path.splitext(original_source)[0]
                safe_base = "".join(
                    c for c in source_without_ext if c.isalnum() or c in ("_", "-")
                ).strip()
                out_path = os.path.join(output_dir, f"{safe_base}{suffix}.md")
                FileManager.save_text(out_path, processed_content)

            results.append(processed_content)

        context.set(output_key, results)
        return context


@register_task("FileAnnotationTask")
class FileAnnotationTask(PipelineTask):
    """
    Reads existing files from disk, runs an LLM on their content,
    and modifies each file in-place by prepending or appending the LLM output.

    Primary input: context items from UrlListLoader (url field = file path).
    Also accepts file_paths list or input_dir + file_glob for direct config use.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_key = config.get("input_key")
        file_paths = config.get("file_paths", [])
        input_dir = config.get("input_dir")
        file_glob = config.get("file_glob", "*.md")
        output_key = config.get("output_key")
        prompt_file = config.get("prompt_file")
        model_name = config.get("model", "default")
        mode = config.get("mode", "prepend")
        annotation_title = config.get("annotation_title", "Annotation")

        if not prompt_file:
            raise ValueError("FileAnnotationTask requires 'prompt_file'.")
        if mode not in ("prepend", "append"):
            raise ValueError(
                f"FileAnnotationTask: 'mode' must be 'prepend' or 'append', got '{mode}'."
            )
        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

        with open(prompt_file, encoding="utf-8") as f:
            prompt_template = f.read()

        files = self._collect_files(context, input_key, file_paths, input_dir, file_glob)

        if not files:
            logger.warning("FileAnnotationTask: No files found to process.")
            if output_key:
                context.set(output_key, [])
            return context

        llm_client = get_llm_client(config)
        annotated_paths = []
        logger.info(f"FileAnnotationTask: Processing {len(files)} files (mode='{mode}')...")

        for filepath in files:
            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()
                llm_output = llm_client.query(
                    prompt_template.format(content=content), model=model_name
                )
                self._modify_file(filepath, llm_output, mode, annotation_title)
                annotated_paths.append(filepath)
                logger.info(f"  Annotated: {os.path.basename(filepath)}")
            except Exception as e:
                logger.error(f"FileAnnotationTask: Failed to process '{filepath}': {e}")

        if output_key:
            context.set(output_key, annotated_paths)

        logger.info(
            f"FileAnnotationTask: Done. {len(annotated_paths)}/{len(files)} files annotated."
        )
        return context

    def _collect_files(self, context, input_key, file_paths, input_dir, file_glob):
        paths = []

        if input_key:
            for item in context.get(input_key, []):
                # UrlListLoader resolves local paths to absolute in 'url'
                fp = item.get("url") or item.get("filepath") or item.get("file_path", "")
                if fp and os.path.isfile(fp):
                    paths.append(fp)

        for fp in file_paths:
            resolved = self.get_workspace_path(context, fp)
            if os.path.isfile(resolved):
                paths.append(resolved)

        if input_dir:
            resolved_dir = self.get_workspace_path(context, input_dir)
            for fp in glob.glob(os.path.join(resolved_dir, file_glob)):
                paths.append(fp)

        seen, result = set(), []
        for fp in paths:
            if fp not in seen:
                seen.add(fp)
                result.append(fp)
        return result

    def _make_dropdown(self, title: str, body: str) -> str:
        return f"<details>\n<summary>{title}</summary>\n\n{body.strip()}\n\n</details>"

    def _modify_file(self, filepath: str, llm_output: str, mode: str, title: str) -> None:
        with open(filepath, encoding="utf-8") as f:
            existing = f.read()

        dropdown = self._make_dropdown(title, llm_output)

        if mode == "prepend":
            new_content = f"{dropdown}\n\n{existing}"
        else:  # append
            new_content = f"{existing}\n\n{dropdown}"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)


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
        force_refresh = config.get("force_refresh", False)

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

            if not force_refresh and item.get(output_key):
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
