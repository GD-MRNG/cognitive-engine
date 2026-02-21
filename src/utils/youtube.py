import logging
import os
import re
import requests
import time
from typing import List
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser

from googleapiclient.discovery import build
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .web import WebDriverManager

logger = logging.getLogger(__name__)


class YouTubeExtractor:
    """
    YouTube content extraction tools.
    """

    PAID_API_URL = "https://www.youtube-transcript.io/api/transcripts"
    TACTIQ_URL = "https://tactiq.io/tools/youtube-transcript"

    def __init__(self):
        self.manager = WebDriverManager()
        self.paid_api_key = os.getenv("YOUTUBE_TRANSCRIPT_API_KEY")
        self.google_data_api_key = os.getenv("GOOGLE_DATA_API_KEY")

    def get_video_title(self, url: str) -> str:
        """
        Fetches title via Selenium.
        Raises: TimeoutException, RuntimeError
        """
        logger.info(f"Fetching YouTube video title (Selenium) for: {url}")
        driver = self.manager.get_driver()

        try:
            driver.get(url)
            # Specific selector for YouTube video title
            title_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//yt-formatted-string[@class='style-scope ytd-watch-metadata']",
                    )
                ),
                message="Timed out waiting for YouTube title element.",
            )

            title = title_element.text.strip()
            if not title:
                logger.error("Title element found, but text content was empty.")
                raise RuntimeError("Title element found but text was empty.")

            logger.info(f"Successfully fetched title: '{title}'")
            return title

        except Exception as e:
            logger.error(f"Error fetching video title: {e}")
            raise

    def get_video_transcript_paid_api(self, url: str) -> str:
        """
        Fetches transcript via Paid API.
        Raises: ValueError (Missing Key), RuntimeError
        """
        if not self.paid_api_key:
            logger.error("Attempted Paid API extraction without API key.")
            raise ValueError("Missing environment variable: YOUTUBE_TRANSCRIPT_API_KEY")

        video_id = self._extract_video_id(url)
        logger.info(f"Attempting Paid API transcript fetch for Video ID: {video_id}")

        headers = {
            "Authorization": f"Basic {self.paid_api_key}",
            "Content-Type": "application/json",
        }
        payload = {"ids": [video_id]}

        try:
            logger.debug(
                f"Sending POST request to {self.PAID_API_URL} with payload: {payload}"
            )
            response = requests.post(self.PAID_API_URL, headers=headers, json=payload)

            logger.debug(f"Received response with status code: {response.status_code}")

            if response.status_code == 429:
                logger.warning(f"Rate limit exceeded for video_id: {video_id}")
                raise RuntimeError(
                    "Rate limit exceeded: received HTTP 429 Too Many Requests."
                )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list) or not data:
                logger.error("Paid API response is empty or not a valid list.")
                raise RuntimeError("Paid API response invalid or empty.")

            item = data[0]

            if "error" in item:
                error_msg = item["error"]
                logger.error(f"Paid API returned error: {error_msg}")
                raise RuntimeError(f"Paid API error: {error_msg}")

            if "text" in item:
                logger.info("Paid API transcript fetch successful.")
                return item["text"]

            logger.error("Key 'text' not found in API response.")
            raise RuntimeError("Key 'text' not found in API response.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Transcript API: {e}")
            raise RuntimeError(f"Failed to connect to Transcript API: {e}")

        except Exception as e:
            logger.error(f"Paid API request failed: {e}")
            raise

        finally:
            logger.debug("Sleeping for 2 seconds to respect API rate limits.")
            time.sleep(2)

    def get_video_transcript_free_api(self, url: str) -> str:
        """
        Fetches transcript via youtube-transcript-api.
        Raises: TranscriptsDisabled, NoTranscriptFound, RuntimeError
        """
        video_id = self._extract_video_id(url)
        if not video_id:
            logger.error("No video ID found for Free API.")
            raise ValueError(f"Could not extract video ID from: {url}")

        logger.info(f"Attempting Free API extraction for Video ID: {video_id}")

        try:
            ytt_api = YouTubeTranscriptApi()
            transcripts_list = ytt_api.fetch(video_id=video_id)

            full_text = " ".join([t.text for t in transcripts_list])

            logger.info("Free API extraction successful.")
            return full_text

        except (TranscriptsDisabled, NoTranscriptFound) as e:
            logger.warning(f"Free API Transcript unavailable for {video_id}: {e}.")
            raise RuntimeError(f"Free API failed: {e}")

        except Exception as e:
            logger.error(f"Free API extraction error for {video_id}: {e}")
            raise RuntimeError(f"Free API failed: {e}")

    def get_video_transcript_tactiq(self, url: str) -> str:
        """
        Fetches transcript via Tactiq (Selenium).
        Raises: TimeoutException, RuntimeError
        """
        logger.info(f"Starting Tactiq (Selenium) extraction for: {url}")
        driver = self.manager.get_driver()

        try:
            driver.get(self.TACTIQ_URL)

            # 1. Input URL
            logger.debug("Waiting for Tactiq URL input...")
            url_input = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "yt-2")),
                message="Tactiq URL input not found",
            )
            url_input.clear()
            url_input.send_keys(url)

            # 2. Click Button
            logger.debug("Clicking 'Get Video Transcript' button...")
            driver.find_element(
                By.XPATH, "//input[@value='Get Video Transcript']"
            ).click()

            # 3. Wait for Transcript Container
            logger.debug("Waiting for transcript container to appear...")
            container = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "transcript")),
                message="Tactiq transcript container did not appear",
            )

            # 4. Wait for text to populate
            WebDriverWait(driver, 10).until(
                lambda d: container.text.strip() != "",
                message="Tactiq transcript container remained empty",
            )

            raw_text = container.text
            cleaned_text = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*", "", raw_text).strip()

            if not cleaned_text:
                logger.error("Tactiq extraction finished but result was empty.")
                raise RuntimeError("Tactiq extraction resulted in empty text.")

            logger.info("Tactiq extraction successful.")
            return cleaned_text

        except Exception as e:
            logger.error(f"Tactiq extraction failed: {e}")
            raise

    def get_recent_channel_titles(self, channel_url: str, days: int = 7) -> List[str]:
        """
        Fetches channel titles via Google Data API.
        Raises: ValueError (Missing Key), HttpError, RuntimeError
        """
        if not self.google_data_api_key:
            logger.error("Attempted Google Data API fetch without API key.")
            raise ValueError("Missing environment variable: GOOGLE_DATA_API_KEY")

        logger.info(
            f"Fetching recent titles for channel: {channel_url} (Last {days} days)"
        )

        handle_match = re.search(r"youtube\.com/(@[A-Za-z0-9_.-]+)", channel_url)
        if not handle_match:
            logger.error(f"Could not extract handle from URL: {channel_url}")
            raise ValueError(f"Could not parse handle from URL: {channel_url}")

        handle = handle_match.group(1)

        try:
            service = build("youtube", "v3", developerKey=self.google_data_api_key)

            # 1. Get Channel ID
            search_res = (
                service.search()
                .list(q=handle, part="id", type="channel", maxResults=1)
                .execute()
            )
            if not search_res.get("items"):
                logger.error(f"Channel handle not found in API: {handle}")
                raise RuntimeError(f"Channel handle not found: {handle}")

            channel_id = search_res["items"][0]["id"]["channelId"]

            # 2. Get Uploads Playlist ID
            channel_res = (
                service.channels().list(id=channel_id, part="contentDetails").execute()
            )
            uploads_id = channel_res["items"][0]["contentDetails"]["relatedPlaylists"][
                "uploads"
            ]

            # 3. Get Video Titles
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            playlist_res = (
                service.playlistItems()
                .list(playlistId=uploads_id, part="snippet", maxResults=50)
                .execute()
            )

            titles = []
            for item in playlist_res.get("items", []):
                published_at = date_parser.isoparse(item["snippet"]["publishedAt"])
                if published_at >= cutoff_date:
                    titles.append(item["snippet"]["title"])

            logger.info(f"Successfully fetched {len(titles)} titles from channel.")
            return titles

        except Exception as e:
            logger.error(f"Google Data API failed: {e}")
            raise

    def _extract_video_id(self, url: str) -> str:
        """Helper to extract ID. Raises ValueError if invalid."""
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        video_id = None

        if "youtube" in parsed.hostname:
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [None])[0]
            elif parsed.path.startswith("/shorts/"):
                video_id = parsed.path.split("/")[-1]
        elif "youtu.be" in parsed.hostname:
            video_id = parsed.path.split("/")[-1]

        if not video_id:
            logger.error(f"Failed to extract video ID from URL: {url}")
            raise ValueError(f"Could not extract Video ID from URL: {url}")

        return video_id
