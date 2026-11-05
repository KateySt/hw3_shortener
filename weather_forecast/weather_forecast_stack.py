from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigateway,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_logs as logs,
)
from constructs import Construct
from shared_config import AppConfig, load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEATHER_LAMBDA_DIR = PROJECT_ROOT / "weather_lambda"
SHARED_LAYER_DIR = PROJECT_ROOT / "shared"
RUNTIME = _lambda.Runtime.PYTHON_3_14
ARCHITECTURE = _lambda.Architecture.ARM_64


class WeatherForecastStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: AppConfig | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        config = config or load_config()

        cache_table = dynamodb.TableV2(
            self,
            "WeatherCacheTable",
            partition_key=dynamodb.Attribute(name="cache_key", type=dynamodb.AttributeType.STRING),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="expires_at",
        )

        shared_layer = _lambda.LayerVersion(
            self,
            "SharedConfigLayer",
            code=_lambda.Code.from_asset(str(SHARED_LAYER_DIR)),
            compatible_runtimes=[RUNTIME],
            compatible_architectures=[ARCHITECTURE],
            removal_policy=RemovalPolicy.DESTROY,
        )

        weather_lambda = _lambda.Function(
            self,
            "WeatherLambda",
            runtime=RUNTIME,
            architecture=ARCHITECTURE,
            handler="weather.get_weather",
            code=_lambda.Code.from_asset(str(WEATHER_LAMBDA_DIR)),
            layers=[shared_layer],
            timeout=Duration.seconds(config.weather_http_timeout_seconds * 2 + 4),
            memory_size=256,
            log_group=logs.LogGroup(
                self,
                "WeatherLambdaLogs",
                retention=logs.RetentionDays[config.log_retention],
                removal_policy=RemovalPolicy.DESTROY,
            ),
            logging_format=_lambda.LoggingFormat.JSON,
            application_log_level_v2=_lambda.ApplicationLogLevel[config.log_level],
            system_log_level_v2=_lambda.SystemLogLevel.WARN,
            environment=config.weather_lambda_environment(cache_table.table_name),
        )

        cache_table.grant(weather_lambda, "dynamodb:GetItem", "dynamodb:PutItem")

        api = apigateway.RestApi(
            self,
            "WeatherAPI",
            rest_api_name=f"{self.stack_name}-api",
            cloud_watch_role=False,
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                throttling_rate_limit=config.api_rate_limit,
                throttling_burst_limit=config.api_burst_limit,
            ),
        )
        api.root.add_resource("weather").add_method(
            "GET",
            apigateway.LambdaIntegration(weather_lambda),
            request_parameters={"method.request.querystring.city": True},
            request_validator_options=apigateway.RequestValidatorOptions(validate_request_parameters=True),
        )

        CfnOutput(self, "WeatherApiUrl", value=f"{api.url}weather")
        CfnOutput(self, "WeatherCacheTableName", value=cache_table.table_name)
