"""Audit writer (ARCH §18, ARCH-035; PRD-085).

- one `audit.audit_event` per: query, retrieval (chunks + scores), record
  access (field list), answer (model id, response hash, grounding summary,
  outcome), HITL action, ingest, config change, login;
- INSERT only (the DB role has no UPDATE/DELETE on the audit schema);
- `prev_hash`/`row_hash` chain for tamper evidence;
- query/response text encrypted (CryptoProvider); `query_hash`/`response_hash`
  in plaintext for correlation without decryption.

Phase 4 implements the writer + the chain-verifier job. `canonical_row` and
`row_hash` are defined now so tests can assert chain behaviour.
"""

from __future__ import annotations

import hashlib
import json

GENESIS_HASH = "0" * 64


def canonical_row(fields: dict) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)


def row_hash(fields: dict, prev_hash: str) -> str:
    return hashlib.sha256((prev_hash + canonical_row(fields)).encode("utf-8")).hexdigest()


def write_event(**_fields: object) -> None:
    raise NotImplementedError("Phase 4 (ARCH §18)")


def verify_chain() -> list[int]:
    """Return the ids of rows where the chain is broken (empty => intact). Phase 4."""
    raise NotImplementedError("Phase 4 (ARCH §18)")
