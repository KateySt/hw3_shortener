from shared_config import AppConfig, EnvVar, load_config


def test_defaults_when_environment_is_empty():
    assert load_config({}) == AppConfig()
    assert AppConfig().link_ttl_seconds == 15 * 60


def test_values_come_from_environment():
    config = load_config({
        EnvVar.STUDENT: "orlovsky",
        EnvVar.LINK_TTL_MINUTES: "5",
        EnvVar.LOG_LEVEL: "debug",
        EnvVar.LOG_RETENTION: "two_weeks",
    })
    assert config.student == "orlovsky"
    assert config.link_ttl_seconds == 300
    assert config.log_level == "DEBUG"
    assert config.log_retention == "TWO_WEEKS"


def test_lambda_environment_round_trips():
    config = load_config({EnvVar.LINK_TTL_MINUTES: "7", EnvVar.LOG_LEVEL: "WARN"})
    lambda_config = load_config(config.lambda_environment("urls-table"))
    assert lambda_config.table_name == "urls-table"
    assert lambda_config.link_ttl_minutes == 7
    assert lambda_config.log_level == "WARN"
