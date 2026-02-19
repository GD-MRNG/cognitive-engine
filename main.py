import argparse
import logging
import sys
import os
import datetime
from dotenv import load_dotenv
from src.core.engine import WorkflowEngine

load_dotenv()


def setup_logging(workspace_dir: str, debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    log_file = os.path.join(workspace_dir, "errors.log")

    os.makedirs(workspace_dir, exist_ok=True)

    # Clear Previous Log
    # Note: mode="w" in FileHandler also truncates, but keeping this for your lock-check logic
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except OSError:
            # If file is locked/open by another process, just ignore
            pass

    # Basic Config (Console Output)
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
    )

    # File Handler for Warnings and Errors
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    logging.getLogger().addHandler(file_handler)


def main():
    parser = argparse.ArgumentParser(
        description="Cognitive Engine: Workflow Automation Platform"
    )
    parser.add_argument(
        "--workflow",
        type=str,
        required=True,
        help="Path to the YAML workflow configuration file.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")

    args = parser.parse_args()

    # Generate Workspace
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    run_id = now.strftime("%H%M%S")
    workspace_dir = os.path.join("outputs", f"{date_str}_{run_id}")
    os.makedirs(workspace_dir, exist_ok=True)

    setup_logging(workspace_dir=workspace_dir, debug=False)
    logger = logging.getLogger(__name__)

    logger.info(f"Workspace directory created at: {workspace_dir}")

    if not os.path.exists(args.workflow):
        logger.error(f"Workflow file not found: {args.workflow}")
        sys.exit(1)

    try:
        engine = WorkflowEngine(args.workflow, workspace_dir=workspace_dir)
        engine.run()
    except Exception as e:
        logger.critical(f"Fatal error during execution: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
