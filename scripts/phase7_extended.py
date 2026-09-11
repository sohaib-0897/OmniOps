"""Controlled final-image, migration, failure and storage audit. Test resources only."""
import asyncio, json, os, sys, time, uuid, subprocess
from pathlib import Path
import httpx
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from phase7_ops import pg_env, docker, command, OUT, ROOT
sys.path.insert(0,str(ROOT/'backend'))
from app.models.user import User, Workspace
from app.models.document import SourceDocument, DocumentChunk
from app.models.investigation import InvestigationSession, AgentToolAttempt, AgentPlanStep, AgentPlan
from app.models.evidence import RuntimeEvent, EvidenceItem, CalculationRecord, VerifiedClaim

report={}
def record(key,value):
    report[key]=value; (OUT/('extended-'+sys.argv[1]+'.json')).write_text(json.dumps(report,indent=2,default=str),encoding='utf-8'); print(key,json.dumps(value,default=str),flush=True)
def sql(statement,db='omniops_phase7_runtime_test'):
    assert db.startswith('omniops_phase7_') and 'test' in db
    return docker('exec','omniops-postgres','psql','-v','ON_ERROR_STOP=1','-U','omniops','-d',db,'-Atc',statement)
def remote(code):
    return json.loads(docker('exec','omniops-phase7-a','python','-c',code))

def migration():
    env=pg_env('omniops_phase7_migration_test'); pg_env('omniops_phase7_restore_test')
    for label,op in [('migration-empty',['upgrade','head']),('migration-down',['downgrade','-1']),('migration-up',['upgrade','head']),('migration-head',['current'])]:
        p,_=command([sys.executable,'-m','alembic','-c','alembic.ini',*op],cwd=ROOT/'backend',env=env,label=label); record(label,{'exit':p.returncode})
    sql("CREATE TABLE phase7_backup_probe (id integer PRIMARY KEY, marker text); INSERT INTO phase7_backup_probe VALUES (7,'AUTHORED_BACKUP_FIXTURE');",'omniops_phase7_migration_test')
    dump=subprocess.run(['docker','exec','omniops-postgres','pg_dump','-U','omniops','-Fc','omniops_phase7_migration_test'],capture_output=True)
    assert dump.returncode==0
    (OUT/'temporary-test-backup.dump').write_bytes(dump.stdout)
    restore=subprocess.run(['docker','exec','-i','omniops-postgres','pg_restore','-U','omniops','-d','omniops_phase7_restore_test','--no-owner'],input=dump.stdout,capture_output=True)
    record('backup_restore',{'dump_exit':dump.returncode,'restore_exit':restore.returncode,'restored_marker':sql('SELECT marker FROM phase7_backup_probe WHERE id=7','omniops_phase7_restore_test'),'restored_head':sql('SELECT version_num FROM alembic_version','omniops_phase7_restore_test')})

def sandbox():
    cases={
        'safe':'return 42',
        'secret_environment':"import os\nreturn sorted(k for k in os.environ if k in ['DATABASE_URL','SECRET_KEY','GEMINI_API_KEY','SANDBOX_RUNNER_TOKEN'])",
        'host_paths':"import os\nreturn {p:os.path.exists(p) for p in ['/app/.env','/host/.env','/var/run/docker.sock']}",
        'privileges':"import os\nreturn {'uid':os.getuid(),'capabilities':[x for x in open('/proc/self/status').read().splitlines() if x.startswith(('CapEff:','NoNewPrivs:'))]}",
        'readonly':"try:\n    open('/outside-marker','w').write('x')\n    return True\nexcept OSError:\n    return False",
        'network':"import socket\ntry:\n    socket.create_connection(('1.1.1.1',80),timeout=1)\n    return True\nexcept OSError:\n    return False",
        'cpu':'while True:\n    pass',
        'memory':'x=bytearray(512*1024*1024)\nreturn len(x)',
        'output':"print('x'*400000)\nreturn 1",
        'processes':"import subprocess\nprocs=[]\nfor n in range(100):\n    procs.append(subprocess.Popen(['python','-c','import time; time.sleep(5)']))\nreturn len(procs)",
    }
    results={}
    for name,code in cases.items():
        # Bypass AST intentionally and invoke the real authenticated remote OS boundary.
        script="import json; from app.tools.python_sandbox import RemoteSandboxRunner; r=RemoteSandboxRunner.execute("+repr(code)+",{},2); print(json.dumps({'success':r.success,'status':r.status,'error_code':r.error_code,'output':r.computed_output,'stdout_bytes':len(r.stdout),'duration_ms':r.duration_ms}))"
        results[name]=remote(script)
    denied=remote("import httpx,json; from app.core.config import settings; c=httpx.Client(trust_env=False); print(json.dumps({'missing':c.post(settings.SANDBOX_RUNNER_URL+'/v1/execute',json={'code':'return 42'}).status_code,'override':c.post(settings.SANDBOX_RUNNER_URL+'/v1/execute',headers={'Authorization':'Bearer '+settings.SANDBOX_RUNNER_TOKEN},json={'code':'return 42','privileged':True}).status_code}))")
    record('final_image_remote_sandbox',results); record('runner_auth_schema',denied)
    record('orphan_sandbox_jobs',docker('ps','-a','--filter','name=omniops-sandbox-','--format','{{.Names}}').splitlines())

async def main():
    mode=sys.argv[1]
    if mode=='migration': migration(); return
    if mode=='sandbox': sandbox(); return
    env=pg_env('omniops_phase7_runtime_test'); engine=create_async_engine(env['DATABASE_URL']); factory=async_sessionmaker(engine,expire_on_commit=False)
    async with httpx.AsyncClient(timeout=45) as client:
        base='http://127.0.0.1:18101/api/v1'
        async with factory() as db:
            user=(await db.execute(select(User).where(User.email.like('phase7-%-a@example.com')).order_by(User.created_at.desc()).limit(1))).scalar_one()
            ws=(await db.execute(select(Workspace).where(Workspace.created_by==user.id).limit(1))).scalar_one(); email=user.email; user_id=user.id; ws_id=ws.id
        auth=await client.post(base+'/auth/login',json={'email':email,'password':'Phase7OnlyStrongPass123!'}); assert auth.status_code==200
        h={'Authorization':'Bearer '+auth.json()['data']['token']['access_token']}
        if mode=='browser-context':
            async with factory() as db:
                actual=(await db.execute(select(InvestigationSession).where(InvestigationSession.user_id==user_id,InvestigationSession.objective=='Phase7 cactus').limit(1))).scalar_one()
                xss='<script>alert(1)</script><img src=x onerror=alert(1)>'
                fixture=InvestigationSession(workspace_id=ws_id,user_id=user_id,objective='AUTHORED PHASE 7 REPORT FIXTURE — not agent output',current_state='completed',status='completed',final_response={'executive_summary':'AUTHORED AUDIT FIXTURE. '+xss,'key_findings':[],'claims':[{'claim_id':'audit-xss','statement':xss,'epistemic_type':'fact','verification_status':'REJECTED','verification_errors':['AUTHORED_UNSUPPORTED_TEST_INPUT'],'citations':[]}],'inferences':[],'recommendations':[],'contradictions':[],'missing_data_warnings':['Authored report fixture. Not produced by the agent.'],'rejected_proposals':[]})
                db.add(fixture);await db.commit()
                record('browser_context',{'email':email,'workspace_id':str(ws_id),'actual_investigation_id':str(actual.id),'fixture_investigation_id':str(fixture.id),'fixture_label':fixture.objective})
        elif mode=='faults':
            before=remote("from pathlib import Path; import json; print(json.dumps(len(list(Path('/app/storage/uploads').rglob('*')))))")
            # Real server-side DB failure after the API has saved file bytes.
            sql("CREATE OR REPLACE FUNCTION phase7_reject_source() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.file_name='phase7-db-failure.txt' THEN RAISE EXCEPTION 'PHASE7_CONTROLLED_DATABASE_FAILURE'; END IF; RETURN NEW; END $$; CREATE TRIGGER phase7_reject_source BEFORE INSERT ON source_documents FOR EACH ROW EXECUTE FUNCTION phase7_reject_source();")
            try:
                resp=await client.post(base+f'/workspaces/{ws_id}/files',headers=h,files={'file':('phase7-db-failure.txt',b'Phase seven unique DB failure upload fixture.','text/plain')})
                record('file_after_db_failure',{'http':resp.status_code,'client_has_sql':any(s in resp.text for s in ['INSERT INTO','Traceback','asyncpg','/app/']),'physical_delta':remote("from pathlib import Path; import json; print(json.dumps(len(list(Path('/app/storage/uploads').rglob('*')))))")-before,'db_rows':sql("SELECT count(*) FROM source_documents WHERE file_name='phase7-db-failure.txt'")})
            finally: sql('DROP TRIGGER IF EXISTS phase7_reject_source ON source_documents; DROP FUNCTION IF EXISTS phase7_reject_source();')
            file=await client.post(base+f'/workspaces/{ws_id}/files',headers=h,files={'file':('phase7-delete-failure.txt',b'Phase7 deletion failure unique fixture.','text/plain')}); assert file.status_code==200; source_id=file.json()['data']['id']
            sql("CREATE OR REPLACE FUNCTION phase7_reject_delete() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.file_name='phase7-delete-failure.txt' THEN RAISE EXCEPTION 'PHASE7_CONTROLLED_DELETE_FAILURE'; END IF; RETURN OLD; END $$; CREATE TRIGGER phase7_reject_delete BEFORE DELETE ON source_documents FOR EACH ROW EXECUTE FUNCTION phase7_reject_delete();")
            try:
                deleted=await client.delete(base+f'/workspaces/{ws_id}/files/{source_id}',headers=h)
                async with factory() as db:
                    source=await db.get(SourceDocument,uuid.UUID(source_id)); path=source.storage_path
                exists=remote('from pathlib import Path; import json; print(json.dumps(Path('+repr(path)+').exists()))')
                record('delete_transaction_divergence',{'http':deleted.status_code,'row_remains':source is not None,'file_remains':exists})
            finally: sql('DROP TRIGGER IF EXISTS phase7_reject_delete ON source_documents; DROP FUNCTION IF EXISTS phase7_reject_delete();')
            # Kill only the isolated audit worker during an actual retrieval query.
            sql("CREATE OR REPLACE FUNCTION phase7_pause_attempt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF EXISTS(SELECT 1 FROM agent_plan_steps s JOIN agent_plans p ON p.id=s.plan_id JOIN investigation_sessions i ON i.id=p.investigation_id WHERE s.id=NEW.step_id AND i.objective='Phase7 crash cactus') THEN PERFORM pg_sleep(45); END IF; RETURN NEW; END $$; CREATE TRIGGER phase7_pause_attempt BEFORE INSERT ON agent_tool_attempts FOR EACH ROW EXECUTE FUNCTION phase7_pause_attempt();")
            try:
                async with factory() as db:
                    inv=InvestigationSession(workspace_id=ws_id,user_id=user_id,objective='Phase7 crash cactus',current_state='ready'); db.add(inv); await db.commit(); iid=inv.id
                observed=False
                for _ in range(25):
                    observed=int(sql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event='PgSleep'"))>0
                    if observed: break
                    await asyncio.sleep(1)
                docker('kill','omniops-phase7-worker')
                async with factory() as db:
                    inv=await db.get(InvestigationSession,iid); before_state=inv.current_state
                    before_events=await db.scalar(select(func.count()).select_from(RuntimeEvent).where(RuntimeEvent.investigation_id==iid))
            finally:
                sql('DROP TRIGGER IF EXISTS phase7_pause_attempt ON agent_tool_attempts; DROP FUNCTION IF EXISTS phase7_pause_attempt();'); docker('start','omniops-phase7-worker')
            for _ in range(30):
                async with factory() as db:
                    inv=await db.get(InvestigationSession,iid)
                    if inv.current_state in ['completed','failed']: break
                await asyncio.sleep(1)
            async with factory() as db:
                counts={}
                for model in [EvidenceItem,CalculationRecord,VerifiedClaim]: counts[model.__tablename__]=await db.scalar(select(func.count()).select_from(model).where(model.session_id==iid))
                counts['events']=await db.scalar(select(func.count()).select_from(RuntimeEvent).where(RuntimeEvent.investigation_id==iid))
                record('real_worker_crash',{'paused_production_attempt_observed':observed,'state_after_kill':before_state,'committed_events_after_kill':before_events,'recovered_state':inv.current_state,'failure_code':inv.failure_code,'counts':counts})
        elif mode=='topology':
            topology={}
            for name in ['a','b','worker','front','runner']:
                container=json.loads(docker('inspect','omniops-phase7-'+name))[0]
                topology[name]={'image_id':container['Image'],'user':container['Config']['User'],'read_only':container['HostConfig']['ReadonlyRootfs'],'privileged':container['HostConfig']['Privileged'],'cap_drop':container['HostConfig'].get('CapDrop'),'security_opt':container['HostConfig'].get('SecurityOpt'),'health':container['State'].get('Health',{}).get('Status'),'mounts':[{'type':m['Type'],'destination':m['Destination']} for m in container['Mounts']]}
            record('containers',topology)
            record('catalog',{'head':sql('SELECT version_num FROM alembic_version'),'indexes':sql("SELECT indexdef FROM pg_indexes WHERE tablename='document_chunks' ORDER BY indexname").splitlines(),'extensions':sql('SELECT extname FROM pg_extension').splitlines(),'rls_tables':sql("SELECT relname FROM pg_class WHERE relrowsecurity AND relnamespace='public'::regnamespace").splitlines()})
            normal=await client.get(base+'/readiness'); record('normal_readiness',{'code':normal.status_code,'body':normal.json()})
            docker('stop','omniops-phase7-runner')
            try:
                r=await client.get(base+'/readiness'); record('runner_down',{'health':(await client.get(base+'/health')).status_code,'readiness':r.status_code,'sandbox':remote("import json; from app.tools.python_sandbox import PythonSandboxRunner; r=PythonSandboxRunner.execute('return 42'); print(json.dumps({'success':r.success,'code':r.error_code}))")})
            finally: docker('start','omniops-phase7-runner')
            docker('network','disconnect','omniops_default','omniops-phase7-a')
            try:
                checked=remote("import httpx,json; c=httpx.Client(timeout=35); print(json.dumps({'health':c.get('http://127.0.0.1:8000/api/v1/health').status_code,'readiness':c.get('http://127.0.0.1:8000/api/v1/readiness').status_code}))")
                record('db_unreachable',{**checked,'B_health':(await client.get('http://127.0.0.1:18102/api/v1/health')).status_code})
            finally: docker('network','connect','omniops_default','omniops-phase7-a')
        else: raise ValueError(mode)
    await engine.dispose()
if __name__=='__main__': asyncio.run(main())
