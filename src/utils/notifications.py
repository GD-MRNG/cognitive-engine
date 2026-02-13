import logging
import os
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """
    Utility to send alerts to a Discord Webhook.
    Reads 'DISCORD_WEBHOOK_URL' and 'DISCORD_USER_ID' from environment variables.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.user_id = os.getenv("DISCORD_USER_ID")  # Optional: for @mentions

        if not self.webhook_url:
            logger.warning(
                "DiscordNotifier: No Webhook URL found. Notifications disabled."
            )

    def send(self, message: str, level: str = "info") -> bool:
        """
        Sends a formatted message to Discord.
        Returns True if successful, False otherwise.
        """
        if not self.webhook_url:
            return False

        # Format Message
        # Add a ping if it's a critical alert or HITL request
        prefix = ""
        if self.user_id and level in ["critical", "hitl"]:
            prefix = f"<@{self.user_id}> "

        # Add emoji indicators
        emoji_map = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "🚨",
            "hitl": "🛑 **ACTION REQUIRED**",
        }
        emoji = emoji_map.get(level, "📢")

        full_content = f"{prefix}{emoji} {message}"

        # Send Request
        payload = {"content": full_content}

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=5)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False
