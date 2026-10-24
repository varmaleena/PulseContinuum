from telemetry import now, telemetry


def inventory() -> list[dict]:
    return [
        {'id': 'generic', 'title': 'CarePlus Pharmacy', 'drug': 'Physician-approved generic', 'copay': '$0',
         'eta': '35 min', 'stock': 24, 'cold_chain': False, 'action': 'Request generic delivery'},
        {'id': 'brand', 'title': 'Apollo Care Pharmacy', 'drug': 'Prescribed brand', 'copay': '$8',
         'eta': '50 min', 'stock': 18, 'cold_chain': False, 'action': 'Request brand delivery'},
        {'id': 'triage', 'title': 'Clinical tele-triage', 'drug': 'On-call clinical review', 'copay': '$0',
         'eta': '4 PM demo slot', 'stock': 3, 'cold_chain': False, 'action': 'Request urgent tele-triage'},
    ]


def check_interactions(transcript: str) -> dict:
    duplicate = any(word in transcript.lower() for word in ['ibuprofen', 'diclofenac', 'blue tablet', 'nsaid'])
    return {'duplicate_nsaid_risk': duplicate,
            'guidance': 'Do not add or repeat pain medication; clinician must reconcile the reported dose.',
            'source': 'Curated demonstration rules; not a comprehensive drug interaction database'}


def reserve_order(episode_id: str, option_id: str) -> dict:
    option = next(o for o in inventory() if o['id'] == option_id)
    result = {'order_id': f'DEMO-RX-{episode_id}-{option_id}', 'status': 'PENDING_CLINICIAN_APPROVAL',
              'option': option, 'created_at': now(), 'fulfillment_mode': 'DEMO_ERP'}
    telemetry.emit({'category': 'MCP_PHARMACY', 'operation': 'reserve_order', 'execution_mode': 'DEMO',
                    'request': {'episode_id': episode_id, 'option_id': option_id}, 'response': result})
    return result


def build_mcp():
    from mcp.server.fastmcp import FastMCP
    server = FastMCP('PulseContinuum pharmacy ERP')
    server.tool()(inventory)
    server.tool()(check_interactions)
    server.tool()(reserve_order)
    return server


if __name__ == '__main__':
    build_mcp().run(transport='stdio')
