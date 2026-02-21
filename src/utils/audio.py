import logging
import os
import torch

logger = logging.getLogger(__name__)


class AudioExtractor:
    """
    Audio transcription utility using local OpenAI Whisper.
    Supports common formats handled by ffmpeg (mp3, m4a, wav, flac).
    """

    def __init__(self, model_size="base"):
        self.model_size = model_size
        self.model = None
        self.use_fp16 = False

    def _load_model(self):
        """Lazy loads the Whisper model to keep pipeline startup fast."""
        if self.model is None:
            import whisper

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(
                f"Loading Whisper model '{self.model_size}' on device: {device.upper()}"
            )
            try:
                self.model = whisper.load_model(self.model_size)
                self.use_fp16 = device == "cuda"
            except Exception as e:
                logger.error(f"Failed to load Whisper model: {e}")
                raise

    def transcribe(self, filepath: str) -> str:
        """
        Transcribes a local audio file into text.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Audio file not found at path: {filepath}")

        self._load_model()

        logger.info(f"Transcribing audio file: {filepath}")
        try:
            # Whisper handles the chunking and decoding under the hood
            result = self.model.transcribe(filepath, fp16=self.use_fp16)
            text = result["text"].strip()

            if not text:
                logger.warning(f"Transcription resulted in empty text for {filepath}")
            else:
                logger.info(
                    f"Transcription successful: {len(text)} characters extracted."
                )

            return text
        except Exception as e:
            logger.error(f"Error transcribing {filepath}: {e}")
            raise
