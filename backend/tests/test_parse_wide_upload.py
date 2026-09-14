"""parse_wide_upload: wide-file record ingestion (ARCH §5.2; DEVIATIONS #64)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.ingestion.records import parse_wide_upload
from app.schemas.record import SYNTHETIC_PROVENANCE


def test_json_bare_list_parses() -> None:
    payload = json.dumps(
        [{"record_id": "1", "mrn": "MRN-1", "dataset_provenance": SYNTHETIC_PROVENANCE}]
    ).encode()
    records = parse_wide_upload(payload, "patients.json")
    assert len(records) == 1
    assert records[0].mrn == "MRN-1"


def test_json_envelope_with_records_key_parses() -> None:
    payload = json.dumps(
        {
            "schema_version": "1.3.0",
            "dataset_provenance": SYNTHETIC_PROVENANCE,
            "records": [{"record_id": "1", "mrn": "MRN-1"}],
        }
    ).encode()
    records = parse_wide_upload(payload, "patients.json")
    assert len(records) == 1


def test_json_non_list_payload_rejected() -> None:
    with pytest.raises(ValueError, match="list"):
        parse_wide_upload(json.dumps({"not": "a list"}).encode(), "patients.json")


def test_json_invalid_record_raises_pydantic_validation_error() -> None:
    payload = json.dumps([{"mrn": "MRN-1"}]).encode()  # missing required record_id
    with pytest.raises(ValidationError):
        parse_wide_upload(payload, "patients.json")


def test_csv_scalar_and_nested_encounter_fields_parse() -> None:
    csv_text = "record_id,mrn,encounter.ward,encounter.presenting_complaint\n1,MRN-1,NBU,grunting\n"
    records = parse_wide_upload(csv_text.encode(), "patients.csv")
    assert len(records) == 1
    assert records[0].encounter.ward == "NBU"
    assert records[0].encounter.presenting_complaint == "grunting"


def test_csv_empty_cell_means_field_absent_not_empty_string() -> None:
    csv_text = "record_id,mrn,encounter.ward\n1,MRN-1,\n"
    records = parse_wide_upload(csv_text.encode(), "patients.csv")
    assert records[0].encounter.ward is None


def test_csv_list_field_column_is_rejected() -> None:
    csv_text = "record_id,mrn,medications\n1,MRN-1,amoxicillin\n"
    with pytest.raises(ValueError, match="list field"):
        parse_wide_upload(csv_text.encode(), "patients.csv")


def test_csv_nested_list_field_column_is_rejected() -> None:
    csv_text = "record_id,mrn,labs.analyte\n1,MRN-1,potassium\n"
    with pytest.raises(ValueError, match="list field"):
        parse_wide_upload(csv_text.encode(), "patients.csv")


def test_unsupported_extension_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported file type"):
        parse_wide_upload(b"whatever", "patients.txt")
