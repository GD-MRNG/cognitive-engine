import os
from abc import ABC, abstractmethod
from typing import Dict, Any
from src.core.context import WorkflowContext


class PipelineTask(ABC):
    """
    The atomic unit of work in the Cognitive Engine.
    All components (Extractors, Summarizers, Loaders) must inherit from this.
    """

    def get_workspace_path(self, context: WorkflowContext, filename: str) -> str:
        """
        Resolves a filename relative to the current run's workspace.
        """
        workspace = context.get("_workspace_dir", "outputs")

        if os.path.isabs(filename):
            return filename

        return os.path.join(workspace, filename)

    @abstractmethod
    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        """
        Performs the specific task logic.

        Args:
            context: The shared state object containing inputs.
            config: A dictionary of runtime parameters (e.g., paths, model names).

        Returns:
            The modified context object.
        """
        pass
