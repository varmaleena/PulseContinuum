"""Exercise the built frontend's public access boundary with temporary credentials."""
import os
import secrets
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def exercise(configured):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    username, password = 'judge', secrets.token_urlsafe(32)
    care_password = secrets.token_urlsafe(32)
    env = {**os.environ, 'REQUIRE_JUDGE_AUTH': 'true', 'JUDGE_USERNAME': username if configured else '',
           'JUDGE_PASSWORD': password if configured else '', 'CARE_USERNAME':'care', 'CARE_PASSWORD':care_password}
    command = [shutil.which('node') or 'node', str(ROOT / 'frontend/node_modules/next/dist/bin/next'),
               'start', '--hostname', '127.0.0.1', '--port', str(port)]
    process = subprocess.Popen(command, cwd=ROOT / 'frontend', env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=10, trust_env=False) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Judge verification server failed to start')
                try:
                    response = client.get('/overview')
                    break
                except httpx.ConnectError:
                    time.sleep(0.2)
            else:
                raise RuntimeError('Judge verification server startup timed out')
            if not configured:
                assert response.status_code == 503, response.status_code
                print('PASS: missing required credentials fails closed (503)')
                return
            assert response.status_code == 307, response.status_code
            assert client.get('/login').status_code == 200
            assert client.get('/api/patients').status_code == 401
            assert client.get('/overview', auth=(username, 'incorrect')).status_code == 401
            for page in ['overview', 'workbench', 'pharmacy-rcs']:
                result = client.get('/' + page, auth=(username, password))
                assert result.status_code == 200, (page, result.status_code)
            care_auth = ('care', care_password)
            assert client.get('/telemetry', auth=care_auth).status_code == 307
            assert client.get('/agentcore', auth=care_auth).status_code == 307
            for path in ['/api/telemetry', '/api/events', '/api/webhooks/inbound']:
                assert client.get(path, auth=care_auth).status_code == 403
            origin = f'http://127.0.0.1:{port}'
            switch = {'json':{'profile':'admin'}, 'headers':{'origin':origin}}
            assert client.post('/api/profile', auth=care_auth, **switch).status_code == 403
            # A forged role header or view cookie must not elevate care credentials.
            assert client.get('/api/telemetry', auth=care_auth,
                headers={'x-pulse-profile':'admin', 'x-pulse-access':'admin', 'cookie':'pulse-profile=admin'}).status_code == 403
            health = client.get('/api/health', auth=care_auth)
            assert health.status_code == 200, 'Start the backend before the access verification'
            assert 'account_id' not in health.json()
            patients = client.get('/api/patients', auth=care_auth).raise_for_status().json()
            assert patients and all(not patient['traces'] for patient in patients)
            assert all('pending_message_id' not in patient for patient in patients)
            assert client.post('/api/profile', auth=(username,password), json={'profile':'admin'},
                headers={'origin':'https://untrusted.example'}).status_code == 403
            changed = client.post('/api/profile', auth=(username,password), **switch)
            assert changed.status_code == 200, (changed.status_code, changed.text)
            for page in ['agentcore', 'telemetry']:
                assert client.get('/' + page, auth=(username,password)).status_code == 200
            assert client.post('/api/profile', auth=(username,password), json={'profile':'care'},
                headers={'origin':origin}).status_code == 200
            assert client.get('/api/telemetry', auth=(username,password)).status_code == 403
            client.cookies.clear()
            assert client.post('/api/auth/login',json={'username':'care','password':care_password},
                headers={'origin':'https://untrusted.example'}).status_code == 403
            signed_in = client.post('/api/auth/login',json={'username':'care','password':care_password},headers={'origin':origin})
            assert signed_in.status_code == 200
            assert 'HttpOnly' in signed_in.headers['set-cookie']
            assert client.get('/workbench').status_code == 200
            assert client.get('/api/telemetry').status_code == 403
            assert client.post('/api/profile',**switch).status_code == 403
            assert client.post('/api/auth/logout',headers={'origin':origin}).status_code == 200
            assert client.get('/api/patients').status_code == 401
            assert client.post('/api/auth/login',json={'username':username,'password':password},headers={'origin':origin}).status_code == 200
            assert client.post('/api/profile',**switch).status_code == 200
            assert client.get('/telemetry').status_code == 200
            client.cookies.clear()
            client.cookies.set('pulse-session','forged.admin.session')
            assert client.get('/api/telemetry').status_code == 401
            print('PASS: anonymous/wrong credentials rejected; care routes work; raw API/page access blocked; '
                  'forged headers/cookie cannot elevate care credentials; signed browser login/logout and admin switching work')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == '__main__':
    exercise(True)
    exercise(False)
