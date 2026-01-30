# DEVELOPMENT GUIDE

This document serves as the primary framework for developing new workflows and expanding the capabilities of the **Cognitive Engine**. It is designed to help you maintain a clear view of the system's architecture and the "Meta-Loop" of development.

---

## 1. The Core Philosophy: The Logic Sandwich

To cut through the industry hype, we view every AI system as a **Logic Sandwich**. This "X-ray" heuristic ensures that we maintain a clear distinction between probabilistic "magic" and deterministic engineering.

* **Top Bun (Deterministic Pre-Processing):**
* **Logic:** Never ask an LLM to do what a regex, SQL query, or simple algorithm can accomplish.
* **Role:** Reducing entropy and cleaning data (loading, splitting, extracting) to maximize the quality of the context window.


* **The Meat (Probabilistic Inference):**
* **Logic:** The LLM is a stateless text transformation function with no memory.
* **Role:** Performing the "fuzzy" cognitive work—transforming unstructured input into structured intent or creative prose.


* **Bottom Bun (Deterministic Post-Processing):**
* **Logic:** The LLM describes an action; the engine executes it. Never let the model touch the "metal" directly.
* **Role:** Grounding the output in reality via parsing (JSON/Markdown), validation, and executing side effects like writing files.



---

## 2. The Development Lifecycle

Development follows two concentric circles: the **Inner Loop** for configuration and the **Outer Loop** for core engine expansion.

### Phase 1: Definition (The "What")

* Identify the **Input** (e.g., MP3s, CSVs, PDFs) and the desired **Output** (e.g., Markdown report, JSON summary).

### Phase 2: Gap Analysis (The "How")

* Consult the "Lego Box" (`src/tasks/`).
* **Decision:** If all required tasks exist, stay in the **Inner Loop**. If a capability is missing (e.g., you need to talk to a new API), trigger the **Outer Loop**.

### Phase 3: The Fork (Build vs. Config)

* **Path A: Inner Loop (Configuration):**
* **Work:** Compose YAML files and write prompt templates.
* **Speed:** Minutes.


* **Path B: Outer Loop (Platform Engineering):**
* **Work:** Write new Python tasks in `src/tasks/` and register them.
* **Speed:** Hours/Days.
* **Goal:** Build a generic "brick" that solves the current problem *and* future ones.



---

## 3. Best Practices

### Mechanism vs. Policy

* **Mechanism (Python):** *How* to do something (e.g., "Read a file"). This belongs in `src/tasks`.
* **Policy (YAML/Prompts):** *What* to do (e.g., "Summarize this lecture"). This belongs in the configuration files.
* **Rule of Thumb:** If you are writing domain-specific words (like "Geopolitics" or "University") inside a Python file, you are making a mistake.

### The Rule of Three (Generalization)

* When forced into the **Outer Loop**, do not build a task for a single specific problem.
* **Bad:** `BBCNewsScraperTask`
* **Good:** `WebScraperTask` (Accepts a generic URL or selector strategy).

### Prompts are Code

* Treat prompt templates as first-class software assets.
* Store them in `prompts/`, use version control, and give them semantic names (e.g., `analysis_to_action.txt`) rather than generic versions.

---

## 4. Summary of Design Patterns

* **Inversion of Control (IoC):** The YAML configuration controls the flow, not the Python code.
* **Blackboard Pattern:** Tasks communicate only through the shared `WorkflowContext` (the "blackboard").
* **Map-Reduce:** Use `BatchLLMTask` to map over items and `TextAggregator` to reduce them into a final product.
