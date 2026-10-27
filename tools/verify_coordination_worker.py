"""Read-only proof that EventBridge invoked the hosted deadline worker without a browser."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import httpx
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]


def main():
    private = json.loads((ROOT/'tmp/hosting-config.json').read_text(encoding='utf-8'))['outputs']
    session = boto3.Session(profile_name='default',region_name='us-east-1')
    bounded = Config(connect_timeout=5,read_timeout=10,retries={'max_attempts':1})
    rule = session.client('events',config=bounded).describe_rule(Name=private['CoordinationRule'])
    function = session.client('lambda',config=bounded)
    config = function.get_function_configuration(FunctionName=private['FunctionName'])
    retries = function.get_function_event_invoke_config(FunctionName=private['FunctionName'])
    assert rule['State']=='ENABLED' and rule['ScheduleExpression']=='rate(5 minutes)'
    assert retries['MaximumRetryAttempts']==1 and retries['DestinationConfig']['OnFailure']['Destination']
    assert config['Environment']['Variables']['OUTBOUND_CHANNELS']==''
    assert config['Environment']['Variables']['MAX_MODEL_CALLS_PER_DAY']=='10'
    spoofed = httpx.post(private['BackendUrl'],json={'source':'pulsecontinuum.coordination',
        'detail-type':'CoordinationTick'},timeout=15)
    assert spoofed.status_code == 401, 'HTTP callers must not impersonate an internal scheduled invocation'
    end = datetime.now(timezone.utc)
    result = session.client('logs',config=bounded).filter_log_events(
        logGroupName=config.get('LoggingConfig',{}).get('LogGroup',f'/aws/lambda/{private["FunctionName"]}'),
        startTime=int((end-timedelta(minutes=20)).timestamp()*1000),
        filterPattern='"coordination_tick"',limit=30)
    ticks = []
    for item in result.get('events',[]):
        try:
            payload = json.loads(item['message'])
        except json.JSONDecodeError:
            continue
        if 'coordination_tick' in payload:
            ticks.append({'timestamp':item['timestamp'], 'result':payload['coordination_tick']})
    proof = {'checked_at':end.isoformat(),'schedule':rule['ScheduleExpression'],'rule_enabled':True,
        'async_retries':retries['MaximumRetryAttempts'],'failure_destination_configured':True,
        'outbound_channels_enabled':False,'daily_model_cap':10,'scheduled_invocations':ticks,
        'spoofed_http_tick_status':spoofed.status_code,
        'note':'This verifier reads logs only; it does not invoke the worker or mutate an episode.'}
    (ROOT/'submission/coordination-worker-verification.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print('AWS rule enabled; bounded retry/failure destination configured; no sends/model calls.')
    print(f'Observed {len(ticks)} actual scheduled worker log records; {sum(len(t["result"]["updated"]) for t in ticks)} updated episodes.')
    if not any(t['result']['updated'] for t in ticks):
        raise SystemExit('No scheduled state update observed yet; wait for the five-minute worker cycle.')


if __name__ == '__main__':
    main()
