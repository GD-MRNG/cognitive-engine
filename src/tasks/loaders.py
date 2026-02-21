import glob
import os
import logging
import pandas as pd
from typing import Dict, Any

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.utils.document import TextExtractor

logger = logging.getLogger(__name__)


@register_task("UrlListLoader")
class UrlListLoader(PipelineTask):
    """
    Reads a text file containing one target per line.
    Supports optional metadata separated by commas: url,title,source,date
    Ignores empty lines and lines starting with '#'.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_file = config.get("input_file")
        output_key = config.get("output_key", "raw_targets")

        if not input_file or not os.path.exists(input_file):
            raise FileNotFoundError(f"URL list not found: {input_file}")

        items = []
        with open(input_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Split by comma and clean whitespace for each part
                parts = [p.strip() for p in line.split(",")]

                url = parts[0]
                title = parts[1] if len(parts) > 1 and parts[1] else ""
                source = parts[2] if len(parts) > 2 and parts[2] else ""
                date = parts[3] if len(parts) > 3 and parts[3] else ""

                # Convert local relative paths to absolute paths for the extractors
                if not url.startswith("http") and not os.path.isabs(url):
                    url = os.path.abspath(url)

                # ==========================================
                # THE STANDARDIZED DATA CONTRACT
                # ==========================================
                # Downstream tasks (like BatchLLMTask) rely heavily on the "source"
                # key being populated to generate file names and metadata blocks.
                # If the user only provided a URL in the text file, we map the URL
                # to the "source" key to ensure the pipeline doesn't crash or output
                # unnamed files, maintaining pipeline stability.
                if not source:
                    source = url

                items.append(
                    {"url": url, "title": title, "source": source, "date": date}
                )

        logger.info(f"UrlListLoader: Found {len(items)} targets.")
        context.set(output_key, items)
        return context


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
                content = TextExtractor.extract(filepath)
                filename = os.path.basename(filepath)
                loaded_data.append(
                    {
                        "filename": filename,
                        "filepath": filepath,
                        "source": filename,
                        "content": content,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to read file {filepath}: {e}")

        context.set(output_key, loaded_data)
        logger.info(f"Loaded {len(loaded_data)} files into context key '{output_key}'.")

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
