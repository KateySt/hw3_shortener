import importlib
import json
import sys
import time
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

LAMBDA_DIR = Path(__file__).resolve().parents[2] / "lambda"
REQUEST_CONTEXT = {"domainName": "abc.execute-api.us-east-1.amazonaws.com", "stage": "prod", "requestId": "r1"}


class FakeDynamoDB:
    def __init__(self):
        self.items = {}

    def put_item(self, TableName, Item, ConditionExpression=None):
        short_key = Item["short_key"]["S"]
        if ConditionExpression and short_key in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[short_key] = Item

    def get_item(self, TableName, Key, ConsistentRead=False):
        item = self.items.get(Key["short_key"]["S"])
        return {"Item": item} if item else {}


@pytest.fixture
def handlers(monkeypatch, tmp_path):
    monkeypatch.setenv("TABLE_NAME", "test-table")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.syspath_prepend(str(LAMBDA_DIR))
    for module_name in ("url_shortener",):
        sys.modules.pop(module_name, None)
    module = importlib.import_module("url_shortener")
    monkeypatch.setattr(module, "dynamodb", FakeDynamoDB())
    return module


def shorten(handlers, body):
    return handlers.shorten_url({"body": body, "requestContext": REQUEST_CONTEXT}, None)


def resolve(handlers, short_key):
    return handlers.resolve_url({"pathParameters": {"short_key": short_key}}, None)


def test_shorten_stores_expires_at_as_number(handlers):
    before = int(time.time())
    response = shorten(handlers, json.dumps({"url": "https://aws.amazon.com"}))

    assert response["statusCode"] == 201
    short_key = json.loads(response["body"])["shortened_url"].rsplit("/", 1)[1]
    stored = handlers.dynamodb.items[short_key]
    assert before + 15 * 60 <= int(stored["expires_at"]["N"]) <= int(time.time()) + 15 * 60


def test_resolve_redirects_fresh_link(handlers):
    response = shorten(handlers, json.dumps({"url": "https://aws.amazon.com"}))
    short_key = json.loads(response["body"])["shortened_url"].rsplit("/", 1)[1]

    redirect = resolve(handlers, short_key)
    assert redirect["statusCode"] == 301
    assert redirect["headers"]["Location"] == "https://aws.amazon.com"


def test_resolve_returns_404_for_expired_link(handlers):
    handlers.dynamodb.items["old"] = {
        "short_key": {"S": "old"},
        "original_url": {"S": "https://aws.amazon.com"},
        "expires_at": {"N": str(int(time.time()) - 1)},
    }
    assert resolve(handlers, "old")["statusCode"] == 404
    assert resolve(handlers, "missing")["statusCode"] == 404


def test_same_url_gets_different_keys(handlers):
    first = shorten(handlers, json.dumps({"url": "https://aws.amazon.com"}))
    second = shorten(handlers, json.dumps({"url": "https://aws.amazon.com"}))
    assert json.loads(first["body"])["shortened_url"] != json.loads(second["body"])["shortened_url"]


@pytest.mark.parametrize(
    "body",
    [None, "not json", '"just a string"', "{}", '{"url": ""}', '{"url": "javascript:alert(1)"}', '{"url": "aws.amazon.com"}'],
)
def test_shorten_rejects_invalid_input(handlers, body):
    assert shorten(handlers, body)["statusCode"] == 400
