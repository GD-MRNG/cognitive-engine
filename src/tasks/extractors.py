import os
import json
from datetime import datetime
import logging
from typing import Dict, Any
from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.utils.web import ContentExtractor
from src.utils.youtube import YouTubeHandler

logger = logging.getLogger(__name__)


@register_task("ContentExtractionTask")
class ContentExtractionTask(PipelineTask):
    """
    Iterates through a list of CSV items (dict).
    Uses 'url' for extraction. Preserves 'title', 'source', 'date'.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_key = config.get("input_key")
        output_key = config.get("output_key")
        failure_key = config.get("failure_key", "failed_items")

        items = context.require(input_key)

        # Initialize the robust extractor
        extractor = ContentExtractor(headless=True)

        success_docs = []
        failed_items = []

        logger.info(f"Starting extraction for {len(items)} items...")

        try:
            for i, item in enumerate(items):
                url = item["url"]
                logger.info(f"[{i+1}/{len(items)}] Processing: {url}")

                try:
                    # Robust Extract
                    raw_text = extractor.extract(url)

                    # Attach CSV Metadata to the Document Object
                    doc = {
                        "filename": f"{item['source']}_{i}.txt",  # Unique ID
                        "content": raw_text,
                        "url": url,
                        "title": item["title"],
                        "source": item["source"],
                        "date": item["date"],
                        "source_type": "text_queue_automated",
                    }
                    success_docs.append(doc)

                except Exception as e:
                    logger.warning(f"Failed to extract {url}: {e}")
                    failed_items.append(item)
        finally:
            extractor.close()

        context.set(output_key, success_docs)
        context.set(failure_key, failed_items)
        return context


@register_task("ManualReviewTask")
class ManualReviewTask(PipelineTask):
    """
    Fallback task for failed items. Pops a browser and asks user to paste content.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_failure_key = config.get("input_failure_key")
        output_success_key = config.get("output_success_key")
        interactive = config.get("interactive", False)

        failed_items = context.get(input_failure_key, [])
        success_docs = context.get(output_success_key, [])

        if not failed_items or not interactive:
            return context

        logger.info(
            f"!!! MANUAL INTERVENTION REQUIRED FOR {len(failed_items)} ITEMS !!!"
        )
        extractor = ContentExtractor(headless=False)  # Visible Browser

        try:
            for item in failed_items:
                url = item["url"]
                print(f"\n{'='*60}\nOPENING: {url}\nTITLE: {item['title']}\n{'='*60}")

                try:
                    if url.startswith("http"):
                        extractor.open_page_for_user(url)
                except Exception:
                    pass

                print(">> Paste Content below (Ctrl+Z/D to finish):")
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass
                content = "\n".join(lines)

                if content.strip():
                    success_docs.append(
                        {
                            "filename": f"manual_{item['source']}.txt",
                            "content": content,
                            "url": url,
                            "title": item["title"],
                            "source": item["source"],
                            "date": item["date"],
                        }
                    )
        finally:
            extractor.close()

        context.set(output_success_key, success_docs)
        return context


@register_task("BreadthGatheringTask")
class BreadthGatheringTask(PipelineTask):
    """
    Automated Breadth Scan.
    Iterates through 'datapoint' sources.
    - If format='youtube': Fetches recent video titles (Headlines).
    - If format='webpage': Scrapes full page content.

    Updates the 'Golden Artifact' (research.json) under a specific top-level key
    (e.g., 'breadth_scan'), preserving existing data.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_key = config.get("input_key", "raw_sources")
        output_key = config.get("output_key", "breadth_scan")
        checkpoint_file = config.get("checkpoint_file", "outputs/research.json")

        # 1. Load Sources from Context
        all_sources = context.get(input_key, [])
        datapoint_sources = [s for s in all_sources if s.get("type") == "datapoint"]

        if not datapoint_sources:
            logger.warning(
                "BreadthGatheringTask: No sources with type='datapoint' found."
            )
            # Initialize empty list in context to prevent downstream errors
            context.set(output_key, [])
            return context

        logger.info(
            f"BreadthGatheringTask: Processing {len(datapoint_sources)} datapoint sources."
        )

        # 2. Load Checkpoint State
        artifact_state = self._load_checkpoint_dict(checkpoint_file)

        # Get the specific list we are working on (e.g., 'breadth_scan')
        current_list = artifact_state.get(output_key, [])

        # Map URL to existing item for quick lookup
        existing_urls = {
            item.get("url"): item for item in current_list if item.get("url")
        }

        # Rebuild the list in source order
        final_data_list = []

        # Initialize Handlers
        extractor = ContentExtractor(headless=True)
        yt_handler = YouTubeHandler()

        try:
            for i, source in enumerate(datapoint_sources):
                url = source.get("url")
                name = source.get("name")
                fmt = source.get("format", "webpage")

                # Resume Logic: Skip if already processed
                if url in existing_urls:
                    logger.info(
                        f"[{i+1}/{len(datapoint_sources)}] Skipping (Already Scanned): {name}"
                    )
                    final_data_list.append(existing_urls[url])
                    continue

                logger.info(
                    f"[{i+1}/{len(datapoint_sources)}] Processing: {name} ({fmt})"
                )

                try:
                    content_result = ""

                    if fmt == "youtube":
                        # For Breadth Scan, we want "Headlines" (Recent Titles), not transcripts
                        titles = yt_handler.get_recent_titles(url, days=7)
                        if titles:
                            content_result = "\n".join(
                                titles
                            )  # Store as newline-separated string
                        else:
                            content_result = "No recent videos found."

                    else:
                        # Default to Web Extraction
                        content_result = extractor.extract(url)

                    # Structure the Item
                    item = {
                        "id": source.get("id"),
                        "source": name,
                        "url": url,
                        "type": "datapoint",
                        "format": fmt,
                        "content": content_result,
                        "scraped_at": datetime.now().isoformat(),
                        "tags": source.get("tags", []),
                        "enrichment": {},
                    }

                    final_data_list.append(item)

                    # Update the specific key in the master state
                    artifact_state[output_key] = final_data_list
                    # Write the FULL artifact back to disk
                    self._save_checkpoint_dict(artifact_state, checkpoint_file)

                except Exception as e:
                    logger.error(f"Failed to process source {name}: {e}")
                    continue

        finally:
            extractor.close()

        # Final Context Update
        context.set(output_key, final_data_list)
        logger.info(
            f"Breadth Scan Complete. Saved to '{output_key}' in {checkpoint_file}"
        )

        return context

    def _load_checkpoint_dict(self, filepath: str) -> Dict[str, Any]:
        """Safely loads the FULL JSON artifact."""
        if os.path.exists(filepath):
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                return {}
        return {}

    def _save_checkpoint_dict(self, data: Dict[str, Any], filepath: str) -> None:
        """Atomic write of the full artifact."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
