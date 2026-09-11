"""Read-only Phase 7 inventory; never emit credential values."""
from pathlib import Path
import hashlib, json, re, subprocess, datetime

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'phase7-evidence'
OUT.mkdir(exist_ok=True)
def run(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
def main():
    status = run('git', 'status', '--porcelain=v1').stdout
    tracked = run('git', 'ls-files').stdout.splitlines()
    findings = []
    # Only locations and detector names are reported, never matched text.
    patterns = {'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', 'google_key': r'AIza[0-9A-Za-z_-]{30,}', 'openai_key': r'sk-(?:proj-)?[A-Za-z0-9_-]{32,}', 'github_token': r'gh[pousr]_[A-Za-z0-9]{30,}'}
    for name in tracked:
        path = ROOT / name
        if not path.is_file() or path.stat().st_size > 5_000_000: continue
        content = path.read_text(encoding='utf-8', errors='replace')
        for detector, pattern in patterns.items():
            for match in re.finditer(pattern, content):
                findings.append({'file': name, 'line': content.count('\n', 0, match.start())+1, 'detector': detector})
    production = [* (ROOT/'backend/app').rglob('*.py'), *(ROOT/'frontend/src').rglob('*.ts'), *(ROOT/'frontend/src').rglob('*.tsx')]
    suspicious = re.compile(r'fake|mock|stub|placeholder|hardcoded|fallback|demo|sample|synthetic|TODO|FIXME|NOT_IMPLEMENTED|NOT_SUPPORTED|sleep\(|random|98\.|99\.|0\.25|zero.hallucination|production.ready|BM25|pgvector|semantic|verified|confidence', re.I)
    matches = [{'file': str(p.relative_to(ROOT)), 'line': i, 'text': line.strip()} for p in production for i,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1) if suspicious.search(line)]
    (OUT/'production-claim-scan.json').write_text(json.dumps(matches,indent=2),encoding='utf-8')
    report = {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'head':run('git','rev-parse','HEAD').stdout.strip(), 'status':status.splitlines(), 'tracked_files':len(tracked), 'audit_sha256':hashlib.sha256((ROOT/'audit.md').read_bytes()).hexdigest(), 'tracked_env_files':[p for p in tracked if Path(p).name=='.env'], 'secret_pattern_findings':findings, 'production_scan_matches':len(matches), 'untracked_required_files':[p for p in ['docker-compose.prod.yml','.github/workflows/ci.yml','backend/app/core/rate_limit.py','backend/alembic/versions/20260911_phase6_sessions.py'] if p not in tracked]}
    (OUT/'inventory.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='status'},indent=2))
if __name__=='__main__': main()
