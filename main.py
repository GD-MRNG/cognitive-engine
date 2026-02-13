import argparse
import logging
import sys
import os
from dotenv import load_dotenv
from src.core.engine import WorkflowEngine

load_dotenv()


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    log_file = "outputs/errors.log"

    os.makedirs("outputs", exist_ok=True)

    # Clear Previous Log
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except OSError:
            # If file is locked/open by another process, just ignore
            pass
    # Basic Configuration (Console Output)
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
    )
    # File Handler for Warnings and Errors
    file_handler = logging.FileHandler(log_file, mode="w")
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
    setup_logging(args.debug)
    logger = logging.getLogger(__name__)

    if not os.path.exists(args.workflow):
        logger.error(f"Workflow file not found: {args.workflow}")
        sys.exit(1)

    try:
        engine = WorkflowEngine(args.workflow)
        engine.run()
    except Exception as e:
        logger.critical(f"Fatal error during execution: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
