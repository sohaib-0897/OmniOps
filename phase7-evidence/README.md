# Phase 7 evidence

The [final audit](../PHASE_7_FINAL_AUDIT.md) records the result and qualifications. Included JSON, text and JUnit files are historical command/probe evidence, not a current green-build claim. Authored fixtures and synthetic vector measurements are not real customer results or semantic quality metrics.

For publication, database dumps, raw provider-chain/smoke payload files, temporary browser context and generated media are kept local. Their source scripts and the audit's scoped outcome summaries are included. References to those withheld local artifacts in the audit are intentional; file availability must not be mistaken for independent live verification.

Phase 7 scripts target the specifically named laboratory topology used for this audit. They are not general production diagnostics. Some perform controlled worker kills, temporary DB triggers and temporary database creation. Review scripts and use disposable resources before reproducing them.

Key included records: `final-backend-junit.xml`, `final-backend-full.txt`, `domain-probes.json`, `database-probes.json`, `last-ops.json`, `results-summary.json` and `report-verification.json`.
