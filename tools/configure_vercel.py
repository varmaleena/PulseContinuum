"""Store server-only deployment configuration using the authenticated official CLI."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT/'tmp/hosting-config.json').read_text(encoding='utf-8'))
    values = {'BACKEND_URL':config['outputs']['BackendUrl'], 'BACKEND_API_TOKEN':config['api_token'],
        'REQUIRE_JUDGE_AUTH':'true', 'BACKEND_EVENT_TRANSPORT':'poll',
        'JUDGE_USERNAME':config['admin_username'], 'JUDGE_PASSWORD':config['admin_password'],
        'CARE_USERNAME':config['care_username'], 'CARE_PASSWORD':config['care_password']}
    env = {**os.environ,'npm_config_cache':str(ROOT.parent/'.npm-cache')}
    for key,value in values.items():
        command = ['npx.cmd' if os.name == 'nt' else 'npx', '--yes','vercel@65.2.0','env','add',key,
            '--environment','production,preview','--sensitive','--force','--yes',
            '--scope','leenas-projects-b545d353']
        result = subprocess.run(command,cwd=ROOT,env=env,input=value+'\n',text=True,
                                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if result.returncode:
            raise RuntimeError(f'Vercel configuration failed for {key}; no secret output printed')
        print('Configured',key,flush=True)
    print('Configured eight encrypted server-only variables. No AWS access keys copied.')


if __name__ == '__main__':
    main()
