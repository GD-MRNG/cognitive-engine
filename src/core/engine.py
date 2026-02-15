import yaml
import logging
import os
from typing import Dict, Any

from src.core.context import WorkflowContext
from src.core.registry import get_task_class
from src.core.interfaces import PipelineTask

# Import all tasks so they register themselves
import src.tasks.loaders  # noqa: F401
import src.tasks.transformers  # noqa: F401
import src.tasks.aggregators  # noqa: F401
import src.tasks.writers  # noqa: F401
import src.tasks.splitters  # noqa: F401
import src.tasks.audio  # noqa: F401
import src.tasks.extractors  # noqa: F401
import src.tasks.utilities  # noqa: F401
import src.tasks.synthesis  # noqa: F401

logger = logging.getLogger(__name__)


class WorkflowEngine:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.workflow_config = self._load_config()
        self.context = WorkflowContext()

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Workflow config not found: {self.config_path}")
        with open(self.config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def run(self):
        workflow_name = self.workflow_config.get("name", "Unnamed Workflow")
        steps = self.workflow_config.get("steps", [])

        logger.info(f"=== Starting Workflow: {workflow_name} ===")

        for i, step in enumerate(steps):
            step_id = step.get("id", f"step_{i}")
            task_type = step.get("type")
            task_config = step.get("config", {})

            logger.info(f"--- Running Step {i+1}: {step_id} ({task_type}) ---")

            try:
                # 1. Instantiate Task
                task_class = get_task_class(task_type)
                task_instance: PipelineTask = task_class()

                # 2. Execute Task
                self.context = task_instance.execute(self.context, task_config)

            except Exception as e:
                logger.critical(
                    f"Workflow failed at step '{step_id}': {e}", exc_info=True
                )
                raise

        logger.info(f"=== Workflow '{workflow_name}' Completed Successfully ===")
