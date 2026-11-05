import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest

from short_urls.short_urls_stack import ShortUrlsStack
from weather_forecast.weather_forecast_stack import WeatherForecastStack

ACCOUNT_WIDE_RESOURCE_TYPES = ("AWS::ApiGateway::Account",)


@pytest.fixture(scope="module", params=[ShortUrlsStack, WeatherForecastStack], ids=["shortener", "weather"])
def template(request):
    app = core.App()
    stack = request.param(app, f"{request.param.__name__}-test")
    return assertions.Template.from_stack(stack)


def test_no_account_wide_settings(template):
    for resource_type in ACCOUNT_WIDE_RESOURCE_TYPES:
        template.resource_count_is(resource_type, 0)


def test_everything_is_deleted_with_the_stack(template):
    retained = {
        logical_id: resource["Type"]
        for logical_id, resource in template.to_json()["Resources"].items()
        if resource.get("DeletionPolicy", "Delete") != "Delete"
    }
    assert retained == {}


def test_api_name_contains_stack_name(template):
    template.has_resource_properties(
        "AWS::ApiGateway::RestApi", {"Name": assertions.Match.string_like_regexp(r"-test-api$")}
    )
