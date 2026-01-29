from typing import Dict, Any
from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task


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
