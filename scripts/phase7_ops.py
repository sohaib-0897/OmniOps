"""Isolated audit operations. Credentials are passed in environment, never printed."""
from pathlib import Path
import json, os, secrets, subprocess, sys, time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'phase7-evidence'
OUT.mkdir(exist_ok=True)
def command(args, *, env=None, cwd=ROOT, label=None):
    start=time.monotonic()
    p=subprocess.run(args,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
    output=p.stdout+'\n'+p.stderr
    if env:
        for key,value in env.items():
            if value and len(value)>8 and any(word in key for word in ('SECRET','TOKEN','PASSWORD','API_KEY','DATABASE_URL')):
                output=output.replace(value,'[REDACTED]')
    if label:
        (OUT/(label+'.txt')).write_text(output,encoding='utf-8')
        record={'label':label,'exit':p.returncode,'seconds':round(time.monotonic()-start,2)}
        (OUT/(label+'.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(json.dumps(record),flush=True)
    if p.returncode and not label: raise RuntimeError('Command failed: '+args[0]+' '+(args[1] if len(args)>1 else '')+'; exit '+str(p.returncode))
    return p,output
def docker(*args): return command(['docker',*args])[0].stdout.strip()
def pg_env(database,container=False):
    assert database.startswith('omniops_phase7_') and 'test' in database
    cfg=json.loads(docker('inspect','omniops-postgres'))[0]
    values=dict(item.split('=',1) for item in cfg['Config']['Env'] if '=' in item)
    existing=docker('exec','omniops-postgres','psql','-U','omniops','-d','postgres','-Atc',f"SELECT 1 FROM pg_database WHERE datname='{database}'")
    if not existing: docker('exec','omniops-postgres','createdb','-U','omniops',database)
    env=dict(os.environ)
    host='omniops-postgres' if container else '127.0.0.1'
    env.update(DATABASE_URL=f"postgresql+asyncpg://omniops:{values['POSTGRES_PASSWORD']}@{host}:5432/{database}",ENVIRONMENT='test',SECRET_KEY=secrets.token_urlsafe(48),OPENAI_API_KEY='',GEMINI_API_KEY='',ANTHROPIC_API_KEY='',LLM_PROVIDER='analytical')
    return env
def main():
    mode=sys.argv[1]
    if mode=='resume':
        for name in ('runner','a','b','worker','front'): docker('start','omniops-phase7-'+name)
        print('Phase 7 containers started; unrelated stopped containers preserved.')
    elif mode=='image-audit':
        frozen=docker('exec','omniops-phase7-a','python','-m','pip','list','--format=freeze')
        (OUT/'backend-image-freeze.txt').write_text(frozen,encoding='utf-8')
        command([sys.executable,'-m','pip_audit','--no-deps','--disable-pip','-r','phase7-evidence/backend-image-freeze.txt','--format=json'],label='pip-audit-image')
    elif mode=='linux-media':
        docker('exec','omniops-phase7-a','mkdir','-p','/tmp/phase7/scripts','/tmp/phase7/phase7-evidence/test-media')
        for source,target in [(ROOT/'scripts/phase7_media.py','/tmp/phase7/scripts/phase7_media.py'),(OUT/'test-media/speech-tts.wav','/tmp/phase7/phase7-evidence/test-media/speech-tts.wav')]:
            uploaded=subprocess.run(['docker','exec','-i','omniops-phase7-a','python','-c','import sys; from pathlib import Path; Path('+repr(target)+').write_bytes(sys.stdin.buffer.read())'],input=source.read_bytes(),capture_output=True)
            assert uploaded.returncode==0,'Audit fixture copy to writable /tmp failed'
        command(['docker','exec','-e','PYTHONPATH=/app','omniops-phase7-a','python','/tmp/phase7/scripts/phase7_media.py'],label='linux-media')
        result=docker('exec','omniops-phase7-a','cat','/tmp/phase7/phase7-evidence/media.json');(OUT/'linux-media-results.json').write_text(result,encoding='utf-8')
    elif mode=='frontend':
        for label,args in [('typescript',['npx.cmd','tsc','--noEmit']),('lint',['npm.cmd','run','lint']),('build',['npm.cmd','run','build']),('audit',['npm.cmd','audit','--json'])]:command(args,cwd=ROOT/'frontend',label='final-frontend-'+label)
        for label,args in [('interaction',['node','--test','scripts/ui_frontend_tests.cjs']),('dedupe',['node','scripts/phase6_frontend_dedupe.cjs']),('replay',['node','scripts/ui_stream_replay_test.cjs'])]:command(args,label='final-frontend-'+label)
    elif mode=='final-regression':
        env=pg_env('omniops_phase7_regression_test');env['POSTGRES_TEST_DATABASE_URL']=env['DATABASE_URL'];env['SANDBOX_IMAGE']='omniops-python-sandbox:phase7'
        command([sys.executable,'-m','pytest','backend/tests','-q','--disable-warnings','--junitxml=phase7-evidence/final-backend-junit.xml'],env=env,label='final-backend-full')
        command([sys.executable,'-m','evals.runner'],env=env,label='final-phase1')
        command([sys.executable,'-m','pytest','backend/tests/test_postgres_hybrid_retrieval.py','-q','--disable-warnings'],env=env,label='final-postgres-retrieval')
        command([sys.executable,'-m','alembic','-c','alembic.ini','upgrade','head'],env=env,cwd=ROOT/'backend',label='final-migration')
    elif mode=='regression':
        env=pg_env('omniops_phase7_regression_test')
        env['POSTGRES_TEST_DATABASE_URL']=env['DATABASE_URL']
        command([sys.executable,'-m','alembic','-c','alembic.ini','upgrade','head'],env=env,cwd=ROOT/'backend',label='regression-migration')
        # The retrieval fixtures migrate/reset only this explicitly named test DB.
        command([sys.executable,'-m','pytest','backend/tests/test_postgres_hybrid_retrieval.py','-q','--disable-warnings'],env=env,label='postgres-retrieval')
        command([sys.executable,'-m','pytest','backend/tests','-q','--disable-warnings','--junitxml=phase7-evidence/backend-junit.xml'],env=env,label='backend-full')
        command([sys.executable,'-m','evals.runner'],env=env,label='phase1-evaluation')
    elif mode=='build':
        for name in ('backend','frontend','sandbox','sandbox-runner'):
            tag='omniops-'+('python-sandbox' if name=='sandbox' else name)+':phase7'
            args=['docker','build','-f',f'docker/Dockerfile.{name}','-t',tag]
            if name in ('sandbox','sandbox-runner'): args+=['--build-arg','BACKEND_IMAGE=omniops-backend:phase7']
            p,_=command([*args,'.'],label='build-'+name)
            if p.returncode: return
    elif mode=='dependencies':
        command([sys.executable,'-m','pip_audit','-r','backend/requirements.txt','--format=json'],label='pip-audit')
        command(['npm.cmd','audit','--json'],cwd=ROOT/'frontend',label='npm-audit')
    elif mode=='scan':
        for name in ('backend','frontend','python-sandbox','sandbox-runner'):
            command(['docker','scout','cves',f'omniops-{name}:phase7','--format','sarif'],label='scout-'+name)
    elif mode=='topology':
        env=pg_env('omniops_phase7_runtime_test',True)
        env.update(ENVIRONMENT='production',COOKIE_SECURE='true',CORS_ORIGINS='["https://localhost:13300"]',SANDBOX_EXECUTION_MODE='remote',SANDBOX_RUNNER_URL='http://omniops-phase7-runner:9100',SANDBOX_RUNNER_TOKEN=secrets.token_urlsafe(48),SANDBOX_IMAGE='omniops-python-sandbox:phase7')
        names=['DATABASE_URL','ENVIRONMENT','SECRET_KEY','COOKIE_SECURE','CORS_ORIGINS','SANDBOX_EXECUTION_MODE','SANDBOX_RUNNER_URL','SANDBOX_RUNNER_TOKEN','SANDBOX_IMAGE','OPENAI_API_KEY','GEMINI_API_KEY','ANTHROPIC_API_KEY','LLM_PROVIDER']
        flags=[arg for key in names for arg in ('-e',key)]
        docker('volume','create','omniops_phase7_audit_storage')
        base=['docker','run','--network','omniops_default']
        command([*base,'-d','--name','omniops-phase7-runner','-e','SANDBOX_RUNNER_TOKEN','-e','SANDBOX_IMAGE','-v','/var/run/docker.sock:/var/run/docker.sock','omniops-sandbox-runner:phase7'],env=env,label='launch-runner')
        p,_=command([*base,'--rm',*flags,'omniops-backend:phase7','alembic','-c','alembic.ini','upgrade','head'],env=env,label='clean-migration')
        if p.returncode: return
        for name,port in [('a',18101),('b',18102),('worker',None)]:
            args=[*base,'-d','--name','omniops-phase7-'+name,*flags,'--read-only','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=256m','--memory','2g','--cpus','2','-v','omniops_phase7_audit_storage:/app/storage']
            if port: args+=['-p',f'127.0.0.1:{port}:8000']
            else: args+=['--health-cmd',"python -c \"from pathlib import Path; assert b'app.worker' in Path('/proc/1/cmdline').read_bytes()\""]
            args+=['omniops-backend:phase7']
            if not port: args+=['python','-m','app.worker']
            command(args,env=env,label='launch-'+name)
        command([*base,'-d','--name','omniops-phase7-front','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=64m','-p','127.0.0.1:13100:3000','omniops-frontend:phase7'],label='launch-front')
    else: raise ValueError('Unknown audit mode')
if __name__=='__main__':main()
