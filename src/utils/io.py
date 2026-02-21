import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Standardized utility for handling 'Golden Artifact' (JSON) I/O.
    """

    @staticmethod
    def load(filepath: str) -> Dict[str, Any]:
        """
        Loads JSON file as a Dictionary.
        Returns an empty dict if file doesn't exist or is invalid.
        """
        if not os.path.exists(filepath):
            return {}

        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.error(
                    f"Checkpoint file {filepath} is not a dictionary. Returning empty dict."
                )
                return {}

            return data
        except Exception as e:
            logger.warning(f"Checkpoint load failed for {filepath}: {e}")
            return {}

    @staticmethod
    def save(filepath: str, data: Dict[str, Any]) -> None:
        """
        Atomically saves the artifact to disk.
        Uses a .tmp file + rename to prevent data corruption during write.
        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            # 1. Write to a temporary file first
            temp_path = f"{filepath}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # 2. Atomic rename (overwrites target instantly)
            os.replace(temp_path, filepath)

        except Exception as e:
            logger.error(f"Checkpoint save failed for {filepath}: {e}")


class FileManager:
    """
    Standardized utility for handling generic file operations (Text, Markdown, HTML).
    """

    @staticmethod
    def save_text(filepath: str, content: str) -> None:
        """
        Saves text content to a file. Automatically creates missing parent directories.
        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            logger.debug(f"Saved file: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save file to {filepath}: {e}")
            raise
