import json
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import boto3
from shared_config import get_logger, load_config

settings = load_config()
logger = get_logger(__name__, settings.log_level)

dynamodb = boto3.client("dynamodb")

WEATHER_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class UpstreamError(Exception):
    pass


def _json_response(status_code, body, headers=None):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", **(headers or {})},
        "body": json.dumps(body),
    }


def _describe(weather_code):
    return WEATHER_DESCRIPTIONS.get(weather_code, "Unknown")


def _fetch_json(url, params):
    try:
        with urlopen(f"{url}?{urlencode(params)}", timeout=settings.weather_http_timeout_seconds) as response:
            return json.loads(response.read())
    except (URLError, TimeoutError, ValueError) as error:
        raise UpstreamError(str(error)) from error


def _find_city(city):
    found = _fetch_json(
        settings.weather_geocoding_url,
        {"name": city, "count": 1, "language": "en", "format": "json"},
    )
    results = found.get("results") or []
    return results[0] if results else None


def _fetch_forecast(latitude, longitude):
    return _fetch_json(
        settings.weather_forecast_url,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,wind_speed_10m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": settings.weather_forecast_days,
        },
    )


def _build_weather(location, forecast):
    current = forecast["current"]
    daily = forecast["daily"]
    return {
        "city": location["name"],
        "country": location.get("country"),
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": {
            "time": current["time"],
            "temperature_c": current["temperature_2m"],
            "wind_kmh": current["wind_speed_10m"],
            "description": _describe(current["weather_code"]),
        },
        "daily": [
            {
                "date": date,
                "min_c": min_c,
                "max_c": max_c,
                "description": _describe(code),
            }
            for date, code, max_c, min_c in zip(
                daily["time"],
                daily["weather_code"],
                daily["temperature_2m_max"],
                daily["temperature_2m_min"],
            )
        ],
    }


def _cache_key(city):
    return f"city#{city.lower()}"


def _read_cache(cache_key, now):
    item = dynamodb.get_item(TableName=settings.table_name, Key={"cache_key": {"S": cache_key}}).get("Item")
    if not item or int(item["expires_at"]["N"]) <= now:
        return None
    return json.loads(item["payload"]["S"]), int(item["expires_at"]["N"])


def _write_cache(cache_key, weather, expires_at):
    dynamodb.put_item(
        TableName=settings.table_name,
        Item={
            "cache_key": {"S": cache_key},
            "payload": {"S": json.dumps(weather)},
            "expires_at": {"N": str(expires_at)},
        },
    )


def _parse_city(event):
    city = ((event.get("queryStringParameters") or {}).get("city") or "").strip()
    if not city:
        return None, "Query parameter \"city\" is required, e.g. /weather?city=Kyiv"
    if len(city) > settings.weather_max_city_length:
        return None, f"City name is longer than {settings.weather_max_city_length} characters"
    return city, None


def get_weather(event, context):
    logger.info("GET /weather request_id=%s", event.get("requestContext", {}).get("requestId"))

    city, error_message = _parse_city(event)
    if error_message:
        return _json_response(400, {"message": error_message})

    now = int(time.time())
    cache_key = _cache_key(city)
    cached = _read_cache(cache_key, now)
    if cached:
        weather, expires_at = cached
        return _json_response(
            200,
            {**weather, "cached": True, "expires_at": expires_at},
            {"Cache-Control": f"public, max-age={expires_at - now}"},
        )

    try:
        location = _find_city(city)
        if not location:
            return _json_response(404, {"message": f"City \"{city}\" not found"})
        weather = _build_weather(location, _fetch_forecast(location["latitude"], location["longitude"]))
    except (UpstreamError, KeyError, TypeError) as error:
        logger.warning("Open-Meteo request failed or returned unexpected data: %r", error)
        return _json_response(502, {"message": "Weather service is unavailable, try again later"})

    expires_at = now + settings.weather_cache_seconds
    _write_cache(cache_key, weather, expires_at)
    return _json_response(
        200,
        {**weather, "cached": False, "expires_at": expires_at},
        {"Cache-Control": f"public, max-age={settings.weather_cache_seconds}"},
    )
