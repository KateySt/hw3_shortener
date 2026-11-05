import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest

from short_urls.short_urls_stack import ShortUrlsStack


@pytest.fixture(scope="module")
def template():
    app = core.App()
    stack = ShortUrlsStack(app, "ShortUrls-test")
    return assertions.Template.from_stack(stack)


def test_table_created(template):
    template.has_resource_properties(
        "AWS::DynamoDB::GlobalTable",
        {
            "KeySchema": [{"AttributeName": "short_key", "KeyType": "HASH"}],
            "BillingMode": "PAY_PER_REQUEST",
        },
    )


def test_lambdas_and_api_created(template):
    template.resource_count_is("AWS::Lambda::Function", 2)
    template.has_resource_properties("AWS::Lambda::Function", {"Handler": "url_shortener.shorten_url"})
    template.has_resource_properties("AWS::Lambda::Function", {"Handler": "url_shortener.resolve_url"})
    template.resource_count_is("AWS::ApiGateway::RestApi", 1)


def test_links_expire(template):
    template.has_resource_properties(
        "AWS::DynamoDB::GlobalTable",
        {"TimeToLiveSpecification": {"AttributeName": "expires_at", "Enabled": True}},
    )
