"""Summarize fresh evidence without reading environment credentials."""
import json, collections, xml.etree.ElementTree as ET
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'phase7-evidence'
result={}
for file in OUT.glob('scout-*.txt'):
    obj,_=json.JSONDecoder().raw_decode(file.read_text(encoding='utf-8').lstrip())
    counts=collections.Counter(); high=[]
    for run in obj['runs']:
        rules={r['id']:r for r in run['tool']['driver']['rules']}
        for row in run.get('results',[]):
            rule=rules[row['ruleId']]; props=rule.get('properties',{})
            severity=str(props.get('severity',props.get('cvssV3_severity','unknown'))).lower()
            if severity=='unknown':
                score=float(props.get('security-severity',0)); severity='critical' if score>=9 else 'high' if score>=7 else 'medium' if score>=4 else 'low'
            counts[severity]+=1
            if severity in ('critical','high'): high.append({'id':row['ruleId'],'severity':severity,'description':rule.get('shortDescription',{}),'help':rule.get('helpUri'),'properties':props,'message':row.get('message',{})})
    result[file.stem]={'counts':dict(counts),'high_critical':high}
suite=ET.parse(OUT/'final-backend-junit.xml'); modules={}
for case in suite.iter('testcase'):
    group=case.get('classname'); stats=modules.setdefault(group,collections.Counter()); stats['total']+=1
    state='failed' if case.find('failure') is not None or case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed'; stats[state]+=1
result['regression_modules']=modules
(OUT/'results-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
