# cognitive-engine
**General-Purpose Cognitive Automation Platform**

---

## 🚀 Getting Started

### ✅ Requirements

- **Python 3.13+**

---

### ⚙️ Setup

#### 1. Create a Virtual Environment

In the root directory, run:

```bash
python -m venv venv
source venv/bin/activate
# On Windows use: venv\Scripts\activate

```

---

#### 2. Install Poetry

Install [Poetry](https://python-poetry.org/docs/cli/) for dependency management:

```bash
pip install -U pip setuptools
pip install poetry

```

---

#### 3. Install Dependencies

Use Poetry to install project dependencies:

```bash
poetry install --no-root

```

> *(Note: This installs pandas, selenium, pyyaml, openai, and other core libraries).*

---

#### 4. Set Up Pre-Commit Hooks

Install [pre-commit](https://pre-commit.ci/) hooks for static tests:

```bash
pre-commit install

```

---

## 📚 Documentation & Architecture

For a deeper understanding of how the platform works and how to configure it, please refer to the documentation located in the `docs/` folder:

- **[Architecture Overview](docs/ARCHITECTURE.md)**  
  High-level design, core concepts, and system diagram.

- **[Workflow Configuration Guide](docs/WORKFLOW_CONFIGURATION_GUIDE.md)**  
  Detailed guide on writing YAML workflows with examples.

---

## ▶️ How to Run

The engine is executed via the command line by pointing to a specific workflow configuration file.

**Workspace Architecture:** Every time you start a fresh run, the engine automatically creates an isolated, timestamped workspace directory (e.g., `outputs/2026-02-20_143000/`). All files, logs, and artifacts for that specific execution are safely stored there to prevent data clashes.

### Command Line Arguments

* **`--workflow`**
*(Required)* Path to the YAML configuration file.
* **`--resume`**
*(Optional)* Path to an existing workspace directory (e.g., `outputs/2026-02-20_143000`). Use this to resume a previous run that failed or was interrupted. The engine will read the existing `research.json` state and automatically skip already completed tasks.
* **`--debug`**
*(Optional)* Enable verbose logging for debugging purposes.

---

### Examples

**1. Starting a Fresh Run**
Run the engine with your target workflow:

```bash
python main.py --workflow workflows/fruit_salad_maker.yaml

```

*Look at the console output to see your newly generated workspace folder (e.g., `outputs/2026-02-20_091530`). You will find your processed results and `errors.log` inside it.*

**2. Resuming a Failed Run**
If the pipeline crashes (e.g., due to an API timeout) midway through a large batch, you do not need to start over. Simply pass the `--resume` flag with the path to the failed run's workspace:

```bash
python main.py --workflow workflows/fruit_salad_maker.yaml --resume outputs/2026-02-20_091530

```

*The engine will load the artifacts from that specific folder, safely append new errors to the existing log, and pick up exactly where it left off.*
