"""Unit tests for list_documents, classify_document, extract_fields, and registry."""

import pytest
from pydantic import ValidationError

from intake.llm.tools.list_documents import list_documents, ListDocumentsInput
from intake.llm.tools.classify_document import classify_document, ClassifyDocumentInput
from intake.llm.tools.extract_fields import extract_fields, ExtractFieldsInput
from intake.llm.tools.registry import execute_tool, get_available_tools


def test_list_documents():
    """Verify list_documents extracts document metadata correctly."""
    inp = ListDocumentsInput(
        packet_id="pkt_001",
        documents=[
            {"doc_id": "doc_01", "filename": "scan_001.txt", "text": "sample 1"},
            {"doc_id": "doc_02", "filename": "bill_02.txt", "text": "sample 2"},
        ]
    )
    res = list_documents(inp)
    assert res.count == 2
    assert res.packet_id == "pkt_001"
    assert res.documents[0].doc_id == "doc_01"
    assert res.documents[1].filename == "bill_02.txt"


def test_classify_document_all_types():
    """Verify classification across all supported banking document types."""
    samples = {
        "ID_PROOF": "REPUBLIC OF INDIA - PASSPORT Given Names: Rahul Verma Expiry: 14-Aug-2032",
        "ADDRESS_PROOF": "TATA POWER DELHI DISTRIBUTION LIMITED ELECTRICITY CONSUMER BILL Bill Date: 15/02/2026",
        "SALARY_SLIP": "INFOSYS TECHNOLOGIES SALARY SLIP FOR MONTH: FEBRUARY 2026 NET DISBURSED: Rs. 75,000",
        "BANK_STATEMENT": "HDFC BANK - ACCOUNT STATEMENT Statement Coverage Window: 01/09/2025 to 28/02/2026",
        "ITR": "INDIAN INCOME TAX RETURN ACKNOWLEDGEMENT (ITR-V) Assessment Year: 2025-26",
        "BUSINESS_PROOF": "GOVERNMENT OF INDIA - GOODS AND SERVICES TAX FORM GST REG-06 GSTIN: 07AABCT1234A1Z5",
        "PROPERTY_DOC": "SUB-REGISTRAR OFFICE REGISTERED DEED OF SALE / TITLE CONVEYANCE Registration Number: 12345",
        "UNREADABLE": "*** ERROR CODE 0x982: OPTICAL OCR RECOGNITION FAILED *** Low scan resolution",
    }

    for expected_type, text in samples.items():
        res = classify_document(ClassifyDocumentInput(doc_id="d1", text=text))
        assert res.doc_type == expected_type, f"Failed for {expected_type}, got {res.doc_type}"
        assert res.confidence >= 0.80


def test_extract_form_fields_clean():
    """Verify clean form field extraction with high confidence."""
    form_text = """
    RETAIL CREDIT APPLICATION FORM
    Application Date: 05/03/2026
    Applicant Full Name: Rahul Kumar Verma
    Loan Product Applied For: personal_loan
    Employment Category: salaried
    Requested Loan Amount: Rs. 6,50,000
    Repayment Tenure (Months): 36
    """
    res = extract_fields(ExtractFieldsInput(text=form_text, target="form"))
    fields = res.fields
    assert fields["applicant_name"].value == "Rahul Kumar Verma"
    assert fields["applicant_name"].confidence >= 0.90

    assert fields["product"].value == "personal_loan"
    assert fields["product"].confidence >= 0.90

    assert fields["employment_type"].value == "salaried"
    assert fields["employment_type"].confidence >= 0.90

    assert fields["loan_amount"].value == 650000
    assert fields["loan_amount"].confidence >= 0.90

    assert fields["tenure_months"].value == 36
    assert fields["tenure_months"].confidence >= 0.90

    assert fields["application_date"].value == "2026-03-05"
    assert fields["application_date"].confidence >= 0.90


def test_extract_form_fields_ambiguous():
    """Verify ambiguous form fields return low confidence (< 0.8)."""
    ambiguous_text = """
    RETAIL CREDIT APPLICATION FORM
    Applicant Full Name: [ILLEGIBLE SIGNATURE SMUDGE]
    Loan Product Applied For: personal_loan
    Employment Category: salaried
    Requested Loan Amount: somewhere between forty to fifty lakhs maybe
    Repayment Tenure (Months): flexible depending on rate
    Application Date: 05/03/2026
    """
    res = extract_fields(ExtractFieldsInput(text=ambiguous_text, target="form"))
    fields = res.fields
    # Low confidence fields
    assert fields["applicant_name"].confidence < 0.80
    assert fields["loan_amount"].confidence < 0.80
    assert fields["tenure_months"].confidence < 0.80


def test_extract_document_period_fields():
    """Verify extraction of period fields from documents."""
    doc_text = """
    PASSPORT OFFICE
    Expiry Date: 14-Aug-2032
    Bill Issue Date: 15/02/2026
    Pay Period: FEBRUARY 2026
    Statement Coverage Window: 2025-09-01 to 2026-02-28
    Assessment Year: 2025-26
    """
    res = extract_fields(ExtractFieldsInput(text=doc_text, target="document"))
    fields = res.fields

    assert fields["expiry_date"].value == "2032-08-14"
    assert fields["issue_date"].value == "2026-02-15"
    assert fields["pay_month"].value == "2026-02"
    assert fields["period_start"].value == "2025-09-01"
    assert fields["period_end"].value == "2026-02-28"
    assert fields["assessment_year"].value == "2025-26"


def test_tool_registry_dispatcher():
    """Verify executing tools through the central registry."""
    tools = get_available_tools()
    assert set(tools) == {"list_documents", "classify_document", "extract_fields", "check_completeness"}

    # Execute list_documents
    result = execute_tool("list_documents", {
        "packet_id": "pkt_100",
        "documents": [{"doc_id": "d1", "filename": "test.txt"}]
    })
    assert result["count"] == 1
    assert result["packet_id"] == "pkt_100"

    # Unknown tool raises KeyError
    with pytest.raises(KeyError, match="Unknown tool"):
        execute_tool("non_existent_tool", {})

    # Invalid tool arguments raises ValidationError
    with pytest.raises(ValidationError):
        execute_tool("classify_document", {"doc_id": "d1"})  # missing required 'text'

