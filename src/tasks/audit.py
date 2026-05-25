import datetime
import json
import logging
import os
from collections import Counter
from typing import Any, Dict

from src.core.context import WorkflowContext
from src.core.interfaces import PipelineTask
from src.core.llm import get_llm_client
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


def _build_section_c(items: list, quality_fields: dict) -> str:
    lines = ["### C. Output Quality\n"]
    for field, thresholds in quality_fields.items():
        min_chars = thresholds.get("min_chars", 0)
        total = len(items)
        missing, too_short, flagged = [], [], []

        for item in items:
            value = item.get(field)
            title = item.get("title") or "no title"
            source = item.get("source") or "no source"
            url = item.get("url") or "no url"
            identity = f"{title} - {source} - {url}"
            if not value:
                missing.append(identity)
            elif len(value) < min_chars:
                too_short.append((identity, len(value)))

        pass_count = total - len(missing) - len(too_short)

        lines.append(f"**{field}** (min {min_chars} chars)")
        lines.append("| status | count | % |")
        lines.append("|--------|-------|---|")
        lines.append(f"| PASS | {pass_count} | {pass_count * 100 // total}% |")
        lines.append(f"| TOO_SHORT | {len(too_short)} | {len(too_short) * 100 // total}% |")
        lines.append(f"| MISSING | {len(missing)} | {len(missing) * 100 // total}% |")

        if too_short or missing:
            flagged_lines = []
            for identity, char_count in too_short:
                flagged_lines.append(f'- [TOO_SHORT] "{identity}" — {char_count} chars')
            for identity in missing:
                flagged_lines.append(f'- [MISSING]   "{identity}"')
            lines.append(
                "\n<details>\n<summary>Flagged items ({} total)</summary>\n\n{}\n</details>".format(
                    len(too_short) + len(missing), "\n".join(flagged_lines)
                )
            )

        lines.append("")
    return "\n".join(lines)


def _build_section_d(workspace_dir: str, error_summary_prompt_file: str, config: dict) -> str:
    log_path = os.path.join(workspace_dir, "errors.log")
    try:
        with open(log_path, encoding="utf-8") as f:
            log_content = f.read().strip()
    except FileNotFoundError:
        log_content = ""

    if not log_content:
        return "### D. Error Summarisation\n\nNo errors or warnings recorded during this run.\n"

    if not os.path.exists(error_summary_prompt_file):
        raise FileNotFoundError(f"Error summary prompt not found: {error_summary_prompt_file}")
    with open(error_summary_prompt_file, encoding="utf-8") as f:
        template = f.read()

    model_name = config.get("model", "default")
    llm_client = get_llm_client(config)
    summary = llm_client.query(template.format(content=log_content), model=model_name)
    return (
        "### D. Error Summarisation\n\n"
        "<details>\n<summary>Click to expand error summary</summary>\n\n"
        f"{summary}\n"
        "</details>\n"
    )


def _build_section_e(combined_sections: str, audit_report_prompt_file: str, config: dict) -> str:
    if not os.path.exists(audit_report_prompt_file):
        raise FileNotFoundError(f"Audit report prompt not found: {audit_report_prompt_file}")
    with open(audit_report_prompt_file, encoding="utf-8") as f:
        template = f.read()

    model_name = config.get("model", "default")
    llm_client = get_llm_client(config)
    report = llm_client.query(template.format(content=combined_sections), model=model_name)
    return f"### E. Audit Report\n\n{report}\n"


@register_task("PipelineAuditTask")
class PipelineAuditTask(PipelineTask):
    def execute(self, context: WorkflowContext, config: Dict[str, Any]) -> WorkflowContext:
        checkpoint_file = config.get("checkpoint_file")
        target_key = config.get("target_key", "research_data")
        input_fields = config.get("input_fields", [])
        workload_fields = config.get("workload_fields", [])
        quality_fields = config.get("quality_fields", {})
        error_summary_prompt_file = config.get("error_summary_prompt_file")
        audit_report_prompt_file = config.get("audit_report_prompt_file")
        report_suffix = config.get("report_suffix", "Audit-Report")
        output_dir = config.get("output_dir", "reports")
        force_refresh = config.get("force_refresh", False)

        if not checkpoint_file:
            raise ValueError("PipelineAuditTask requires 'checkpoint_file' in config.")

        checkpoint_path = self.get_workspace_path(context, checkpoint_file)
        workspace_dir = context.get("_workspace_dir", "outputs")

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

        if quality_fields:
            sections.append(_build_section_c(items, quality_fields))
            logger.info("Section C complete.")

        if error_summary_prompt_file:
            sections.append(_build_section_d(workspace_dir, error_summary_prompt_file, config))
            logger.info("Section D complete.")

        combined = "\n\n".join(sections)

        if audit_report_prompt_file:
            section_e = _build_section_e(combined, audit_report_prompt_file, config)
            sections.append(section_e)
            logger.info("Section E complete.")

        full_report = "\n\n".join(sections)

        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            header = (
                f"# Pipeline Audit Report\n\n"
                f"- **Date:** {date_str}\n"
                f"- **Checkpoint:** {checkpoint_file}\n"
                f"- **Items audited:** {len(items)}\n\n---\n\n"
            )
            f.write(header + full_report)
        logger.info(f"Audit report written to: {report_path}")

        return context
