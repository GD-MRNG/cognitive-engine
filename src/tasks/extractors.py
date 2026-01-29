import logging
from typing import Dict, Any
from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.utils.web import ContentExtractor

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
