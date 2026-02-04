import logging
from typing import Dict, Any
from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.utils.web import ContentExtractor
from src.utils.youtube import YouTubeHandler

import os
import json
from datetime import datetime


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


@register_task("BreadthScanExtractionTask")
class BreadthScanExtractionTask(PipelineTask):
    """
    Standardized Breadth-First Content Extractor.
    """

    def execute(self, context: WorkflowContext, config: Dict[str, Any]) -> None:
        sources = context.get(config.get("input_key", "source_registry"), [])
        # Filter for datapoints (Breadth)
        datapoints = [s for s in sources if s.get("type") == "datapoint"]

        checkpoint_path = config.get(
            "checkpoint_json", "checkpoints/breadth_state.json"
        )
        report_path = config.get("report_md", "outputs/breadth_report.md")

        os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)

        # Resilience: Load existing state to support restarts
        data_state = self._load_checkpoint(checkpoint_path)
        logger.info(
            f"BreadthScout: Processing {len(datapoints)} sources. {len(data_state)} already completed."
        )

        for source in datapoints:
            s_id = source["id"]
            if s_id in data_state:
                continue

            logger.info(f"Scanning Breadth: {source['name']} ({source['url']})")

            # Polymorphic Fetching
            raw_data = ""
            if source.get("format") == "youtube":
                handler = YouTubeHandler()
                titles = handler.get_recent_titles(channel_url=source["url"], days=7)
                raw_data = "\n".join(titles) if titles else "No recent videos found."
            else:
                extractor = ContentExtractor(headless=True)
                try:
                    raw_data = extractor.extract(source["url"])
                except Exception as e:
                    logger.error(f"Web extraction failed for {source['name']}: {e}")
                    raw_data = "Web extraction failed.\n"

            if raw_data:
                # Wrap in Source Tags for LLM Context clarity
                tagged_content = (
                    f"<source id='{s_id}' name='{source['name']}' url='{source['url']}'>\n"
                    f"{raw_data}\n"
                    f"</source>"
                )

                # Incremental Persistence
                data_state[s_id] = {
                    "metadata": source,
                    "content": tagged_content,
                    "timestamp": datetime.now().isoformat(),
                }
                self._save_checkpoint(data_state, checkpoint_path)

        self._generate_md_report(data_state, report_path)

    def _load_checkpoint(self, path: str) -> Dict:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_checkpoint(self, state: Dict, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _generate_md_report(self, data_state: Dict, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                f"# Breadth Scan Extraction Report: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            )
            for s_id, entry in data_state.items():
                f.write(f"## {entry['metadata']['name']}\n")
                f.write(
                    f"**Format:** {entry['metadata']['format']} | **Rank:** {entry['metadata']['rank']}\n\n"
                )
                f.write(f"{entry['content']}\n\n---\n\n")
