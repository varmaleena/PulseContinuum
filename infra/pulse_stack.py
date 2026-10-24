from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_events as events,
)
from aws_cdk import (
    aws_events_targets as targets,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_ses as ses,
)
from aws_cdk import (
    aws_ses_actions as ses_actions,
)
from aws_cdk import (
    aws_sns as sns,
)
from aws_cdk import (
    aws_sns_subscriptions as subscriptions,
)
from aws_cdk import (
    aws_sqs as sqs,
)
from constructs import Construct


class PulseStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, existing_table_name: str | None = None,
                 existing_bucket_name: str | None = None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        table = (dynamodb.Table.from_table_name(self, 'ExistingMemoryTable', existing_table_name)
            if existing_table_name else dynamodb.Table(self, 'PulseContinuumMemoryTable',
            partition_key=dynamodb.Attribute(name='EpisodeID', type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name='EntityKey', type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=True),
            removal_policy=RemovalPolicy.RETAIN))
        if not existing_table_name:
            table.add_global_secondary_index(index_name='ChannelIdentityIndex',
                partition_key=dynamodb.Attribute(name='ChannelAddress', type=dynamodb.AttributeType.STRING),
                projection_type=dynamodb.ProjectionType.ALL)
        bucket = (s3.Bucket.from_bucket_name(self, 'ExistingAssetsBucket', existing_bucket_name)
            if existing_bucket_name else s3.Bucket(self, 'PulseClinicalAssetsBucket', encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True, versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[s3.LifecycleRule(abort_incomplete_multipart_upload_after=Duration.days(1))]))
        imported_bucket_policy = None
        if existing_bucket_name:
            imported_bucket_policy = s3.BucketPolicy(self, 'ExistingAssetsBucketPolicy', bucket=bucket)
            imported_bucket_policy.document.add_statements(
                iam.PolicyStatement(principals=[iam.ServicePrincipal('ses.amazonaws.com')],
                    actions=['s3:PutObject'], resources=[bucket.arn_for_objects('inbound/*')],
                    conditions={'StringEquals': {'aws:SourceAccount': self.account}}),
                iam.PolicyStatement(effect=iam.Effect.DENY, principals=[iam.AnyPrincipal()],
                    actions=['s3:*'], resources=[bucket.bucket_arn, bucket.arn_for_objects('*')],
                    conditions={'Bool': {'aws:SecureTransport': 'false'}}))
        topic = sns.Topic(self, 'CDSInboundAndDeliveryEvents', enforce_ssl=True)
        ses_publish = topic.add_to_resource_policy(iam.PolicyStatement(
            principals=[iam.ServicePrincipal('ses.amazonaws.com')], actions=['sns:Publish'],
            resources=[topic.topic_arn], conditions={'StringEquals': {'aws:SourceAccount': self.account}}))
        dead_letter = sqs.Queue(self, 'InboundDeadLetter', retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED, enforce_ssl=True)
        queue = sqs.Queue(self, 'InboundQueue', visibility_timeout=Duration.seconds(60),
            encryption=sqs.QueueEncryption.SQS_MANAGED, enforce_ssl=True,
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=4, queue=dead_letter))
        topic.add_subscription(subscriptions.SqsSubscription(queue, raw_message_delivery=True))
        inbound = events.Rule(self, 'InboundAndDeliveryRule', event_pattern=events.EventPattern(
            source=['aws.social-messaging', 'aws.socialmessaging', 'aws.sms-voice']))
        inbound.add_target(targets.SnsTopic(topic, dead_letter_queue=dead_letter))
        failure = events.Rule(self, 'ClinicalDeliveryFailureRule', event_pattern=events.EventPattern(
            source=['pulsecontinuum.delivery'], detail_type=['ClinicalDeliveryFailure'],
            detail={'status': ['FAILED', 'UNDELIVERED', 'TIMEOUT']}))
        failure.add_target(targets.SnsTopic(topic, dead_letter_queue=dead_letter))
        # EventBridge itself cannot delay an event by 15 seconds. SQS message delay is the timer.
        timer = sqs.Queue(self, 'DeliveryWatchdogQueue', delivery_delay=Duration.seconds(15),
            visibility_timeout=Duration.seconds(60), encryption=sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl=True, dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=4, queue=dead_letter))
        pending = events.Rule(self, 'PendingAlertRule', event_pattern=events.EventPattern(
            source=['pulsecontinuum.delivery'], detail_type=['ClinicalAlertPending']))
        pending.add_target(targets.SqsQueue(timer, message=events.RuleTargetInput.from_event_path('$.detail')))
        watchdog = lambda_.Function(self, 'DeliveryWatchdog', runtime=lambda_.Runtime.PYTHON_3_11,
            handler='index.handler', timeout=Duration.seconds(30),
            environment={'MEMORY_TABLE': table.table_name},
            code=lambda_.Code.from_inline('''import json, os, boto3
ddb = boto3.client('dynamodb')
events = boto3.client('events')
def handler(event, context):
    for record in event['Records']:
        detail = json.loads(record['body'])
        item = ddb.get_item(TableName=os.environ['MEMORY_TABLE'], Key={
            'EpisodeID': {'S': detail['episode_id']}, 'EntityKey': {'S': 'STATE#CURRENT'}}, ConsistentRead=True).get('Item')
        if not item:
            continue
        state = json.loads(item['State']['S'])
        if state.get('pending_message_id') == detail['message_id'] and state.get('delivery_status') == 'PENDING':
            detail['status'] = 'TIMEOUT'
            response = events.put_events(Entries=[{'Source': 'pulsecontinuum.delivery',
                'DetailType': 'ClinicalDeliveryFailure', 'Detail': json.dumps(detail)}])
            if response.get('FailedEntryCount'):
                raise RuntimeError('EventBridge rejected delivery timeout')
    return {'status': 'ok'}
'''))
        from aws_cdk.aws_lambda_event_sources import SqsEventSource
        watchdog.add_event_source(SqsEventSource(timer, batch_size=1))
        table.grant_read_data(watchdog)
        watchdog.add_to_role_policy(iam.PolicyStatement(actions=['events:PutEvents'],
            resources=[self.format_arn(service='events', resource='event-bus', resource_name='default')]))
        # SES rules are provisioned inactive: activate after domain verification and MX setup.
        rules = ses.ReceiptRuleSet(self, 'HospitalDischargeInbound')
        receipt_rule = rules.add_rule('StoreDischargeMIME', enabled=True, scan_enabled=True,
            actions=[ses_actions.S3(bucket=bucket, object_key_prefix='inbound/', topic=topic)])
        if ses_publish.policy_dependable:
            receipt_rule.node.add_dependency(ses_publish.policy_dependable)
        if imported_bucket_policy:
            receipt_rule.node.add_dependency(imported_bucket_policy)
        role = iam.Role(self, 'BackendServiceRole', assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'))
        messaging_role = iam.Role(self, 'MessagingSNSPublishRole',
            assumed_by=iam.ServicePrincipal('sms-voice.amazonaws.com', conditions={
                'StringEquals': {'aws:SourceAccount': self.account}}))
        topic.grant_publish(messaging_role)
        topic.add_to_resource_policy(iam.PolicyStatement(
            principals=[iam.ServicePrincipal('social-messaging.amazonaws.com')],
            actions=['sns:Publish'], resources=[topic.topic_arn],
            conditions={'StringEquals': {'aws:SourceAccount': self.account}}))
        table.grant_read_write_data(role)
        bucket.grant_read_write(role)
        queue.grant_consume_messages(role)
        role.add_to_policy(iam.PolicyStatement(actions=['social-messaging:SendWhatsAppMessage',
            'sms-voice:SendTextMessage', 'sms-voice:SendRcsMessage', 'ses:SendEmail',
            'bedrock:InvokeModel', 'bedrock:ApplyGuardrail', 'bedrock-agentcore:InvokeAgentRuntime'],
            resources=['*']))
        role.add_to_policy(iam.PolicyStatement(actions=['events:PutEvents'],
            resources=[self.format_arn(service='events', resource='event-bus', resource_name='default')]))
        for name, value in {'MemoryTable': table.table_name, 'AssetsBucket': bucket.bucket_name,
                            'InboundTopicArn': topic.topic_arn, 'InboundQueueUrl': queue.queue_url,
                            'BackendRoleArn': role.role_arn, 'MessagingSNSRoleArn': messaging_role.role_arn,
                            'ReceiptRuleSet': rules.receipt_rule_set_name}.items():
            CfnOutput(self, name, value=value)
