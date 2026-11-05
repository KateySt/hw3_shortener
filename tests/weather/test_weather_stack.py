import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest

from weather_forecast.weather_forecast_stack import WeatherForecastStack


@pytest.fixture(scope="module")
def template():
    app = core.App()
    stack = WeatherForecastStack(app, "Weather-test")
    return assertions.Template.from_stack(stack)


def test_cache_table_expires_items(template):
    template.has_resource_properties(
        "AWS::DynamoDB::GlobalTable",
        {
            "KeySchema": [{"AttributeName": "cache_key", "KeyType": "HASH"}],
            "TimeToLiveSpecification": {"AttributeName": "expires_at", "Enabled": True},
        },
    )


def test_weather_lambda_and_route(template):
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.has_resource_properties("AWS::Lambda::Function", {"Handler": "weather.get_weather"})
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {"HttpMethod": "GET", "RequestParameters": {"method.request.querystring.city": True}},
    )


def test_weather_lambda_has_only_cache_access(template):
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": [
                    assertions.Match.object_like({"Action": ["dynamodb:GetItem", "dynamodb:PutItem"]})
                ]
            }
        },
    )
