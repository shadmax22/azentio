"""Noise generators for date formatting, Indian currency representation, filenames, and text noise."""

import random
from datetime import datetime


def format_noisy_date(iso_date_str: str, rng: random.Random) -> str:
    """Format an ISO date string (YYYY-MM-DD) into a realistic noisy format.
    
    Supported formats:
    - DD/MM/YYYY (e.g. 15/03/2026)
    - D-Mon-YY (e.g. 5-Mar-26)
    - DD-Mon-YYYY (e.g. 15-March-2026)
    - Month DD, YYYY (e.g. March 15, 2026)
    - ISO (e.g. 2026-03-15)
    """
    if not iso_date_str:
        return ""
    
    dt = datetime.strptime(iso_date_str, "%Y-%m-%d")
    styles = [
        dt.strftime("%d/%m/%Y"),
        f"{dt.day}-{dt.strftime('%b')}-{dt.strftime('%y')}",
        f"{dt.day:02d}-{dt.strftime('%b')}-{dt.year}",
        dt.strftime("%B %d, %Y"),
        iso_date_str,
    ]
    return rng.choice(styles)


def format_noisy_currency(amount_inr: int, rng: random.Random) -> str:
    """Format an integer amount in INR into realistic Indian variations.
    
    Examples:
    - 'Rs. 5,00,000'
    - '5 Lakh' / '5.5 Lakhs'
    - 'INR 5,00,000'
    - '5,00,000 /-'
    """
    if not amount_inr:
        return ""

    # Indian comma formatting (e.g. 500000 -> 5,00,000)
    s = str(amount_inr)
    if len(s) > 3:
        last_three = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        indian_comma = ",".join(groups) + "," + last_three
    else:
        indian_comma = s

    variations = [
        f"Rs. {indian_comma}",
        f"INR {indian_comma}",
        f"{indian_comma} /-",
        str(amount_inr),
    ]

    # Lakh format only applies to amounts >= 1,00,000 INR
    if amount_inr >= 100000:
        lakh_val = amount_inr / 100000.0
        lakh_str = f"{lakh_val:.1f}".rstrip("0").rstrip(".") + " Lakh"
        variations.append(f"{lakh_str}")
        variations.append(f"Rs. {lakh_str}")

    return rng.choice(variations)


def generate_noisy_filename(doc_type: str, index: int, rng: random.Random) -> str:
    """Generate unhelpful scanner filenames or descriptive names."""
    scan_number = rng.randint(10, 999)
    generic_options = [
        f"scan_{scan_number:04d}.txt",
        f"IMG_{scan_number:04d}.txt",
        f"upload_file_{index}.txt",
        f"doc_{scan_number}.txt",
        f"attachment_{index:02d}.txt",
    ]
    descriptive_options = {
        "ID_PROOF": [f"id_proof_{index}.txt", "passport_scan.txt", "pan_front.txt", "voter_id.txt"],
        "ADDRESS_PROOF": ["utility_bill.txt", "electricity_bill.txt", "water_bill.txt", "rent_agreement.txt"],
        "SALARY_SLIP": [f"payslip_{index}.txt", f"salary_slip_{index}.txt", "pay_voucher.txt"],
        "BANK_STATEMENT": [f"bank_stmt_{index}.txt", "account_statement.txt", "hdfc_passbook.txt"],
        "ITR": ["itr_ack.txt", "tax_return.txt", "form16_itr.txt"],
        "BUSINESS_PROOF": ["gst_certificate.txt", "business_license.txt", "udyam_cert.txt"],
        "PROPERTY_DOC": ["property_deed.txt", "sale_agreement.txt", "title_deed.txt"],
        "UNREADABLE": [f"corrupted_scan_{scan_number}.txt", f"bad_image_{index}.txt", "scan_blurry.txt"],
    }
    
    # 60% chance of generic scan filename, 40% chance of descriptive
    if rng.random() < 0.6:
        return rng.choice(generic_options)
    choices = descriptive_options.get(doc_type, generic_options)
    return rng.choice(choices)


def inject_header_footer(text: str, rng: random.Random) -> str:
    """Inject realistic header/footer disclaimers, watermarks, or page numbers."""
    headers = [
        "*** CONFIDENTIAL FINANCIAL DOCUMENT ***",
        "============================================================",
        "DIGITALLY ARCHIVED COPY - VERIFIED BY LENDER PORTAL",
        "",
    ]
    footers = [
        "\n--- Page 1 of 1 --- [Generated electronically, no signature needed]",
        "\n*** Computer Generated Document. Confidential & Privileged ***",
        "\nFor customer support, call 1800-11-2233 | Branch code: 042",
        "",
    ]
    header = rng.choice(headers)
    footer = rng.choice(footers)
    parts = []
    if header:
        parts.append(header)
    parts.append(text.strip())
    if footer:
        parts.append(footer)
    return "\n".join(parts)


def generate_unreadable_text(rng: random.Random) -> str:
    """Generate corrupted or unclassifiable OCR text for HUMAN_REVIEW cases."""
    corrupted_templates = [
        """
        *** ERROR CODE 0x982: OPTICAL OCR RECOGNITION FAILED ***
        #@%@#%^@#$^%@#^$^@#^
        Low scan resolution: 48 DPI below minimum required 300 DPI.
        Cannot decipher characters: ~~~~ ??? ||| [][][]
        Applicant name: [BLURRED / UNREADABLE ARTIFACT]
        Date: ??/??/????
        *** IMAGE CORRUPTION DETECTED ***
        """,
        """
        [CAMERA PHOTO - EXCESSIVE GLARE DETECTED]
        ====================================================
        Photocopy blacked out by camera flash reflection.
        Text unidentifiable. Missing document boundary headers.
        ====================================================
        """,
        """
        Scan page contains illegible handwritten smudge.
        ----------------------------------------------------
        $%^&*()_+++~~~
        Cannot determine whether document is ID proof or receipt.
        ----------------------------------------------------
        """,
    ]
    return rng.choice(corrupted_templates).strip()
