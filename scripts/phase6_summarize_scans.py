"""Summarize actual Docker Scout SARIF rules, retaining package-specific findings."""
import collections
import json
from pathlib import Path


report = json.loads(Path("phase6-container-evidence.json").read_text())
findings = {}
for entry in report["scans"]:
    if "artifact" not in entry:
        continue
    run = json.loads(Path(entry["artifact"]).read_text(encoding="utf-8"))["runs"][0]
    rules = run["tool"]["driver"]["rules"]
    counts = collections.Counter(rule["properties"].get("cvssV3_severity", "UNKNOWN") for rule in rules)
    entry["severity_counts"] = {key.lower(): counts[key] for key in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")}
    print(entry["image"], entry["severity_counts"])
    for rule in rules:
        props = rule["properties"]
        if props.get("cvssV3_severity") not in ("CRITICAL", "HIGH"):
            continue
        key = rule["id"] + "|" + ",".join(props["purls"])
        finding = findings.setdefault(key, {"id": rule["id"], "severity": props["cvssV3_severity"], "packages": props["purls"], "fixed": props["fixed_version"], "description": rule["help"]["text"], "url": rule.get("helpUri"), "images": []})
        finding["images"].append(entry["image"])
report["critical_high_findings"] = list(findings.values())
assessments = {
    "CVE-2026-57585": "Accepted residual: pip-vendored Unpacker is not invoked by application request paths; update pip's vendor bundle when available.",
    "GHSA-6v7p-g79w-8964": "Alias of CVE-2026-57585; retained in raw counts, not a second underlying bug.",
    "CVE-2025-47273": "Accepted non-reachable vendor attribution: pip has pkg_resources but no vendored setuptools/PackageIndex downloader.",
    "CVE-2026-86140": "Accepted potential native-parser residual: no application DTD validation found; no compatible Debian trixie fix, no unstable-library substitution.",
    "CVE-2026-85091": "Accepted residual: vulnerable nonblocking gzwrite/gzprintf pattern not found in application; no Debian fix reported.",
}
for finding in report["critical_high_findings"]:
    finding["assessment"] = assessments.get(finding["id"], "REVIEW_REQUIRED")
for entry in report["scans"]:
    relevant = [finding for finding in report["critical_high_findings"] if entry["image"] in finding["images"]]
    entry["status"] = "REVIEW_REQUIRED" if any(finding["assessment"] == "REVIEW_REQUIRED" for finding in relevant) else "REVIEWED_WITH_RESIDUALS" if relevant else "REVIEWED_NO_CRITICAL_HIGH"
report["assessment_document"] = "PHASE_6_REMEDIATION.md: Every original critical/high finding: decision"
Path("phase6-container-evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
for finding in findings.values():
    print(json.dumps(finding))
