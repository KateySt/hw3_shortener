#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared" / "python"))

import boto3
from botocore.exceptions import ClientError

from shared_config import get_logger, load_config, load_env_file
from shared_config.env import DEFAULT_TOOLKIT_STACK_NAME, validate_bootstrap_qualifier

logger = get_logger("cleanup")

APP_STACK_PREFIXES = ("ShortUrls", "Weather")
DELETE_BATCH_SIZE = 1000


def parse_arguments():
    load_env_file()
    config = load_config()
    parser = argparse.ArgumentParser(
        description="Delete your stacks and your own CDK bootstrap. Dry run unless --yes is passed."
    )
    parser.add_argument("--student", default=config.student, help="last name used in -c student=")
    parser.add_argument("--qualifier", default=config.bootstrap_qualifier, help="bootstrap qualifier to remove")
    parser.add_argument("--region", default=config.region)
    parser.add_argument("--keep-bootstrap", action="store_true", help="delete only the app stacks")
    parser.add_argument("--yes", action="store_true", help="really delete (without it nothing is changed)")
    arguments = parser.parse_args()
    if not arguments.student:
        parser.error("pass --student or set STUDENT in .env")
    arguments.qualifier = validate_bootstrap_qualifier(arguments.qualifier)
    return arguments


def stack_outputs(cloudformation, stack_name):
    try:
        stack = cloudformation.describe_stacks(StackName=stack_name)["Stacks"][0]
    except ClientError as error:
        if "does not exist" in str(error):
            return None
        raise
    return {output["OutputKey"]: output["OutputValue"] for output in stack.get("Outputs", [])}


def delete_stack(cloudformation, stack_name, really_delete):
    if stack_outputs(cloudformation, stack_name) is None:
        logger.info("Stack %s: not found, nothing to delete", stack_name)
        return
    if not really_delete:
        logger.info("Stack %s: WOULD delete", stack_name)
        return
    logger.info("Stack %s: deleting...", stack_name)
    cloudformation.delete_stack(StackName=stack_name)
    cloudformation.get_waiter("stack_delete_complete").wait(
        StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": 90}
    )
    logger.info("Stack %s: deleted", stack_name)


def bucket_exists(s3, bucket_name):
    try:
        s3.head_bucket(Bucket=bucket_name)
        return True
    except ClientError:
        return False


def empty_bucket(s3, bucket_name, really_delete):
    paginator = s3.get_paginator("list_object_versions")
    object_count = 0
    for page in paginator.paginate(Bucket=bucket_name):
        versions = [
            {"Key": entry["Key"], "VersionId": entry["VersionId"]}
            for entry in page.get("Versions", []) + page.get("DeleteMarkers", [])
        ]
        object_count += len(versions)
        if really_delete:
            for start in range(0, len(versions), DELETE_BATCH_SIZE):
                s3.delete_objects(
                    Bucket=bucket_name,
                    Delete={"Objects": versions[start:start + DELETE_BATCH_SIZE], "Quiet": True},
                )
    action = "deleted" if really_delete else "WOULD delete"
    logger.info("Bucket %s: %s %d object versions", bucket_name, action, object_count)


def delete_bootstrap(session, qualifier, really_delete):
    toolkit_stack_name = f"{DEFAULT_TOOLKIT_STACK_NAME}-{qualifier}"
    cloudformation = session.client("cloudformation")
    s3 = session.client("s3")
    ecr = session.client("ecr")

    outputs = stack_outputs(cloudformation, toolkit_stack_name)
    if outputs is None:
        logger.info("Stack %s: not found, nothing to delete", toolkit_stack_name)
        return
    bucket_name = outputs.get("BucketName")
    repository_name = outputs.get("ImageRepositoryName")

    if bucket_name and bucket_exists(s3, bucket_name):
        empty_bucket(s3, bucket_name, really_delete)
    delete_stack(cloudformation, toolkit_stack_name, really_delete)

    if bucket_name and bucket_exists(s3, bucket_name):
        if really_delete:
            s3.delete_bucket(Bucket=bucket_name)
        logger.info("Bucket %s: %s", bucket_name, "deleted" if really_delete else "WOULD delete")
    if repository_name:
        try:
            ecr.describe_repositories(repositoryNames=[repository_name])
        except ClientError:
            return
        if really_delete:
            ecr.delete_repository(repositoryName=repository_name, force=True)
        logger.info("ECR repository %s: %s", repository_name, "deleted" if really_delete else "WOULD delete")


def main():
    arguments = parse_arguments()
    session = boto3.Session(region_name=arguments.region)
    identity = session.client("sts").get_caller_identity()
    logger.info("Account %s, region %s, user %s", identity["Account"], arguments.region, identity["Arn"])
    if not arguments.yes:
        logger.info("DRY RUN: nothing will be deleted. Add --yes to delete.")

    cloudformation = session.client("cloudformation")
    for prefix in APP_STACK_PREFIXES:
        delete_stack(cloudformation, f"{prefix}-{arguments.student}", arguments.yes)

    if arguments.keep_bootstrap:
        logger.info("Bootstrap kept (--keep-bootstrap)")
    elif not arguments.qualifier:
        logger.info(
            "No BOOTSTRAP_QUALIFIER: the shared %s stack is never deleted by this script", DEFAULT_TOOLKIT_STACK_NAME
        )
    else:
        delete_bootstrap(session, arguments.qualifier, arguments.yes)

    logger.info("Done" if arguments.yes else "Dry run finished")


if __name__ == "__main__":
    main()
