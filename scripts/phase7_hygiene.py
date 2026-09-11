"""Safe working-tree/history credential scan and clean-HEAD release gate."""
import json,re,subprocess,zipfile,io,hashlib,shutil
from pathlib import Path
from phase7_ops import ROOT,OUT,command
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
patterns={
 'private_key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'google_key':re.compile(rb'AIza[0-9A-Za-z_-]{35}'),
 'openai_key':re.compile(rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}'),
 'github_token':re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
 'aws_access_id':re.compile(rb'AKIA[0-9A-Z]{16}'),
}
findings=[];files=git('ls-files','--cached','--others','--exclude-standard','-z').decode().split('\0');large=[];scanned=0
for name in files:
 if not name:continue
 path=ROOT/name
 if not path.is_file():continue
 size=path.stat().st_size
 if size>10*1024*1024:large.append({'path':name,'bytes':size})
 if size>30*1024*1024:continue
 data=path.read_bytes();scanned+=1
 for label,pattern in patterns.items():
  if pattern.search(data):findings.append({'scope':'working_tree','path':name,'pattern':label})
history=0;seen=set()
for entry in git('rev-list','--objects','--all').decode().splitlines():
 sha,_,name=entry.partition(' ')
 if sha in seen:continue
 seen.add(sha)
 if git('cat-file','-t',sha).strip()!=b'blob':continue
 if int(git('cat-file','-s',sha))>30*1024*1024:continue
 history+=1;data=git('cat-file','blob',sha)
 for label,pattern in patterns.items():
  if pattern.search(data):findings.append({'scope':'history','object':sha,'path':name,'pattern':label})
snapshot=ROOT/'.ui-qa/phase7-clean-head';snapshot.mkdir(parents=True,exist_ok=True)
archive=git('archive','--format=zip','HEAD')
with zipfile.ZipFile(io.BytesIO(archive)) as z:
 for member in z.infolist():
  target=(snapshot/member.filename).resolve();assert target.is_relative_to(snapshot.resolve())
 z.extractall(snapshot)
p,output=command(['docker','compose','-f','docker-compose.prod.yml','config','--quiet'],cwd=snapshot,label='clean-head-compose')
required=['docker-compose.prod.yml','backend/app/core/observability.py','backend/app/worker.py','backend/alembic/versions/20260911_phase6_sessions.py','.github/workflows/ci.yml']
result={'working_tree_files_scanned':scanned,'history_blobs_scanned':history,'history_commits':int(git('rev-list','--count','HEAD')),'scanner':{'gitleaks':bool(shutil.which('gitleaks')),'trufflehog':bool(shutil.which('trufflehog')),'method':'targeted credential signatures; not exhaustive entropy scan'},'findings':findings,'large_nonignored_files':large,'clean_head':{'sha':git('rev-parse','HEAD').decode().strip(),'missing_required_files':[n for n in required if not(snapshot/n).exists()],'production_compose_exit':p.returncode,'dependent_clean_launch':'NOT_RUN: required release topology/modules absent'},'audit_sha256':hashlib.sha256((ROOT/'audit.md').read_bytes()).hexdigest(),'remote_count':len(git('remote').decode().splitlines()),'GitHub_hosted_CI':'NOT_RUN'}
(OUT/'hygiene.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
