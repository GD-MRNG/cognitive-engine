import logging
import os
import shutil
import subprocess
from typing import Dict, Any
import boto3
from botocore.exceptions import NoCredentialsError

from src.core.interfaces import PipelineTask
from src.core.context import WorkflowContext
from src.core.registry import register_task

logger = logging.getLogger(__name__)


@register_task("CloudArchivalTask")
class CloudArchivalTask(PipelineTask):
    """
    Zips the current workspace and uploads it to an S3 bucket.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        workspace_dir = context.get("_workspace_dir")
        if not workspace_dir or not os.path.exists(workspace_dir):
            logger.error("CloudArchivalTask: No workspace directory found to archive.")
            return context

        bucket_name = config.get("bucket_name", "cognitive-engine-history")
        s3_prefix = config.get("s3_prefix", "general_research")

        logger.info(f"Zipping workspace: {workspace_dir}")
        zip_base_path = f"{workspace_dir}"  # shutil appends .zip
        try:
            zip_file_path = shutil.make_archive(
                base_name=zip_base_path, format="zip", root_dir=workspace_dir
            )
            logger.info(f"Created archive: {zip_file_path}")
        except Exception as e:
            logger.error(f"Failed to zip workspace: {e}")
            return context

        try:
            s3_client = boto3.client("s3")

            filename = os.path.basename(zip_file_path)
            s3_key = f"{s3_prefix.strip('/')}/{filename}"

            logger.info(f"Uploading to S3 -> s3://{bucket_name}/{s3_key} ...")
            s3_client.upload_file(zip_file_path, bucket_name, s3_key)
            logger.info("✅ S3 Archival Complete.")

        except ImportError:
            logger.error(
                "boto3 is not installed. Run 'pip install boto3' to use CloudArchivalTask."
            )
        except NoCredentialsError:
            logger.error(
                "AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
            )
        except Exception as e:
            logger.error(f"S3 Upload failed: {e}")

        return context


@register_task("GitPublisherTask")
class GitPublisherTask(PipelineTask):
    """
    Copies the generated report to a local repository, commits, and pushes it.
    """

    def execute(
        self, context: WorkflowContext, config: Dict[str, Any]
    ) -> WorkflowContext:
        repo_path = config.get("repo_path")
        dest_folder = config.get("dest_folder", "_posts")
        commit_message = config.get(
            "commit_message", "Auto-Publish: New Intelligence Brief"
        )
        branch = config.get("branch", "main")

        if not repo_path or not os.path.exists(repo_path):
            logger.error(f"GitPublisherTask: Invalid repo_path provided: {repo_path}")
            return context

        source_file = context.get("generated_report_path")
        if not source_file or not os.path.exists(source_file):
            logger.error(
                "GitPublisherTask: Could not locate the generated report path in context."
            )
            return context

        dest_dir_full = os.path.join(repo_path, dest_folder)
        os.makedirs(dest_dir_full, exist_ok=True)

        filename = os.path.basename(source_file)
        dest_file = os.path.join(dest_dir_full, filename)

        try:
            shutil.copy2(source_file, dest_file)
            logger.info(f"Copied report to: {dest_file}")
        except Exception as e:
            logger.critical(f"Failed to copy file to repo: {e}")
            return context

        try:

            def run_git(args):
                logger.debug(f"Executing: git {' '.join(args)}")
                subprocess.run(
                    ["git"] + args,
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )

            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            if not status.stdout.strip():
                logger.info(
                    "No changes to commit. Report may be identical to previous run."
                )
                return context

            logger.info(f"Committing and pushing to branch: '{branch}'...")

            run_git(["checkout", branch])
            run_git(["add", "."])
            run_git(["commit", "-m", commit_message])
            run_git(["push", "origin", branch])

            logger.info(f"✅ Successfully deployed '{filename}' to remote repository.")

        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e.stderr}")

        return context
