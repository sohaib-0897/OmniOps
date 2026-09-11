"""Last isolated deployment failures and complete Docker stdout/stderr log review."""
import json,os,subprocess,time,re
import httpx
from phase7_ops import docker,OUT,command
info=json.loads(docker('inspect','omniops-phase7-a'))[0];env=dict(os.environ);env.update(dict(x.split('=',1) for x in info['Config']['Env'] if '=' in x))
result={}
for case,changes,port in [('db_down',{'DATABASE_URL':'postgresql+asyncpg://audit:audit@127.0.0.1:1/unavailable'},18103),('wrong_runner_token',{'SANDBOX_RUNNER_TOKEN':'PHASE7_WRONG_RUNNER_TOKEN'},18104)]:
    trial={**env,**changes};keys=['DATABASE_URL','ENVIRONMENT','SECRET_KEY','COOKIE_SECURE','CORS_ORIGINS','SANDBOX_EXECUTION_MODE','SANDBOX_RUNNER_URL','SANDBOX_RUNNER_TOKEN','GEMINI_API_KEY','OPENAI_API_KEY'];flags=[v for k in keys for v in ['-e',k]]
    name='omniops-phase7-'+case
    p,_=command(['docker','run','--rm','-d','--name',name,'--network','omniops_default','-p',f'127.0.0.1:{port}:8000',*flags,'omniops-backend:phase7'],env=trial,label='fault-launch-'+case)
    if p.returncode:result[case]={'launch_exit':p.returncode};continue
    try:
        with httpx.Client(timeout=35) as client:
            for n in range(30):
                try:
                    health=client.get(f'http://127.0.0.1:{port}/api/v1/health')
                    if health.status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.5)
            ready=client.get(f'http://127.0.0.1:{port}/api/v1/readiness');result[case]={'health':health.status_code,'readiness':ready.status_code,'checks':ready.json()['data']['checks']}
    except Exception as exc:result[case]={'exception_type':type(exc).__name__}
    finally:docker('stop',name)
logs=[]
for name in ['a','b']:
    p=subprocess.run(['docker','logs','omniops-phase7-'+name],capture_output=True,text=True,encoding='utf-8',errors='replace');logs.append(p.stdout+p.stderr)
logs='\n'.join(logs)
found=[key for key in ['SECRET_KEY','SANDBOX_RUNNER_TOKEN','GEMINI_API_KEY','OPENAI_API_KEY'] if env.get(key) and env[key] in logs]
if 'Phase7OnlyStrongPass123!' in logs:found.append('TEST_PASSWORD')
result['complete_log_scan']={'stdout_and_stderr':True,'bytes':len(logs),'known_credentials_found':found,'jwt_literal':bool(re.search(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',logs)),'refresh_literal':bool(re.search(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.[A-Za-z0-9_-]{40,}',logs)),'sql_error_text':'INSERT INTO source_documents' in logs,'refresh_replay_event':'auth.refresh_replay' in logs,'logs_exported':False}
result['final_health']={n:httpx.get(f'http://127.0.0.1:{p}/api/v1/readiness',timeout=35).status_code for n,p in [('a',18101),('b',18102)]}
(OUT/'last-ops.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
