import logging
from typing import Dict, Any
from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task

logger = logging.getLogger(__name__)


@register_task("ListMergerTask")
class ListMergerTask(PipelineTask):
    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        merged = []
        for key in config.get("inputs", []):
            merged.extend(context.get(key, []))
        context.set(config.get("output_key"), merged)
        return context


@register_task("UserConfirmationTask")
class UserConfirmationTask(PipelineTask):
    """
    Pauses the pipeline execution to allow the user to inspect intermediate outputs.
    Resumes only when the user presses Enter.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        message = config.get("message", "Pipeline paused. Press Enter to continue...")

        print(f"\n{'-'*60}")
        print("🛑 USER INTERVENTION REQUIRED")
        print(f"   {message}")
        print(f"{'-'*60}\n")

        # This blocks the thread until Enter is pressed
        input(">> Press [ENTER] to resume pipeline...")

        logger.info("User confirmed. Resuming pipeline...")
        return context
