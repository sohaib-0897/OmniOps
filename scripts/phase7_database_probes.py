"""Real PostgreSQL cursor/lease/planner adversarial probes, test database only."""
import asyncio, json, uuid, sys
from datetime import datetime,timezone,timedelta
import httpx
from sqlalchemy import select,text,update,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from phase7_ops import ROOT,OUT,pg_env
sys.path.insert(0,str(ROOT/'backend'))
from app.models.user import User,Workspace
from app.models.document import SourceDocument,DocumentChunk
from app.models.investigation import InvestigationSession
from app.models.evidence import RuntimeEvent
from app.agent.runtime import acquire_lease,release_lease,persist_runtime_event
async def main():
    env=pg_env('omniops_phase7_runtime_test');engine=create_async_engine(env['DATABASE_URL']);factory=async_sessionmaker(engine,expire_on_commit=False);result={}
    async with factory() as db:
        user=(await db.execute(select(User).where(User.email.like('phase7-%-b@example.com')).limit(1))).scalar_one();ws=(await db.execute(select(Workspace).where(Workspace.created_by==user.id).limit(1))).scalar_one();email=user.email;wid=ws.id
        inv=InvestigationSession(workspace_id=ws.id,user_id=user.id,objective='PHASE7 lease and SSE boundary fixture',status='failed',current_state='failed');db.add(inv);await db.commit();iid=inv.id
    async with factory() as a, factory() as b:
        old=await a.get(InvestigationSession,iid);await acquire_lease(a,old,'phase7-stale-a',30);await a.commit()
        await b.execute(update(InvestigationSession).where(InvestigationSession.id==iid).values(lease_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)));await b.commit()
        new=await b.get(InvestigationSession,iid);acquired=await acquire_lease(b,new,'phase7-new-b',30);await b.commit()
        await release_lease(a,old,'phase7-stale-a');await a.commit()
        async with factory() as check:
            current=await check.get(InvestigationSession,iid);result['stale_release']={'B_acquired':acquired,'owner_after_stale_A_release':current.worker_id,'B_lease_preserved':current.worker_id=='phase7-new-b'}
    async with httpx.AsyncClient(timeout=10) as client:
        base='http://127.0.0.1:18102/api/v1';r=await client.post(base+'/auth/login',json={'email':email,'password':'Phase7OnlyStrongPass123!'});assert r.status_code==200;h={'Authorization':'Bearer '+r.json()['data']['token']['access_token']}
        async with factory() as late, factory() as early:
            one=await persist_runtime_event(late,iid,'phase7.late_commit',uuid.uuid4().hex,{'audit_fixture':True})
            await asyncio.sleep(.1)
            two=await persist_runtime_event(early,iid,'phase7.early_commit',uuid.uuid4().hex,{'audit_fixture':True});await early.commit()
            observed=[]
            async with client.stream('GET',base+f'/investigations/{iid}/stream',headers=h) as stream:
                iterator=stream.aiter_lines()
                async for line in iterator:
                    if line.startswith('id:'):observed.append(line[3:].strip());break
                await late.commit()
                try:
                    async with asyncio.timeout(3):
                        async for line in iterator:
                            if line.startswith('id:'):observed.append(line[3:].strip());break
                except TimeoutError:pass
            resumed=[]
            try:
                async with asyncio.timeout(3):
                    async with client.stream('GET',base+f'/investigations/{iid}/stream',headers={**h,'Last-Event-ID':str(two.id)}) as stream:
                        async for line in stream.aiter_lines():
                            if line.startswith('id:'):resumed.append(line[3:].strip());break
            except TimeoutError:pass
            result['late_commit_cursor']={'durable_events':2,'early_commit_seen':str(two.id) in observed,'late_commit_seen_live':str(one.id) in observed,'late_commit_seen_reconnect':str(one.id) in resumed,'fixture':'Two legitimate event-writer transactions commit out of creation order'}
    # Planner workload consists solely of labeled synthetic data, not quality evaluation.
    async with factory() as db:
        source=SourceDocument(workspace_id=wid,file_name='AUTHORED_SYNTHETIC_INDEX_FIXTURE',storage_path='/audit/no-physical-file',mime_type='text/plain',byte_size=0,sha256_hash=uuid.uuid4().hex*2,modality='text',processing_status='ready');db.add(source);await db.flush()
        vec='['+','.join(['1']+['0']*1535)+']'
        await db.execute(text("INSERT INTO document_chunks (id,workspace_id,source_id,chunk_index,content,modality,chunk_metadata,extraction_method,embedding,semantic_search_status,lexical_search_status,created_at,updated_at) SELECT gen_random_uuid(),:wid,:sid,n,CASE WHEN n%1000=0 THEN 'phase7rareterm cactus' ELSE 'AUTHORED planner fixture commonplace text' END,'text','{}','AUTHORED_FIXTURE',CAST(:vec AS vector),'READY','READY',now(),now() FROM generate_series(1,6000) n"),{'wid':wid,'sid':source.id,'vec':vec})
        await db.execute(text('ANALYZE document_chunks'))
        queries={
            'fts':("SELECT id FROM document_chunks WHERE workspace_id=:wid AND search_vector @@ websearch_to_tsquery('english','phase7rareterm') ORDER BY ts_rank_cd(search_vector,websearch_to_tsquery('english','phase7rareterm')) DESC LIMIT 5",{'wid':wid}),
            'production_semantic_shape':("SELECT id,row_number() OVER (ORDER BY embedding <=> CAST(:v AS vector),id) FROM document_chunks WHERE workspace_id=:wid AND embedding IS NOT NULL AND semantic_search_status='READY' ORDER BY embedding <=> CAST(:v AS vector),id LIMIT 50",{'wid':wid,'v':vec}),
            'hnsw_eligible_control':("SELECT id FROM document_chunks WHERE embedding IS NOT NULL ORDER BY embedding <=> CAST(:v AS vector) LIMIT 50",{'v':vec}),
        }
        plans={}
        for name,(query,params) in queries.items():plans[name]=(await db.execute(text('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+query),params)).scalar_one()
        result['planner']={'rows':6000,'synthetic_vectors':True,'quality_metrics':'NOT_MEASURED','plans':plans}
        await db.rollback()
    await engine.dispose();(OUT/'database-probes.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='planner'},indent=2));print('Planner evidence saved, 6000 labeled synthetic rows rolled back.')
if __name__=='__main__':asyncio.run(main())
