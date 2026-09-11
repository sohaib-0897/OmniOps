"""Characterize disputed invariants using real ORM and implementation functions.

Outputs describe findings, not passing certification tests. Test DB only.
"""
import asyncio, json, logging, io, sys, uuid
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from phase7_ops import pg_env, OUT
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.models.user import User, Workspace
from app.models.document import SourceDocument, DocumentChunk
from app.models.investigation import InvestigationSession
from app.models.evidence import EvidenceItem, CalculationRecord
from app.evidence.validator import validate_claim_proposal, validate_supporting_claims
from app.llm.client import OmniOpsLLMClient
from app.llm.base import ProviderError
async def main():
    env=pg_env('omniops_phase7_runtime_test'); engine=create_async_engine(env['DATABASE_URL']); factory=async_sessionmaker(engine,expire_on_commit=False)
    result={}
    async with factory() as db:
        user=(await db.execute(select(User).limit(1))).scalar_one(); ws=(await db.execute(select(Workspace).where(Workspace.created_by==user.id).limit(1))).scalar_one()
        inv=InvestigationSession(workspace_id=ws.id,user_id=user.id,objective='Phase7 lineage attack',status='failed',current_state='failed');db.add(inv);await db.flush()
        sources=[]
        for name in ('a','b'):
            source=SourceDocument(workspace_id=ws.id,file_name='phase7-'+name+'.txt',storage_path='/audit-fixture/'+name,mime_type='text/plain',byte_size=10,sha256_hash=uuid.uuid4().hex*2,modality='text',processing_status='ready');db.add(source);sources.append(source)
        await db.flush()
        chunk=DocumentChunk(workspace_id=ws.id,source_id=sources[0].id,chunk_index=0,content='Revenue is 10.',modality='text',extraction_method='AUTHORED_AUDIT_FIXTURE');db.add(chunk);await db.flush()
        ev=EvidenceItem(session_id=inv.id,source_id=sources[1].id,chunk_id=chunk.id,exact_quote=chunk.content);db.add(ev);await db.flush()
        calc=CalculationRecord(session_id=inv.id,calculation_type='aggregation',formula_or_code='10 + 1',computed_output=999,reproducibility_hash='not-a-valid-hash',input_values={'revenue':10},evidence_ids=[str(ev.id)],source_ids=[]);db.add(calc);await db.flush()
        direct=await validate_claim_proposal(db,inv.id,[str(ev.id)],[])
        nested=await validate_claim_proposal(db,inv.id,[],[str(calc.id)])
        result['broken_source_chain']={'direct_evidence_accepted':direct.valid,'calculation_wrapped_accepted':nested.valid,'direct_errors':direct.errors,'nested_errors':nested.errors}
        result['unrecomputed_calculation']={'formula':'10 + 1','stored_output':999,'invalid_hash_accepted':nested.valid}
        empty=await validate_supporting_claims(db,inv.id,[]); result['empty_inference_support_accepted']=empty.valid
        for name,ids,cids in [('no_support',[],[]),('missing_evidence',[str(uuid.uuid4())],[]),('missing_calculation',[],[str(uuid.uuid4())])]:
            check=await validate_claim_proposal(db,inv.id,ids,cids); result[name]={'valid':check.valid,'errors':check.errors}
        await db.rollback()
    # Controlled provider failure containing an audit sentinel, not a real key.
    stream=io.StringIO(); handler=logging.StreamHandler(stream); logger=logging.getLogger('app.llm.client');logger.addHandler(handler)
    client=OmniOpsLLMClient()
    async def fail(): raise RuntimeError('PHASE7_SECRET_SENTINEL provider payload')
    try:
        try: await client._invoke('audit',fail)
        except ProviderError: pass
        result['raw_provider_exception_logged']='PHASE7_SECRET_SENTINEL' in stream.getvalue()
    finally: logger.removeHandler(handler)
    (OUT/'boundary-probes.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));await engine.dispose()
if __name__=='__main__':asyncio.run(main())
