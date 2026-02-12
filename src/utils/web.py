import logging
from typing import Dict
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import trafilatura

logger = logging.getLogger(__name__)


class WebPageExtractor:
    """
    Webpage content extractor.
    Resets the browser every X fetches to prevent memory bloat.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.fetch_count = 0
        self.RESET_THRESHOLD = 10  # Rotation limit

    def _setup_driver(self):
        # If driver exists but reached threshold, kill it first
        if self.driver and self.fetch_count >= self.RESET_THRESHOLD:
            logger.info(
                f"Reset threshold ({self.RESET_THRESHOLD}) reached. Rotating driver..."
            )
            self.close()

        # Initialize fresh driver if none exists
        if not self.driver:
            firefox_options = Options()
            if self.headless:
                firefox_options.add_argument("-headless")

            # Performance/Memory Preferences
            firefox_options.set_preference(
                "permissions.default.image", 2
            )  # 2 = Block images
            firefox_options.set_preference(
                "dom.ipc.plugins.enabled.libflashplayer.so", "false"
            )

            self.driver = webdriver.Firefox(options=firefox_options)
            self.fetch_count = 0  # Reset counter for the new driver

    def extract(self, url: str) -> Dict[str, str]:
        self._setup_driver()
        self.fetch_count += 1  # Increment on every call

        try:
            logger.info(
                f"[{self.fetch_count}/{self.RESET_THRESHOLD}] Navigating to: {url}"
            )
            self.driver.get(url)

            # Explicit Wait (The "Selenium Way")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            page_source = self.driver.page_source

            # Content Extraction
            content = trafilatura.extract(page_source, include_comments=False)
            if not content:
                soup = BeautifulSoup(page_source, "html.parser")
                content = soup.get_text(separator="\n", strip=True)

            title = self._extract_title_metadata(page_source)

            return {"content": content, "title": title}

        except Exception as e:
            logger.error(f"Web extraction failed for {url}: {e}")
            return {"content": "", "title": ""}

    def _extract_title_metadata(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return "Untitled Document"

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error during driver quit: {e}")
            finally:
                self.driver = None
