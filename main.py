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

    os.makedirs(workspace_dir, exist_ok=True)
    log_file = os.path.join(workspace_dir, "errors.log")

    # Basic Config (Console Output)
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
    )

    # File Handler for Warnings and Errors
    # Using mode="a" handles both scenarios:
    # 1. Fresh run: creates the file.
    # 2. Resume run: safely appends to the existing file.
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
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
    parser.add_argument(
        "--resume",
        type=str,
        help="Path to an existing workspace directory to resume a previous run.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")

    args = parser.parse_args()

    if args.resume:
        workspace_dir = os.path.normpath(args.resume)
        if not os.path.exists(workspace_dir):
            print(f"CRITICAL: Cannot resume. Directory does not exist: {workspace_dir}")
            sys.exit(1)
        print(f"🔄 Resuming previous run from workspace: {workspace_dir}")
    else:
        # Generate new workspace
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        run_id = now.strftime("%H%M%S")
        workspace_dir = os.path.join("outputs", f"{date_str}_{run_id}")
        os.makedirs(workspace_dir, exist_ok=True)
        print(f"🆕 Starting new run in workspace: {workspace_dir}")

    setup_logging(workspace_dir=workspace_dir, debug=args.debug)
    logger = logging.getLogger(__name__)

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
