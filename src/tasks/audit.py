import datetime
import json
import logging
import os
from collections import Counter
from typing import Any, Dict

from src.core.context import WorkflowContext
from src.core.interfaces import PipelineTask
from src.core.registry import register_task

logger = logging.getLogger(__name__)


def _build_section_a(items: list, input_fields: list) -> str:
    lines = ["### A. Input Quantification\n"]
    for field in input_fields:
        lines.append(f"**{field}**")
        sample = next((item.get(field) for item in items if item.get(field) is not None), None)
        if isinstance(sample, list):
            counts = Counter(tag for item in items for tag in item.get(field, []))
        else:
            counts = Counter(item.get(field) for item in items)
        lines.append("| value | count |")
        lines.append("|-------|-------|")
        for value, count in sorted(counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {value} | {count} |")
        lines.append("")
    return "\n".join(lines)


def _build_section_b(items: list, workload_fields: list) -> str:
    total = len(items)
    lines = [
        "### B. Processing Workload\n",
        "| field | total items | completed | pending |",
        "|-------|-------------|-----------|---------|",
    ]
    for field in workload_fields:
        completed = sum(1 for item in items if item.get(field))
        pending = total - completed
        lines.append(f"| {field} | {total} | {completed} | {pending} |")
    lines.append("")
    return "\n".join(lines)


@register_task("PipelineAuditTask")
class PipelineAuditTask(PipelineTask):
    def execute(self, context: WorkflowContext, config: Dict[str, Any]) -> WorkflowContext:
        checkpoint_file = config.get("checkpoint_file")
        target_key = config.get("target_key", "research_data")
        input_fields = config.get("input_fields", [])
        workload_fields = config.get("workload_fields", [])
        report_suffix = config.get("report_suffix", "Audit-Report")
        output_dir = config.get("output_dir", "reports")
        force_refresh = config.get("force_refresh", False)

        if not checkpoint_file:
            raise ValueError("PipelineAuditTask requires 'checkpoint_file' in config.")

        checkpoint_path = self.get_workspace_path(context, checkpoint_file)

        # Resumability: skip if report already exists
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        report_path = self.get_workspace_path(
            context, os.path.join(output_dir, f"{date_str}-{report_suffix}.md")
        )
        if os.path.exists(report_path) and not force_refresh:
            logger.info(f"Audit report already exists, skipping: {report_path}")
            return context

        # Load checkpoint
        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        with open(checkpoint_path, encoding="utf-8") as f:
            checkpoint_data = json.load(f)
        items = checkpoint_data.get(target_key, [])
        logger.info(f"PipelineAuditTask: loaded {len(items)} items from '{checkpoint_path}'")

        sections = []

        if input_fields:
            sections.append(_build_section_a(items, input_fields))
            logger.info("Section A complete.")

        if workload_fields:
            sections.append(_build_section_b(items, workload_fields))
            logger.info("Section B complete.")

        combined = "\n\n".join(sections)
        if combined:
            logger.info("=== Audit Output ===\n" + combined)

        return context
