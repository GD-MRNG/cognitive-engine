import logging
from typing import Dict, Any

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.utils.notifications import DiscordNotifier

logger = logging.getLogger(__name__)


@register_task("NotificationTask")
class NotificationTask(PipelineTask):
    """
    Sends a configured message to Discord during pipeline execution.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        message = config.get("message", "Pipeline step completed.")
        level = config.get("level", "info")

        notifier = DiscordNotifier()
        notifier.send(message, level=level)

        logger.info(f"NotificationTask: Sent '{level}' alert.")
        return context
