"""Text templates for application forms and banking supporting documents."""

import random
from typing import Dict, Any
from intake.generator.noise import format_noisy_date, format_noisy_currency, inject_header_footer, generate_unreadable_text
from intake.generator.sample_data import COMPANIES, BANKS, UTILITIES


def render_application_form(fields: Dict[str, Any], is_ambiguous: bool, rng: random.Random) -> str:
    """Render application form free text. If is_ambiguous is True, inject ambiguous values."""
    name = fields.get("applicant_name") or "Applicant Name Missing"
    product = fields.get("product") or "personal_loan"
    employment = fields.get("employment_type") or "salaried"
    raw_amount = fields.get("loan_amount") or 500000
    tenure = fields.get("tenure_months") or 36
    raw_date = fields.get("application_date") or "2026-03-01"

    if is_ambiguous:
        # Ambiguous amount or tenure or product
        ambiguous_variants = [
            "Requested Loan Amount: somewhere between forty to fifty lakhs maybe, let underwriter decide",
            "Requested Loan Amount: unspecified pending property valuation",
            "Tenure: flexible depending on interest rate quote",
            "Applicant Name: [Illegible smudge on applicant signature block]",
        ]
        amount_line = rng.choice(ambiguous_variants)
    else:
        amount_line = f"Requested Loan Amount: {format_noisy_currency(raw_amount, rng)}"

    formatted_date = format_noisy_date(raw_date, rng)

    template = f"""
======================================================================
                  RETAIL CREDIT APPLICATION FORM
======================================================================
Application Date: {formatted_date}
Applicant Full Name: {name}
Loan Product Applied For: {product}
Employment Category: {employment}
{amount_line}
Repayment Tenure (Months): {tenure}
Declaration:
I hereby confirm that all details furnished above are accurate and true
to the best of my knowledge and I agree to credit assessment checks.
======================================================================
"""
    return inject_header_footer(template, rng)


def render_id_proof(name: str, expiry_date: str, rng: random.Random) -> str:
    """Render an ID Proof document (Passport, PAN, Voter ID, or DL)."""
    id_types = ["PASSPORT", "VOTER_ID", "DRIVING_LICENCE", "NATIONAL_ID"]
    id_type = rng.choice(id_types)
    doc_num = f"{rng.choice(['Z', 'A', 'N', 'K'])}{rng.randint(1000000, 9999999)}"
    formatted_exp = format_noisy_date(expiry_date, rng)

    template = f"""
GOVERNMENT OF INDIA - OFFICIAL IDENTIFICATION DOCUMENT
Document Type: {id_type}
Document Number: {doc_num}
Holder Name: {name}
Nationality: INDIAN
Gender: {rng.choice(['MALE', 'FEMALE'])}
Expiry Date: {formatted_exp}
Authority: Regional Passport / Transport Office
"""
    return inject_header_footer(template, rng)


def render_address_proof(name: str, issue_date: str, rng: random.Random) -> str:
    """Render an Address Proof document (Utility bill or rental agreement)."""
    provider = rng.choice(UTILITIES)
    bill_no = f"BILL-{rng.randint(100000, 999999)}"
    formatted_issue = format_noisy_date(issue_date, rng)
    amount = format_noisy_currency(rng.randint(850, 4200), rng)

    template = f"""
{provider}
MONTHLY UTILITY SERVICE & CONSUMPTION INVOICE
Bill Number: {bill_no}
Consumer Name: {name}
Premises Address: Flat {rng.randint(101, 909)}, Maple Heights, Sector 62, New Delhi
Bill Issue Date: {formatted_issue}
Total Due Payable: {amount}
Status: PAID IN FULL VIA ONLINE CLEARING
"""
    return inject_header_footer(template, rng)


def render_salary_slip(name: str, pay_month: str, rng: random.Random) -> str:
    """Render a Salary Slip for a specific month (YYYY-MM)."""
    company = rng.choice(COMPANIES)
    basic = rng.randint(40000, 120000)
    hra = int(basic * 0.4)
    special = int(basic * 0.25)
    deductions = int(basic * 0.1)
    net_pay = basic + hra + special - deductions

    month_name = pay_month  # e.g. 2026-02

    template = f"""
{company}
EMPLOYEE SALARY STATEMENT / PAYSLIP
Pay Period: {month_name}
Employee Name: {name}
Department: Engineering / Operations
Basic Salary: {format_noisy_currency(basic, rng)}
House Rent Allowance: {format_noisy_currency(hra, rng)}
Special Allowance: {format_noisy_currency(special, rng)}
Standard Deductions & PF: {format_noisy_currency(deductions, rng)}
----------------------------------------------------------------------
NET DISBURSED AMOUNT: {format_noisy_currency(net_pay, rng)}
Disbursement Channel: NEFT / Direct Account Credit
"""
    return inject_header_footer(template, rng)


def render_bank_statement(name: str, start_date: str, end_date: str, rng: random.Random) -> str:
    """Render a Bank Statement covering start_date to end_date."""
    bank = rng.choice(BANKS)
    acc_no = f"50100{rng.randint(100000000, 999999999)}"
    fmt_start = format_noisy_date(start_date, rng)
    fmt_end = format_noisy_date(end_date, rng)

    template = f"""
{bank} - ACCOUNT TRANSACTION REPORT
Account Name: {name}
Savings Account No: {acc_no}
Statement Coverage Window: {fmt_start} to {fmt_end}
Opening Balance: {format_noisy_currency(rng.randint(25000, 80000), rng)}
Total Credits: {format_noisy_currency(rng.randint(300000, 900000), rng)}
Total Debits: {format_noisy_currency(rng.randint(250000, 750000), rng)}
Closing Balance: {format_noisy_currency(rng.randint(45000, 150000), rng)}
======================================================================
Periodic transaction summary verified by core banking database.
"""
    return inject_header_footer(template, rng)


def render_itr(name: str, assessment_year: str, rng: random.Random) -> str:
    """Render an Income Tax Return Acknowledgement (ITR-V)."""
    pan = f"{rng.choice(['A', 'B', 'C'])}{rng.choice(['P', 'F'])}{rng.choice(['X', 'Z'])}{name[:2].upper()}{rng.randint(1000, 9999)}{rng.choice(['K', 'M'])}"
    ack_no = f"{rng.randint(100000000000, 999999999999)}"
    gross_income = rng.randint(850000, 2400000)

    template = f"""
GOVERNMENT OF INDIA - INCOME TAX DEPARTMENT
INDIAN INCOME TAX RETURN ACKNOWLEDGEMENT (ITR-V)
Assessment Year: {assessment_year}
Name: {name}
PAN: {pan}
Form: ITR-3 / ITR-4 (Business & Profession)
e-Filing Acknowledgement Number: {ack_no}
Total Gross Income: {format_noisy_currency(gross_income, rng)}
Taxes Paid: Verified e-verification completed via Aadhaar OTP
"""
    return inject_header_footer(template, rng)


def render_business_proof(name: str, rng: random.Random) -> str:
    """Render a Business Proof (GST Registration Certificate)."""
    gstin = f"07{name[:3].upper()}{rng.randint(1000, 9999)}{rng.choice(['A', 'Z'])}1Z{rng.choice(['5', '9'])}"
    trade_name = f"{name} Consulting & Enterprises"

    template = f"""
GOVERNMENT OF INDIA - GOODS AND SERVICES TAX
FORM GST REG-06: CERTIFICATE OF REGISTRATION
Registration Number (GSTIN): {gstin}
Legal Name: {name}
Trade Name: {trade_name}
Constitution of Business: Sole Proprietorship
Principal Place of Business: Sector 18, Commercial Arcade, Noida 201301
Date of Validity: Continuing
Date of Issue: 12-Apr-2022
Jurisdiction: State Tax Ward 4, Delhi/NCR
"""
    return inject_header_footer(template, rng)


def render_property_doc(name: str, rng: random.Random) -> str:
    """Render a Property Document (Sale Agreement / Title Deed)."""
    reg_no = f"REG-DOC-{rng.randint(10000, 99999)}/2024"
    prop_amount = rng.randint(4500000, 9500000)

    template = f"""
SUB-REGISTRAR OFFICE - REGISTRATION AND STAMP DEPARTMENT
REGISTERED DEED OF SALE / TITLE CONVEYANCE
Registration Number: {reg_no}
Purchaser / Title Holder: {name}
Property Description: Residential Flat No. B-402, Green Meadows Enclave, Plot 14, Whitefield
Total Sale Consideration: {format_noisy_currency(prop_amount, rng)}
Stamp Duty Paid: Fully cleared and verified on state portal
Title Status: Absolute Ownership Clear of Prior Encumbrances
"""
    return inject_header_footer(template, rng)

