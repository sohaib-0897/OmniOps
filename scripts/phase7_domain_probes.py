"""Concurrent production persistence helpers and deletion/finalization boundaries."""
import asyncio,json,sys,uuid
from datetime import datetime,timezone,timedelta
from sqlalchemy import select,delete,update
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from phase7_ops import ROOT,OUT,pg_env
sys.path.insert(0,str(ROOT/'backend'))
from app.models.user import User,Workspace
from app.models.document import SourceDocument,DocumentChunk
from app.models.investigation import InvestigationSession
from app.models.evidence import EvidenceItem,VerifiedClaim
from app.agent.persistence import persist_evidence,persist_calculation,persist_claim,finalize_synthesis
from app.agent.runtime import persist_runtime_event,acquire_lease
from app.evidence.validator import validate_claim_proposal
async def main():
    engine=create_async_engine(pg_env('omniops_phase7_runtime_test')['DATABASE_URL']);factory=async_sessionmaker(engine,expire_on_commit=False);results={}
    async with factory() as db:
        user=(await db.execute(select(User).limit(1))).scalar_one();ws=(await db.execute(select(Workspace).where(Workspace.created_by==user.id).limit(1))).scalar_one()
        inv=InvestigationSession(workspace_id=ws.id,user_id=user.id,objective='AUTHORED concurrent domain test',status='failed',current_state='failed');db.add(inv)
        source=SourceDocument(workspace_id=ws.id,file_name='AUTHORED DOMAIN FIXTURE',storage_path='/audit/no-file',mime_type='text/plain',byte_size=0,sha256_hash=uuid.uuid4().hex*2,modality='text',processing_status='ready');db.add(source);await db.flush()
        chunk=DocumentChunk(workspace_id=ws.id,source_id=source.id,chunk_index=0,content='Audit revenue was 10.',modality='text',extraction_method='AUTHORED_AUDIT');db.add(chunk);await db.commit();iid,wid,sid,cid=inv.id,ws.id,source.id,chunk.id
    async def race(kind):
        async def writer():
            async with factory() as db:
                try:
                    if kind=='evidence':row=await persist_evidence(db,session_id=iid,workspace_id=wid,source_id=sid,chunk_id=cid,locator={'audit':1},exact_quote='Audit revenue was 10.')
                    elif kind=='calculation':row=await persist_calculation(db,session_id=iid,step_id='audit',formula='10+1',inputs={'value':10},calculation_type='aggregation',computed_output=11,reproducibility_hash='AUTHORED_IDEMPOTENCY_FIXTURE',evidence_ids=[],source_ids=[str(sid)])
                    elif kind=='claim':row=await persist_claim(db,session_id=iid,step_id='audit',statement='Audit revenue was 10.',lineage={'evidence':[evidence_id]},epistemic_type='fact',verification_status='VERIFIED',supporting_citations=[evidence_id])
                    else:row=await persist_runtime_event(db,iid,'phase7.idempotent','phase7-'+str(iid),{'audit':True})
                    await db.commit();return {'id':str(row.id)}
                except Exception as exc:await db.rollback();return {'error':type(exc).__name__}
        rows=await asyncio.gather(*(writer() for _ in range(5)));results[kind]={'writers':5,'errors':[r['error'] for r in rows if 'error' in r],'unique_ids':len(set(r['id'] for r in rows if 'id' in r))};return next((r['id'] for r in rows if 'id' in r),None)
    evidence_id=await race('evidence');await race('calculation');claim_id=await race('claim');await race('event')
    async with factory() as db:
        before=await validate_claim_proposal(db,iid,[evidence_id],[])
        await db.execute(delete(SourceDocument).where(SourceDocument.id==sid));await db.commit()
        claim=await db.get(VerifiedClaim,uuid.UUID(claim_id));after=await validate_claim_proposal(db,iid,[evidence_id],[])
        results['source_deletion']={'valid_before':before.valid,'valid_after':after.valid,'persisted_claim_status':claim.verification_status,'dangling_citations':claim.supporting_citations}
    async with factory() as a,factory() as b:
        old=await a.get(InvestigationSession,iid);await acquire_lease(a,old,'stale-finalizer',30);await a.commit()
        await b.execute(update(InvestigationSession).where(InvestigationSession.id==iid).values(lease_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)));await b.commit()
        new=await b.get(InvestigationSession,iid);await acquire_lease(b,new,'new-finalizer',30);await finalize_synthesis(b,new,{'audit_winner':'new'},1);await b.commit()
        await finalize_synthesis(a,old,{'audit_winner':'stale'},1);await a.commit()
        async with factory() as db:
            row=await db.get(InvestigationSession,iid);results['stale_finalization']={'authoritative_owner':row.worker_id,'stored_winner':row.final_response.get('audit_winner')}
    await engine.dispose();(OUT/'domain-probes.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
if __name__=='__main__':asyncio.run(main())
