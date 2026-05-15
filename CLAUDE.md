# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A declarative, configuration-driven cognitive automation platform — a workflow engine that uses LLMs to orchestrate data transformation, extraction, and synthesis pipelines. Workflows are defined in YAML; Python implements the individual tasks.

## Commands

```bash
# Install dependencies
poetry install --no-root

# Run a workflow
python main.py --workflow <path_to_workflow.yaml>

# Resume a workflow from a checkpoint
python main.py --workflow <path_to_workflow.yaml> --resume outputs/<workspace_dir>

# Run with debug logging
python main.py --workflow <path_to_workflow.yaml> --debug

# Lint / format
ruff check .
ruff format .

# Pre-commit (runs ruff, pyupgrade, file checks)
pre-commit run --all-files
```

There is no test suite currently. The `.env` file holds API keys (`POE_API_KEY`, `GEMINI_API_KEY`, `YOUTUBE_TRANSCRIPT_API_KEY`, `DISCORD_WEBHOOK_URL`).

## Architecture

### Execution Flow

`main.py` → `WorkflowEngine.run()` → sequential task execution via `TaskRegistry`

1. `main.py` parses CLI args, creates a timestamped workspace under `outputs/YYYY-MM-DD_HHMMSS/`
2. `WorkflowEngine` loads the YAML workflow and iterates over `steps`
3. Each step's `type` maps to a registered task class
4. Tasks receive and mutate the shared `WorkflowContext` (a dict-like blackboard)
5. `WorkflowContext` state is checkpointed to JSON so workflows can resume

### Core Abstractions (`src/core/`)

| Component | Role |
|---|---|
| `PipelineTask` | Abstract base — all tasks implement `execute(context, config)` |
| `WorkflowContext` | Shared state passed between every task (Blackboard Pattern) |
| `WorkflowEngine` | Loads YAML, resolves tasks from registry, runs them sequentially |
| `TaskRegistry` | `@register_task("name")` decorator maps YAML `type:` to Python class |
| `ProductionLLMClient` | Multi-provider LLM client (Poe → Gemini → Ollama fallback chain) with output cleaning |

### Workflow YAML Shape

```yaml
name: "Workflow Name"
steps:
  - id: step_id
    type: RegisteredTaskName   # must match @register_task("name")
    config:
      key: value
```

### Tasks (`src/tasks/`)

25+ tasks registered with `@register_task`. Broad categories:

- **Loaders**: `UrlListLoader`, `DirectoryLoader`, `SourceCSVLoader`
- **Extractors**: `UniversalExtractorTask`, `ContentScrapingTask`, `TitleScrapingTask`, `SourceGatheringTask`, `ManualReviewTask`
- **Transformers**: `LLMEnrichmentTask`, `BatchLLMTask`, `RegionCategorizationTask`, `SummarizationTask`
- **Aggregators / Writers**: `TextAggregator`, `CitationCompilerTask`, `ReportWriterTask`, `ArtifactCheckpointTask`
- **Delivery**: `CloudArchivalTask`, `GitPublisherTask`, `NotificationTask`
- **Utilities**: `UserConfirmationTask`, `TextFileSplitterTask`, `BookDigestTask`, `ListMergerTask`, `StrategicSynthesisTask`, `ReportGenerationTask`

### Utilities (`src/utils/`)

- `document.py` — `TextExtractor`, `PDFExtractor`, `EpubExtractor`
- `io.py` — `CheckpointManager` (JSON persistence), `FileManager`
- `web.py`, `youtube.py`, `audio.py` — specialized content extractors
- `formatting.py`, `notifications.py` — helpers

## Extending the System

### Adding a New Task

1. Create a file in `src/tasks/`
2. Inherit from `PipelineTask` and decorate:

```python
from src.core.interfaces import PipelineTask
from src.core.registry import register_task

@register_task("MyTaskName")
class MyTask(PipelineTask):
    def execute(self, context: dict, config: dict) -> dict:
        # read from context / config, write results back to context
        return context
```

3. Import the module in `src/tasks/__init__.py` so the decorator fires on startup.

### Key Design Principles

- **"Logic Sandwich"**: Wrap probabilistic LLM calls between deterministic pre/post-processing steps.
- **Declarative policy, imperative mechanism**: YAML controls flow and parameters; Python implements behaviour. Never hard-code workflow logic in task classes.
- **Map-Reduce pattern**: `BatchLLMTask` processes list items individually; `TextAggregator` combines results.

## Docs

The `docs/` directory has detailed references:

- `ARCHITECTURE.md` — core design rationale
- `WORKFLOW_CONFIGURATION_GUIDE.md` — full task parameter reference
- `DEVELOPMENT_GUIDE.md` — "Logic Sandwich" philosophy and inner/outer loop patterns
- `SOURCES_CSV_GUIDE.md` — format for `SourceCSVLoader`
- `FILE_NAMING_CONVENTION.md` — output file naming standards
