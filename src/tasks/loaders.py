import glob
import csv
import os
import logging
import pandas as pd
from typing import Dict, Any

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task

logger = logging.getLogger(__name__)


@register_task("DirectoryLoader")
class DirectoryLoader(PipelineTask):
    """
    Loads raw text files from a directory into the Context.
    Output in Context: A list of dictionaries [{'filename': '...', 'content': '...'}, ...]
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_pattern = config.get("input_path")  # e.g., "./inputs/*.txt"
        output_key = config.get("output_key", "raw_files")

        if not input_pattern:
            raise ValueError("DirectoryLoader requires 'input_path' in config.")

        files = glob.glob(input_pattern)
        logger.info(
            f"DirectoryLoader found {len(files)} files matching '{input_pattern}'"
        )

        loaded_data = []
        for filepath in files:
            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()

                filename = os.path.basename(filepath)
                loaded_data.append(
                    {"filename": filename, "filepath": filepath, "content": content}
                )
            except Exception as e:
                logger.error(f"Failed to read file {filepath}: {e}")

        # Store the list in the context
        context.set(output_key, loaded_data)
        logger.info(f"Loaded {len(loaded_data)} files into context key '{output_key}'.")

        return context


@register_task("ResearchCSVLoader")
class ResearchCSVLoader(PipelineTask):
    """
    Parses a CSV file with columns: url, title, source, date.
    Splits items into 'text_queue' (Web/YouTube/Txt) and 'audio_queue' (Mp3/M4a).
    """

    REQUIRED_COLUMNS = ["url", "title", "source", "date"]

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_file = config.get("input_file")
        output_text_key = config.get("output_text_key", "text_queue")
        output_audio_key = config.get("output_audio_key", "audio_queue")

        if not os.path.exists(input_file):
            raise FileNotFoundError(f"CSV file not found: {input_file}")

        text_items = []
        audio_items = []

        with open(input_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Validation
            if not reader.fieldnames or not set(self.REQUIRED_COLUMNS).issubset(
                set(reader.fieldnames)
            ):
                raise ValueError(
                    f"CSV missing required columns: {self.REQUIRED_COLUMNS}"
                )

            for row in reader:
                item = {k: v.strip() for k, v in row.items()}
                url = item["url"].lower()

                # Fix relative paths for local files
                if not url.startswith("http") and not os.path.isabs(item["url"]):
                    # Assuming paths are relative to the CSV location or CWD
                    # For safety, let's assume they are relative to CWD
                    item["url"] = os.path.abspath(item["url"])

                # Classification
                if url.endswith((".mp3", ".m4a", ".wav", ".flac")):
                    audio_items.append(item)
                else:
                    text_items.append(item)

        context.set(output_text_key, text_items)
        context.set(output_audio_key, audio_items)
        logger.info(
            f"Loaded {len(text_items)} text items and {len(audio_items)} audio items."
        )
        return context


@register_task("SourceCSVLoader")
class SourceCSVLoader(PipelineTask):
    """
    Standardized Source Loader.
    """

    def execute(self, context: WorkflowContext, config: Dict[str, Any]) -> None:
        file_path = config.get("input_file")
        filter_tag = config.get("filter_tag")

        # Ranking Logic Config
        top_priority = config.get("top_priority_value", 1)
        rank_cutoff = config.get("rank_cutoff", 5)

        # Source Type Priority
        type_order = config.get("type_priority", ["datapoint", "analysis"])

        output_key = config.get("output_key", "source_registry")

        if not file_path:
            raise ValueError("SourceRegistryLoader: 'input_file' is missing.")

        df = pd.read_csv(file_path)

        # Pre-processing & Normalization
        df["tags"] = (
            df["tags"].fillna("").apply(lambda x: [t.strip() for t in x.split(",")])
        )
        df["rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(rank_cutoff)

        # Filtering
        if top_priority < rank_cutoff:
            mask = (df["rank"] >= top_priority) & (df["rank"] <= rank_cutoff)
        else:
            mask = (df["rank"] <= top_priority) & (df["rank"] >= rank_cutoff)

        if filter_tag:
            mask &= df["tags"].apply(lambda x: filter_tag in x)

        df = df[mask].copy()

        # First: Sort by 'type' based on the type_order list
        df["type"] = pd.Categorical(df["type"], categories=type_order, ordered=True)

        # Second: Sort by 'rank' (1 is usually processed before 5)
        ascending_rank = top_priority < rank_cutoff

        df = df.sort_values(by=["type", "rank"], ascending=[True, ascending_rank])

        # Final Context Update
        sources = df.to_dict("records")
        context.set(output_key, sources)

        logger.info(
            f"Registry Loaded: {len(sources)} sources prioritized by {type_order}"
        )
