"""Check final audit accounting against saved execution evidence."""
import collections
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
report = (root / 'PHASE_7_FINAL_AUDIT.md').read_text(encoding='utf-8')
original = (root / 'audit.md').read_text(encoding='utf-8')
original_ids = set(re.findall(r'\*\*((?:SEC|ARC|DAT|FE|OPS)-\d{2})\*\*', original))
rows = re.findall(r'^\| ((?:SEC|ARC|DAT|FE|OPS)-\d{2})[^|]*\| ([A-Z_]+) \|', report, re.M)
assert len(rows) == 30 and {row[0] for row in rows} == original_ids
statuses = dict(collections.Counter(row[1] for row in rows))
assert statuses == {'CLOSED': 24, 'PARTIALLY_CLOSED': 3, 'STILL_OPEN': 2, 'OBSOLETE': 1}
findings = re.findall(r'^\| (P7-\d{2})[^|]*\| (HIGH|MEDIUM|LOW) \|', report, re.M)
assert len(findings) == 19 and len({row[0] for row in findings}) == 19
severities = dict(collections.Counter(row[1] for row in findings))
assert severities == {'HIGH': 7, 'MEDIUM': 11, 'LOW': 1}
headings = '''Executive Verdict|Architecture Verified|Original Audit Reconciliation|Release Blockers|Security Assessment|Authentication Assessment|Tenant Isolation|Agent Runtime|Evidence Integrity|Retrieval|Multimodal|Sandbox|SSRF / Web Security|Persistence / Durability|SSE / Multi-Worker|Database / Migrations|Frontend|Dependency / Container Security|CI/CD|Observability|Failure Testing|Performance Sanity|Repository Hygiene|Documentation Accuracy|Residual Risks|CV-Safe Claims|Final Scorecard|Final Classification'''.split('|')
assert all('## ' + heading + '\n' in report for heading in headings)
digest = hashlib.sha256((root / 'audit.md').read_bytes()).hexdigest()
assert digest == 'f52705af7e850c00103a39d29d11c28d91803916fdb22d2cfdf946f23793940c'
counts = collections.Counter()
for case in ET.parse(root / 'phase7-evidence/final-backend-junit.xml').iter('testcase'):
    counts['failed' if case.find('failure') is not None or case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed'] += 1
assert counts == {'passed': 176, 'failed': 2}
references = set(re.findall(r'E/([A-Za-z0-9_./-]+\.(?:json|txt|xml))', report))
withheld = {'provider-chain.json', 'provider-smoke.json', 'extended-browser-context.json'}
missing = {path for path in references if not (root / 'phase7-evidence' / path).is_file()}
assert missing <= withheld, f'Unexpected missing evidence: {sorted(missing - withheld)}'
result = {'report_sections': len(headings), 'original_findings': statuses,
          'application_findings': severities, 'final_backend': dict(counts),
          'explicit_evidence_references_checked': len(references),
          'withheld_publication_artifacts': sorted(missing), 'audit_sha256': digest,
          'classification': 'NOT_RELEASE_READY', 'consistency_check': 'PASS'}
(root / 'phase7-evidence/report-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
