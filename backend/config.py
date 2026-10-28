from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    aws_region: str = 'us-east-1'
    aws_mode: str = 'demo'
    aws_profile: str = ''
    allow_demo_fallback: bool = True
    outbound_channels: str = ''
    allowed_email_recipients: str = ''
    aws_account_id: str = ''
    test_physician_email: str = ''
    whatsapp_origination_id: str = ''
    whatsapp_meta_api_version: str = 'v23.0'
    sms_origination_id: str = ''
    rcs_origination_id: str = ''
    ses_verified_sender: str = ''
    memory_table: str = ''
    assets_bucket: str = ''
    event_bus_name: str = 'default'
    inbound_queue_url: str = ''
    bedrock_model_id: str = 'us.amazon.nova-pro-v1:0'
    bedrock_guardrail_id: str = ''
    bedrock_guardrail_version: str = 'DRAFT'
    agentcore_runtime_arn: str = ''
    webhook_token: str = ''
    api_token: str = ''
    audit_signing_key: str = 'demo-only-not-a-production-key'
    cors_origins: str = 'http://localhost:3000,http://127.0.0.1:3000'
    data_dir: str = '.data'
    serverless: bool = False
    allow_synthetic_reset: bool = False
    max_model_calls_per_day: int = 0
    demo_email_enabled: bool = False
    demo_email_recipient: str = ''
    explicit_email_only: bool = False

    def channel_enabled(self, channel: str) -> bool:
        return self.aws_mode == 'demo' or channel in self.outbound_channels.upper().split(',')


@lru_cache
def settings() -> Settings:
    return Settings()
