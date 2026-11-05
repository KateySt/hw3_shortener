import json
import secrets
import time
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
from shared_config import get_logger, load_config

settings = load_config()
logger = get_logger(__name__, settings.log_level)

dynamodb = boto3.client("dynamodb")


def _json_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _parse_url(event):
    try:
        body = json.loads(event.get("body") or "")
    except (TypeError, ValueError):
        return None, "Request body must be JSON: {\"url\": \"https://...\"}"
    if not isinstance(body, dict):
        return None, "Request body must be a JSON object: {\"url\": \"https://...\"}"

    original_url = body.get("url")
    if not isinstance(original_url, str) or not original_url.strip():
        return None, "Field \"url\" is required"
    original_url = original_url.strip()
    if len(original_url) > settings.max_url_length:
        return None, f"URL is longer than {settings.max_url_length} characters"

    parsed = urlparse(original_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None, "URL must be an absolute http(s) URL, e.g. https://example.com"
    return original_url, None


def _save_link(original_url, created_at, expires_at):
    for _ in range(settings.max_key_attempts):
        short_key = secrets.token_urlsafe(settings.short_key_bytes)
        try:
            dynamodb.put_item(
                TableName=settings.table_name,
                Item={
                    "short_key": {"S": short_key},
                    "original_url": {"S": original_url},
                    "created_at": {"N": str(created_at)},
                    "expires_at": {"N": str(expires_at)},
                },
                ConditionExpression="attribute_not_exists(short_key)",
            )
            return short_key
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            logger.warning("Short key collision, retrying")
    raise RuntimeError("Could not generate a unique short key")


def shorten_url(event, context):
    logger.info("POST /shorten request_id=%s", event.get("requestContext", {}).get("requestId"))

    original_url, error_message = _parse_url(event)
    if error_message:
        return _json_response(400, {"message": error_message})

    created_at = int(time.time())
    expires_at = created_at + settings.link_ttl_seconds
    short_key = _save_link(original_url, created_at, expires_at)

    request_context = event["requestContext"]
    shortened_url = f"https://{request_context['domainName']}/{request_context['stage']}/{short_key}"
    return _json_response(201, {"shortened_url": shortened_url, "expires_at": expires_at})


def resolve_url(event, context):
    short_key = (event.get("pathParameters") or {}).get("short_key")
    if not short_key:
        return _json_response(404, {"message": "URL not found"})

    item = dynamodb.get_item(
        TableName=settings.table_name,
        Key={"short_key": {"S": short_key}},
        ConsistentRead=True,
    ).get("Item")

    now = int(time.time())
    expires_at = int(item["expires_at"]["N"]) if item and "expires_at" in item else None
    if not item or (expires_at is not None and expires_at <= now):
        return _json_response(404, {"message": "URL not found"})

    seconds_left = expires_at - now if expires_at is not None else 0
    return {
        "statusCode": 301,
        "headers": {
            "Location": item["original_url"]["S"],
            "Cache-Control": f"private, max-age={seconds_left}",
        },
    }
