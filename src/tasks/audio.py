import logging
import os
import glob
from typing import Dict, Any
import torch

# Import whisper inside the class or method to avoid loading it if not used
# import whisper

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task

logger = logging.getLogger(__name__)


@register_task("AudioTranscribeTask")
class AudioTranscribeTask(PipelineTask):
    """
    Transcribes audio files using local OpenAI Whisper.

    Can operate in two modes:
    1.  **Context Mode**: Reads a list of dictionaries from a context key specified
        by `input_key`. Each dictionary must contain a 'url' key with the path
        to the audio file. Other metadata like 'title', 'source', 'date' are preserved.
    2.  **Glob Mode**: Finds audio files on the filesystem using a glob pattern
        specified by `input_path`.

    The output is a list of dictionaries, each representing a transcribed document,
    which is saved to the context key specified by `output_key`.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        input_key = config.get("input_key")
        output_key = config.get("output_key", "transcribed_docs")
        model_size = config.get("model_size", "base")

        # Part 1: Determine input source (Context key or file glob)
        is_context_mode = input_key is not None
        items_to_process = []

        if is_context_mode:
            # Mode 1: Get items from a context key (e.g., from a CSV loader)
            items = context.require(input_key)
            if not items:
                logger.warning(
                    f"Input key '{input_key}' is present but contains no items."
                )
                context.set(output_key, [])
                return context
            items_to_process = items
            logger.info(
                f"Found {len(items)} items to transcribe from context key '{input_key}'."
            )
        else:
            # Mode 2: Find files using a glob pattern (legacy)
            input_pattern = config.get("input_path")
            if not input_pattern:
                raise ValueError(
                    "AudioTranscribeTask requires 'input_key' (for context items) or 'input_path' (for file glob)."
                )

            files = glob.glob(input_pattern)
            if not files:
                logger.warning(
                    f"No audio files found matching pattern: {input_pattern}"
                )
                context.set(output_key, [])
                return context
            items_to_process = files  # The items are just file paths
            logger.info(
                f"Found {len(files)} audio files to transcribe from path '{input_pattern}'."
            )

        # Part 2: Load Whisper model (common to both modes)
        # Lazy import to keep startup fast for non-audio workflows
        import whisper

        device = "cuda" if torch.cuda.is_available() else "cpu"
        use_fp16 = device == "cuda"
        logger.info(f"Loading Whisper model '{model_size}' on device: {device.upper()}")

        try:
            model = whisper.load_model(model_size)
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

        # Part 3: Transcribe loop
        results = []
        if is_context_mode:
            # Process items from context
            for item in items_to_process:
                filepath = item.get("url")
                if not filepath or not isinstance(filepath, str):
                    logger.warning(f"Skipping item due to invalid 'url': {item}")
                    continue

                logger.info(f"Transcribing: {filepath}")
                try:
                    res = model.transcribe(filepath, fp16=use_fp16)
                    results.append(
                        {
                            "filename": f"{item.get('source', 'transcribed_audio')}.txt",
                            "content": res["text"].strip(),
                            "url": filepath,
                            "title": item.get("title"),
                            "source": item.get("source"),
                            "date": item.get("date"),
                        }
                    )
                except Exception as e:
                    logger.error(f"Transcribe failed for {filepath}: {e}")
        else:
            # Process files from glob (legacy)
            save_to_disk = config.get("save_to_disk", False)
            output_dir = config.get("output_dir", "./outputs/transcripts")
            if save_to_disk:
                os.makedirs(output_dir, exist_ok=True)

            for filepath in items_to_process:
                filename = os.path.basename(filepath)
                logger.info(f"Transcribing: {filename}...")
                try:
                    transcript_result = model.transcribe(filepath, fp16=use_fp16)
                    text = transcript_result["text"].strip()
                    doc_record = {
                        "filename": f"{filename}.txt",
                        "filepath": filepath,
                        "content": text,
                    }
                    results.append(doc_record)
                    if save_to_disk:
                        txt_path = os.path.join(output_dir, f"{filename}.txt")
                        with open(txt_path, "w", encoding="utf-8") as f:
                            f.write(text)
                        logger.debug(f"Saved raw transcript: {txt_path}")
                except Exception as e:
                    logger.error(f"Error transcribing {filename}: {e}")

        # Part 4: Update context
        context.set(output_key, results)
        logger.info(
            f"Transcribed {len(results)} files, result in context key '{output_key}'."
        )

        return context
