import os
import time
import logging
from datetime import datetime
from typing import Dict, Any, List
from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.utils.web import WebDriverManager, WebPageExtractor
from src.utils.youtube import YouTubeExtractor
from src.utils.audio import AudioExtractor
from src.utils.io import CheckpointManager
from src.utils.notifications import DiscordNotifier

logger = logging.getLogger(__name__)

# TODO: Refactor or Deprecate this task

# @register_task("ContentExtractionTask")
# class ContentExtractionTask(PipelineTask):
#     """
#     Iterates through a list of CSV items (dict).
#     Uses 'url' for extraction. Preserves 'title', 'source', 'date'.
#     """

#     def execute(
#         self, context: WorkflowContext, config: Dict[str, Any]
#     ) -> WorkflowContext:
#         input_key = config.get("input_key")
#         output_key = config.get("output_key")
#         failure_key = config.get("failure_key", "failed_items")

#         items = context.require(input_key)

#         # Initialize the robust extractor
#         extractor = ContentExtractor(headless=True)

#         success_docs = []
#         failed_items = []

#         logger.info(f"Starting extraction for {len(items)} items...")

#         try:
#             for i, item in enumerate(items):
#                 url = item["url"]
#                 logger.info(f"[{i+1}/{len(items)}] Processing: {url}")

#                 try:
#                     # Robust Extract
#                     raw_text = extractor.extract(url)

#                     # Attach CSV Metadata to the Document Object
#                     doc = {
#                         "filename": f"{item['source']}_{i}.txt",  # Unique ID
#                         "content": raw_text,
#                         "url": url,
#                         "title": item["title"],
#                         "source": item["source"],
#                         "date": item["date"],
#                         "source_type": "text_queue_automated",
#                     }
#                     success_docs.append(doc)

#                 except Exception as e:
#                     logger.warning(f"Failed to extract {url}: {e}")
#                     failed_items.append(item)
#         finally:
#             extractor.close()

#         context.set(output_key, success_docs)
#         context.set(failure_key, failed_items)
#         return context


@register_task("ManualReviewTask")
class ManualReviewTask(PipelineTask):
    """
    Human-in-the-Loop (HITL) Review.
    1. Pre-scans all items to identify those with missing fields.
    2. Sends a Discord Notification if intervention is required.
    3. Opens a visible browser and prompts user for CLI input sequentially.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        target_key = config.get("target_key", "research_data")
        checkpoint_file = config.get("checkpoint_file", "outputs/research.json")
        target_types = config.get("target_types", ["analysis"])
        missing_fields = config.get("missing_fields", ["content"])

        artifact = CheckpointManager.load(checkpoint_file)
        items = artifact.get(target_key, [])

        if not items:
            items = context.get(target_key, [])
            if not items:
                logger.info("ManualReviewTask: No items to check.")
                return context

        # Pre-calculate Items Needing Review
        # We store indices so we can modify the original list in place
        items_to_review_indices = []

        for i, item in enumerate(items):
            if item.get("type") not in target_types:
                continue

            if any(not item.get(field) for field in missing_fields):
                items_to_review_indices.append(i)

        count_needed = len(items_to_review_indices)

        if count_needed == 0:
            logger.info("ManualReviewTask: No items missing data. Skipping.")
            return context

        logger.info(f"ManualReviewTask: {count_needed} items require intervention.")
        DiscordNotifier().send(
            f"Manual Review Required: {count_needed} items missing {missing_fields}.",
            level="hitl",
        )

        driver_manager = WebDriverManager()
        updated = False

        print(f"\n{'='*60}")
        print(f"!!! HITL INTERVENTION STARTED: {count_needed} ITEMS !!!")
        print(f"{'='*60}\n")

        try:
            for current_idx, item_idx in enumerate(items_to_review_indices):
                item = items[item_idx]

                # Re-calculate missing fields (double check)
                fields_to_fix = [
                    field for field in missing_fields if not item.get(field)
                ]

                if not fields_to_fix:
                    continue

                url = item.get("url", "")
                source = item.get("source", "Unknown")

                # UX: Progress based on fix list, not total list
                print(f"\n{'!'*60}")
                print(f"REVIEWING [{current_idx+1}/{count_needed}]")
                print(f"Source: {source}")
                print(f"URL:    {url}")
                print(f"Missing: {', '.join(fields_to_fix)}")
                print(f"{'!'*60}")

                # Open Browser (Visible Mode)
                if url:
                    logger.info(f"Opening browser for: {url}")
                    driver = driver_manager.get_driver(headless=False)
                    try:
                        driver.get(url)
                    except Exception as e:
                        logger.error(f"Failed to open URL automatically: {e}")
                else:
                    print(">> No URL provided for this item.")

                # Sequential Input Loop
                for field in fields_to_fix:
                    print(
                        f"\n>>> Please enter value for '{field}' (End with Ctrl+D or Ctrl+Z on Windows):"
                    )

                    user_input_lines = []
                    try:
                        while True:
                            line = input()
                            user_input_lines.append(line)
                    except EOFError:
                        pass  # User signaled end of input

                    value = "\n".join(user_input_lines).strip()

                    if value:
                        item[field] = value
                        updated = True
                        print(f">> Updated '{field}'.")
                    else:
                        print(f">> Skipped '{field}' (empty input).")

                # Atomic Save after every item to prevent data loss on crash
                if updated:
                    artifact[target_key] = items
                    CheckpointManager.save(checkpoint_file, artifact)

        except KeyboardInterrupt:
            print("\nManual review interrupted by user.")
        finally:
            driver_manager.quit_driver()

        if updated:
            context.set(target_key, items)

        return context


@register_task("SourceGatheringTask")
class SourceGatheringTask(PipelineTask):

    """
    Constructs the 'To-Do' list for the research pipeline.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_key = config.get("input_key", "raw_sources")
        output_key = config.get("output_key", "research_data")
        checkpoint_file = config.get("checkpoint_file", "outputs/research.json")
        link_file = config.get("link_file", "inputs/curated_links.txt")

        all_sources = context.get(input_key, [])
        if not all_sources:
            logger.warning("SourceGatheringTask: No sources found in context.")
            return context

        datapoint_sources = [s for s in all_sources if s.get("type") == "datapoint"]
        analysis_sources = [s for s in all_sources if s.get("type") == "analysis"]

        artifact = CheckpointManager.load(checkpoint_file)
        current_items = artifact.get(output_key, [])
        if not isinstance(current_items, list):
            current_items = []

        processed_source_ids = {
            item.get("id") for item in current_items if item.get("id")
        }

        # Create a lookup for deduplication
        existing_urls = {
            item.get("url"): item for item in current_items if item.get("url")
        }

        # --- PHASE 1: Automated Breadth Scan ---
        if datapoint_sources:
            logger.info(
                f"--- Starting Phase 1: Automated Breadth Scan ({len(datapoint_sources)} sources) ---"
            )
            for source in datapoint_sources:
                url = source.get("url")

                if url in existing_urls:
                    # Ensure it's in our list=
                    if existing_urls[url] not in current_items:
                        current_items.append(existing_urls[url])
                    continue

                self._add_item(current_items, source, url, "datapoint")

                artifact[output_key] = current_items
                CheckpointManager.save(checkpoint_file, artifact)

        # --- PHASE 2: Interactive Depth Scan ---
        if analysis_sources:
            logger.info(
                f"--- Starting Phase 2: Interactive Depth Scan ({len(analysis_sources)} sources) ---"
            )
            os.makedirs(os.path.dirname(link_file), exist_ok=True)

            driver_manager = WebDriverManager()

            for i, source in enumerate(analysis_sources):
                s_id = source["id"]
                source_name = source.get("name")
                source_url = source.get("url")

                if s_id in processed_source_ids:
                    logger.info(
                        f"Skipping '{source_name}' (ID: {s_id}) - Data already exists in JSON."
                    )
                    continue

                if source_url:
                    logger.info(f"Opening browser for source: {source_name}")
                    try:
                        driver = driver_manager.get_driver(headless=False)
                        driver.get(source_url)
                    except Exception as e:
                        logger.warning(
                            f"Could not auto-open browser for {source_name}: {e}"
                        )

                with open(link_file, "w", encoding="utf-8") as f:
                    f.write(
                        f">>> Input links for source: {source_name} below:\n\n"
                    )  # UX

                print(f"\nSOURCE [{i+1}/{len(analysis_sources)}]: {source_name}")
                print(f"Action: Paste links into '{link_file}' and save.")
                input(">> Press [ENTER] when ready... ")

                new_urls = self._read_link_file(link_file)

                if not new_urls:
                    logger.info(f"No links provided for {source_name}.")
                    continue

                for url in new_urls:
                    if url in existing_urls:
                        logger.info(f"Skipping duplicate: {url}")
                        continue

                    if source.get("format") == "podcast":
                        if not os.path.exists(url):
                            logger.error(f"Podcast file not found: {url}. Skipping.")
                            continue

                    self._add_item(current_items, source, url, "analysis")

                    # Update Lookup
                    existing_urls[url] = current_items[-1]

                    artifact[output_key] = current_items
                    CheckpointManager.save(checkpoint_file, artifact)

        context.set(output_key, current_items)

        return context

    def _add_item(
        self, items_list: List, source_obj: Dict, url: str, type_override: str
    ):
        items_list.append(
            {
                "id": source_obj.get("id"),
                "source": source_obj.get("name"),
                "url": url,
                "type": type_override,
                "format": source_obj.get("format", "webpage"),
                "tags": source_obj.get("tags", []),
            }
        )

    def _read_link_file(self, filepath: str) -> List[str]:
        urls = []
        if os.path.exists(filepath):
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    cleaned = line.strip()
                    if cleaned and not cleaned.startswith(">>>"):
                        urls.append(cleaned)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("")
        return urls


@register_task("ContentScrapingTask")
class ContentScrapingTask(PipelineTask):
    """
    Source Content Scraper.
    Orchestrates extraction logic based on source type/format.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        target_key = config.get("target_key", "research_data")
        checkpoint_file = config.get("checkpoint_file", "outputs/research.json")

        artifact = CheckpointManager.load(checkpoint_file)
        items = artifact.get(target_key, [])

        if not items:
            items = context.get(target_key, [])
            if not items:
                logger.warning(f"ContentScrapingTask: No items found in '{target_key}'")
                return context

        self.web_extractor = WebPageExtractor()
        self.yt_extractor = YouTubeExtractor()
        self.audio_extractor = AudioExtractor()

        updated = False
        logger.info(f"ContentScrapingTask: Processing {len(items)} items.")

        try:
            for item in items:
                # Skip if content key exists and is truthy
                if item.get("content"):
                    continue

                url = item.get("url")
                fmt = item.get("format", "webpage")
                typ = item.get("type", "datapoint")

                if not url:
                    continue

                logger.info(f"Scraping [{typ}/{fmt}]: {item.get('source')}")

                try:
                    content_result = ""

                    if fmt == "youtube":
                        if typ == "datapoint":
                            content_result = self._scrape_youtube_headlines(url)
                        else:
                            content_result = (
                                self._scrape_youtube_transcript_with_fallback(url)
                            )
                    elif fmt == "podcast":
                        content_result = self._scrape_audio_transcript(url)
                    else:
                        content_result = self._scrape_webpage_with_retry(url)

                    item["content"] = content_result
                    item["scraped_at"] = datetime.now().isoformat()
                    updated = True

                    artifact[target_key] = items
                    CheckpointManager.save(checkpoint_file, artifact)

                except Exception as e:
                    logger.error(f"Failed to scrape {url}: {e}")
                    # Mark as empty to prevent infinite blocking
                    item["content"] = ""

        finally:
            WebDriverManager().quit_driver()

        if updated:
            context.set(target_key, items)

        return context

    def _scrape_youtube_headlines(self, url: str) -> str:
        try:
            titles = self.yt_extractor.get_recent_channel_titles(url)
            if titles:
                return "\n".join(titles)
            return "No recent videos found."
        except Exception as e:
            logger.error(f"YouTube Headline fetch failed for {url}: {e}")
            return ""

    def _scrape_youtube_transcript_with_fallback(self, url: str) -> str:
        # Priority 1: Paid API
        for attempt in range(3):
            try:
                return self.yt_extractor.get_video_transcript_paid_api(url)
            except ValueError:
                logger.warning("Paid API Key missing. Skipping to next method.")
                break
            except Exception as e:
                logger.warning(f"Paid API Attempt {attempt+1}/3 failed: {e}")
                if attempt < 2:
                    time.sleep(2)

        logger.info("Paid API failed. Falling back to Free API.")

        # Priority 2: Free API
        for attempt in range(2):
            try:
                return self.yt_extractor.get_video_transcript_free_api(url)
            except Exception as e:
                logger.warning(f"Free API Attempt {attempt+1}/2 failed: {e}")

        logger.info("Free API failed. Falling back to Tactiq (Selenium).")

        # Priority 3: Tactiq
        for attempt in range(2):
            try:
                return self.yt_extractor.get_video_transcript_tactiq(url)
            except Exception as e:
                logger.warning(f"Tactiq Attempt {attempt+1}/2 failed: {e}")

        logger.error(f"All transcript extraction methods failed for {url}")
        return ""

    def _scrape_audio_transcript(self, filepath: str) -> str:
        try:
            return self.audio_extractor.transcribe(filepath)
        except Exception as e:
            logger.warning(f"Audio transcription failed for {filepath}: {e}")
            return ""

    def _scrape_webpage_with_retry(self, url: str) -> str:
        for attempt in range(2):
            try:
                content = self.web_extractor.get_webpage_content(url)
                if content:
                    return content
            except Exception as e:
                logger.warning(
                    f"Web scrape Attempt {attempt+1}/2 failed for {url}: {e}"
                )

        return ""


@register_task("TitleScrapingTask")
class TitleScrapingTask(PipelineTask):
    """
    Enriches items with titles.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        target_key = config.get("target_key", "research_data")
        checkpoint_file = config.get("checkpoint_file", "outputs/research.json")
        target_types = config.get("target_types", ["analysis"])
        force_refresh = config.get("force_refresh", False)

        artifact = CheckpointManager.load(checkpoint_file)
        items = artifact.get(target_key, [])

        if not items:
            items = context.get(target_key, [])
            if not items:
                logger.warning(f"TitleScrapingTask: No items found in '{target_key}'")
                return context

        web_extractor = WebPageExtractor()
        yt_extractor = YouTubeExtractor()

        updated = False
        logger.info(f"TitleScrapingTask: Checking {len(items)} items.")

        try:
            for item in items:
                # 1. Filter by Type
                if item.get("type") not in target_types:
                    continue

                # 2. Skip if exists (unless forced)
                if item.get("title") and not force_refresh:
                    continue

                url = item.get("url")
                if not url:
                    continue

                fmt = item.get("format", "webpage")
                logger.info(f"Fetching title for [{fmt}]: {url}")
                fetched_title = ""

                try:
                    # 3. Routing
                    if fmt == "youtube":
                        fetched_title = yt_extractor.get_video_title(url)
                    elif fmt == "podcast":
                        fetched_title = self._format_filename_to_title(url)
                    else:
                        fetched_title = web_extractor.get_webpage_title(url)

                    # 4. Save Result
                    if fetched_title:
                        item["title"] = fetched_title
                        updated = True
                        logger.info(f"Found title: {fetched_title}")

                        artifact[target_key] = items
                        CheckpointManager.save(checkpoint_file, artifact)
                    else:
                        logger.warning(f"Title unavailable for {url}")
                        item["title"] = "Title Unavailable"

                except Exception as e:
                    logger.error(f"Failed to fetch title for {url}: {e}")
        finally:
            WebDriverManager().quit_driver()

        if updated:
            context.set(target_key, items)

        return context

    def _format_filename_to_title(self, filepath: str) -> str:
        """Converts snake_case or kebab-case filenames to Title Case."""
        # Get just the filename without the extension
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        clean_name = base_name.replace("_", " ").replace("-", " ")
        return clean_name.title()
