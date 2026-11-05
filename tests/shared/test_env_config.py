import pytest

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


def test_bootstrap_qualifier_defaults_to_shared_toolkit():
    assert load_config({}).toolkit_stack_name == "CDKToolkit"


def test_bootstrap_qualifier_gives_own_toolkit():
    config = load_config({EnvVar.BOOTSTRAP_QUALIFIER: "KaTest"})
    assert config.bootstrap_qualifier == "katest"
    assert config.toolkit_stack_name == "CDKToolkit-katest"


@pytest.mark.parametrize("qualifier", ["has-dash", "waytoolongqualifier", "кирилиця"])
def test_invalid_bootstrap_qualifier_is_rejected(qualifier):
    with pytest.raises(ValueError):
        load_config({EnvVar.BOOTSTRAP_QUALIFIER: qualifier})
