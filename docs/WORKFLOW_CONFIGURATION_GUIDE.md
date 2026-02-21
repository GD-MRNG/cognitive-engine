# Workflow Configuration Guide

Workflows in the Cognitive Engine are defined using YAML. A workflow is essentially a list of **steps**, executed in order.

## Structure of a Workflow File

```yaml
name: "Name of your Workflow"

steps:
  - id: "unique_step_identifier"
    type: "RegisteredTaskClassName"
    config:
      # Task-specific configuration parameters go here
      key: value

```

### Generic Example: "Fruit Salad Maker"

This example demonstrates the logic of passing data between steps without referencing a specific real-world use case.

```yaml
name: "Fruit Salad Automation"

steps:
  # STEP 1: INGEST (The Loader)
  # Reads raw items from a source.
  - id: "buy_fruit"
    type: "DirectoryLoader"
    config:
      input_path: "./fridge/*.txt"   # Where to look
      output_key: "raw_ingredients"  # Variable name for the data in memory

  # STEP 2: PROCESS (The Transformer / Map)
  # Performs an action on every single item found in Step 1.
  - id: "chop_fruit"
    type: "BatchLLMTask"
    config:
      input_key: "raw_ingredients"   # Grab the data from Step 1
      output_key: "chopped_pieces"   # Save the result here
      prompt_file: "prompts/chop_instructions.txt" # Instructions for the LLM
      save_intermediate_files: true  # Save intermediate files to the workspace

  # STEP 3: AGGREGATE (The Reduce)
  # Combines all individual processed items into one bowl.
  - id: "mix_bowl"
    type: "TextAggregator"
    config:
      input_key: "chopped_pieces"    # Grab the list from Step 2
      output_key: "mixed_salad"      # Save the combined blob here
      separator: "\n---\n"           # How to separate items

  # STEP 4: FINALIZE (The Writer)
  # Saves the final result to a file in the workspace.
  - id: "serve_salad"
    type: "ReportWriterTask"
    config:
      filename: "final_salad.md"
      sections:
        - title: "Delicious Salad"
          content_key: "mixed_salad" # Write the data from Step 3

```

## Best Practices

* **Unique IDs**: Give every step a unique id. This helps with debugging logs.
* **Flow Connectivity**: Ensure the `output_key` of one step matches the `input_key` of the next step that needs that data.
* **Workspace Paths**: All relative output paths automatically resolve to the isolated run workspace (e.g., `outputs/YYYY-MM-DD_RunID/`). Input paths (like `./inputs` or `prompts/`) generally resolve relative to the root directory where `main.py` is executed.

---

# Task Configuration Reference

This document is the single source of truth for all available `PipelineTask` implementations in the Cognitive Engine. It serves as a "menu" of capabilities for **Solutions Engineering** when composing YAML workflows.

---

## 1. Data Ingestion (Loaders & Extractors)

### `SourceCSVLoader`

**Description:** Loads a dynamic source registry CSV into the context, validating the standard schema (`id, name, url, type, rank, tags, format`) and allowing tag/type filtering.
**Python Path:** `src.tasks.loaders.SourceCSVLoader`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_file` | string | Yes | - | Path to the source CSV file |
| `output_key` | string | No | `raw_sources` | Context key to store the sources |
| `filter_tag` | string | No | - | Only load sources containing this tag |
| `filter_type` | string | No | - | Only load sources matching this type (e.g., `datapoint`, `analysis`) |

### `UrlListLoader`

**Description:** Reads a text file containing one URL/target per line. Supports optional comma-separated metadata (`url,title,source,date`).
**Python Path:** `src.tasks.loaders.UrlListLoader`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_file` | string | Yes | - | Path to the `.txt` URL list file |
| `output_key` | string | No | `raw_targets` | Context key to store the list of targets |

### `DirectoryLoader`

**Description:** Scans a directory for raw text files and loads their content into the `WorkflowContext`.
**Python Path:** `src.tasks.loaders.DirectoryLoader`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_path` | string | Yes | - | Glob pattern for input files (e.g., `./inputs/*.txt`) |
| `output_key` | string | No | `raw_files` | Context key to store the list of file dictionaries |

### `SourceGatheringTask`

**Description:** Orchestrates the ingestion routing. Splits breadth scanning (automated) and depth scanning (waits for manual Human-in-the-Loop curation of links).
**Python Path:** `src.tasks.extractors.SourceGatheringTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | No | `raw_sources` | Context key containing raw sources from the loader |
| `output_key` | string | No | `research_data` | Context key to store the research manifest |
| `checkpoint_file` | string | No | `research.json` | Workspace artifact filename to persist data state |
| `link_file` | string | No | `inputs/curated_links.txt` | Path to the file where manual links are pasted |

### `ContentScrapingTask`

**Description:** A unified extraction router. Iterates over the manifest and fetches content using appropriate internal extractors (Web, YouTube, Podcast, etc.).
**Python Path:** `src.tasks.extractors.ContentScrapingTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `target_key` | string | No | `research_data` | Key representing the data manifest |
| `checkpoint_file` | string | No | `research.json` | Workspace artifact file to load/save state |

### `TitleScrapingTask`

**Description:** Enriches items in the manifest with titles, skipping if already present.
**Python Path:** `src.tasks.extractors.TitleScrapingTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `target_key` | string | No | `research_data` | Key representing the data manifest |
| `checkpoint_file` | string | No | `research.json` | Workspace artifact filename |
| `target_types` | list | No | `["analysis"]` | Which source types to target |
| `force_refresh` | boolean | No | `False` | Ignore existing titles and re-scrape |

### `UniversalExtractorTask`

**Description:** Fast-lane, brute-force extractor. Bypasses metadata scraping and routes URLs directly to internal utilities based on string matching.
**Python Path:** `src.tasks.extractors.UniversalExtractorTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Context key containing the targets |
| `output_key` | string | No | `extracted_docs` | Context key for successful document extractions |

### `ManualReviewTask`

**Description:** Human-in-the-Loop (HITL) fallback. Identifies items missing specified fields, opens the browser, and prompts user via CLI.
**Python Path:** `src.tasks.extractors.ManualReviewTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `target_key` | string | No | `research_data` | Context key containing the data list |
| `checkpoint_file` | string | No | `research.json` | Checkpoint to save atomic manual updates to |
| `target_types` | list | No | `["analysis"]` | Which item types to enforce manual review on |
| `missing_fields` | list | No | `["content"]` | The specific fields to check for manual override |

---

## 2. Document Processing & Splitting

### `TextFileSplitterTask`

**Description:** Splits a single large text file into multiple documents based on a custom regex delimiter.
**Python Path:** `src.tasks.splitters.TextFileSplitterTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_file` | string | Yes | - | Path to the large text file |
| `output_key` | string | No | `split_docs` | Key for the resulting list of documents |
| `save_to_disk` | boolean | No | `False` | Save individual split files to the workspace |
| `output_dir` | string | No | `split_files` | Workspace sub-folder for outputting raw splits |
| `delimiter_pattern` | string | No | `^%%%\s+(.+)$` | Regex pattern defining split chunks |

### `BookDigestTask`

**Description:** Ingests binary books (`.pdf`, `.epub`), optionally splits them by chapter, and converts them to formatted text.
**Python Path:** `src.tasks.splitters.BookDigestTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_file` | string | Yes | - | Path to the book file |
| `output_key` | string | No | `digested_chapters` | Context key for chapter documents |
| `split_chapters` | boolean | No | `True` | Set `False` to merge the entire book into one document |
| `split_pattern` | string | No | `(?i)(?=Chapter|^# )` | Regex used to find chapters in PDFs |
| `save_to_disk` | boolean | No | `False` | Write text chunks to workspace |
| `output_dir` | string | No | `digested_books` | Workspace folder for chunks |
| `wrap_text` | boolean | No | `True` | Apply standard text wrapping |
| `line_width` | int | No | `80` | Number of characters per line if wrapping is active |

---

## 3. Transformation & Enrichment

### `LLMTransformTask`

**Description:** Applies a single LLM prompt to one specific string input in the context.
**Python Path:** `src.tasks.transformers.LLMTransformTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Context key containing the raw text |
| `output_key` | string | Yes | - | Key to store the LLM-processed result |
| `prompt_file` | string | Yes | - | Path to the text file containing the prompt template |
| `model` | string | No | `default` | LLM model identifier (e.g., `gemini-2.5-flash`, `qwen2.5:14b`) |

### `BatchLLMTask`

**Description:** Iterates over a list of documents, maps an LLM over each, and optionally saves intermediate markdown files.
**Python Path:** `src.tasks.transformers.BatchLLMTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Key containing a list of document dictionaries |
| `output_key` | string | Yes | - | Key to store the list of processed strings |
| `prompt_file` | string | Yes | - | Path to the prompt template file |
| `include_original` | boolean | No | `True` | Append the original raw content below the summary |
| `save_intermediate` | boolean | No | `False` | Output individual files to the workspace |
| `output_dir` | string | No | `processed_files` | Folder in the workspace for intermediate files |
| `filename_suffix` | string | No | `_processed` | Suffix for saved files |

### `RegionCategorizationTask`

**Description:** Sub-class of `LLMEnrichmentTask`. Infers and tags a standardized region (e.g., 'North America') based on title and content.
**Python Path:** `src.tasks.transformers.RegionCategorizationTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `target_key` | string | No | `research_data` | Context key holding the manifest dictionary |
| `output_key` | string | No | `enrichment_result` | Dictionary key to write output to |
| `checkpoint_file` | string | No | `research.json` | Checkpoint to save atomic state |
| `target_types` | list | No | `[]` | Limit task to specific types (e.g., `["analysis"]`) |
| `input_fields` | list | No | `["title", "content"]` | Document attributes to provide to the LLM |
| `max_chars` | int | No | `3000` | Limits context size to prevent exceeding LLM limits |

### `SummarizationTask`

**Description:** Sub-class of `LLMEnrichmentTask`. Enriches items by summarizing their content directly inside the data manifest.
**Python Path:** `src.tasks.transformers.SummarizationTask`

*(Uses the exact same parameters as `RegionCategorizationTask`)*

---

## 4. Synthesis & Aggregation

### `StrategicSynthesisTask`

**Description:** The "Brain" of the intelligence pipeline. Aggregates enriched data, applies global and regional prompts, and updates the artifact's `intelligence` block.
**Python Path:** `src.tasks.synthesis.StrategicSynthesisTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `target_key` | string | No | `research_data` | Context key holding the manifest |
| `checkpoint_file` | string | No | `research.json` | Golden artifact file |
| `group_by` | string | No | `region` | Grouping key for category-level assessments |
| `max_context_chars` | int | No | `0` | Truncates aggregated texts (`0` = no limit) |
| `global_prompt_file` | string | No | `.../global_...` | Prompt template for the global summary |
| `category_prompt_file` | string | No | `.../category_...` | Prompt template for the regional summaries |
| `force_refresh` | boolean | No | `False` | Skip LLM caches and regenerate reports |

### `TextAggregator`

**Description:** Joins a list of text strings into a single combined string with separators.
**Python Path:** `src.tasks.aggregators.TextAggregator`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Key containing the list of strings |
| `output_key` | string | Yes | - | Key for the final combined string |
| `separator` | string | No | `\n\n---\n\n` | String used to join the items |
| `save_to_file` | string | No | - | Optional filename to save aggregated string in workspace |

### `CitationCompilerTask`

**Description:** Generates a formatted Markdown bibliography section gracefully utilizing available metadata (Title, Source, Date, URL).
**Python Path:** `src.tasks.aggregators.CitationCompilerTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_key` | string | Yes | - | Key containing documents with metadata |
| `output_key` | string | Yes | - | Key for the compiled Markdown string |

---

## 5. Writing & Delivery

### `ReportGenerationTask`

**Description:** Compiles the complete intelligence block using Jinja2 templating to construct a complex markdown briefing. Integrates automatic time-shifting for Jekyll compatibility.
**Python Path:** `src.tasks.synthesis.ReportGenerationTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `checkpoint_file` | string | No | `research.json` | The golden artifact to draw `intelligence` from |
| `template_file` | string | No | `.../weekly_report.md.j2` | Path to the Jinja2 file |
| `output_dir` | string | No | `reports` | Workspace directory to output the markdown |
| `report_suffix` | string | No | `Weekly-Brief` | Identifiable suffix for the final filename |

### `ReportWriterTask`

**Description:** Compiles multiple context strings sequentially into a multi-section Markdown report.
**Python Path:** `src.tasks.writers.ReportWriterTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `filename` | string | Yes | - | Final output filename inside the workspace |
| `sections` | list | Yes | - | List of dicts: `{'title': '...', 'content_key': '...'}` |

### `ArtifactCheckpointTask`

**Description:** Manually dumps specific context keys into a JSON file, creating an arbitrary persistent artifact.
**Python Path:** `src.tasks.writers.ArtifactCheckpointTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input_keys` | list | Yes | - | List of context keys to back up |
| `output_file` | string | No | `research.json` | Destination JSON in the workspace |

### `CloudArchivalTask`

**Description:** Zips the active workspace directory and uploads it to an AWS S3 Bucket for historical backup.
**Python Path:** `src.tasks.delivery.CloudArchivalTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `bucket_name` | string | No | `cognitive-engine-history` | Destination S3 Bucket |
| `s3_prefix` | string | No | `general_research` | Sub-folder prefix inside the bucket |

### `GitPublisherTask`

**Description:** Automates pushing reports to a web repository. Copies generated markdown, stages it, and performs `git push`.
**Python Path:** `src.tasks.delivery.GitPublisherTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `repo_path` | string | Yes | - | Absolute local path to your target Git repository |
| `dest_folder` | string | No | `_posts` | Destination folder relative to the repository root |
| `commit_message` | string | No | `Auto-Publish: New...` | Git commit message |
| `branch` | string | No | `main` | Target branch to push to |

---

## 6. Utilities & Notifications

### `NotificationTask`

**Description:** Sends status messages to an external Discord webhook (requires `DISCORD_WEBHOOK_URL` in environment).
**Python Path:** `src.tasks.notifications.NotificationTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `message` | string | No | `Pipeline step completed.` | Text payload |
| `level` | string | No | `info` | Alert type (`info`, `success`, `warning`, `error`, `hitl`) |

### `UserConfirmationTask`

**Description:** Pauses the pipeline's thread. Use this to allow human inspection of intermediate files in the workspace. Resumes via CLI 'Enter'.
**Python Path:** `src.tasks.utilities.UserConfirmationTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `message` | string | No | `Pipeline paused...` | Text shown to the user on the command line |

### `ListMergerTask`

**Description:** Merges multiple lists from different context keys into a single combined list.
**Python Path:** `src.tasks.utilities.ListMergerTask`

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `inputs` | list | Yes | - | List of context keys to merge (e.g., `['queue_a', 'queue_b']`) |
| `output_key` | string | Yes | - | Key for the resulting merged list |
