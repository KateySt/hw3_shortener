import importlib
import json
import sys
import time
from pathlib import Path

import pytest

WEATHER_LAMBDA_DIR = Path(__file__).resolve().parents[2] / "weather_lambda"

KYIV = {"name": "Kyiv", "country": "Ukraine", "latitude": 50.45, "longitude": 30.52}
FORECAST = {
    "current": {"time": "2026-11-05T10:00", "temperature_2m": 7.4, "wind_speed_10m": 12.1, "weather_code": 3},
    "daily": {
        "time": ["2026-11-05", "2026-11-06"],
        "weather_code": [61, 0],
        "temperature_2m_max": [9.0, 11.2],
        "temperature_2m_min": [3.1, 4.0],
    },
}


class FakeDynamoDB:
    def __init__(self):
        self.items = {}

    def put_item(self, TableName, Item):
        self.items[Item["cache_key"]["S"]] = Item

    def get_item(self, TableName, Key):
        item = self.items.get(Key["cache_key"]["S"])
        return {"Item": item} if item else {}


class FakeOpenMeteo:
    def __init__(self, module, locations=None, fail=False):
        self.module = module
        self.locations = locations if locations is not None else [KYIV]
        self.fail = fail
        self.calls = []

    def __call__(self, url, params):
        self.calls.append(url)
        if self.fail:
            raise self.module.UpstreamError("timed out")
        if url == self.module.settings.weather_geocoding_url:
            return {"results": self.locations} if self.locations else {}
        return FORECAST


@pytest.fixture
def weather(monkeypatch, tmp_path):
    monkeypatch.setenv("TABLE_NAME", "weather-cache")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.syspath_prepend(str(WEATHER_LAMBDA_DIR))
    sys.modules.pop("weather", None)
    module = importlib.import_module("weather")
    monkeypatch.setattr(module, "dynamodb", FakeDynamoDB())
    return module


def use_open_meteo(monkeypatch, weather, **kwargs):
    fake = FakeOpenMeteo(weather, **kwargs)
    monkeypatch.setattr(weather, "_fetch_json", fake)
    return fake


def get(weather, city):
    params = None if city is None else {"city": city}
    response = weather.get_weather({"queryStringParameters": params}, None)
    return response["statusCode"], json.loads(response["body"])


def test_first_request_fetches_and_caches(monkeypatch, weather):
    open_meteo = use_open_meteo(monkeypatch, weather)
    status, body = get(weather, "Kyiv")

    assert status == 200
    assert body["cached"] is False
    assert body["city"] == "Kyiv"
    assert body["current"] == {"time": "2026-11-05T10:00", "temperature_c": 7.4, "wind_kmh": 12.1, "description": "Overcast"}
    assert body["daily"][0] == {"date": "2026-11-05", "min_c": 3.1, "max_c": 9.0, "description": "Slight rain"}
    assert len(open_meteo.calls) == 2
    stored = weather.dynamodb.items["city#kyiv"]
    assert int(stored["expires_at"]["N"]) >= int(time.time()) + 10 * 60 - 1


def test_second_request_is_served_from_cache(monkeypatch, weather):
    open_meteo = use_open_meteo(monkeypatch, weather)
    get(weather, "Kyiv")
    status, body = get(weather, " kyiv ")

    assert status == 200
    assert body["cached"] is True
    assert len(open_meteo.calls) == 2


def test_expired_cache_is_refetched(monkeypatch, weather):
    open_meteo = use_open_meteo(monkeypatch, weather)
    get(weather, "Kyiv")
    weather.dynamodb.items["city#kyiv"]["expires_at"] = {"N": str(int(time.time()) - 1)}

    status, body = get(weather, "Kyiv")
    assert status == 200
    assert body["cached"] is False
    assert len(open_meteo.calls) == 4


def test_unknown_city_returns_404(monkeypatch, weather):
    use_open_meteo(monkeypatch, weather, locations=[])
    status, _ = get(weather, "Nowhereland")
    assert status == 404


def test_upstream_failure_returns_502(monkeypatch, weather):
    use_open_meteo(monkeypatch, weather, fail=True)
    status, _ = get(weather, "Kyiv")
    assert status == 502
    assert weather.dynamodb.items == {}


@pytest.mark.parametrize("city", [None, "", "   ", "x" * 101])
def test_invalid_city_returns_400(monkeypatch, weather, city):
    use_open_meteo(monkeypatch, weather)
    status, _ = get(weather, city)
    assert status == 400
