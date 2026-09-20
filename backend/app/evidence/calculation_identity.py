"""Canonical identities for persisted deterministic calculations."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def calculation_reproducibility_hash(
    formula_or_code: str,
    input_values: Any,
    computed_output: Any,
) -> str:
    """Hash the complete logical calculation using stable JSON serialization."""
    canonical = json.dumps(
        {
            "formula_or_code": formula_or_code.strip(),
            "input_values": input_values,
            "computed_output": computed_output,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
