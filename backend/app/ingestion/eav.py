"""EAV / long-format record ingestion (ARCH-039; ARCH §5.2; DEVIATIONS #34).

Some patient datasets arrive in entity-attribute-value / long form
(`key, field_name, field_value, context`) with variable names that do not match
`app/schemas/record.py`. This module:

  1. pivots long → wide, keyed on `key` (one row per patient);
  2. applies a **declarative mapping spec** (`field_mapping.yaml`) that says, per
     source field, which `record.py` path it maps to and which transform to run;
  3. yields validated `PatientRecord` objects.

The same mapping spec is the contract for file ingestion now and a future
pull-API (`app/ingestion/sources/rest_api.py`) that returns the same variables.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.schemas.record import SCHEMA_VERSION, PatientRecord

# ── transforms ──────────────────────────────────────────────────────────────
_TRUE = {"true", "1", "yes", "y", "t"}
_FALSE = {"false", "0", "no", "n", "f"}
_NULL_LITERALS = {"", "none", "null", "na", "n/a", "nan"}


def _identity(v: str) -> Any:
    return v


def _to_int(v: str) -> int | None:
    v = v.strip()
    return None if v.lower() in _NULL_LITERALS else int(float(v))


def _to_float(v: str) -> float | None:
    v = v.strip()
    return None if v.lower() in _NULL_LITERALS else float(v)


def _kg_to_g(v: str) -> float | None:
    f = _to_float(v)
    return None if f is None else round(f * 1000.0, 1)


def _sex_norm(v: str) -> str | None:
    s = v.strip().lower()
    if s in _NULL_LITERALS:
        return None
    return {"m": "male", "male": "male", "f": "female", "female": "female"}.get(s, s)


def _bool_truthy(v: str) -> bool | None:
    s = v.strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    if s in _NULL_LITERALS:
        return None
    raise ValueError(f"not a boolean: {v!r}")


def _parse_datetime(v: str) -> datetime | None:
    s = v.strip()
    if s.lower() in _NULL_LITERALS:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.fromisoformat(s)


def _none_literal_to_null(v: str) -> str | None:
    return None if v.strip().lower() in _NULL_LITERALS else v.strip()


TRANSFORMS = {
    "identity": _identity,
    "to_int": _to_int,
    "to_float": _to_float,
    "kg_to_g": _kg_to_g,
    "sex_norm": _sex_norm,
    "bool_truthy": _bool_truthy,
    "parse_datetime": _parse_datetime,
    "none_literal_to_null": _none_literal_to_null,
}


# ── mapping spec ────────────────────────────────────────────────────────────
@dataclass
class MappingSpec:
    dataset_id: str
    provenance: str
    schema_version: str
    identity: dict[str, str]  # {record_id: "{key}", mrn: "DEID-{key}"}
    fields: dict[str, dict[str, str]]  # src -> {target, transform}
    list_targets: dict[str, dict[str, Any]]
    defaults: dict[str, Any] = field(default_factory=dict)
    vitals_recorded_at_from: str | None = None
    derived: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MappingSpec":
        import yaml

        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            dataset_id=raw["dataset_id"],
            provenance=raw["provenance"],
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            identity=raw["identity"],
            fields=raw.get("fields", {}),
            list_targets=raw.get("list_targets", {}),
            defaults=raw.get("defaults", {}),
            vitals_recorded_at_from=raw.get("vitals_recorded_at_from"),
            derived=raw.get("derived", {}),
        )


# ── pivot ──────────────────────────────────────────────────────────────────
def load_wide(csv_path: str | Path) -> Iterator[tuple[str, dict[str, str]]]:
    """Yield (key, {field_name: field_value}) — one wide row per patient key.

    Assumes (key, field_name) is unique (verified for the newborn dataset).
    """
    current_key: str | None = None
    row: dict[str, str] = {}
    with Path(csv_path).open(newline="", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            k = rec["key"]
            if current_key is not None and k != current_key:
                yield current_key, row
                row = {}
            current_key = k
            row[rec["field_name"]] = rec["field_value"]
    if current_key is not None:
        yield current_key, row


# ── apply ──────────────────────────────────────────────────────────────────
def _set_path(target: dict[str, Any], dotted: str, value: Any) -> None:
    """Set `value` at a dotted path. Supports `vitals.0.key` list indexing."""
    parts = dotted.split(".")
    cur: Any = target
    for i, part in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if nxt.isdigit():  # current part is a list
            lst = cur.setdefault(part, [])
            idx = int(nxt)
            while len(lst) <= idx:
                lst.append({})
            cur = lst[idx]
            # skip the numeric part on next iteration
        elif part.isdigit():
            continue
        else:
            cur = cur.setdefault(part, {})
    last = parts[-1]
    if not last.isdigit():
        cur[last] = value


def apply_mapping(key: str, wide: dict[str, str], spec: MappingSpec) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": spec.schema_version,
        "dataset_provenance": spec.provenance,
        "record_id": spec.identity["record_id"].format(key=key),
        "mrn": spec.identity["mrn"].format(key=key),
    }

    # single-value fields
    for src, rule in spec.fields.items():
        if src not in wide:
            continue
        fn = TRANSFORMS[rule.get("transform", "identity")]
        try:
            val = fn(wide[src])
        except (ValueError, TypeError):
            continue  # malformed source value -> treat as missing
        if val is not None:
            _set_path(out, rule["target"], val)

    # vitals timestamps
    if spec.vitals_recorded_at_from and spec.vitals_recorded_at_from in wide:
        ts = _parse_datetime(wide[spec.vitals_recorded_at_from])
        for v in out.get("vitals", []):
            v.setdefault("recorded_at", ts.isoformat() if ts else None)

    # drop a vitals[0] that ended up with only a timestamp
    out["vitals"] = [
        v for v in out.get("vitals", [])
        if any(k != "recorded_at" and val is not None for k, val in v.items())
    ]

    # repeated-field families -> list[...]
    for grp in spec.list_targets.values():
        items: list[dict[str, Any]] = []
        ts_src = grp.get("recorded_at_from") or grp.get("started_at_from")
        ts = _parse_datetime(wide[ts_src]) if ts_src and ts_src in wide else None
        for member in grp["members"]:
            if member not in wide:
                continue
            try:
                flag = _bool_truthy(wide[member])
            except ValueError:
                continue
            if flag is None:
                continue
            item: dict[str, Any] = {"name": member}
            if "present_key" in grp:
                item[grp["present_key"]] = flag
            if "active_key" in grp:
                item[grp["active_key"]] = flag
            if ts is not None and "ts_key" in grp:
                item[grp["ts_key"]] = ts.isoformat()
            items.append(item)
        if items:
            out[grp["target"]] = items

    # derived
    for name, rule in spec.derived.items():
        if rule.get("rule") == "admitted_minus_days":
            adm = out.get("encounter", {}).get("admitted_at")
            dol = out.get("encounter", {}).get("day_of_life")
            if adm and dol is not None:
                d = _parse_datetime(adm) if isinstance(adm, str) else adm
                out[name] = (d - timedelta(days=int(dol))).date().isoformat()

    # defaults (only where unset)
    for path, value in spec.defaults.items():
        if "." in path:
            _set_path(out, path, value)
        else:
            out.setdefault(path, value)

    return out


def build_records(
    csv_path: str | Path, spec: MappingSpec, *, limit: int | None = None
) -> Iterator[PatientRecord]:
    for i, (key, wide) in enumerate(load_wide(csv_path)):
        if limit is not None and i >= limit:
            break
        yield PatientRecord(**apply_mapping(key, wide, spec))
