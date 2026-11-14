"""Tests for synthetic packet and ground-truth label generator."""

import json
from pathlib import Path
from intake.generate import generate_dataset
from intake.schemas import Packet, PacketLabel


def test_generator_reproducibility(tmp_path: Path):
    """Verify that the same seed produces byte-identical output across two separate runs."""
    dir_run1 = tmp_path / "run1"
    dir_run2 = tmp_path / "run2"

    generate_dataset(total_packets=40, seed=7, out_dir=str(dir_run1))
    generate_dataset(total_packets=40, seed=7, out_dir=str(dir_run2))

    # 1. Compare labels.jsonl
    labels1_bytes = (dir_run1 / "labels.jsonl").read_bytes()
    labels2_bytes = (dir_run2 / "labels.jsonl").read_bytes()
    assert labels1_bytes == labels2_bytes, "labels.jsonl is not byte-identical between runs with the same seed"

    # 2. Compare every packet file
    packets1 = sorted((dir_run1 / "packets").glob("*.json"))
    packets2 = sorted((dir_run2 / "packets").glob("*.json"))
    assert len(packets1) == 40
    assert len(packets2) == 40

    for p1, p2 in zip(packets1, packets2):
        assert p1.name == p2.name
        assert p1.read_bytes() == p2.read_bytes(), f"Packet {p1.name} differs between runs with same seed"


def test_packet_files_contain_no_label_fields(tmp_path: Path):
    """Verify that packet files contain zero ground truth / label keys (no label leakage)."""
    out_dir = tmp_path / "data"
    generate_dataset(total_packets=40, seed=7, out_dir=str(out_dir))

    forbidden_keys = {
        "doc_type",
        "expected_decision",
        "expected_requests",
        "period_start",
        "period_end",
        "pay_month",
        "issue_date",
        "expiry_date",
        "assessment_year",
    }

    packet_files = list((out_dir / "packets").glob("*.json"))
    assert len(packet_files) == 40

    for pf in packet_files:
        with open(pf, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate packet schema
        packet_obj = Packet.model_validate(data)
        assert packet_obj.packet_id == pf.stem

        # Check top-level keys
        assert set(data.keys()) == {"packet_id", "as_of", "application_form", "documents"}

        # Check document keys
        for doc in data["documents"]:
            assert set(doc.keys()) == {"doc_id", "filename", "text"}
            for fk in forbidden_keys:
                assert fk not in doc, f"Found leaked key '{fk}' in {pf.name} document {doc.get('doc_id')}"


def test_dataset_distribution_and_quotas(tmp_path: Path):
    """Verify that dataset meets all quotas: >=40% request docs (all 4 codes), >=15% review."""
    out_dir = tmp_path / "data"
    generate_dataset(total_packets=40, seed=7, out_dir=str(out_dir))

    labels_file = out_dir / "labels.jsonl"
    labels = []
    with open(labels_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                label_dict = json.loads(line)
                label_obj = PacketLabel.model_validate(label_dict)
                labels.append(label_obj)

    assert len(labels) == 40

    decisions = [l.expected_decision for l in labels]
    request_count = decisions.count("REQUEST_DOCUMENTS")
    review_count = decisions.count("HUMAN_REVIEW")
    complete_count = decisions.count("COMPLETE")

    # 1. At least 40% (16+) need documents
    assert request_count >= 16, f"Expected >= 16 REQUEST_DOCUMENTS, got {request_count}"

    # 2. At least 15% (6+) need human review
    assert review_count >= 6, f"Expected >= 6 HUMAN_REVIEW, got {review_count}"

    # 3. For HUMAN_REVIEW, expected_requests must be empty
    for l in labels:
        if l.expected_decision == "HUMAN_REVIEW":
            assert len(l.expected_requests) == 0, f"Packet {l.packet_id} has HUMAN_REVIEW but non-empty expected_requests"

    # 4. Check all 4 reason codes appear in REQUEST_DOCUMENTS
    all_reason_codes = set()
    for l in labels:
        if l.expected_decision == "REQUEST_DOCUMENTS":
            assert len(l.expected_requests) > 0, f"Packet {l.packet_id} is REQUEST_DOCUMENTS but expected_requests is empty"
            for req in l.expected_requests:
                all_reason_codes.add(req.reason_code)

    expected_codes = {"MISSING", "INCOMPLETE_COVERAGE", "STALE", "EXPIRED"}
    assert expected_codes.issubset(all_reason_codes), f"Missing reason codes: {expected_codes - all_reason_codes}"

