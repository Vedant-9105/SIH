import os
import cv2
import numpy as np
import time
import datetime
from pathlib import Path
import hashlib

from src.pipeline import MultiModelProductPipeline
from src.rules.compliance_engine import ComplianceEngine
from src.reports.pdf_generator import LegalMetrologyPDFGenerator
from src.database.connection import SessionLocal, Base, engine
from src.database.models import User, Store, Inspection, ExtractedDeclaration, Violation, AuditLog
from src.routers.legal_router import generate_penalty_memo, verify_evidence_hash
from src.config import UPLOAD_DIR, OUTPUT_DIR

def create_non_compliant_packaging_image() -> str:
    """
    Creates a synthetic test commodity image with deliberate statutory violations:
    1. Forbidden non-standard unit '250 GMS' (Violation of Rule 12 & Rule 6(1)(c))
    2. Missing Consumer Care Email (Violation of Rule 6(1)(n))
    3. Valid MRP Rs. 85.00 (Incl. of all taxes)
    4. Valid Batch and Mfg Date
    """
    img = np.ones((800, 600, 3), dtype=np.uint8) * 245
    
    # Outer box border
    cv2.rectangle(img, (40, 40), (560, 750), (255, 255, 255), -1)
    cv2.rectangle(img, (40, 40), (560, 750), (180, 50, 40), 3)

    # Title & Brand
    cv2.putText(img, "AMRUT PREMIUM CHANA DAL", (65, 140), cv2.FONT_HERSHEY_DUPLEX, 0.8, (20, 20, 160), 2)
    cv2.putText(img, "Unpolished Pulses & Grains", (65, 185), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (60, 60, 60), 2)

    # Non-compliant Net Qty with forbidden abbreviation 'GMS'
    cv2.putText(img, "NET QTY: 250 GMS", (65, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    # Compliant MRP
    cv2.putText(img, "MRP Rs. 85.00 (Incl. of all taxes)", (65, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)

    # Batch & Date
    cv2.putText(img, "BATCH NO: AM-2026-CH04", (65, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
    cv2.putText(img, "PKD DATE: 07/2026", (65, 430), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
    cv2.putText(img, "BEST BEFORE 12 MONTHS FROM PACKING", (65, 480), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

    # Manufacturer
    cv2.putText(img, "MFD BY: Amrut Agro Foods Pvt. Ltd.", (65, 540), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(img, "Survey 104, APMC Yard, Yeshwanthpur, Bengaluru 560022", (65, 575), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1)

    # Incomplete Consumer Care (Phone only, missing email)
    cv2.putText(img, "CONSUMER GRIEVANCE: 1800-425-9988", (65, 630), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
    cv2.putText(img, "COUNTRY OF ORIGIN: INDIA", (65, 680), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    test_path = UPLOAD_DIR / "test_non_compliant_dal.jpg"
    cv2.imwrite(str(test_path), img)
    return str(test_path)


def test_end_to_end_flow():
    print("================================================================================")
    print("      LEGAL METROLOGY COMPLIANCE ENFORCEMENT SYSTEM — E2E VERIFICATION")
    print("================================================================================")

    # --------------------------------------------------------------------------
    # STEP 1: Evidence Image Acquisition
    # --------------------------------------------------------------------------
    print("\n[STEP 1] Generating Non-Compliant Synthetic Test Commodity...")
    img_path = create_non_compliant_packaging_image()
    assert os.path.exists(img_path), "Test image creation failed."
    print(f"Evidence image generated at: {img_path}")

    # --------------------------------------------------------------------------
    # STEP 2: Phase 1 — Core AI Vision Pipeline
    # --------------------------------------------------------------------------
    print("\n[STEP 2] Executing Core AI Vision Pipeline (Detection -> Preprocessing -> OCR -> Multilingual -> Gemini)...")
    pipeline = MultiModelProductPipeline()
    ai_result = pipeline.process_image(img_path)

    print(f"Pipeline Execution Complete in {ai_result['timings']['total_ms']} ms")
    print(f"Detection Agreement: {ai_result['detection']['average_agreement']}")
    print(f"Best Preprocessing Variant: {ai_result['preprocessing']['best_variant_key']}")
    print(f"Total Fused OCR Lines: {ai_result['ocr']['total_lines']}")
    
    extracted_fields = ai_result["extracted_fields"]
    assert extracted_fields["mrp"]["value"] is not None, "MRP must be detected."
    assert extracted_fields["net_quantity"]["value"] is not None, "Net quantity must be detected."
    print("Phase 1 Core AI Pipeline validated successfully.")

    # --------------------------------------------------------------------------
    # STEP 3: Phase 2 — Rule Matching Engine
    # --------------------------------------------------------------------------
    print("\n[STEP 3] Running Statutory Rule Matching Engine (LM PCR 2011)...")
    eval_res = ComplianceEngine.evaluate(extracted_fields, category="Packaged Food")

    print(f"Compliance Status: {eval_res['compliance_status']}")
    print(f"Overall Compliance Score: {eval_res['compliance_score']}%")
    print(f"Violations Count: {eval_res['violations_count']}")
    for idx, v in enumerate(eval_res["violations"], 1):
        print(f"  [{idx}] [{v['rule_code']}] {v['issue']} (Severity: {v['severity']}, Fee: ₹{v['compounding_amount']})")

    assert eval_res["compliance_status"] == "NON_COMPLIANT", "Must be flagged NON_COMPLIANT due to deliberate violations."
    assert eval_res["violations_count"] >= 1, "At least one statutory violation must be caught."
    print("Phase 2 Rule Matching validated successfully.")

    # --------------------------------------------------------------------------
    # STEP 4: Phase 2 — Inspector Terminal Submission & DB Persistence
    # --------------------------------------------------------------------------
    print("\n[STEP 4] Simulating Inspector Terminal Submission & DB Record Creation...")
    db = SessionLocal()
    try:
        store = db.query(Store).first()
        officer = db.query(User).filter(User.role == "INSPECTOR").first()
        
        insp_num = f"INSP-2026-E2E-{int(time.time()*1000)%100000}"
        inspection = Inspection(
            inspection_number=insp_num,
            store_id=store.id,
            officer_id=officer.id,
            category="Packaged Food",
            image_path=img_path,
            compliance_status=eval_res["compliance_status"],
            compliance_score=eval_res["compliance_score"],
            score_breakdown=eval_res["score_breakdown"],
            officer_verified=True,
            verified_at=datetime.datetime.utcnow(),
            compounding_fee=eval_res["estimated_compounding_fee"],
            supervisor_status="PENDING"
        )
        db.add(inspection)
        db.commit()
        db.refresh(inspection)

        # Save extracted declarations
        for f_key, f_data in extracted_fields.items():
            dec = ExtractedDeclaration(
                inspection_id=inspection.id,
                field_name=f_key,
                detected_value=str(f_data.get("value")),
                normalized_value=str(f_data.get("normalized_value") or f_data.get("value")),
                is_present=f_data.get("status") != "MISSING",
                confidence=float(f_data.get("confidence", 0.95))
            )
            db.add(dec)

        # Save violations
        for v in eval_res["violations"]:
            viol = Violation(
                inspection_id=inspection.id,
                rule_code=v["rule_code"],
                category=v["category"],
                issue=v["issue"],
                expected_requirement=v["expected_requirement"],
                detected_value=str(v.get("detected_value")),
                severity=v["severity"],
                legal_reference=v["legal_reference"],
                compounding_amount=v["compounding_amount"]
            )
            db.add(viol)

        # Save audit log
        audit = AuditLog(
            officer_id=officer.id,
            officer_name=officer.full_name,
            action="INSPECTION_SUBMITTED_AND_VERIFIED",
            target_type="INSPECTION",
            target_id=insp_num
        )
        db.add(audit)
        db.commit()
        print(f"Inspection {insp_num} saved to database with ID: {inspection.id}")

        # --------------------------------------------------------------------------
        # STEP 5: Phase 2 — Official PDF Inspection Report Generation
        # --------------------------------------------------------------------------
        print("\n[STEP 5] Generating Official Government Form I Inspection Memo (PDF)...")
        report_data = {
            "inspection_number": insp_num,
            "product_name": extracted_fields.get("product_name", {}).get("value") or "Chana Dal",
            "category": "Packaged Food",
            "compliance_score": eval_res["compliance_score"],
            "compliance_status": eval_res["compliance_status"],
            "overall_confidence": 0.96,
            "store": {
                "store_name": store.store_name,
                "store_code": store.store_code,
                "gstin": store.gstin,
                "address": store.address,
                "city": store.city,
                "gps_lat": store.gps_lat,
                "gps_lng": store.gps_lng
            },
            "officer": {
                "full_name": officer.full_name,
                "officer_id": officer.officer_id,
                "designation": officer.designation
            },
            "extracted_fields": extracted_fields,
            "violations": eval_res["violations"],
            "estimated_compounding_fee": eval_res["estimated_compounding_fee"],
            "prosecution_recommended": eval_res["prosecution_recommended"]
        }
        pdf_file = LegalMetrologyPDFGenerator.generate_inspection_report(report_data)
        assert os.path.exists(pdf_file), "PDF file was not created."
        assert os.path.getsize(pdf_file) > 1000, "PDF file is suspiciously small."
        print(f"Official PDF generated at: {pdf_file} (Size: {os.path.getsize(pdf_file)} bytes)")

        # --------------------------------------------------------------------------
        # STEP 6: Phase 3 — Supervisor Adjudication
        # --------------------------------------------------------------------------
        print("\n[STEP 6] Simulating Supervisor Review & Compounding Order...")
        inspection.supervisor_status = "COMPOUNDED"
        inspection.supervisor_notes = "Compounding composition authorized under Section 48."
        db.commit()
        print(f"Supervisor status updated to: {inspection.supervisor_status}")

        # --------------------------------------------------------------------------
        # STEP 7: Phase 4 — Legal Validation & Chain of Custody
        # --------------------------------------------------------------------------
        print("\n[STEP 7] Generating Section 36 Penalty Memo & Verifying Cryptographic Hash...")
        penalty_memo = generate_penalty_memo(inspection.id, db)
        assert "BEFORE THE CONTROLLER" in penalty_memo["formal_legal_notice"], "Legal notice text should contain standard formal header."
        assert penalty_memo["total_compounding_fee"] > 0, "Compounding fee should be > 0."
        print(f"Section 36 Legal Memo Generated with {len(penalty_memo['violations_summary'])} charges.")

        # Test tamper check
        sha_check = verify_evidence_hash({
            "sha256_hash": hashlib.sha256(open(pdf_file, 'rb').read()).hexdigest(),
            "evidence_string": open(pdf_file, 'rb').read().decode('latin1')
        })
        assert sha_check["is_tamper_free"] is True, "Evidence SHA-256 hash must match."
        print(f"Chain of Custody Check: {sha_check['integrity_status']} (SHA-256: {sha_check['computed_sha256'][:24]}...)")

    finally:
        db.close()

    print("\n================================================================================")
    print("      ALL 4 PHASES END-TO-END FLOW VALIDATED WITH 100% SUCCESS!")
    print("================================================================================")


if __name__ == "__main__":
    test_end_to_end_flow()
