import re
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from src.database.models import Rule

VALID_UNITS = ["g", "kg", "mg", "ml", "l", "kl", "m", "cm", "mm", "n", "u", "unit", "units", "piece", "pieces", "sticks"]
FORBIDDEN_UNIT_PATTERNS = [r"\bgms\b", r"\bgm\b", r"\bkilos\b", r"\bltrs\b", r"\bpkts\b"]

class ComplianceEngine:
    """
    Rule Matching and Regulatory Adjudication Engine.
    Evaluates extracted packaging declarations against statutory Legal Metrology requirements:
    - Legal Metrology Act, 2009 (Sections 18, 36, 48)
    - Legal Metrology (Packaged Commodities) Rules, 2011 (Rules 6, 9, 12, Schedule III)
    """

    @classmethod
    def evaluate(
        cls,
        extracted_fields: Dict[str, Any],
        db_rules: Optional[List[Rule]] = None,
        category: str = "General Packaged Commodity"
    ) -> Dict[str, Any]:
        violations: List[Dict[str, Any]] = []
        
        scores = {
            "mandatory_declarations": 100.0,
            "quantity_standards": 100.0,
            "mrp_and_pricing": 100.0,
            "consumer_care": 100.0,
            "traceability_and_origin": 100.0
        }

        def get_field_info(key: str):
            f = extracted_fields.get(key, {})
            val = f.get("value")
            raw = f.get("raw_text", "") or ""
            status = f.get("status", "MISSING")
            conf = f.get("confidence", 0.0)
            bbox = f.get("bounding_box", [0, 0, 0, 0])
            evidence = f.get("evidence", "")
            return val, str(raw).strip(), status, conf, bbox, evidence

        # 1. Product Generic Name (LM-PC-001)
        p_val, p_raw, p_stat, p_conf, p_bbox, p_ev = get_field_info("product_name")
        if not p_val or p_stat == "MISSING":
            violations.append({
                "rule_code": "LM-PC-001",
                "category": "Product Identity",
                "issue": "Generic or common name of commodity is missing on the Principal Display Panel.",
                "detected_value": "Not Detected",
                "expected_requirement": "Generic or common name must be prominently displayed (Rule 6(1)(a)).",
                "severity": "CRITICAL",
                "confidence": 0.96,
                "legal_reference": "Rule 6(1)(a), Legal Metrology (PC) Rules, 2011",
                "evidence_zone": "Header / Display Panel",
                "compounding_amount": 10000.0
            })
            scores["mandatory_declarations"] -= 30.0

        # 2. Manufacturer / Packer Name (LM-PC-002)
        m_val, m_raw, m_stat, m_conf, m_bbox, m_ev = get_field_info("manufacturer_name")
        if not m_val or m_stat == "MISSING":
            violations.append({
                "rule_code": "LM-PC-002",
                "category": "Manufacturer Traceability",
                "issue": "Name of manufacturer, packer, or importer missing from package.",
                "detected_value": "Not Detected",
                "expected_requirement": "Name and identity of manufacturer or packer must be stated (Rule 6(1)(b)).",
                "severity": "HIGH",
                "confidence": 0.95,
                "legal_reference": "Rule 6(1)(b), Legal Metrology (PC) Rules, 2011",
                "evidence_zone": "Manufacturer Zone",
                "compounding_amount": 5000.0
            })
            scores["mandatory_declarations"] -= 25.0

        # 3. Complete Address (LM-PC-003)
        a_val, a_raw, a_stat, a_conf, a_bbox, a_ev = get_field_info("manufacturer_address")
        if not a_val or a_stat == "MISSING":
            violations.append({
                "rule_code": "LM-PC-003",
                "category": "Manufacturer Address",
                "issue": "Complete address of manufacturer or packer missing from package.",
                "detected_value": "Not Detected",
                "expected_requirement": "Complete address with street, city, state and PIN code required (Rule 6(1)(b)).",
                "severity": "HIGH",
                "confidence": 0.92,
                "legal_reference": "Rule 6(1)(b), Legal Metrology (PC) Rules, 2011",
                "evidence_zone": "Address Zone",
                "compounding_amount": 5000.0
            })
            scores["traceability_and_origin"] -= 30.0
        elif len(str(a_val)) < 15:
            violations.append({
                "rule_code": "LM-PC-003",
                "category": "Manufacturer Address",
                "issue": "Incomplete manufacturer address; lacking full postal traceability.",
                "detected_value": str(a_val),
                "expected_requirement": "Full address enabling postal and regulatory contact must be stated (Rule 6(1)(b)).",
                "severity": "MEDIUM",
                "confidence": 0.88,
                "legal_reference": "Rule 6(1)(b), Legal Metrology (PC) Rules, 2011",
                "evidence_zone": "Address Zone",
                "compounding_amount": 3000.0
            })
            scores["traceability_and_origin"] -= 15.0

        # 4. Net Quantity (LM-PC-004)
        q_val, q_raw, q_stat, q_conf, q_bbox, q_ev = get_field_info("net_quantity")
        if not q_val or q_stat == "MISSING":
            violations.append({
                "rule_code": "LM-PC-004",
                "category": "Net Quantity Standard",
                "issue": "Net quantity declaration missing from package.",
                "detected_value": "Not Detected",
                "expected_requirement": "Net weight or measure must be clearly stated in standard SI units (Rule 6(1)(c)).",
                "severity": "CRITICAL",
                "confidence": 0.98,
                "legal_reference": "Rule 6(1)(c) & Rule 12, Legal Metrology (PC) Rules, 2011",
                "evidence_zone": "Net Quantity Zone",
                "compounding_amount": 15000.0
            })
            scores["quantity_standards"] -= 50.0
        else:
            for pat in FORBIDDEN_UNIT_PATTERNS:
                if re.search(pat, q_raw.lower()):
                    forbidden_match = re.search(pat, q_raw.lower()).group(0)
                    violations.append({
                        "rule_code": "LM-PC-004",
                        "category": "Net Quantity Standard",
                        "issue": f"Forbidden non-standard unit abbreviation '{forbidden_match}' detected in net quantity.",
                        "detected_value": q_raw,
                        "expected_requirement": "Only legal standard symbols permitted: g, kg, ml, l. Forbidden: gm, gms, ltrs (Rule 12).",
                        "severity": "HIGH",
                        "confidence": 0.94,
                        "legal_reference": "Rule 12 & Schedule III, Legal Metrology (PC) Rules, 2011",
                        "evidence_zone": "Net Quantity Zone",
                        "compounding_amount": 5000.0
                    })
                    scores["quantity_standards"] -= 30.0
                    break

        # 5. MRP Declaration (LM-PC-005)
        mrp_val, mrp_raw, mrp_stat, mrp_conf, mrp_bbox, mrp_ev = get_field_info("mrp")
        if not mrp_val or mrp_stat == "MISSING":
            violations.append({
                "rule_code": "LM-PC-005",
                "category": "Maximum Retail Price",
                "issue": "MRP declaration missing from package.",
                "detected_value": "Not Detected",
                "expected_requirement": "Maximum Retail Price inclusive of all taxes must be declared (Rule 6(1)(e)).",
                "severity": "CRITICAL",
                "confidence": 0.98,
                "legal_reference": "Rule 6(1)(e), Legal Metrology (PC) Rules, 2011",
                "evidence_zone": "MRP Zone",
                "compounding_amount": 15000.0
            })
            scores["mrp_and_pricing"] -= 50.0
        else:
            tax_match = re.search(r"(incl|inclusive).*?(tax|all taxes)", mrp_raw.lower())
            if not tax_match:
                violations.append({
                    "rule_code": "LM-PC-005",
                    "category": "Maximum Retail Price",
                    "issue": "Mandatory statement '(Inclusive of all taxes)' missing from MRP declaration.",
                    "detected_value": mrp_raw,
                    "expected_requirement": "MRP must unambiguously state 'Inclusive of all taxes' or 'Incl. of all taxes' (Rule 6(1)(e)).",
                    "severity": "HIGH",
                    "confidence": 0.93,
                    "legal_reference": "Rule 6(1)(e), Legal Metrology (PC) Rules, 2011",
                    "evidence_zone": "MRP Zone",
                    "compounding_amount": 5000.0
                })
                scores["mrp_and_pricing"] -= 25.0

        # 6. Manufacturing Date (LM-PC-006)
        d_val, d_raw, d_stat, d_conf, d_bbox, d_ev = get_field_info("manufacturing_date")
        if not d_val or d_stat == "MISSING":
            violations.append({
                "rule_code": "LM-PC-006",
                "category": "Date of Manufacture / Packing",
                "issue": "Month and year of manufacture or pre-packing missing.",
                "detected_value": "Not Detected",
                "expected_requirement": "Month and year of manufacture/packing must be clearly stated (Rule 6(1)(d)).",
                "severity": "HIGH",
                "confidence": 0.95,
                "legal_reference": "Rule 6(1)(d), Legal Metrology (PC) Rules, 2011",
                "evidence_zone": "Date / Batch Zone",
                "compounding_amount": 5000.0
            })
            scores["mandatory_declarations"] -= 20.0

        # 7. Consumer Care Details (LM-PC-007)
        c_val, c_raw, c_stat, c_conf, c_bbox, c_ev = get_field_info("consumer_care")
        if not c_val or c_stat == "MISSING":
            violations.append({
                "rule_code": "LM-PC-007",
                "category": "Consumer Care Grievance",
                "issue": "Consumer care details missing from package.",
                "detected_value": "Not Detected",
                "expected_requirement": "Consumer care telephone helpline and email ID required (Rule 6(1)(n)).",
                "severity": "HIGH",
                "confidence": 0.95,
                "legal_reference": "Rule 6(1)(n), Legal Metrology (PC) Rules, 2011",
                "evidence_zone": "Consumer Care Zone",
                "compounding_amount": 5000.0
            })
            scores["consumer_care"] -= 50.0
        else:
            has_phone = bool(re.search(r"\b(\d{3,4}[- ]?\d{3,4}[- ]?\d{3,4}|1800[- ]?\d{3}[- ]?\d{3,4})\b", c_raw))
            has_email = bool(re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", c_raw))
            if not (has_phone and has_email):
                missing_part = "phone number" if not has_phone else "email address"
                violations.append({
                    "rule_code": "LM-PC-007",
                    "category": "Consumer Care Grievance",
                    "issue": f"Consumer care grievance cell incomplete: missing {missing_part}.",
                    "detected_value": c_raw,
                    "expected_requirement": "Both a telephone helpline and an email address must be provided for consumer grievance (Rule 6(1)(n)).",
                    "severity": "MEDIUM",
                    "confidence": 0.90,
                    "legal_reference": "Rule 6(1)(n), Legal Metrology (PC) Rules, 2011",
                    "evidence_zone": "Consumer Care Zone",
                    "compounding_amount": 2500.0
                })
                scores["consumer_care"] -= 25.0

        # 8. Country of Origin (LM-PC-008)
        co_val, co_raw, co_stat, co_conf, co_bbox, co_ev = get_field_info("country_of_origin")
        if not co_val or co_stat == "MISSING":
            violations.append({
                "rule_code": "LM-PC-008",
                "category": "Country of Origin",
                "issue": "Country of origin / manufacture not stated on commodity.",
                "detected_value": "Not Detected",
                "expected_requirement": "Country of origin is mandatory on all packaged commodities (Rule 6(1)(f)).",
                "severity": "HIGH",
                "confidence": 0.92,
                "legal_reference": "Rule 6(1)(f), Legal Metrology (PC) Rules, 2011",
                "evidence_zone": "Origin Zone",
                "compounding_amount": 5000.0
            })
            scores["traceability_and_origin"] -= 25.0

        for k in scores:
            scores[k] = max(0.0, min(100.0, round(scores[k], 1)))

        weights = {
            "mandatory_declarations": 0.25,
            "quantity_standards": 0.25,
            "mrp_and_pricing": 0.25,
            "consumer_care": 0.15,
            "traceability_and_origin": 0.10
        }
        total_score = sum(scores[k] * weights[k] for k in weights)
        total_score = round(max(0.0, min(100.0, total_score)), 1)

        critical_count = sum(1 for v in violations if v["severity"] == "CRITICAL")
        high_count = sum(1 for v in violations if v["severity"] == "HIGH")

        if critical_count > 0 or high_count > 0:
            compliance_status = "NON_COMPLIANT"
        elif len(violations) > 0:
            compliance_status = "NEEDS_MANUAL_VERIFICATION"
        else:
            compliance_status = "COMPLIANT"

        total_compounding = sum(v.get("compounding_amount", 0.0) for v in violations)

        return {
            "compliance_status": compliance_status,
            "compliance_score": total_score,
            "score_breakdown": scores,
            "violations": violations,
            "violations_count": len(violations),
            "critical_violations": critical_count,
            "high_violations": high_count,
            "estimated_compounding_fee": total_compounding,
            "prosecution_recommended": critical_count >= 2 or total_score < 50.0
        }
