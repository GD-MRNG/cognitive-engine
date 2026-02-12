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
    Loads a sources.csv into the Context.
    Schema: id, name, url, type, rank, tags, format
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        file_path = config.get("input_file")
        output_key = config.get("output_key", "raw_sources")

        # Filtering Options
        filter_tag = config.get("filter_tag")
        filter_type = config.get("filter_type")  # e.g. "datapoint" or "analysis"

        # validation
        if not file_path:
            raise ValueError("SourceCSVLoader: 'input_file' config is missing.")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"SourceCSVLoader: File not found at {file_path}")

        try:
            df = pd.read_csv(file_path)
            logger.info(f"Loaded CSV with columns: {list(df.columns)}")
        except Exception as e:
            raise RuntimeError(f"Failed to parse CSV: {e}")

        # 1. Normalize Legacy Columns
        # Ensure tags are a list, handling NaNs
        if "tags" in df.columns:
            df["tags"] = (
                df["tags"]
                .fillna("")
                .astype(str)
                .apply(lambda x: [t.strip() for t in x.split(",") if t.strip()])
            )
        else:
            df["tags"] = [[] for _ in range(len(df))]

        # Ensure rank is numeric, default to 999 (lowest priority)
        if "rank" in df.columns:
            df["rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(999)
        else:
            df["rank"] = 999

        # Ensure other critical fields exist
        required_fields = ["id", "name", "url", "type", "format"]
        for field in required_fields:
            if field not in df.columns:
                df[field] = ""  # Fill missing schema fields with empty string

        # 2. Filtering
        if filter_tag:
            # Check if filter_tag exists in the list column
            df = df[df["tags"].apply(lambda tags: filter_tag in tags)]

        if filter_type:
            df = df[df["type"].astype(str).str.lower() == filter_type.lower()]

        if df.empty:
            logger.warning("SourceCSVLoader: Filters resulted in 0 items.")
            context.set(output_key, [])
            return context

        # 3. Sorting (Rank Ascending = 1 is highest priority)
        df = df.sort_values(by=["rank"], ascending=True)

        # 4. Finalize
        sources = df.to_dict("records")
        context.set(output_key, sources)

        logger.info(f"Loaded {len(sources)} sources into key '{output_key}'")
        return context
