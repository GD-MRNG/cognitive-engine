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
    Reads a CSV, filters by tag/rank, and sorts by Type Priority + Rank.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        file_path = config.get("input_file")
        filter_tag = config.get("filter_tag")

        # Ranking Config
        top_priority = config.get("top_priority_value", 1)
        rank_cutoff = config.get("rank_cutoff", 5)

        # Source Priority
        type_order = config.get("type_priority", ["datapoint", "analysis"])

        output_key = config.get("output_key", "source_registry")

        # 1. Validation
        if not file_path:
            raise ValueError("SourceCSVLoader: 'input_file' config is missing.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"SourceCSVLoader: File not found at {file_path}")

        # 2. Load
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            raise RuntimeError(f"Failed to parse CSV: {e}")

        # 3. Pre-processing
        # Ensure tags are a list, handling NaNs
        df["tags"] = (
            df["tags"]
            .fillna("")
            .astype(str)
            .apply(lambda x: [t.strip() for t in x.split(",") if t.strip()])
        )

        # Ensure rank is numeric, default to cutoff (lowest priority) if missing
        df["rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(rank_cutoff)

        # 4. Filtering
        # Rank Logic: Supports 1->5 (Ascending) or 5->1 (Descending)
        if top_priority < rank_cutoff:
            mask = (df["rank"] >= top_priority) & (df["rank"] <= rank_cutoff)
            ascending_rank = True
        else:
            mask = (df["rank"] <= top_priority) & (df["rank"] >= rank_cutoff)
            ascending_rank = False

        if filter_tag:
            # Check if filter_tag exists in the list column
            mask &= df["tags"].apply(lambda tags: filter_tag in tags)

        df = df[mask].copy()

        if df.empty:
            logger.warning(
                f"SourceCSVLoader: Filters resulted in 0 items. (Tag: {filter_tag})"
            )
            context.set(output_key, [])
            return context

        # 5. Sorting (Non-Destructive)
        # We create a temporary categorical column just for sorting index
        # Any type NOT in type_order gets a code of -1 (or similar) and drops to bottom
        df["_sort_type"] = pd.Categorical(
            df["type"], categories=type_order, ordered=True
        )

        # Sort by Type (custom order) -> Rank
        df = df.sort_values(by=["_sort_type", "rank"], ascending=[True, ascending_rank])

        # Cleanup helper column
        df.drop(columns=["_sort_type"], inplace=True)

        # 6. Finalize
        sources = df.to_dict("records")
        context.set(output_key, sources)

        logger.info(f"Registry Loaded: {len(sources)} sources from {file_path}")

        return context
