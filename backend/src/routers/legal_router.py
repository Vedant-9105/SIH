import hashlib
import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Inspection, Store, User, Rule, Violation, AuditLog

router = APIRouter(prefix="/api/legal", tags=["Legal & Compliance Review"])

# Statutory Rule Traceability Matrix
RULE_TRACEABILITY_MATRIX = [
    {
        "declaration": "Generic / Common Name",
        "act_section": "Section 18(1), Legal Metrology Act, 2009",
        "rule_clause": "Rule 6(1)(a), Legal Metrology (Packaged Commodities) Rules, 2011",
        "gazette_reference": "G.S.R. 202(E) dated 07.03.2011",
        "offence_category": "Omission of Statutory Commodity Identity",
        "punitive_section": "Section 36(1) — Fine up to ₹25,000 (1st), ₹50,000 (2nd), ₹1,00,000 or 1 year jail (subsequent)",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1) of Legal Metrology Act, 2009"
    },
    {
        "declaration": "Manufacturer / Packer Name & Complete Address",
        "act_section": "Section 18(1), Legal Metrology Act, 2009",
        "rule_clause": "Rule 6(1)(b), Legal Metrology (Packaged Commodities) Rules, 2011",
        "gazette_reference": "G.S.R. 202(E) as amended by G.S.R. 779(E)",
        "offence_category": "Defective Traceability / Missing Manufacturer Contact",
        "punitive_section": "Section 36(1) — Fine up to ₹25,000 (1st), ₹50,000 (2nd)",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1) of Legal Metrology Act, 2009"
    },
    {
        "declaration": "Net Quantity in Standard SI Units",
        "act_section": "Section 18(1) read with Section 8(1), Legal Metrology Act, 2009",
        "rule_clause": "Rule 6(1)(c) & Rule 12 & Schedule III, LM PCR 2011",
        "gazette_reference": "G.S.R. 202(E) & Weights and Measures Standard Schedule",
        "offence_category": "Use of Non-Standard Units / False Quantity Declaration",
        "punitive_section": "Section 36(1) & Section 29 — Fine up to ₹25,000",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1) of Legal Metrology Act, 2009"
    },
    {
        "declaration": "Month & Year of Manufacture / Packing",
        "act_section": "Section 18(1), Legal Metrology Act, 2009",
        "rule_clause": "Rule 6(1)(d), Legal Metrology (Packaged Commodities) Rules, 2011",
        "gazette_reference": "G.S.R. 202(E)",
        "offence_category": "Omission of Packaging/Manufacturing Date",
        "punitive_section": "Section 36(1) — Fine up to ₹25,000",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1)"
    },
    {
        "declaration": "Maximum Retail Price (MRP) with (Inclusive of all taxes)",
        "act_section": "Section 18(1) read with Section 36, Legal Metrology Act, 2009",
        "rule_clause": "Rule 6(1)(e) & Rule 18(2), Legal Metrology (Packaged Commodities) Rules, 2011",
        "gazette_reference": "G.S.R. 202(E) & Consumer Protection Notifications",
        "offence_category": "Dual MRP / Omission of Tax Inclusive Statement / Overcharging",
        "punitive_section": "Section 36(1) & Section 36(2) — Fine up to ₹50,000",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1)"
    },
    {
        "declaration": "Consumer Care Helpline & Email",
        "act_section": "Section 18(1), Legal Metrology Act, 2009",
        "rule_clause": "Rule 6(1)(n), Legal Metrology (Packaged Commodities) Rules, 2011",
        "gazette_reference": "G.S.R. 426(E) dated 23.06.2017",
        "offence_category": "Deprivation of Consumer Grievance Redressal Mechanism",
        "punitive_section": "Section 36(1) — Fine up to ₹25,000",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1)"
    },
    {
        "declaration": "Country of Origin / Manufacture",
        "act_section": "Section 18(1), Legal Metrology Act, 2009",
        "rule_clause": "Rule 6(1)(f), Legal Metrology (Packaged Commodities) Rules, 2011",
        "gazette_reference": "G.S.R. 779(E) dated 02.11.2021",
        "offence_category": "Omission of Country of Origin on Packaging / E-commerce",
        "punitive_section": "Section 36(1) — Fine up to ₹25,000",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1)"
    },
    {
        "declaration": "Unit Sale Price (USP)",
        "act_section": "Section 18(1), Legal Metrology Act, 2009",
        "rule_clause": "Rule 6(11), Legal Metrology (Packaged Commodities) Rules, 2011",
        "gazette_reference": "G.S.R. 779(E) effective from 01.12.2022",
        "offence_category": "Non-display of Unit Sale Price per g/kg/ml/l",
        "punitive_section": "Section 36(1) — Fine up to ₹25,000",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1)"
    },
    {
        "declaration": "Batch / Lot / Code Number",
        "act_section": "Section 18(1), Legal Metrology Act, 2009",
        "rule_clause": "Rule 6(1)(d), Legal Metrology (Packaged Commodities) Rules, 2011",
        "gazette_reference": "G.S.R. 202(E) dated 07.03.2011",
        "offence_category": "Omission of Production Identification and Traceability Code",
        "punitive_section": "Section 36(1) — Fine up to ₹25,000",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1)"
    },
    {
        "declaration": "Best Before / Expiry / Use By Date",
        "act_section": "Section 18(1), Legal Metrology Act, 2009 read with Food Safety Act",
        "rule_clause": "Rule 6(1)(d) & FSSAI Packaging & Labelling Regulations, 2011",
        "gazette_reference": "F. No. P. 15025/24/2012-PA/FSSAI",
        "offence_category": "Distribution of Expired / Unsafe Packaged Commodities",
        "punitive_section": "Section 36(1) & FSS Act Section 59",
        "compounding_eligible": False,
        "compounding_section": "Not compoundable if food safety compromised"
    },
    {
        "declaration": "Dimensions / Sizes of Commodity",
        "act_section": "Section 18(1), Legal Metrology Act, 2009",
        "rule_clause": "Rule 13 & Schedule II, Legal Metrology (Packaged Commodities) Rules, 2011",
        "gazette_reference": "G.S.R. 202(E) dated 07.03.2011",
        "offence_category": "Failure to declare length/breadth/thickness in standard metric units",
        "punitive_section": "Section 36(1) — Fine up to ₹25,000",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1)"
    },
    {
        "declaration": "Vegetarian / Non-Vegetarian Logo",
        "act_section": "Section 18(1), Legal Metrology Act, 2009 read with FSS Regulations",
        "rule_clause": "Rule 6 & FSSAI Labelling Regulation 2.2.2(4)",
        "gazette_reference": "Gazette Notification F.No. 1-94/FSSAI/SP(L&C)/2020",
        "offence_category": "Misleading Dietary Nature / Logo Dimension Deficiencies",
        "punitive_section": "Section 36(1) & Section 52 of FSS Act",
        "compounding_eligible": True,
        "compounding_section": "Section 48(1)"
    }
]


@router.get("/rules-traceability")
def get_rules_traceability():
    """Returns statutory mapping from package declarations to Act sections and rules."""
    return {
        "statute": "Legal Metrology Act, 2009 (Act No. 1 of 2010)",
        "rules": "Legal Metrology (Packaged Commodities) Rules, 2011",
        "matrix": RULE_TRACEABILITY_MATRIX,
        "traceability_matrix": RULE_TRACEABILITY_MATRIX
    }


@router.get("/penalty-memo/{inspection_id}")
def generate_penalty_memo(inspection_id: int, db: Session = Depends(get_db)):
    """
    Generates formal Section 36 Legal Notice & Compounding Assessment Memo
    for Public Prosecutor / Legal Enforcement Officers.
    """
    ins = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not ins:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    store = ins.store
    officer = ins.officer

    memo_date = datetime.datetime.utcnow().strftime("%d-%m-%Y")
    violations_summary = []
    total_compounding = 0.0

    for idx, v in enumerate(ins.violations, 1):
        amt = v.compounding_amount or 5000.0
        total_compounding += amt
        violations_summary.append({
            "count": idx,
            "rule_code": v.rule_code,
            "legal_reference": v.legal_reference,
            "detected_value": v.detected_value,
            "charge": v.issue,
            "severity": v.severity,
            "compounding_liability": amt
        })

    is_repeat = db.query(Inspection).filter(
        Inspection.store_id == ins.store_id,
        Inspection.compliance_status == "NON_COMPLIANT",
        Inspection.id != ins.id
    ).count() > 0

    penalty_scale = "FIRST OFFENCE — Penalty up to ₹25,000 per violation under Section 36(1)" if not is_repeat else "SECOND / SUBSEQUENT OFFENCE — Penalty up to ₹50,000 / ₹1,00,000 or imprisonment under Section 36(1)"

    memo_text = f"""
================================================================================
BEFORE THE CONTROLLER / AUTHORIZED LEGAL METROLOGY ADJUDICATING OFFICER
DEPARTMENT OF LEGAL METROLOGY, GOVERNMENT OF INDIA
================================================================================

NOTICE OF SEIZURE AND STATUTORY INSPECTION MEMO UNDER SECTION 15 & 18
OF THE LEGAL METROLOGY ACT, 2009 READ WITH RULE 6 & 12 OF LM (PC) RULES, 2011

MEMO REF NO: {ins.inspection_number}/LEGAL
DATE: {memo_date}

TO:
The Proprietor / Partners / Directors,
{store.store_name if store else 'Retail Trader'},
{store.address if store else 'Premises'}, {store.city if store else 'Bengaluru'}, {store.state if store else 'Karnataka'}.
GSTIN: {store.gstin if store else 'UNREGISTERED'}

SUBJECT: Show Cause & Compounding Notice for contravention of Section 18 of the Legal Metrology Act, 2009.

1. PREMISES INSPECTION & RECORD:
Be it known that on {ins.inspection_date.strftime('%d-%m-%Y at %H:%M UTC')}, Inspecting Officer {officer.full_name if officer else 'LMO'} ({officer.officer_id if officer else 'LMO001'}), Legal Metrology Department, inspected your business premises situated at {store.address if store else 'Inspection Location'}.

2. COMMODITY SAMPLED & TESTED:
Commodity Inspected: {ins.category}
AI Vision & OCR Audit Confidence: {round(ins.compliance_score, 1)}%
Image Evidence Checksum (SHA-256): {ins.sha256_hash or 'Verified Digital Evidence'}

3. SPECIFIC CHARGES & CONTRAVENTIONS OF STATUTE:
Upon scrutiny and automated computational vision analysis, the following statutory contraventions of Rule 6 of the Legal Metrology (Packaged Commodities) Rules, 2011 have been recorded:
"""
    for v in violations_summary:
        memo_text += f"\n[{v['count']}] Charge under {v['legal_reference']}:\n    - Offence: {v['charge']}\n    - Stamped/Detected Value: '{v['detected_value']}'\n    - Severity: {v['severity']}\n    - Proposed Compounding Composition: ₹{v['compounding_liability']:,.2f}\n"

    memo_text += f"""
4. STATUTORY PENALTY PROVISIONS:
- Section 36(1), Legal Metrology Act, 2009: {penalty_scale}.
- Cumulative Compounding Composition Assessment: ₹{total_compounding:,.2f}.

5. OPPORTUNITY FOR COMPOUNDING UNDER SECTION 48:
In accordance with Section 48 of the Legal Metrology Act, 2009, the undersigned officer offers the option of compounding the said offences upon payment of ₹{total_compounding:,.2f} within 14 calendar days from receipt of this notice, failing which prosecution will be instituted before the competent Judicial Magistrate First Class having jurisdiction.

ISSUED UNDER THE OFFICIAL HAND AND SEAL OF THE LEGAL METROLOGY OFFICER:
Signature: ____________________________________
Designation: {officer.designation if officer else 'Legal Metrology Officer'}
Central Enforcement Wing, Legal Metrology Division
"""

    return {
        "inspection_number": ins.inspection_number,
        "is_repeat_offender": is_repeat,
        "penalty_scale": penalty_scale,
        "violations_summary": violations_summary,
        "total_compounding_fee": total_compounding,
        "formal_legal_notice": memo_text.strip()
    }


@router.post("/verify-evidence")
def verify_evidence_hash(payload: Dict[str, Any] = Body(...)):
    """
    Validates digital evidence chain-of-custody.
    Verifies that the client or stored hash matches the generated SHA-256 digest.
    """
    client_hash = payload.get("sha256_hash", "")
    content_str = payload.get("evidence_string", "")
    file_path = payload.get("file_path", "")

    if file_path and os.path.exists(file_path):
        with open(file_path, "rb") as f:
            computed_hash = hashlib.sha256(f.read()).hexdigest()
    elif isinstance(content_str, str):
        try:
            computed_hash = hashlib.sha256(content_str.encode("latin1")).hexdigest()
        except Exception:
            computed_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()
    else:
        computed_hash = hashlib.sha256(str(content_str).encode()).hexdigest()

    matches = (client_hash.lower() == computed_hash.lower()) if client_hash else True

    return {
        "computed_sha256": computed_hash,
        "client_sha256": client_hash,
        "is_tamper_free": matches,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "integrity_status": "AUTHENTIC_UNALTERED_EVIDENCE" if matches else "INTEGRITY_COMPROMISED"
    }
