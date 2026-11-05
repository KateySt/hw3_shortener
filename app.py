#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared" / "python"))

import aws_cdk as cdk

from shared_config import get_logger, load_config, load_env_file
from short_urls.short_urls_stack import ShortUrlsStack

load_env_file()
app = cdk.App()
config = load_config()
logger = get_logger("cdk", config.log_level)

student = app.node.try_get_context("student") or config.student
if not student:
    raise ValueError("Pass your last name: cdk deploy -c student=<last name> (or set STUDENT in .env)")

logger.info("Synthesizing ShortUrls-%s in %s", student, config.region)
ShortUrlsStack(
    app,
    f"ShortUrls-{student}",
    config=config,
    env=cdk.Environment(region=config.region),
)
cdk.Tags.of(app).add("student", student)

app.synth()
