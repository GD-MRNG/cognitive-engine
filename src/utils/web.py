import logging
import time
import os
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)


class ContentExtractor:
    """
    The Unified Extractor.
    - Handles Web (Selenium + BS4 Clean)
    - Handles YouTube (Paid -> Free -> Tactiq -> Manual Failover)
    - Manages Memory (Driver Rotation)
    - Centralized Retry Configuration
    """

    DRIVER_RESET_THRESHOLD = 25

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.request_count = 0

        # --- Centralized Retry Configuration ---

        self.max_retries = 2
        self.retry_delays = [1, 2]

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    # --- Driver Lifecycle ---

    def _init_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

        logger.info(f"Initializing Firefox WebDriver (Headless: {self.headless})...")
        options = FirefoxOptions()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Firefox(options=options)
        self.request_count = 0
        return self.driver

    def _get_driver(self):
        if self.driver is None or self.request_count >= self.DRIVER_RESET_THRESHOLD:
            self._init_driver()
        return self.driver

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def open_page_for_user(self, url: str):
        """
        FAILOVER TOOL: Launches a VISIBLE browser for the user to see the page.
        """
        logger.info("Switching to Visible Mode for manual review...")
        if self.headless:
            if self.driver:
                self.driver.quit()
            self.driver = None
            self.headless = False

        driver = self._get_driver()
        driver.get(url)

    # --- Main Entry Point ---

    def extract(self, url_or_path: str) -> str:
        self.request_count += 1

        # 1. Local File
        if os.path.exists(url_or_path):
            return self._read_local_file(url_or_path)

        # 2. YouTube
        if "youtube.com" in url_or_path or "youtu.be" in url_or_path:
            return self._extract_youtube(url_or_path)

        # 3. Web Page
        return self._extract_web(url_or_path)

    # --- Helpers ---

    def _clean_html_content(self, html_content: str) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        for script_or_style in soup(
            [
                "script",
                "style",
                "noscript",
                "header",
                "footer",
                "nav",
                "aside",
                "iframe",
            ]
        ):
            script_or_style.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _read_local_file(self, path: str) -> str:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            raise RuntimeError(f"Failed to read local file: {e}")

    def _get_delay(self, attempt_index: int) -> int:
        if attempt_index < len(self.retry_delays):
            return self.retry_delays[attempt_index]
        return 2

    # --- Extraction Strategies ---

    def _extract_youtube(self, url: str) -> str:
        video_id = self.yt_handler.extract_video_id(url)
        if not video_id:
            raise ValueError("Invalid YouTube URL")

        # # Tier 0: Paid API
        for attempt in range(self.max_retries + 1):
            text = self.yt_handler.get_transcript_paid(video_id)
            if text:
                logger.info(
                    f"YouTube extraction success (Tier 0: Paid API, Attempt {attempt+1})"
                )
                return f"Source: YouTube (Paid API)\n\n{text}"

            if attempt < self.max_retries:
                time.sleep(self._get_delay(attempt))

        # Tier 1: Free API
        for attempt in range(self.max_retries + 1):
            text = self.yt_handler.get_transcript_free(video_id)
            if text:
                logger.info(
                    f"YouTube extraction success (Tier 2: Free API, Attempt {attempt+1})"
                )
                return f"Source: YouTube (Free API)\n\n{text}"

            if attempt < self.max_retries:
                time.sleep(self._get_delay(attempt))

        # Tier 2: Selenium Tactiq
        for attempt in range(self.max_retries + 1):
            try:
                driver = self._get_driver()
                text = self.yt_handler.get_transcript_tactiq(driver, url)
                if text:
                    logger.info(
                        f"YouTube extraction success (Tier 1: Tactiq, Attempt {attempt+1})"
                    )
                    return f"Source: YouTube (Tactiq)\n\n{text}"
            except Exception as e:
                logger.warning(f"Tactiq attempt {attempt+1} failed: {e}")
                self._init_driver()

            if attempt < self.max_retries:
                time.sleep(self._get_delay(attempt))

        # This ensures the Task catches it and moves the item to the Failed queue.
        raise RuntimeError("YouTube Automated Extraction Failed (All Tiers).")

    def _extract_web(self, url: str) -> str:
        """
        Extracts webpage content using Selenium + BS4.
        """
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(
                        f"Webpage Retry {attempt + 1}/{self.max_retries + 1}..."
                    )

                driver = self._get_driver()
                driver.get(url)

                WebDriverWait(driver, 20).until(
                    lambda d: d.find_element(By.TAG_NAME, "body").text.strip() != ""
                )

                html = driver.page_source
                cleaned_text = self._clean_html_content(html)

                if cleaned_text:
                    logger.info(f"Webpage extraction successful on attempt {attempt+1}")
                    return f"Source: Web (Selenium)\n\n{cleaned_text}"

            except Exception as e:
                logger.warning(f"Webpage attempt {attempt + 1} failed: {e}")
                self._init_driver()

            if attempt < self.max_retries:
                time.sleep(self._get_delay(attempt))

        # This ensures the Task catches it and moves the item to the Failed queue.
        raise RuntimeError(f"All webpage extraction attempts failed for {url}")
