import logging
import atexit
from scrapling.fetchers import StealthyFetcher
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

StealthyFetcher.configure(auto_match=False)

MIN_CONTENT_CHARS = 500  # below this threshold, content is likely a bot-challenge page

_BOT_CHALLENGE_TITLES = (
    "just a moment",
    "access denied",
    "403 forbidden",
    "attention required",
    "please wait",
    "checking your browser",
    "enable javascript",
)


def _is_bot_challenge_title(title: str) -> bool:
    return any(p in title.lower() for p in _BOT_CHALLENGE_TITLES)


def _scrapling_fetch_html(url: str) -> str:
    """Fetch raw HTML via StealthyFetcher (stealth Playwright). Returns empty string on failure."""
    try:
        fetcher = StealthyFetcher()
        page = fetcher.fetch(url, headless=True, network_idle=True)
        return page.html_content or ""
    except Exception as e:
        logger.warning(f"Scrapling fetch failed for {url}: {e}")
        return ""


def _parse_content(html: str) -> str:
    """Extract plain text from HTML using the standard junk-tag removal pipeline."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "footer", "header", "aside", "script", "style", "noscript", "form"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _parse_title(html: str) -> str:
    """Extract best title from HTML: OG tag > <title> > H1."""
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


class WebDriverManager:
    """
    Singleton to manage a single Firefox instance.
    """

    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.driver = None
            cls._instance.fetch_count = 0
            cls._instance.RESET_THRESHOLD = 10
            cls._instance.current_headless_mode = True  # Default state

            atexit.register(cls._instance.quit_driver)

        return cls._instance

    def get_driver(self, headless: bool = True):
        """
        Returns the WebDriver instance.
        Restarts the driver if the requested 'headless' mode differs from the active one.
        """
        # Check if we need to switch modes
        if self.driver is not None and self.current_headless_mode != headless:
            logger.info(
                f"Switching Driver Mode (Headless: {self.current_headless_mode} -> {headless}). Restarting..."
            )
            self.quit_driver()

        if self.driver and self.fetch_count >= self.RESET_THRESHOLD:
            logger.info(
                f"Global reset threshold ({self.RESET_THRESHOLD}) reached. Rotating Driver."
            )
            self.quit_driver()

        if not self.driver:
            self.current_headless_mode = headless  # Update state
            mode_str = "Headless" if headless else "UI (Visible)"
            logger.info(f"Initializing Firefox WebDriver in {mode_str} mode...")

            options = Options()
            if headless:
                options.add_argument("-headless")
                options.set_preference("permissions.default.image", 2)  # Disable images

            # Optimization preferences
            options.set_preference("browser.display.use_document_fonts", 0)
            options.set_preference("media.autoplay.default", 5)
            options.set_preference("media.autoplay.blocking_policy", 2)
            options.set_preference("media.volume_scale", "0.0")
            options.set_preference("network.prefetch-next", False)
            options.set_preference("network.dns.disablePrefetch", True)
            options.set_preference("dom.ipc.plugins.enabled.libflashplayer.so", "false")
            options.set_preference("browser.safebrowsing.malware.enabled", False)
            options.set_preference("browser.safebrowsing.phishing.enabled", False)

            try:
                self.driver = webdriver.Firefox(options=options)
                self.fetch_count = 0
                logger.info(f"Firefox WebDriver initialized ({mode_str}).")
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
        Extracts main content text. Tries Scrapling (stealth Playwright) first;
        falls back to Selenium if the result is below MIN_CONTENT_CHARS.
        Raises RuntimeError if both fetchers fail to return sufficient content.
        """
        logger.info(f"Starting content extraction for: {url}")

        # Primary: Scrapling
        html = _scrapling_fetch_html(url)
        if html:
            content = _parse_content(html)
            if len(content) >= MIN_CONTENT_CHARS:
                logger.info(f"Scrapling extracted {len(content)} chars from {url}")
                return content
            logger.warning(
                f"Scrapling returned only {len(content)} chars for {url} "
                f"(threshold: {MIN_CONTENT_CHARS}) — falling back to Selenium"
            )

        # Fallback: Selenium
        logger.info(f"Selenium fallback for content: {url}")
        self._ensure_page_loaded(url)
        driver = self.manager.get_driver()
        content = _parse_content(driver.page_source)

        if len(content) < MIN_CONTENT_CHARS:
            logger.error(f"Extraction failed. No content found for {url}")
            raise RuntimeError(f"Failed to extract meaningful content from {url}")

        logger.info(f"Selenium extracted {len(content)} characters from {url}")
        return content

    def get_webpage_title(self, url: str) -> str:
        """
        Extracts the best possible title (OG Tag > Title Tag > H1).
        Tries Scrapling first; falls back to Selenium if the result is empty
        or matches a known bot-challenge pattern (e.g. "Just a moment...").
        Raises RuntimeError if no title is found.
        """
        logger.info(f"Starting title extraction for: {url}")

        # Primary: Scrapling
        html = _scrapling_fetch_html(url)
        if html:
            title = _parse_title(html)
            if title and not _is_bot_challenge_title(title):
                logger.info(f"Scrapling found title: {title}")
                return title
            if title:
                logger.warning(f"Scrapling returned bot-challenge title '{title}' for {url} — falling back to Selenium")
            else:
                logger.warning(f"Scrapling returned no title for {url} — falling back to Selenium")

        # Fallback: Selenium
        logger.info(f"Selenium fallback for title: {url}")
        self._ensure_page_loaded(url)
        driver = self.manager.get_driver()
        soup = BeautifulSoup(driver.page_source, "html.parser")

        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
            logger.info(f"Selenium found OpenGraph title: {title}")
            return title

        if driver.title and driver.title.strip():
            title = driver.title.strip()
            logger.info(f"Selenium found standard page title: {title}")
            return title

        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
            logger.info(f"Selenium found H1 title: {title}")
            return title

        logger.error(f"Title extraction failed for {url}")
        raise RuntimeError(f"Could not determine title for {url}")
