import logging
import atexit
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class WebDriverManager:
    """
    Singleton to manage a single Firefox instance across all extractors.
    """

    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.driver = None
            cls._instance.fetch_count = 0
            cls._instance.RESET_THRESHOLD = 10
            cls._instance.headless = False

            # Register cleanup.
            # Runs automatically when the Python script exits.
            atexit.register(cls._instance.quit_driver)

        return cls._instance

    def get_driver(self):
        if self.driver and self.fetch_count >= self.RESET_THRESHOLD:
            logger.info(
                f"Global reset threshold ({self.RESET_THRESHOLD}) reached. Rotating Driver to clear RAM."
            )
            self.quit_driver()

        if not self.driver:
            logger.info("Initializing fresh Firefox WebDriver instance...")
            options = Options()
            if self.headless:
                options.add_argument("-headless")

            # --- Optimization preferences ---
            # Heavy Resource Blocking (Huge bandwidth saver)
            options.set_preference("permissions.default.image", 2)  # Block Images
            options.set_preference(
                "browser.display.use_document_fonts", 0
            )  # Block Web Fonts
            # Media & Autoplay Blocking
            # 0=Allow, 1=Block, 5=Block All (including HTML5 video)
            options.set_preference("media.autoplay.default", 5)
            options.set_preference("media.autoplay.blocking_policy", 2)
            options.set_preference("media.volume_scale", "0.0")  # Mute audio
            # Network & Telemetry (Reduce overhead)
            options.set_preference("network.prefetch-next", False)
            options.set_preference("network.dns.disablePrefetch", True)
            options.set_preference("dom.ipc.plugins.enabled.libflashplayer.so", "false")
            # Disable Firefox "Safe Browsing" (Can save 1-2s on startup)
            options.set_preference("browser.safebrowsing.malware.enabled", False)
            options.set_preference("browser.safebrowsing.phishing.enabled", False)

            try:
                self.driver = webdriver.Firefox(options=options)
                self.fetch_count = 0
                logger.info("Firefox WebDriver initialized successfully.")
            except Exception as e:
                logger.critical(f"Failed to initialize Firefox WebDriver: {e}")
                raise

        self.fetch_count += 1
        return self.driver

    def quit_driver(self):
        if self.driver:
            logger.info("Quitting Firefox WebDriver...")
            try:
                self.driver.quit()
                logger.info("WebDriver closed successfully.")
            except Exception as e:
                logger.error(f"Error during WebDriver quit: {e}")
            finally:
                self.driver = None
                self.fetch_count = 0


class WebPageExtractor:
    """
    Webpage content extraction tools.
    """

    def __init__(self):
        self.manager = WebDriverManager()

    def _ensure_page_loaded(self, url: str):
        """Helper to navigate only if not already on the page."""
        driver = self.manager.get_driver()
        if driver.current_url != url:
            logger.info(f"Navigating to URL: {url}")
            try:
                driver.get(url)
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                logger.debug("Page body loaded successfully.")
            except TimeoutException:
                logger.error(f"Timeout waiting for page to load: {url}")
                raise RuntimeError(f"Timeout loading {url}")
            except Exception as e:
                logger.error(f"Failed to navigate to {url}: {e}")
                raise RuntimeError(f"Navigation failed: {e}")

    def get_webpage_content(self, url: str) -> str:
        """
        Extracts main content text using Trafilatura or BeautifulSoup fallback.
        Raises RuntimeError if content is empty.
        """
        logger.info(f"Starting content extraction for: {url}")
        self._ensure_page_loaded(url)
        driver = self.manager.get_driver()
        page_source = driver.page_source

        # 1. Primary Strategy: Trafilatura
        logger.debug("Attempting extraction via Trafilatura...")
        content = trafilatura.extract(page_source, include_comments=False)

        # 2. Fallback Strategy: BeautifulSoup
        if not content:
            logger.info("Trafilatura failed. Falling back to BeautifulSoup.")
            soup = BeautifulSoup(page_source, "html.parser")
            content = soup.get_text(separator="\n", strip=True)

        if not content:
            logger.error(f"Extraction failed. No content found for {url}")
            raise RuntimeError(f"Failed to extract meaningful content from {url}")

        logger.info(f"Successfully extracted {len(content)} characters from {url}")
        return content

    def get_webpage_title(self, url: str) -> str:
        """
        Extracts the best possible title (OG Tag > Title Tag > H1).
        Raises RuntimeError if no title is found.
        """
        logger.info(f"Starting title extraction for: {url}")
        self._ensure_page_loaded(url)
        driver = self.manager.get_driver()
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Priority 1: OpenGraph
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
            logger.info(f"Found OpenGraph title: {title}")
            return title

        # Priority 2: Standard Title
        if driver.title and driver.title.strip():
            title = driver.title.strip()
            logger.info(f"Found standard page title: {title}")
            return title

        # Priority 3: H1
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
            logger.info(f"Found H1 title: {title}")
            return title

        logger.error(f"Title extraction failed for {url}")
        raise RuntimeError(f"Could not determine title for {url}")
