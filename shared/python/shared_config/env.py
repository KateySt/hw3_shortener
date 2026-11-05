import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class EnvVar:
    STUDENT = "STUDENT"
    AWS_REGION = "AWS_REGION"
    TABLE_NAME = "TABLE_NAME"
    LINK_TTL_MINUTES = "LINK_TTL_MINUTES"
    LOG_LEVEL = "LOG_LEVEL"
    LOG_RETENTION = "LOG_RETENTION"
    API_RATE_LIMIT = "API_RATE_LIMIT"
    API_BURST_LIMIT = "API_BURST_LIMIT"
    ENABLE_WEATHER = "ENABLE_WEATHER"
    WEATHER_CACHE_MINUTES = "WEATHER_CACHE_MINUTES"
    WEATHER_FORECAST_DAYS = "WEATHER_FORECAST_DAYS"
    WEATHER_HTTP_TIMEOUT_SECONDS = "WEATHER_HTTP_TIMEOUT_SECONDS"
    BOOTSTRAP_QUALIFIER = "BOOTSTRAP_QUALIFIER"


TRUE_VALUES = ("1", "true", "yes", "on")
BOOTSTRAP_QUALIFIER_PATTERN = re.compile(r"^[a-z0-9]{1,10}$")
DEFAULT_TOOLKIT_STACK_NAME = "CDKToolkit"


def validate_bootstrap_qualifier(qualifier: str | None) -> str | None:
    if qualifier is None:
        return None
    if not BOOTSTRAP_QUALIFIER_PATTERN.match(qualifier):
        raise ValueError(
            f"{EnvVar.BOOTSTRAP_QUALIFIER} must be 1-10 lowercase letters or digits, got {qualifier!r}"
        )
    return qualifier


@dataclass(frozen=True)
class AppConfig:
    student: str | None = None
    region: str = "us-east-1"
    table_name: str | None = None
    link_ttl_minutes: int = 15
    log_level: str = "INFO"
    log_retention: str = "ONE_WEEK"
    api_rate_limit: int = 10
    api_burst_limit: int = 20
    max_url_length: int = 2048
    short_key_bytes: int = 6
    max_key_attempts: int = 3
    enable_weather: bool = False
    weather_cache_minutes: int = 10
    weather_forecast_days: int = 3
    weather_http_timeout_seconds: int = 3
    weather_max_city_length: int = 100
    weather_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    weather_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    bootstrap_qualifier: str | None = None

    @property
    def toolkit_stack_name(self) -> str:
        if self.bootstrap_qualifier:
            return f"{DEFAULT_TOOLKIT_STACK_NAME}-{self.bootstrap_qualifier}"
        return DEFAULT_TOOLKIT_STACK_NAME

    @property
    def link_ttl_seconds(self) -> int:
        return self.link_ttl_minutes * 60

    @property
    def weather_cache_seconds(self) -> int:
        return self.weather_cache_minutes * 60

    def lambda_environment(self, table_name: str) -> dict[str, str]:
        return {
            EnvVar.TABLE_NAME: table_name,
            EnvVar.LINK_TTL_MINUTES: str(self.link_ttl_minutes),
            EnvVar.LOG_LEVEL: self.log_level,
        }

    def weather_lambda_environment(self, table_name: str) -> dict[str, str]:
        return {
            EnvVar.TABLE_NAME: table_name,
            EnvVar.LOG_LEVEL: self.log_level,
            EnvVar.WEATHER_CACHE_MINUTES: str(self.weather_cache_minutes),
            EnvVar.WEATHER_FORECAST_DAYS: str(self.weather_forecast_days),
            EnvVar.WEATHER_HTTP_TIMEOUT_SECONDS: str(self.weather_http_timeout_seconds),
        }


def load_env_file(env_file: Path = ENV_FILE) -> None:
    from dotenv import load_dotenv

    load_dotenv(env_file, override=False)


def load_config(environ: Mapping[str, str] = os.environ) -> AppConfig:
    defaults = AppConfig()
    return AppConfig(
        student=environ.get(EnvVar.STUDENT) or defaults.student,
        region=environ.get(EnvVar.AWS_REGION, defaults.region),
        table_name=environ.get(EnvVar.TABLE_NAME, defaults.table_name),
        link_ttl_minutes=int(environ.get(EnvVar.LINK_TTL_MINUTES, defaults.link_ttl_minutes)),
        log_level=environ.get(EnvVar.LOG_LEVEL, defaults.log_level).upper(),
        log_retention=environ.get(EnvVar.LOG_RETENTION, defaults.log_retention).upper(),
        api_rate_limit=int(environ.get(EnvVar.API_RATE_LIMIT, defaults.api_rate_limit)),
        api_burst_limit=int(environ.get(EnvVar.API_BURST_LIMIT, defaults.api_burst_limit)),
        enable_weather=environ.get(EnvVar.ENABLE_WEATHER, "").strip().lower() in TRUE_VALUES,
        weather_cache_minutes=int(environ.get(EnvVar.WEATHER_CACHE_MINUTES, defaults.weather_cache_minutes)),
        weather_forecast_days=int(environ.get(EnvVar.WEATHER_FORECAST_DAYS, defaults.weather_forecast_days)),
        weather_http_timeout_seconds=int(
            environ.get(EnvVar.WEATHER_HTTP_TIMEOUT_SECONDS, defaults.weather_http_timeout_seconds)
        ),
        bootstrap_qualifier=validate_bootstrap_qualifier(
            environ.get(EnvVar.BOOTSTRAP_QUALIFIER, "").strip().lower() or defaults.bootstrap_qualifier
        ),
    )
