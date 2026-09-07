import os
import shutil
import time
import uuid
import hashlib
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import (
    User, Store, Product, Rule, Inspection, ExtractedDeclaration, Violation, InspectionEvidence, AuditLog
)
from src.rules.compliance_engine import ComplianceEngine
from src.reports.pdf_generator import LegalMetrologyPDFGenerator
from src.config import UPLOAD_DIR, OUTPUT_DIR

router = APIRouter(prefix="/api/inspections", tags=["Inspections"])

# Lazy pipeline accessor to share with app.py
def get_pipeline():
    from app import get_pipeline as app_get_pipeline
    return app_get_pipeline()


@router.get("")
def list_inspections(
    status: Optional[str] = None,
    officer_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(Inspection)
    if status and status != "ALL":
        query = query.filter(Inspection.compliance_status == status)
    if officer_id:
        user = db.query(User).filter(User.officer_id == officer_id).first()
        if user:
            query = query.filter(Inspection.officer_id == user.id)
    
    inspections = query.order_by(Inspection.created_at.desc()).limit(limit).all()
    
    results = []
    for ins in inspections:
        store_name = ins.store.store_name if ins.store else "Unassigned Store"
        officer_name = ins.officer.full_name if ins.officer else "Inspector"
        viol_count = len(ins.violations)
        results.append({
            "id": ins.id,
            "inspection_number": ins.inspection_number,
            "store_name": store_name,
            "category": ins.category,
            "officer_name": officer_name,
            "compliance_status": ins.compliance_status,
            "compliance_score": ins.compliance_score,
            "violations_count": viol_count,
            "officer_verified": ins.officer_verified,
            "supervisor_status": ins.supervisor_status,
            "inspection_date": ins.inspection_date.strftime("%Y-%m-%d %H:%M"),
            "image_url": ins.evidence_image_path or ins.image_path,
            "sync_status": ins.sync_status
        })
    return results


@router.get("/{inspection_id}")
def get_inspection_detail(inspection_id: int, db: Session = Depends(get_db)):
    ins = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not ins:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    store_data = {
        "id": ins.store.id if ins.store else None,
        "store_code": ins.store.store_code if ins.store else "",
        "store_name": ins.store.store_name if ins.store else "Retail Establishment",
        "gstin": ins.store.gstin if ins.store else "",
        "fssai": ins.store.fssai_license if ins.store else "",
        "address": ins.store.address if ins.store else "",
        "city": ins.store.city if ins.store else "",
        "gps_lat": ins.store.gps_lat if ins.store else 12.9716,
        "gps_lng": ins.store.gps_lng if ins.store else 77.5946
    } if ins.store else {}

    officer_data = {
        "id": ins.officer.id if ins.officer else None,
        "officer_id": ins.officer.officer_id if ins.officer else "",
        "full_name": ins.officer.full_name if ins.officer else "Inspector",
        "designation": ins.officer.designation if ins.officer else "Legal Metrology Officer"
    } if ins.officer else {}

    decs = []
    for d in ins.declarations:
        decs.append({
            "id": d.id,
            "field_name": d.field_name,
            "detected_value": d.detected_value,
            "normalized_value": d.normalized_value,
            "unit": d.unit,
            "is_present": d.is_present,
            "confidence": d.confidence,
            "readability_status": d.readability_status,
            "raw_bounding_box": d.raw_bounding_box,
            "is_officer_edited": d.is_officer_edited,
            "officer_notes": d.officer_notes
        })

    viols = []
    for v in ins.violations:
        viols.append({
            "id": v.id,
            "rule_code": v.rule_code,
            "category": v.category,
            "issue": v.issue,
            "expected_requirement": v.expected_requirement,
            "detected_value": v.detected_value,
            "severity": v.severity,
            "confidence": v.confidence,
            "legal_reference": v.legal_reference,
            "compounding_amount": v.compounding_amount,
            "status": v.status
        })

    return {
        "id": ins.id,
        "inspection_number": ins.inspection_number,
        "store": store_data,
        "officer": officer_data,
        "category": ins.category,
        "compliance_status": ins.compliance_status,
        "compliance_score": ins.compliance_score,
        "score_breakdown": ins.score_breakdown,
        "inspection_date": ins.inspection_date.strftime("%Y-%m-%d %H:%M"),
        "remarks": ins.remarks,
        "officer_verified": ins.officer_verified,
        "verified_at": ins.verified_at.strftime("%Y-%m-%d %H:%M") if ins.verified_at else None,
        "supervisor_status": ins.supervisor_status,
        "compounding_fee": ins.compounding_fee,
        "image_path": ins.image_path,
        "evidence_image_path": ins.evidence_image_path,
        "sha256_hash": ins.sha256_hash,
        "sync_status": ins.sync_status,
        "declarations": decs,
        "violations": viols
    }


@router.post("/analyze-evidence")
async def analyze_evidence_image(file: UploadFile = File(...)):
    """
    Runs Core AI Vision Pipeline (Detection -> Preprocessing -> OCR -> Multilingual -> Gemini)
    and evaluates Legal Metrology Rules for real-time Inspector preview.
    """
    if file.content_type and not (file.content_type.startswith("image/") or file.content_type == "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a valid image.")

    clean_filename = os.path.basename(file.filename or "evidence.jpg")
    filename = f"field_evidence_{int(time.time()*1000)}_{clean_filename}"
    file_path = UPLOAD_DIR / filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        pipeline = get_pipeline()
        ai_result = pipeline.process_image(str(file_path))
        extracted_fields = ai_result["extracted_fields"]

        # Run statutory rule compliance evaluation
        compliance_eval = ComplianceEngine.evaluate(extracted_fields)

        return {
            "evidence_image_url": f"/uploads/{filename}",
            "crop_image_url": ai_result["detection"]["crop_image_url"],
            "detection": ai_result["detection"],
            "preprocessing": ai_result["preprocessing"],
            "ocr": ai_result["ocr"],
            "gemini_validation": ai_result.get("gemini_validation"),
            "extracted_fields": extracted_fields,
            "compliance_evaluation": compliance_eval,
            "timings": ai_result["timings"]
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI Vision Pipeline error: {str(e)}")


@router.post("")
def create_inspection(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Finalizes inspection record in database, applies compliance rules, logs audit trail,
    and produces official GoI PDF Inspection Memo.
    """
    store_id = payload.get("store_id")
    officer_id_str = payload.get("officer_id", "LMO001")
    category = payload.get("category", "Packaged Commodity")
    image_url = payload.get("image_url", "")
    evidence_image_url = payload.get("evidence_image_url", image_url)
    extracted_fields = payload.get("extracted_fields", {})
    remarks = payload.get("remarks", "AI-assisted field inspection screening.")
    officer_verified = payload.get("officer_verified", False)

    # 1. Resolve officer
    officer = db.query(User).filter(User.officer_id == officer_id_str).first()
    if not officer:
        officer = db.query(User).filter(User.role == "INSPECTOR").first()
    officer_db_id = officer.id if officer else 1

    # 2. Resolve store
    store = None
    if store_id:
        store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        store_name = payload.get("store_name", "General Retail Store")
        store = Store(
            store_code=f"STR-{uuid.uuid4().hex[:6].upper()}",
            store_name=store_name,
            address=payload.get("store_address", "Market Area, Bengaluru"),
            city="Bengaluru",
            state="Karnataka",
            pincode="560001",
            gps_lat=payload.get("gps_lat", 12.9716),
            gps_lng=payload.get("gps_lng", 77.5946)
        )
        db.add(store)
        db.commit()
        db.refresh(store)

    # 3. Evaluate Compliance Rules
    eval_res = ComplianceEngine.evaluate(extracted_fields, category=category)
    insp_num = f"INSP-2026-{uuid.uuid4().hex[:6].upper()}"

    # Calculate SHA-256 fingerprint for chain of custody
    sha_str = f"{insp_num}|{store.store_code}|{eval_res['compliance_score']}|{eval_res['violations_count']}"
    sha_hash = hashlib.sha256(sha_str.encode()).hexdigest()

    # 4. Create Inspection Record
    inspection = Inspection(
        inspection_number=insp_num,
        store_id=store.id,
        officer_id=officer_db_id,
        category=category,
        image_path=image_url,
        evidence_image_path=evidence_image_url,
        compliance_status=eval_res["compliance_status"],
        compliance_score=eval_res["compliance_score"],
        score_breakdown=eval_res["score_breakdown"],
        inspection_date=datetime.datetime.utcnow(),
        remarks=remarks,
        officer_verified=officer_verified,
        verified_at=datetime.datetime.utcnow() if officer_verified else None,
        supervisor_status="PENDING",
        compounding_fee=eval_res["estimated_compounding_fee"],
        sync_status="SYNCED",
        sha256_hash=sha_hash
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)

    # 5. Save Extracted Declarations
    for f_name, f_data in extracted_fields.items():
        if isinstance(f_data, dict):
            dec = ExtractedDeclaration(
                inspection_id=inspection.id,
                field_name=f_name,
                detected_value=str(f_data.get("value")) if f_data.get("value") is not None else None,
                normalized_value=str(f_data.get("normalized_value") or f_data.get("value")),
                unit=f_data.get("unit"),
                is_present=f_data.get("status") != "MISSING",
                confidence=float(f_data.get("confidence", 0.90)),
                readability_status="PASS" if f_data.get("confidence", 0) > 0.6 else "FLAGGED",
                raw_bounding_box=f_data.get("bounding_box"),
                is_officer_edited=f_data.get("is_officer_edited", False),
                officer_notes=f_data.get("officer_notes")
            )
            db.add(dec)

    # 6. Save Violations
    for v in eval_res["violations"]:
        rule_obj = db.query(Rule).filter(Rule.rule_code == v.get("rule_code")).first()
        viol = Violation(
            inspection_id=inspection.id,
            rule_id=rule_obj.id if rule_obj else None,
            rule_code=v.get("rule_code", "LM-PC"),
            category=v.get("category", "Packaging"),
            issue=v.get("issue", "Violation"),
            expected_requirement=v.get("expected_requirement", ""),
            detected_value=str(v.get("detected_value", "")),
            severity=v.get("severity", "HIGH"),
            confidence=float(v.get("confidence", 0.95)),
            legal_reference=v.get("legal_reference", "LM PCR 2011"),
            evidence_zone=v.get("evidence_zone", "Packaging Panel"),
            compounding_amount=float(v.get("compounding_amount", 5000.0)),
            status="OPEN"
        )
        db.add(viol)

    # 7. Audit Log
    audit = AuditLog(
        officer_id=officer_db_id,
        officer_name=officer.full_name if officer else "Inspector",
        action="INSPECTION_CREATED",
        target_type="INSPECTION",
        target_id=insp_num,
        details={
            "score": eval_res["compliance_score"],
            "status": eval_res["compliance_status"],
            "violations_count": eval_res["violations_count"]
        }
    )
    db.add(audit)
    db.commit()

    # 8. Generate Official PDF Report
    report_dict = {
        "inspection_number": insp_num,
        "product_name": extracted_fields.get("product_name", {}).get("value") or "Packaged Commodity",
        "category": category,
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
            "full_name": officer.full_name if officer else "Inspector",
            "officer_id": officer.officer_id if officer else "LMO001",
            "designation": officer.designation if officer else "Legal Metrology Officer"
        },
        "extracted_fields": extracted_fields,
        "violations": eval_res["violations"],
        "estimated_compounding_fee": eval_res["estimated_compounding_fee"],
        "prosecution_recommended": eval_res["prosecution_recommended"]
    }

    pdf_filename = f"Inspection_Report_{insp_num}.pdf"
    LegalMetrologyPDFGenerator.generate_inspection_report(report_dict, output_filename=pdf_filename)

    return {
        "inspection_id": inspection.id,
        "inspection_number": insp_num,
        "compliance_status": eval_res["compliance_status"],
        "compliance_score": eval_res["compliance_score"],
        "violations_count": eval_res["violations_count"],
        "report_url": f"/outputs/reports/{pdf_filename}",
        "sha256_hash": sha_hash
    }


@router.put("/{inspection_id}/verify")
def verify_inspection(
    inspection_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Inspector side-by-side human review submission:
    Updates edited fields, marks officer_verified = True, recalculates score, and updates audit trail.
    """
    ins = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not ins:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    edited_fields = payload.get("edited_fields", {})
    remarks = payload.get("remarks")

    # Update declarations with inspector edits
    for dec in ins.declarations:
        if dec.field_name in edited_fields:
            edit_val = edited_fields[dec.field_name]
            if edit_val != dec.detected_value:
                dec.detected_value = edit_val
                dec.normalized_value = edit_val
                dec.is_officer_edited = True
                dec.confidence = 1.0  # Verified by officer

    ins.officer_verified = True
    ins.verified_at = datetime.datetime.utcnow()
    if remarks:
        ins.remarks = remarks

    # Recalculate compliance with updated fields
    current_fields_dict = {
        d.field_name: {
            "value": d.detected_value,
            "raw_text": d.detected_value,
            "status": "CONFIRMED" if d.detected_value else "MISSING",
            "confidence": d.confidence
        }
        for d in ins.declarations
    }
    re_eval = ComplianceEngine.evaluate(current_fields_dict)
    ins.compliance_status = re_eval["compliance_status"]
    ins.compliance_score = re_eval["compliance_score"]
    ins.score_breakdown = re_eval["score_breakdown"]
    ins.compounding_fee = re_eval["estimated_compounding_fee"]

    # Audit log
    audit = AuditLog(
        officer_id=ins.officer_id,
        officer_name=ins.officer.full_name if ins.officer else "Inspector",
        action="INSPECTION_OFFICER_VERIFIED",
        target_type="INSPECTION",
        target_id=ins.inspection_number,
        details={"edited_fields": list(edited_fields.keys()), "new_score": re_eval["compliance_score"]}
    )
    db.add(audit)
    db.commit()

    # Re-generate PDF with verified stamp
    pdf_filename = f"Inspection_Report_{ins.inspection_number}.pdf"
    report_dict = {
        "inspection_number": ins.inspection_number,
        "product_name": current_fields_dict.get("product_name", {}).get("value") or "Packaged Commodity",
        "category": ins.category,
        "compliance_score": re_eval["compliance_score"],
        "compliance_status": re_eval["compliance_status"],
        "overall_confidence": 1.0,
        "store": {
            "store_name": ins.store.store_name if ins.store else "",
            "store_code": ins.store.store_code if ins.store else "",
            "gstin": ins.store.gstin if ins.store else "",
            "address": ins.store.address if ins.store else "",
            "city": ins.store.city if ins.store else "",
            "gps_lat": ins.store.gps_lat if ins.store else 12.9716,
            "gps_lng": ins.store.gps_lng if ins.store else 77.5946
        },
        "officer": {
            "full_name": ins.officer.full_name if ins.officer else "",
            "officer_id": ins.officer.officer_id if ins.officer else "",
            "designation": ins.officer.designation if ins.officer else ""
        },
        "extracted_fields": current_fields_dict,
        "violations": re_eval["violations"],
        "estimated_compounding_fee": re_eval["estimated_compounding_fee"],
        "prosecution_recommended": re_eval["prosecution_recommended"]
    }
    LegalMetrologyPDFGenerator.generate_inspection_report(report_dict, output_filename=pdf_filename)

    return {
        "message": "Inspection successfully verified by Legal Metrology Officer.",
        "compliance_score": ins.compliance_score,
        "compliance_status": ins.compliance_status,
        "report_url": f"/outputs/reports/{pdf_filename}"
    }


@router.get("/{inspection_id}/report")
def download_inspection_report(inspection_id: int, db: Session = Depends(get_db)):
    ins = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not ins:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    pdf_filename = f"Inspection_Report_{ins.inspection_number}.pdf"
    pdf_path = OUTPUT_DIR / "reports" / pdf_filename
    if not pdf_path.exists():
        # Generate on the fly
        fields_dict = {
            d.field_name: {
                "value": d.detected_value,
                "raw_text": d.detected_value,
                "status": "CONFIRMED" if d.detected_value else "MISSING",
                "confidence": d.confidence
            }
            for d in ins.declarations
        }
        report_dict = {
            "inspection_number": ins.inspection_number,
            "product_name": fields_dict.get("product_name", {}).get("value") or "Packaged Commodity",
            "category": ins.category,
            "compliance_score": ins.compliance_score,
            "compliance_status": ins.compliance_status,
            "overall_confidence": 0.95,
            "store": {
                "store_name": ins.store.store_name if ins.store else "",
                "store_code": ins.store.store_code if ins.store else "",
                "gstin": ins.store.gstin if ins.store else "",
                "address": ins.store.address if ins.store else "",
                "city": ins.store.city if ins.store else "",
                "gps_lat": ins.store.gps_lat if ins.store else 12.9716,
                "gps_lng": ins.store.gps_lng if ins.store else 77.5946
            },
            "officer": {
                "full_name": ins.officer.full_name if ins.officer else "",
                "officer_id": ins.officer.officer_id if ins.officer else "",
                "designation": ins.officer.designation if ins.officer else ""
            },
            "extracted_fields": fields_dict,
            "violations": [
                {
                    "rule_code": v.rule_code,
                    "legal_reference": v.legal_reference,
                    "issue": v.issue,
                    "severity": v.severity,
                    "compounding_amount": v.compounding_amount
                }
                for v in ins.violations
            ],
            "estimated_compounding_fee": ins.compounding_fee
        }
        LegalMetrologyPDFGenerator.generate_inspection_report(report_dict, output_filename=pdf_filename)

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=pdf_filename
    )


@router.post("/sync")
def sync_offline_inspections(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Offline Synchronization Endpoint.
    Accepts an array of cached offline inspections, persists them to SQLite,
    evaluates rules, generates reports, and returns synced IDs.
    """
    offline_items = payload.get("inspections", [])
    synced_ids = []

    for item in offline_items:
        try:
            res = create_inspection(item, db)
            synced_ids.append({
                "offline_client_id": item.get("offline_id"),
                "server_inspection_number": res["inspection_number"],
                "status": "SYNCED"
            })
        except Exception as e:
            synced_ids.append({
                "offline_client_id": item.get("offline_id"),
                "error": str(e),
                "status": "FAILED"
            })

    return {
        "synced_count": len([s for s in synced_ids if s["status"] == "SYNCED"]),
        "total_attempted": len(offline_items),
        "results": synced_ids
    }
