# URL Shortener (AWS CDK, Python): ДЗ 3

API Gateway + Lambda + DynamoDB. Short links stay valid for 15 minutes.

## Project layout

```
app.py                                     CDK entry point: loads .env, creates the stack
short_urls/short_urls_stack.py             table, shared layer, two Lambdas, API Gateway
lambda/url_shortener.py                    handlers: POST /shorten, GET /{short_key}
shared/python/shared_config/env.py         ALL environment variables and defaults (global config)
shared/python/shared_config/logging_config.py  logging setup for both CDK and Lambda
tests/unit/                                stack tests (the 3 homework tests)
tests/handlers/                            handler tests with a fake DynamoDB
tests/shared/                              config tests
weather_forecast/weather_forecast_stack.py extra: separate Weather-<student> stack (off by default)
weather_lambda/weather.py                  extra: GET /weather?city= handler
tests/weather/                             extra: weather handler and stack tests
scripts/cleanup.py                         deletes your stacks and your own CDK bootstrap (dry run by default)
.env.example                               copy to .env and fill in
pytest.ini                                 puts shared/python on the import path for tests
```

## Shared config (global)

`shared/python/shared_config` is one package used by both folders:

- `short_urls/` (CDK) and `app.py` import it directly (`app.py` adds `shared/python` to `sys.path`).
- `lambda/` gets it through a Lambda Layer: CDK packages `shared/` as a layer, and AWS mounts it at
  `/opt/python`, which is already on the Lambda import path. So the Lambda asset contains only `url_shortener.py`.

`env.py` is the only place in the project that reads environment variables:

- `EnvVar`: all variable names.
- `AppConfig`: all settings with defaults (plus app constants such as `max_url_length`).
- `load_env_file()`: loads `.env` (CDK side only, `python-dotenv` is not needed in Lambda).
- `load_config()`: builds `AppConfig` from the environment, the same way locally and in Lambda.
- `AppConfig.lambda_environment()`: the variables the stack passes to the Lambdas.

`logging_config.py` is the only place that sets up logging:

- Locally (CDK synth, tests): `basicConfig` with one format.
- In Lambda: the runtime already has a handler with native JSON logs (`logging_format=JSON` in the stack),
  so it's left as is, and the level is set by `application_log_level_v2` from `LOG_LEVEL`.
- `boto3`/`botocore`/`urllib3` are lowered to `WARNING` everywhere.

## Configuration (.env)

```bash
copy .env.example .env
```

| Variable           | Default     | Used for                                       |
|--------------------|-------------|------------------------------------------------|
| `STUDENT`          | none        | stack name `ShortUrls-<STUDENT>`, if `-c student=` is not passed |
| `AWS_REGION`       | `us-east-1` | region for the stack                           |
| `LINK_TTL_MINUTES` | `15`        | link lifetime, passed to Lambda                |
| `LOG_LEVEL`        | `INFO`      | log level for CDK and Lambda (`DEBUG`, `INFO`, `WARN`, `ERROR`) |
| `LOG_RETENTION`    | `ONE_WEEK`  | CloudWatch retention, a `RetentionDays` name   |
| `API_RATE_LIMIT`   | `10`        | API Gateway requests per second                |
| `API_BURST_LIMIT`  | `20`        | API Gateway burst                              |
| `ENABLE_WEATHER`   | `false`     | extra: also create the `Weather-<STUDENT>` stack (same as `-c weather=true`) |
| `WEATHER_CACHE_MINUTES` | `10`   | extra: how long a forecast stays in the cache  |
| `WEATHER_FORECAST_DAYS` | `3`    | extra: number of days in the forecast          |
| `WEATHER_HTTP_TIMEOUT_SECONDS` | `3` | extra: timeout for each Open-Meteo request |

`-c student=<last name>` takes priority over `STUDENT` from `.env`. `.env` is in `.gitignore`.
The Lambdas don't read `.env`: the stack passes `TABLE_NAME`, `LINK_TTL_MINUTES` and `LOG_LEVEL` to them at deploy time.

## Database structure

DynamoDB is schemaless: the stack declares only the key (`short_key`) and the TTL attribute.
The other attributes come from what `shorten_url` writes.

Table `UrlShortenerTable` (CDK `TableV2`, CloudFormation `AWS::DynamoDB::GlobalTable` with one region, on-demand billing):

| Attribute      | Type | Role                                                      |
|----------------|------|-----------------------------------------------------------|
| `short_key`    | S    | partition key, random 8 characters (`secrets.token_urlsafe(6)`) |
| `original_url` | S    | redirect target                                           |
| `created_at`   | N    | creation time, epoch seconds                              |
| `expires_at`   | N    | TTL attribute: `created_at + 15 * 60`, epoch seconds      |

Example item:

```json
{
  "short_key":    {"S": "q3Zr_x8A"},
  "original_url": {"S": "https://aws.amazon.com"},
  "created_at":   {"N": "1793861579"},
  "expires_at":   {"N": "1793862479"}
}
```

The only access pattern is "get by short_key", so no sort key or indexes are needed.
TTL deletes expired items lazily (sometimes days later), so `resolve_url` also checks `expires_at` itself.

## What changed (ДЗ 3)

- TTL: `time_to_live_attribute="expires_at"` on the table, `expires_at` written as a Number, 404 after expiry.
- Bonus, all three problems from slide 16:
  - URL validation: `400` instead of a `502` crash (missing or invalid body, no `url`, non-`http(s)` URL such as `javascript:`).
  - `201 Created` for `POST /shorten`.
  - Random key instead of MD5, with a conditional write (`attribute_not_exists`) so an existing link is never overwritten.
- Other best practices:
  - Least privilege: shorten may only `PutItem`, resolve may only `GetItem`.
  - Log groups with configurable retention (default 7 days), deleted with the stack; native JSON Lambda logs.
  - ARM64 Lambdas (cheaper), explicit timeout and memory.
  - API Gateway throttling: protects the shared course account.
  - Logs show the request id, not the whole event (which contains headers and IP).
  - `Cache-Control: private, max-age=<seconds left>` on the 301 so a browser doesn't keep redirecting after the link expires.

## Run the tests

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/unit -v      # the 3 homework tests
pytest tests/weather -v   # the extra weather tests
pytest -v                 # everything
```

## Deploy and check

```bash
cdk deploy -c student=<last name>
curl -X POST "$API/shorten" --data '{"url": "https://aws.amazon.com"}'   # 201 + shortened_url
curl -I "$SHORT_URL"          # 301 + Location
# 15+ minutes later
curl -I "$SHORT_URL"          # 404
cdk destroy -c student=<last name>
```

## Extra: weather forecast (approved by the curator)

The homework is untouched: it's tagged `hw3` in git, and the weather lives in a separate stack
that is **off by default**. Without the flag, `cdk deploy -c student=<last name>` deploys exactly the homework.

```
curl ──► API Gateway ──► WeatherLambda ──► WeatherCacheTable (DynamoDB, TTL 10 min)
          GET /weather       │  cache miss or expired
          ?city=Kyiv         ▼
                       Open-Meteo (free, no API key)
```

1. `GET /weather?city=Kyiv` looks up `city#kyiv` in the cache table.
2. Cache hit that hasn't expired: returns it with `"cached": true`.
3. Otherwise: finds the city's coordinates (Open-Meteo geocoding), fetches the forecast,
   stores it with `expires_at = now + 10 min`, returns it with `"cached": false`.
4. DynamoDB TTL removes old forecasts, the same mechanism as the short links.

Errors: no `city` → `400`, unknown city → `404`, Open-Meteo down or timed out → `502`.

Cache table `WeatherCacheTable`:

| Attribute    | Type | Role                                   |
|--------------|------|----------------------------------------|
| `cache_key`  | S    | partition key, `city#<name in lowercase>` |
| `payload`    | S    | forecast as JSON                       |
| `expires_at` | N    | TTL attribute, epoch seconds           |

Example response:

```json
{
  "city": "Kyiv", "country": "Ukraine", "latitude": 50.45, "longitude": 30.52,
  "current": {"time": "2026-11-05T09:30", "temperature_c": 1.7, "wind_kmh": 11.7, "description": "Overcast"},
  "daily": [{"date": "2026-11-05", "min_c": -0.4, "max_c": 5.2, "description": "Overcast"}],
  "cached": false,
  "expires_at": 1793862479
}
```

Deploy and check:

```bash
cdk deploy --all -c student=<last name> -c weather=true    # prints WeatherApiUrl
curl -s "$WEATHER_API_URL?city=Kyiv"                       # "cached": false
curl -s "$WEATHER_API_URL?city=Kyiv"                       # "cached": true
curl -s "$WEATHER_API_URL?city=Nowhereland12345"           # 404
cdk destroy --all -c student=<last name> -c weather=true
```

With two stacks CDK needs `--all` (or a stack name such as `Weather-<last name>`).

## Own CDK bootstrap and cleanup

CDK needs a one-time "bootstrap" per account and region: a `CDKToolkit` stack with an S3 bucket for Lambda zips
and templates, an ECR repository and IAM roles. `cdk destroy` never removes it.

In a shared course account, bootstrap your **own** toolkit with a qualifier, so you can remove it completely
without touching anyone else's:

```bash
# .env
STUDENT=katest
BOOTSTRAP_QUALIFIER=katest        # 1-10 lowercase letters or digits
```

```bash
cdk bootstrap aws://<account-id>/us-east-1 --qualifier katest --toolkit-stack-name CDKToolkit-katest
cdk deploy                        # uses STUDENT and BOOTSTRAP_QUALIFIER from .env
```

Without `BOOTSTRAP_QUALIFIER` the project uses the default shared `CDKToolkit`, as on the slides.
`-c qualifier=<name>` overrides `.env`.

Cleanup (`scripts/cleanup.py`) deletes only `ShortUrls-<student>`, `Weather-<student>` and `CDKToolkit-<qualifier>`
with its bucket (all object versions) and ECR repository. It never deletes the shared `CDKToolkit`.

```bash
python scripts/cleanup.py          # dry run: shows what it would delete
python scripts/cleanup.py --yes    # deletes
python scripts/cleanup.py --yes --keep-bootstrap   # only the app stacks
```
