import logging
import os
import datetime
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task
from src.core.llm import get_llm_client
from src.utils.io import CheckpointManager

logger = logging.getLogger(__name__)


ORDERED_REGIONS = [
    "Global",
    "China",
    "East Asia",
    "Singapore",
    "Southeast Asia",
    "South Asia",
    "Central Asia",
    "Russia",
    "West Asia (Middle East)",
    "Africa",
    "Europe",
    "Latin America & Caribbean",
    "North America",
    "Oceania",
]


@register_task("StrategicSynthesisTask")
class StrategicSynthesisTask(PipelineTask):
    """
    Aggregates all intel and generates:
    1. Global Executive Summary.
    2. Category-Level Strategic Assessments.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        target_key = config.get("target_key", "research_data")
        checkpoint_file = config.get("checkpoint_file", "outputs/research.json")

        group_key = config.get("group_by", "region")
        max_context_chars = config.get("max_context_chars", 0)
        force_refresh = config.get("force_refresh", False)

        artifact = CheckpointManager.load(checkpoint_file)
        items = artifact.get(target_key, [])

        intelligence = artifact.get("intelligence", {})

        # --- 1. Aggregation ---
        datapoint_trends = [
            i.get("trend_summary")
            for i in items
            if i.get("type") == "datapoint" and i.get("trend_summary")
        ]

        analysis_items = [
            i for i in items if i.get("type") == "analysis" and i.get("intel_summary")
        ]

        grouped_items = {}
        for item in analysis_items:
            k = item.get(group_key, "Uncategorized")
            if k not in grouped_items:
                grouped_items[k] = []
            grouped_items[k].append(item)

        # --- 2. Prepare Contexts ---
        global_trends_text = "\n\n".join(datapoint_trends)

        all_analysis_text_list = []
        for item in analysis_items:
            txt = f"Title: {item.get('title')}\nSource: {item.get('source')}\nSummary: {item.get('intel_summary')}"
            all_analysis_text_list.append(txt)
        all_analysis_text = "\n\n---\n\n".join(all_analysis_text_list)

        if max_context_chars > 0:
            global_trends_text = global_trends_text[:max_context_chars]
            all_analysis_text = all_analysis_text[:max_context_chars]

        # --- 3. LLM Setup ---
        llm_client = get_llm_client(config)
        global_prompt_file = config.get(
            "global_prompt_file", "prompts/global_executive_summary.txt"
        )
        category_prompt_file = config.get(
            "category_prompt_file", "prompts/category_assessment.txt"
        )

        with open(global_prompt_file, encoding="utf-8") as f:
            global_template = f.read()
        with open(category_prompt_file, encoding="utf-8") as f:
            category_template = f.read()

        # --- 4. Global Executive Summary ---
        # CHECK: Skip if exists
        if not force_refresh and intelligence.get("Global_Executive_Summary"):
            logger.info(
                "StrategicSynthesisTask: Global Summary exists. Skipping LLM call."
            )
        else:
            logger.info(
                "StrategicSynthesisTask: Generating Global Executive Summary..."
            )
            try:
                prompt = global_template.format(
                    global_trends=global_trends_text,
                    all_analysis_briefs=all_analysis_text,
                )
                global_summary = llm_client.query(prompt, model=config.get("model"))
                intelligence["Global_Executive_Summary"] = global_summary
            except Exception as e:
                logger.error(f"Global Summary Failed: {e}")
                intelligence["Global_Executive_Summary"] = "Generation Failed."

        # --- 5. Category Assessments ---
        for category_name, category_items in grouped_items.items():
            if not category_name:
                continue

            # Create the dictionary entry if missing
            if category_name not in intelligence:
                intelligence[category_name] = {}

            # CHECK: Skip if assessment exists
            if not force_refresh and intelligence[category_name].get("assessment"):
                logger.info(
                    f"StrategicSynthesisTask: Assessment for '{category_name}' exists. Skipping LLM call."
                )
                # IMPORTANT: Always update the 'articles' list even if we skip the LLM,
                # in case the underlying items changed but you wanted to keep the old summary.
                intelligence[category_name]["articles"] = category_items
                continue

            logger.info(
                f"StrategicSynthesisTask: Generating Assessment for {category_name}..."
            )

            # Prepare Context
            cat_text_list = []
            for item in category_items:
                txt = f"Title: {item.get('title')}\nSource: {item.get('source')}\nSummary: {item.get('intel_summary')}"
                cat_text_list.append(txt)
            category_intel_text = "\n\n---\n\n".join(cat_text_list)

            try:
                prompt = category_template.format(
                    category_name=category_name,
                    global_summary=intelligence.get("Global_Executive_Summary", ""),
                    category_intel=category_intel_text,
                )
                assessment = llm_client.query(prompt, model=config.get("model"))

                intelligence[category_name]["assessment"] = assessment
                intelligence[category_name]["articles"] = category_items

            except Exception as e:
                logger.error(f"Assessment failed for {category_name}: {e}")

        artifact["intelligence"] = intelligence
        CheckpointManager.save(checkpoint_file, artifact)

        return context


@register_task("ReportGenerationTask")
class ReportGenerationTask(PipelineTask):
    """
    Renders the final Markdown report using Jinja2.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        checkpoint_file = config.get("checkpoint_file", "outputs/research.json")
        template_file = config.get("template_file", "templates/weekly_report.md.j2")
        output_dir = config.get("output_dir", "outputs/reports")

        artifact = CheckpointManager.load(checkpoint_file)
        intelligence = artifact.get("intelligence", {})

        if not intelligence:
            logger.warning("No intelligence data found. Skipping report generation.")
            return context

        env = Environment(loader=FileSystemLoader(os.path.dirname(template_file)))
        template = env.get_template(os.path.basename(template_file))

        today = datetime.datetime.now()
        report_date = today.strftime("%Y-%m-%d")
        display_date = today.strftime("%d %B %Y")

        try:
            rendered_report = template.render(
                date=report_date,
                display_date=display_date,
                intelligence=intelligence,
                ordered_regions=ORDERED_REGIONS,
                to_anchor=lambda x: x.lower()
                .replace(" ", "-")
                .replace("&", "")
                .replace("(", "")
                .replace(")", ""),
            )

            os.makedirs(output_dir, exist_ok=True)
            filename = f"{output_dir}/{report_date}-Weekly-Brief.md"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(rendered_report)

            logger.info(f"Report generated successfully: {filename}")

        except Exception as e:
            logger.critical(f"Jinja Rendering Failed: {e}")
            raise e

        return context
