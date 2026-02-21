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

### Basic Usage

```bash
python main.py --workflow workflows/fruit_salad_maker.yaml
```

---

### Command Line Arguments

- **`--workflow`**  
  *(Required)* Path to the YAML configuration file.

- **`--debug`**  
  *(Optional)* Enable verbose logging for debugging purposes.

---

### Example: Running the University Notes Workflow

Ensure you have your raw fruit files in `inputs/`.

Run the engine:

```bash
python main.py --workflow workflows/fruit_salad_maker.yaml
```

Find your processed fruit salad in `outputs/`.
