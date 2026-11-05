#!/usr/bin/env python3
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared" / "python"))

import aws_cdk as cdk

from shared_config import get_logger, load_config, load_env_file
from shared_config.env import TRUE_VALUES, validate_bootstrap_qualifier
from short_urls.short_urls_stack import ShortUrlsStack
from weather_forecast.weather_forecast_stack import WeatherForecastStack

load_env_file()
app = cdk.App()
config = load_config()
logger = get_logger("cdk", config.log_level)

student = app.node.try_get_context("student") or config.student
if not student:
    raise ValueError("Pass your last name: cdk deploy -c student=<last name> (or set STUDENT in .env)")

qualifier_context = app.node.try_get_context("qualifier")
if qualifier_context:
    config = replace(config, bootstrap_qualifier=validate_bootstrap_qualifier(str(qualifier_context).lower()))


def stack_synthesizer() -> cdk.DefaultStackSynthesizer | None:
    if not config.bootstrap_qualifier:
        return None
    return cdk.DefaultStackSynthesizer(qualifier=config.bootstrap_qualifier)


logger.info(
    "Synthesizing ShortUrls-%s in %s (bootstrap: %s)", student, config.region, config.toolkit_stack_name
)
ShortUrlsStack(
    app,
    f"ShortUrls-{student}",
    config=config,
    env=cdk.Environment(region=config.region),
    synthesizer=stack_synthesizer(),
)

weather_context = app.node.try_get_context("weather")
enable_weather = config.enable_weather if weather_context is None else str(weather_context).lower() in TRUE_VALUES
if enable_weather:
    logger.info("Synthesizing Weather-%s in %s", student, config.region)
    WeatherForecastStack(
        app,
        f"Weather-{student}",
        config=config,
        env=cdk.Environment(region=config.region),
        synthesizer=stack_synthesizer(),
    )

cdk.Tags.of(app).add("student", student)

app.synth()
