import json
from pathlib import Path

from aws_client import call
from config import settings
from models.schemas import ClinicalProfile, PatientState


def seed() -> dict[str, PatientState]:
    dataset = json.loads((Path(__file__).parent.parent / 'sample_assets/synthetic_cohort.json').read_text(encoding='utf-8'))
    return {record['episode_id']: PatientState(
        **{key: record[key] for key in ('episode_id', 'patient_id', 'name', 'age', 'condition', 'day',
                                       'risk_score', 'phone', 'caregiver_phone', 'medications', 'red_flags')},
        physician_email=settings().test_physician_email or 'dr.rao@example.org',
        active_channel='LOCAL_REVIEW' if settings().aws_mode == 'live' else 'WHATSAPP',
        profile=ClinicalProfile.model_validate({**record, 'dataset_id': dataset['dataset_id'],
                                               'reference_date': dataset['reference_date']}))
        for record in dataset['episodes']}


class MemoryGraph:
    """DynamoDB unified identity graph; local JSON persistence is explicitly demo storage."""
    def __init__(self):
        self.path = Path(settings().data_dir) / 'episodes.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.states = seed()
        self.templates = seed()
        if self.path.exists():
            for key, value in json.loads(self.path.read_text(encoding='utf-8')).items():
                self.states[key] = self.enrich(PatientState.model_validate(value))

    def enrich(self, state: PatientState) -> PatientState:
        """Upgrade only known fictional fixture episodes; preserve completed workflows and audit IDs."""
        template = self.templates.get(state.episode_id)
        if template and state.is_synthetic:
            state.profile = template.profile
            state.phone = template.phone
            state.caregiver_phone = template.caregiver_phone
            if not state.ingested:
                state.medications = template.medications
                state.red_flags = template.red_flags
        return state

    def hydrate(self):
        if settings().aws_mode != 'live':
            return
        if not settings().memory_table:
            raise RuntimeError('Live mode requires a configured DynamoDB table')
        for episode_id in list(self.states):
            result = call('dynamodb', 'get_item', {'TableName': settings().memory_table,
                'Key': {'EpisodeID': {'S': episode_id}, 'EntityKey': {'S': 'STATE#CURRENT'}},
                'ConsistentRead': True}, 'DYNAMODB_MEMORY', demo={})
            item = result['response'].get('Item')
            if item:
                original = PatientState.model_validate_json(item['State']['S'])
                enriched = self.enrich(original.model_copy(deep=True))
                self.states[episode_id] = enriched
                if enriched != original:
                    self.save(enriched)
            else:
                self.save(self.states[episode_id])

    def get(self, episode_id: str) -> PatientState:
        if episode_id not in self.states:
            raise KeyError(episode_id)
        if settings().aws_mode == 'live' and settings().memory_table:
            result = call('dynamodb', 'get_item', {'TableName': settings().memory_table,
                'Key': {'EpisodeID': {'S': episode_id}, 'EntityKey': {'S': 'STATE#CURRENT'}},
                'ConsistentRead': True}, 'DYNAMODB_MEMORY', demo={})
            item = result['response'].get('Item')
            if item:
                self.states[episode_id] = PatientState.model_validate_json(item['State']['S'])
        return self.states[episode_id].model_copy(deep=True)

    def save(self, state: PatientState) -> PatientState:
        if settings().aws_mode == 'live':
            items = [('STATE#CURRENT', None), ('IDENTITY#WHATSAPP', state.phone),
                     ('IDENTITY#RCS', state.phone), ('IDENTITY#SMS', state.caregiver_phone),
                     ('IDENTITY#SES', state.physician_email)]
            for entity, address in items:
                item = {'EpisodeID': {'S': state.episode_id}, 'EntityKey': {'S': entity}}
                if address:
                    item['ChannelAddress'] = {'S': address}
                else:
                    item['State'] = {'S': state.model_dump_json()}
                call('dynamodb', 'put_item', {'TableName': settings().memory_table, 'Item': item},
                     'DYNAMODB_MEMORY', configured=bool(settings().memory_table))
        self.states[state.episode_id] = state
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({k: v.model_dump() for k, v in self.states.items()}, indent=2), encoding='utf-8')
        temporary.replace(self.path)
        return state

    def resolve(self, address: str) -> str:
        if settings().aws_mode == 'live' and settings().memory_table:
            result = call('dynamodb', 'query', {'TableName': settings().memory_table,
                'IndexName': 'ChannelIdentityIndex', 'KeyConditionExpression': 'ChannelAddress = :a',
                'ExpressionAttributeValues': {':a': {'S': address}}}, 'DYNAMODB_MEMORY', demo={})
            if result['response'].get('Items'):
                return result['response']['Items'][0]['EpisodeID']['S']
        for state in self.states.values():
            if address in (state.phone, state.caregiver_phone, state.physician_email):
                return state.episode_id
        raise KeyError(address)
