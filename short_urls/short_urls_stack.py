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
LAMBDA_DIR = PROJECT_ROOT / "lambda"
SHARED_LAYER_DIR = PROJECT_ROOT / "shared"
RUNTIME = _lambda.Runtime.PYTHON_3_14


class ShortUrlsStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: AppConfig | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        config = config or load_config()

        table = dynamodb.TableV2(
            self,
            "UrlShortenerTable",
            partition_key=dynamodb.Attribute(name="short_key", type=dynamodb.AttributeType.STRING),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="expires_at",
        )

        shared_layer = _lambda.LayerVersion(
            self,
            "SharedConfigLayer",
            code=_lambda.Code.from_asset(str(SHARED_LAYER_DIR)),
            compatible_runtimes=[RUNTIME],
            compatible_architectures=[_lambda.Architecture.ARM_64],
            removal_policy=RemovalPolicy.DESTROY,
        )

        shorten_lambda = self._create_function(
            "ShortenLambda", "url_shortener.shorten_url", table, shared_layer, config
        )
        resolve_lambda = self._create_function(
            "ResolveLambda", "url_shortener.resolve_url", table, shared_layer, config
        )

        table.grant(shorten_lambda, "dynamodb:PutItem")
        table.grant(resolve_lambda, "dynamodb:GetItem")

        api = apigateway.RestApi(
            self,
            "UrlShortenerAPI",
            rest_api_name=f"{self.stack_name}-api",
            cloud_watch_role=False,
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                throttling_rate_limit=config.api_rate_limit,
                throttling_burst_limit=config.api_burst_limit,
            ),
        )
        api.root.add_resource("shorten").add_method(
            "POST", apigateway.LambdaIntegration(shorten_lambda)
        )
        api.root.add_resource("{short_key}").add_method(
            "GET", apigateway.LambdaIntegration(resolve_lambda)
        )

        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "TableName", value=table.table_name)

    def _create_function(
        self,
        construct_id: str,
        handler: str,
        table: dynamodb.TableV2,
        shared_layer: _lambda.LayerVersion,
        config: AppConfig,
    ) -> _lambda.Function:
        log_group = logs.LogGroup(
            self,
            f"{construct_id}Logs",
            retention=logs.RetentionDays[config.log_retention],
            removal_policy=RemovalPolicy.DESTROY,
        )
        return _lambda.Function(
            self,
            construct_id,
            runtime=RUNTIME,
            architecture=_lambda.Architecture.ARM_64,
            handler=handler,
            code=_lambda.Code.from_asset(str(LAMBDA_DIR)),
            layers=[shared_layer],
            timeout=Duration.seconds(10),
            memory_size=256,
            log_group=log_group,
            logging_format=_lambda.LoggingFormat.JSON,
            application_log_level_v2=_lambda.ApplicationLogLevel[config.log_level],
            system_log_level_v2=_lambda.SystemLogLevel.WARN,
            environment=config.lambda_environment(table.table_name),
        )
