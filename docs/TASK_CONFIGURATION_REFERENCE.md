# Task Configuration Reference

This document is the single source of truth for all available `PipelineTask` implementations in the Cognitive Engine. It serves as a "menu" of capabilities for **Solutions Engineering** when composing YAML workflows.

---

## 1. Data Ingestion (Loaders & Extractors)

### `DirectoryLoader`

**Description:** Scans a directory for raw text files and loads their content into the `WorkflowContext`.
**Python Path:** `src.tasks.loaders.DirectoryLoader`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_path` | string | Yes | - | Glob pattern for input files (e.g., `./inputs/*.txt`) |
| `output_key` | string | No | `raw_files` | Context key to store the list of file dictionaries |

#### Example YAML

```yaml
- id: "load_raw_files"
  type: "DirectoryLoader"
  config:
    input_path: "./data/*.txt"
    output_key: "my_files"

```

---

### `ResearchCSVLoader`

**Description:** Parses a CSV with specific metadata columns (`url`, `title`, `source`, `date`) and routes items into text or audio queues based on file extension.
**Python Path:** `src.tasks.loaders.ResearchCSVLoader`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_file` | string | Yes | - | Path to the source CSV file |
| `output_text_key` | string | No | `text_queue` | Key for non-audio items |
| `output_audio_key` | string | No | `audio_queue` | Key for audio files (.mp3, .m4a, etc.) |

---

### `ContentExtractionTask`

**Description:** Iterates through a list of URLs and extracts cleaned text content using Selenium and BeautifulSoup.
**Python Path:** `src.tasks.extractors.ContentExtractionTask`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Context key containing the list of items to process |
| `output_key` | string | Yes | - | Key to store successfully extracted documents |
| `failure_key` | string | No | `failed_items` | Key to store items that failed automated extraction |

---

### `ManualReviewTask`

**Description:** A failover task that opens a visible browser for items that failed automated extraction, allowing the user to manually paste content.
**Python Path:** `src.tasks.extractors.ManualReviewTask`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_failure_key` | string | Yes | - | Key containing failed items (from ContentExtractionTask) |
| `output_success_key` | string | Yes | - | Key to append manually reviewed items to |
| `interactive` | boolean | No | `False` | Must be `True` to trigger the browser and input prompt |

---

## 2. Audio & Document Processing

### `AudioTranscribeTask`

**Description:** Transcribes audio files (local or from context URLs) using a local OpenAI Whisper model.
**Python Path:** `src.tasks.audio.AudioTranscribeTask`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | No* | - | Context key for items (Required if `input_path` is not provided) |
| `input_path` | string | No* | - | Glob pattern for local files (Required if `input_key` is not provided) |
| `output_key` | string | No | `transcribed_docs` | Key to store transcribed text documents |
| `model_size` | string | No | `base` | Whisper model size (tiny, base, small, medium, large) |

---

### `TextFileSplitterTask`

**Description:** Splits a single large text file into multiple documents based on a custom delimiter (e.g., `%%% filename`).
**Python Path:** `src.tasks.splitters.TextFileSplitterTask`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_file` | string | Yes | - | Path to the large text file |
| `output_key` | string | No | `split_docs` | Key for the resulting list of documents |
| `save_to_disk` | boolean | No | `False` | Whether to save individual split files to disk |

---

## 3. Transformation (The "Meat")

### `LLMTransformTask`

**Description:** Applies a single LLM prompt to one specific string input in the context.
**Python Path:** `src.tasks.transformers.LLMTransformTask`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Context key containing the raw text |
| `output_key` | string | Yes | - | Key to store the LLM-processed result |
| `prompt_file` | string | Yes | - | Path to the text file containing the prompt template |
| `model` | string | No | `default` | LLM model identifier (e.g., `gpt-4o`, `qwen2.5:14b`) |

---

### `BatchLLMTask`

**Description:** Iterates over a list of documents, processes each with an LLM, and preserves metadata.
**Python Path:** `src.tasks.transformers.BatchLLMTask`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Key containing a list of document dictionaries |
| `output_key` | string | Yes | - | Key to store the list of processed strings |
| `prompt_file` | string | Yes | - | Path to the prompt template file |
| `include_original` | boolean | No | `True` | Whether to append the original content to the output |
| `save_intermediate` | boolean | No | `False` | Write each processed file to disk immediately |

---

## 4. Aggregation & Output

### `TextAggregator`

**Description:** Joins a list of text strings into a single combined string with separators.
**Python Path:** `src.tasks.aggregators.TextAggregator`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Key containing the list of strings |
| `output_key` | string | Yes | - | Key for the final combined string |
| `separator` | string | No | `\n\n---\n\n` | String used to join the items |

---

### `CitationCompilerTask`

**Description:** Generates a formatted Markdown "Sources" section from a list of document metadata.
**Python Path:** `src.tasks.aggregators.CitationCompilerTask`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Key containing documents with metadata (url, title, etc.) |
| `output_key` | string | Yes | - | Key for the compiled Markdown string |

---

### `ReportWriterTask`

**Description:** Compiles multiple context variables into a final multi-section Markdown report.
**Python Path:** `src.tasks.writers.ReportWriterTask`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `filename` | string | Yes | - | Output path for the final Markdown file |
| `sections` | list | Yes | - | List of dicts: `{'title': '...', 'content_key': '...'}` |

#### Example YAML

```yaml
- id: "write_final_report"
  type: "ReportWriterTask"
  config:
    filename: "./outputs/research_report.md"
    sections:
      - title: "Executive Summary"
        content_key: "summary_text"
      - title: "Detailed Analysis"
        content_key: "combined_content"
      - title: "Citations"
        content_key: "references"

```

---

## 5. Utilities

### `ListMergerTask`

**Description:** Merges multiple lists from different context keys into a single list.
**Python Path:** `src.tasks.utilities.ListMergerTask`

#### Configuration (`config` block)

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `inputs` | list | Yes | - | List of context keys to merge (e.g., `['list1', 'list2']`) |
| `output_key` | string | Yes | - | Key for the resulting merged list |

---

**[IMPORTANT]**


When adding new tasks to the codebase, ensure they are registered in `src/core/registry.py`. Update this reference by adding a new section under the appropriate category, ensuring you provide a one-line description, the full Python path, and a detailed configuration table.

---
