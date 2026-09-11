"""Actual production startup failure checks and safe capability/config inspection."""
import json,os,subprocess,sys
from phase7_ops import ROOT,OUT,docker,command
config=json.loads(docker('inspect','omniops-phase7-a'))[0];env=dict(os.environ);env.update(dict(v.split('=',1) for v in config['Config']['Env'] if '=' in v))
keys=['DATABASE_URL','ENVIRONMENT','SECRET_KEY','COOKIE_SECURE','CORS_ORIGINS','SANDBOX_EXECUTION_MODE','SANDBOX_RUNNER_URL','SANDBOX_RUNNER_TOKEN','GEMINI_API_KEY','OPENAI_API_KEY'];flags=[v for k in keys for v in ['-e',k]]
script="import asyncio\nfrom app.main import app, lifespan\nasync def probe():\n    async with lifespan(app): pass\nasyncio.run(probe())"
results={}
for case,changes in [('missing_secret',{'SECRET_KEY':''}),('missing_runner_token',{'SANDBOX_RUNNER_TOKEN':''}),('missing_database',{'DATABASE_URL':''}),('insecure_cookie',{'COOKIE_SECURE':'false'}),('development',{'ENVIRONMENT':'development','SECRET_KEY':''}),('test',{'ENVIRONMENT':'test','SECRET_KEY':''})]:
 trial={**env,**changes}
 p,_=command(['docker','run','--rm','--network','omniops_default',*flags,'omniops-backend:phase7','python','-c',script],env=trial,label='config-'+case);results[case]={'startup_exit':p.returncode}
env.update(OMNIOPS_BACKEND_IMAGE=config['Image'],OMNIOPS_FRONTEND_IMAGE=json.loads(docker('inspect','omniops-phase7-front'))[0]['Image'])
p,_=command(['docker','compose','-f','docker-compose.prod.yml','config','--quiet'],env=env,label='production-compose-config');results['compose_config_exit']=p.returncode
# Actual readiness checks only unauthenticated /health; characterize wrong-token gap.
readiness="import asyncio,json\nfrom app.core.config import settings\nfrom app.api.v1.health import readiness\nsettings.SANDBOX_RUNNER_TOKEN='PHASE7_INVALID_TOKEN'\nasync def probe():\n    result=await readiness();print(json.dumps({'readiness_response_type':type(result).__name__,'status_code':getattr(result,'status_code',200)}))\nasyncio.run(probe())"
# Signature may use dependencies; do not fake those. Static gap is documented separately.
capabilities="import json; from app.core.config import settings; from app.ingestion.capabilities import capability_matrix; r={}; settings.OPENAI_API_KEY=None; settings.GEMINI_API_KEY=None; r['missing_all']={k:v.status.value for k,v in capability_matrix().items()}; settings.GEMINI_API_KEY='configured-audit-placeholder-not-a-live-key'; r['configured_key_presence_only']={k:v.status.value for k,v in capability_matrix().items()}; print(json.dumps(r))"
results['capabilities']=json.loads(docker('exec','omniops-phase7-a','python','-c',capabilities))
results['capability_fixture']='Configuration-presence test only; placeholder key makes no provider request.'
(OUT/'configuration.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
