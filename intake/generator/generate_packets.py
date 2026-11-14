"""Packet renderer converting ground truth label structures into raw text packets."""

import random
from intake.schemas import PacketLabel, Packet, RawDocument
from intake.generator.noise import generate_noisy_filename, generate_unreadable_text
from intake.generator.templates import (
    render_application_form,
    render_id_proof,
    render_address_proof,
    render_salary_slip,
    render_bank_statement,
    render_itr,
    render_business_proof,
    render_property_doc,
)


def render_packet(label: PacketLabel, as_of: str, is_ambiguous_form: bool, rng: random.Random) -> Packet:
    """Render a raw loan application packet from ground truth label with realistic noise."""
    name = label.form_fields.applicant_name or "Applicant"
    
    # 1. Render Application Form Free Text
    form_text = render_application_form(
        fields=label.form_fields.model_dump(),
        is_ambiguous=is_ambiguous_form,
        rng=rng
    )

    # 2. Render each document
    raw_docs = []
    for idx, doc_label in enumerate(label.documents, start=1):
        filename = generate_noisy_filename(doc_label.doc_type, idx, rng)
        
        if doc_label.doc_type == "ID_PROOF":
            text = render_id_proof(name, doc_label.expiry_date or as_of, rng)
        elif doc_label.doc_type == "ADDRESS_PROOF":
            text = render_address_proof(name, doc_label.issue_date or as_of, rng)
        elif doc_label.doc_type == "SALARY_SLIP":
            text = render_salary_slip(name, doc_label.pay_month or "2026-02", rng)
        elif doc_label.doc_type == "BANK_STATEMENT":
            text = render_bank_statement(
                name,
                doc_label.period_start or "2025-09-01",
                doc_label.period_end or "2026-02-28",
                rng
            )
        elif doc_label.doc_type == "ITR":
            text = render_itr(name, doc_label.assessment_year or "2025-26", rng)
        elif doc_label.doc_type == "BUSINESS_PROOF":
            text = render_business_proof(name, rng)
        elif doc_label.doc_type == "PROPERTY_DOC":
            text = render_property_doc(name, rng)
        elif doc_label.doc_type == "UNREADABLE":
            text = generate_unreadable_text(rng)
        else:
            text = f"SUPPORTING DOCUMENT: {doc_label.doc_type}\nHolder: {name}\nDate: {as_of}"

        raw_docs.append(RawDocument(
            doc_id=doc_label.doc_id,
            filename=filename,
            text=text
        ))

    return Packet(
        packet_id=label.packet_id,
        as_of=as_of,
        application_form=form_text,
        documents=raw_docs
    )

