"""Low-idle-cost backend; explicit bounded SES demo, no phone-send permissions."""
from aws_cdk import CfnCondition, CfnOutput, CfnParameter, Duration, Fn, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_destinations as destinations
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class HostedStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, code_bucket: str, code_key: str,
                 existing_table: str | None = None, existing_bucket: str | None = None,
                 existing_logs: str | None = None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        api_token = CfnParameter(self, 'ApiToken', no_echo=True, min_length=32)
        signing_key = CfnParameter(self, 'SigningKey', no_echo=True, min_length=32)
        demo_email = CfnParameter(self, 'DemoEmailAddress', no_echo=True, default='')
        email_enabled = CfnCondition(self,'DemoEmailEnabled',expression=Fn.condition_not(Fn.condition_equals(demo_email.value_as_string,'')))
        table = (dynamodb.Table.from_table_name(self, 'ExistingHostedMemory', existing_table) if existing_table else dynamodb.Table(self, 'HostedMemory',
            partition_key=dynamodb.Attribute(name='EpisodeID', type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name='EntityKey', type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute='ExpiresAt',
            encryption=dynamodb.TableEncryption.AWS_MANAGED, removal_policy=RemovalPolicy.RETAIN))
        if not existing_table:
            table.add_global_secondary_index(index_name='ChannelIdentityIndex',
                partition_key=dynamodb.Attribute(name='ChannelAddress', type=dynamodb.AttributeType.STRING),
                projection_type=dynamodb.ProjectionType.ALL)
        assets = (s3.Bucket.from_bucket_name(self, 'ExistingHostedAssets', existing_bucket) if existing_bucket else
            s3.Bucket(self, 'HostedAssets', block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True, encryption=s3.BucketEncryption.S3_MANAGED, removal_policy=RemovalPolicy.RETAIN))
        bus = events.EventBus(self, 'HostedEvents')
        group = (logs.LogGroup.from_log_group_name(self, 'ExistingBackendLogs', existing_logs) if existing_logs else
            logs.LogGroup(self, 'BackendLogs', retention=logs.RetentionDays.ONE_WEEK,
                          removal_policy=RemovalPolicy.RETAIN))
        function = lambda_.Function(self, 'Backend', runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.X86_64,
            code=lambda_.Code.from_bucket(s3.Bucket.from_bucket_name(self, 'CodeBucket', code_bucket), code_key),
            handler='lambda_handler.handler', timeout=Duration.seconds(60), memory_size=1024,
            log_group=group, environment={
                'AWS_MODE':'live', 'ALLOW_DEMO_FALLBACK':'false', 'SERVERLESS':'true',
                'DATA_DIR':'/tmp/pulsecontinuum', 'MEMORY_TABLE':table.table_name,
                'ASSETS_BUCKET':assets.bucket_name, 'EVENT_BUS_NAME':bus.event_bus_name,
                'API_TOKEN':api_token.value_as_string, 'AUDIT_SIGNING_KEY':signing_key.value_as_string,
                'OUTBOUND_CHANNELS':Fn.condition_if(email_enabled.logical_id,'SES','').to_string(),
                'TEST_PHYSICIAN_EMAIL':'clinician@synthetic.example',
                'DEMO_EMAIL_ENABLED':Fn.condition_if(email_enabled.logical_id,'true','false').to_string(),
                'DEMO_EMAIL_RECIPIENT':demo_email.value_as_string,'SES_VERIFIED_SENDER':demo_email.value_as_string,
                'EXPLICIT_EMAIL_ONLY':'true',
                'ALLOW_SYNTHETIC_RESET':'true', 'MAX_MODEL_CALLS_PER_DAY':'10',
                'BEDROCK_MODEL_ID':'us.amazon.nova-pro-v1:0'})
        table.grant_read_write_data(function)
        assets.grant_read_write(function)
        bus.grant_put_events_to(function)
        function.add_to_role_policy(iam.PolicyStatement(actions=['ses:SendEmail'],
            resources=[Fn.condition_if(email_enabled.logical_id,
                f'arn:aws:ses:{self.region}:{self.account}:identity/{demo_email.value_as_string}',
                f'arn:aws:ses:{self.region}:{self.account}:identity/disabled.example').to_string()],
            conditions={'StringEquals':{'ses:FromAddress':demo_email.value_as_string},
                'ForAllValues:StringEquals':{'ses:Recipients':[demo_email.value_as_string]}}))
        failed_ticks = sqs.Queue(self, 'CoordinationTickFailures',
            encryption=sqs.QueueEncryption.SQS_MANAGED, retention_period=Duration.days(1))
        function.configure_async_invoke(retry_attempts=1, max_event_age=Duration.minutes(5),
            on_failure=destinations.SqsDestination(failed_ticks))
        deadline_rule = events.Rule(self, 'CoordinationDeadlines',
            schedule=events.Schedule.rate(Duration.minutes(5)),
            description='Bounded synthetic handoff deadlines; no model calls or outbound messages')
        deadline_rule.add_target(targets.LambdaFunction(function,
            event=events.RuleTargetInput.from_object({'source':'pulsecontinuum.coordination',
                'detail-type':'CoordinationTick'}), retry_attempts=2,
            max_event_age=Duration.minutes(5), dead_letter_queue=failed_ticks))
        function.add_to_role_policy(iam.PolicyStatement(actions=['bedrock:InvokeModel'], resources=[
            f'arn:aws:bedrock:us-east-1:{self.account}:inference-profile/us.amazon.nova-pro-v1:0',
            'arn:aws:bedrock:*::foundation-model/amazon.nova-pro-v1:0']))
        url = function.add_function_url(auth_type=lambda_.FunctionUrlAuthType.NONE)
        CfnOutput(self, 'BackendUrl', value=url.url)
        CfnOutput(self, 'FunctionName', value=function.function_name)
        CfnOutput(self, 'MemoryTable', value=table.table_name)
        CfnOutput(self, 'AssetsBucket', value=assets.bucket_name)
        CfnOutput(self, 'CoordinationRule', value=deadline_rule.rule_name)
        CfnOutput(self, 'CoordinationFailureQueue', value=failed_ticks.queue_url)
