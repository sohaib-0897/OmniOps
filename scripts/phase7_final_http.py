"""Final controlled auth/rate/SSE probes. Only isolated Phase 7 test state."""
import asyncio,json,sys,uuid,time,statistics
from datetime import datetime,timezone,timedelta
from contextlib import AsyncExitStack
import httpx,jwt
from sqlalchemy import select,func,text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from phase7_ops import ROOT,OUT,pg_env,docker
sys.path.insert(0,str(ROOT/'backend'))
from app.models.user import User,Workspace
from app.models.investigation import InvestigationSession
from app.models.evidence import RuntimeEvent
result={}
def save(name,value):result[name]=value;(OUT/'final-http.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8');print(name,json.dumps(value,default=str),flush=True)
async def main():
    env=pg_env('omniops_phase7_runtime_test');engine=create_async_engine(env['DATABASE_URL']);factory=async_sessionmaker(engine,expire_on_commit=False)
    cfg=json.loads(docker('inspect','omniops-phase7-a'))[0];actual_env=dict(v.split('=',1) for v in cfg['Config']['Env'] if '=' in v)
    a='http://127.0.0.1:18101/api/v1';b='http://127.0.0.1:18102/api/v1'
    async with factory() as db:
        user=(await db.execute(select(User).where(User.email.like('phase7-%-b@example.com')).limit(1))).scalar_one();ws=(await db.execute(select(Workspace).where(Workspace.created_by==user.id).limit(1))).scalar_one();wid=ws.id;uid=user.id;email=user.email
    async with httpx.AsyncClient(timeout=35,limits=httpx.Limits(max_connections=40)) as client:
        r=await client.post(a+'/auth/login',json={'email':email,'password':'Phase7OnlyStrongPass123!'});assert r.status_code==200;token=r.json()['data']['token']['access_token'];cookie=r.cookies.get('omniops_refresh');h={'Authorization':'Bearer '+token}
        second=await client.post(b+'/auth/login',json={'email':email,'password':'Phase7OnlyStrongPass123!'});assert second.status_code==200;second_token=second.json()['data']['token']['access_token']
        payload=jwt.decode(token,options={'verify_signature':False});payload['exp']=int(time.time())-10;expired=jwt.encode(payload,actual_env['SECRET_KEY'],algorithm='HS256');altered=token[:-5]+'abcde'
        async with factory() as db:
            inv=InvestigationSession(workspace_id=wid,user_id=uid,objective='AUTHORED slow SSE fixture',current_state='failed',status='failed');db.add(inv);await db.flush();iid=inv.id
            now=datetime.now(timezone.utc)
            for n in range(1200):db.add(RuntimeEvent(investigation_id=iid,event_type='phase7.slow',logical_identity=uuid.uuid4().hex,payload={'n':n,'padding':'x'*8192},created_at=now+timedelta(microseconds=n)))
            await db.commit();ids=[str(v) for v in (await db.execute(select(RuntimeEvent.id).where(RuntimeEvent.investigation_id==iid).order_by(RuntimeEvent.created_at,RuntimeEvent.id))).scalars()]
        save('access_attacks',{'expired_api':(await client.get(a+'/auth/me',headers={'Authorization':'Bearer '+expired})).status_code,'expired_sse':(await client.get(b+f'/investigations/{iid}/stream',headers={'Authorization':'Bearer '+expired})).status_code,'altered_signature':(await client.get(a+'/auth/me',headers={'Authorization':'Bearer '+altered})).status_code})
        refreshed=await client.post(b+'/auth/refresh',headers={'Cookie':'omniops_refresh='+cookie,'Origin':'https://localhost:13300'});assert refreshed.status_code==200;h={'Authorization':'Bearer '+refreshed.json()['data']['token']['access_token']}
        def rss():
            return int(docker('exec','omniops-phase7-a','python','-c',"from pathlib import Path; print(next(int(x.split()[1]) for x in Path('/proc/1/status').read_text().splitlines() if x.startswith('VmRSS:')))"))
        before=rss();seen=[]
        async with client.stream('GET',a+f'/investigations/{iid}/stream',headers=h) as stream:
            assert stream.status_code==200;await asyncio.sleep(3);paused=rss()
            async for line in stream.aiter_lines():
                if line.startswith('id:'):
                    seen.append(line[3:].strip())
                    if len(seen)%100==0:await asyncio.sleep(.1)
                    if len(seen)==len(ids):break
        await asyncio.sleep(1)
        async with factory() as db:activity=dict((await db.execute(text("SELECT state,count(*) FROM pg_stat_activity WHERE datname=current_database() GROUP BY state"))).all())
        save('slow_sse',{'persisted_events':len(ids),'payload_bytes_per_event':8192,'received':len(seen),'exact_order':seen==ids,'duplicates':len(seen)-len(set(seen)),'rss_kib_before':before,'rss_kib_paused':paused,'rss_kib_after':rss(),'db_activity':activity,'capacity_claim':False})
        # Concurrent real requests exercise the durable database rate limiter.
        limit=asyncio.Semaphore(4)
        async def submit(n):
            async with limit:
                return (await client.post((a if n%2 else b)+f'/workspaces/{wid}/investigations',headers=h,json={'objective':f'Phase7 concurrent request {n}','max_steps':6})).status_code
        statuses=await asyncio.gather(*(submit(n) for n in range(24)));save('investigation_rate_A_B',{'requests':24,'concurrency':4,'statuses':{str(s):statuses.count(s) for s in set(statuses)}})
        uploads=[]
        for n in range(32):uploads.append((await client.post((a if n%2 else b)+f'/workspaces/{wid}/files',headers=h,files={'file':('invalid.exe',b'AUDIT','application/octet-stream')})).status_code)
        save('upload_rate_A_B',{'requests':32,'statuses':{str(s):uploads.count(s) for s in set(uploads)}})
        logout=await client.post(a+'/auth/logout-all',headers=h);save('logout_all',{'status':logout.status_code,'session_one':(await client.get(a+'/auth/me',headers=h)).status_code,'session_two':(await client.get(b+'/auth/me',headers={'Authorization':'Bearer '+second_token})).status_code})
        login=[]
        for n in range(14):login.append((await client.post((a if n%2 else b)+'/auth/login',json={'email':'phase7-no-account@example.com','password':'wrong-password'})).status_code)
        save('login_rate_A_B',{'requests':14,'statuses':{str(s):login.count(s) for s in set(login)}})
        save('response_headers',{name:(await client.get(base)).headers.get(name) for name,base in [('x-request-id',a+'/health'),('x-content-type-options',a+'/health'),('content-security-policy','http://127.0.0.1:13100/')]})
    logs='\n'.join(docker('logs','omniops-phase7-'+n) for n in ['a','b'])
    exact_leaks=[]
    for label,value in [('access',token),('refresh',cookie),('password','Phase7OnlyStrongPass123!'),('secret',actual_env['SECRET_KEY']),('runner_token',actual_env['SANDBOX_RUNNER_TOKEN'])]:
        if value and value in logs:exact_leaks.append(label)
    save('log_scan',{'exact_test_credentials_found':exact_leaks,'raw_SQL_in_error_logs':'INSERT INTO source_documents' in logs,'refresh_replay_audit_event':'auth.refresh_replay' in logs,'log_bytes':len(logs),'logs_exported':False})
    await engine.dispose()
if __name__=='__main__':asyncio.run(main())
