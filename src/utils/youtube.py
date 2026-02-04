import logging
import os
import re
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from typing import Optional, List, Any
import requests
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


class YouTubeHandler:
    """
    Handles fetching YouTube transcript and title data via multiple strategies:
    1. Paid API (youtube-transcript.io)
    2. Free API (youtube-transcript-api)
    3. Selenium Automation (Tactiq.io)
    """

    PAID_API_URL = "https://www.youtube-transcript.io/api/transcripts"
    TACTIQ_URL = "https://tactiq.io/tools/youtube-transcript"

    def __init__(self):
        self.paid_api_key = os.getenv("YOUTUBE_TRANSCRIPT_API_KEY")
        self.google_data_api_key = os.getenv("GOOGLE_DATA_API_KEY")

    def get_recent_titles(self, channel_url: str, days: int = 7) -> List[str]:
        """
        Fetches video titles published within a specific window (default 7 days).
        Uses the Google YouTube Data API v3.
        """
        if not self.google_data_api_key:
            logger.error("Google Data API Key is required for fetching titles.")
            return []

        # 1. Extract Handle
        handle_match = re.search(r"youtube\.com/(@[A-Za-z0-9_.-]+)", channel_url)
        if not handle_match:
            logger.error(f"Could not extract handle from URL: {channel_url}")
            return []
        handle = handle_match.group(1)

        try:
            service = build("youtube", "v3", developerKey=self.google_data_api_key)

            # 2. Resolve Handle to Channel ID
            search_res = (
                service.search()
                .list(q=handle, part="id", type="channel", maxResults=1)
                .execute()
            )

            if not search_res.get("items"):
                logger.error(f"Channel ID not found for handle: {handle}")
                return []

            channel_id = search_res["items"][0]["id"]["channelId"]

            # 3. Get the 'Uploads' Playlist ID
            channel_res = (
                service.channels().list(id=channel_id, part="contentDetails").execute()
            )

            uploads_id = channel_res["items"][0]["contentDetails"]["relatedPlaylists"][
                "uploads"
            ]

            # 4. Fetch Items from Playlist
            one_week_ago = datetime.now(timezone.utc) - timedelta(days=days)
            playlist_res = (
                service.playlistItems()
                .list(playlistId=uploads_id, part="snippet", maxResults=50)
                .execute()
            )

            titles = []
            for item in playlist_res.get("items", []):
                snippet = item["snippet"]
                published = date_parser.isoparse(snippet["publishedAt"])

                if published >= one_week_ago:
                    titles.append(snippet["title"])

            logger.info(
                f"Successfully fetched {len(titles)} titles for handle {handle}"
            )
            return titles

        except HttpError as e:
            logger.error(f"YouTube API Error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching titles: {e}")
            return []

    def get_transcript_paid(self, video_id: str) -> Optional[str]:
        """
        YouTube Transcript API (PAID)
        https://www.youtube-transcript.io/
        """
        if not self.paid_api_key:
            return None

        headers = {
            "Authorization": f"Basic {self.paid_api_key}",
            "Content-Type": "application/json",
        }
        payload = {"ids": [video_id]}

        try:
            response = requests.post(self.PAID_API_URL, headers=headers, json=payload)
            if response.status_code == 429:
                logger.warning("Paid API Rate Limit Exceeded")
                return None
            response.raise_for_status()

            data = response.json()
            # API returns a list of results
            if data and isinstance(data, list) and len(data) > 0 and "text" in data[0]:
                logger.info(f"Paid API successful for video ID: {video_id}")
                return data[0]["text"]
            return None
        except Exception as e:
            logger.warning(f"Paid API failed for {video_id}: {e}")
            return None

    def get_transcript_free(self, video_id: str) -> Optional[str]:
        """
        youtube-transcript-api (FREE)
        https://pypi.org/project/youtube-transcript-api/
        """
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            logger.info(f"Free API successful for video ID: {video_id}")
            return " ".join([t["text"] for t in transcript_list])
        except (TranscriptsDisabled, NoTranscriptFound):
            logger.warning(f"Free API: Transcripts disabled/not found for {video_id}")
            return None
        except Exception as e:
            logger.error(f"Free API Error for {video_id}: {e}")
            return None

    def get_transcript_tactiq(self, driver: Any, video_url: str) -> Optional[str]:
        """
        Selenium Scrape via Tactiq.io (FREE)
        Requires an active Selenium WebDriver instance.
        """
        logger.debug(f"Attempting Tactiq extraction for: {video_url}")
        try:
            logger.debug(f"Tactiq: Navigating to {self.TACTIQ_URL}.")
            driver.get(self.TACTIQ_URL)

            # 1. Input URL
            logger.debug("Tactiq: Waiting for URL input field.")
            url_input = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "yt-2"))
            )
            url_input.clear()
            logger.info(f"Tactiq: Inputting YouTube URL: {video_url}.")
            url_input.send_keys(video_url)

            # 2. Click Button
            logger.debug("Tactiq: Waiting for 'Get Video Transcript' button.")
            btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//input[@value='Get Video Transcript']")
                )
            )
            logger.debug("Tactiq: Clicking 'Get Transcript' button.")
            btn.click()

            # 3. Wait for Result (URL change or Container check)
            logger.debug("Tactiq: Waiting for transcript page to load.")
            WebDriverWait(driver, 20).until(EC.url_contains("run/youtube_transcript"))

            logger.debug(
                "Tactiq: Waiting for transcript container to be present and populated."
            )
            container = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "transcript"))
            )

            # Wait for text to populate
            WebDriverWait(driver, 20).until(lambda d: container.text.strip() != "")
            raw_text = container.text

            # Clean timestamps (e.g., "00:01:23 ")
            cleaned_text = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*", "", raw_text).strip()

            if cleaned_text:
                logger.info(f"Tactiq extraction successful for {video_url}.")
                return cleaned_text
            logger.warning(
                f"Tactiq extraction failed: No cleaned text found after extraction for {video_url}"
            )
            return None

        except Exception as e:
            logger.warning(
                f"Tactiq extraction failed for {video_url} due to an unexpected error: {e}"
            )
            return None

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        if parsed.hostname in ["www.youtube.com", "youtube.com"]:
            if parsed.path == "/watch":
                return parse_qs(parsed.query).get("v", [None])[0]
            elif parsed.path.startswith("/shorts/"):
                return parsed.path.split("/")[-1]
        elif parsed.hostname == "youtu.be":
            return parsed.path.split("/")[-1]
        logger.warning(f"Could not extract video ID from URL: {url}")
        return None
