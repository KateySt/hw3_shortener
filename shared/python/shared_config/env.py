import os
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

    @property
    def link_ttl_seconds(self) -> int:
        return self.link_ttl_minutes * 60

    def lambda_environment(self, table_name: str) -> dict[str, str]:
        return {
            EnvVar.TABLE_NAME: table_name,
            EnvVar.LINK_TTL_MINUTES: str(self.link_ttl_minutes),
            EnvVar.LOG_LEVEL: self.log_level,
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
    )
