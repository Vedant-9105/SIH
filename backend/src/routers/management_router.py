import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.connection import get_db
from src.database.models import (
    User, Store, Product, Rule, Inspection, ExtractedDeclaration, Violation, AuditLog
)

router = APIRouter(prefix="/api", tags=["Management & Admin"])


# ==============================================================================
# SUPERVISOR TERMINAL ENDPOINTS
# ==============================================================================

@router.get("/supervisor/inspections")
def get_supervisor_inspections(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(Inspection)
    if status and status != "ALL":
        query = query.filter(Inspection.supervisor_status == status)
    
    inspections = query.order_by(Inspection.created_at.desc()).limit(limit).all()
    results = []
    for ins in inspections:
        store_name = ins.store.store_name if ins.store else "Unassigned Store"
        officer_name = ins.officer.full_name if ins.officer else "Inspector"
        assigned_name = ins.assigned_officer.full_name if ins.assigned_officer else None
        results.append({
            "id": ins.id,
            "inspection_number": ins.inspection_number,
            "store_name": store_name,
            "category": ins.category,
            "officer_name": officer_name,
            "assigned_officer": assigned_name,
            "compliance_status": ins.compliance_status,
            "compliance_score": ins.compliance_score,
            "violations_count": len(ins.violations),
            "supervisor_status": ins.supervisor_status,
            "compounding_fee": ins.compounding_fee,
            "officer_verified": ins.officer_verified,
            "inspection_date": ins.inspection_date.strftime("%Y-%m-%d %H:%M"),
            "image_url": ins.evidence_image_path or ins.image_path
        })
    return results


@router.post("/supervisor/assign")
def assign_inspection(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """Assigns an inspection or store audit task to an LMO with deadline."""
    store_id = payload.get("store_id")
    officer_id = payload.get("officer_id")
    category = payload.get("category", "Packaged Food / Retail")
    notes = payload.get("notes", "Routine Market Surveillance Audit")

    officer = db.query(User).filter(User.id == officer_id).first()
    if not officer:
        raise HTTPException(status_code=404, detail="Assigned officer not found.")

    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store premises not found.")

    insp_num = f"TASK-{int(datetime.datetime.utcnow().timestamp())}"
    task = Inspection(
        inspection_number=insp_num,
        store_id=store.id,
        officer_id=officer.id,
        assigned_to_id=officer.id,
        category=category,
        image_path="",
        compliance_status="PENDING_AUDIT",
        compliance_score=0.0,
        remarks=notes,
        supervisor_status="ASSIGNED",
        inspection_date=datetime.datetime.utcnow()
    )
    db.add(task)
    db.commit()

    # Audit Log
    audit = AuditLog(
        officer_name="Supervisor",
        action="INSPECTION_ASSIGNED",
        target_type="INSPECTION",
        target_id=insp_num,
        details={"assigned_to": officer.full_name, "store": store.store_name}
    )
    db.add(audit)
    db.commit()

    return {"message": f"Audit {insp_num} successfully assigned to {officer.full_name}.", "task_id": task.id}


@router.post("/supervisor/adjudicate/{inspection_id}")
def adjudicate_inspection(
    inspection_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Supervisor Adjudication:
    Action options:
    - 'APPROVE_COMPLIANT': Mark approved as compliant
    - 'ISSUE_COMPOUNDING_NOTICE': Issue Sec 48 compounding notice with agreed fee
    - 'REFER_FOR_PROSECUTION': Recommend Sec 36 Judicial prosecution
    """
    ins = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not ins:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    action = payload.get("action", "APPROVE_COMPLIANT")
    notes = payload.get("notes", "")
    compounding_fee = payload.get("compounding_fee", ins.compounding_fee)

    if action == "ISSUE_COMPOUNDING_NOTICE":
        ins.supervisor_status = "COMPOUNDED"
        ins.compounding_fee = compounding_fee
    elif action == "REFER_FOR_PROSECUTION":
        ins.supervisor_status = "REFERRED_FOR_PROSECUTION"
    else:
        ins.supervisor_status = "APPROVED"

    ins.supervisor_notes = notes

    # Audit Log
    audit = AuditLog(
        officer_name="Supervisor",
        action=f"SUPERVISOR_{action}",
        target_type="INSPECTION",
        target_id=ins.inspection_number,
        details={"action": action, "notes": notes, "compounding_fee": ins.compounding_fee}
    )
    db.add(audit)
    db.commit()

    return {
        "message": f"Inspection {ins.inspection_number} adjudicated with status: {ins.supervisor_status}.",
        "supervisor_status": ins.supervisor_status,
        "compounding_fee": ins.compounding_fee
    }


# ==============================================================================
# ADMIN & ANALYTICS ENDPOINTS
# ==============================================================================

@router.get("/admin/analytics")
def get_analytics(db: Session = Depends(get_db)):
    total_inspections = db.query(Inspection).count()
    compliant_count = db.query(Inspection).filter(Inspection.compliance_status == "COMPLIANT").count()
    non_compliant_count = db.query(Inspection).filter(Inspection.compliance_status == "NON_COMPLIANT").count()
    flagged_count = db.query(Inspection).filter(Inspection.compliance_status == "NEEDS_MANUAL_VERIFICATION").count()
    
    compliance_rate = round((compliant_count / total_inspections * 100), 1) if total_inspections > 0 else 100.0

    # Violations by severity
    crit_viols = db.query(Violation).filter(Violation.severity == "CRITICAL").count()
    high_viols = db.query(Violation).filter(Violation.severity == "HIGH").count()
    med_viols = db.query(Violation).filter(Violation.severity == "MEDIUM").count()

    # Top violated rules
    top_rules_raw = db.query(
        Violation.rule_code, Violation.category, func.count(Violation.id).label("count")
    ).group_by(Violation.rule_code).order_by(func.count(Violation.id).desc()).limit(5).all()

    top_rules = [{"rule_code": r[0], "category": r[1], "count": r[2]} for r in top_rules_raw]

    # Total compounding penalty accrued
    total_penalties = db.query(func.sum(Inspection.compounding_fee)).scalar() or 0.0

    return {
        "total_inspections": total_inspections,
        "compliant_count": compliant_count,
        "non_compliant_count": non_compliant_count,
        "flagged_count": flagged_count,
        "compliance_rate": compliance_rate,
        "severity_breakdown": {
            "critical": crit_viols,
            "high": high_viols,
            "medium": med_viols
        },
        "top_violated_rules": top_rules,
        "total_penalties_accrued": round(float(total_penalties), 2)
    }


@router.get("/admin/rules")
def get_rules(db: Session = Depends(get_db)):
    rules = db.query(Rule).order_by(Rule.rule_code.asc()).all()
    return [
        {
            "id": r.id,
            "rule_code": r.rule_code,
            "category": r.category,
            "description": r.description,
            "legal_reference": r.legal_reference,
            "requirement_text": r.requirement_text,
            "severity": r.severity,
            "weight": r.weight,
            "is_active": r.is_active
        }
        for r in rules
    ]


@router.put("/admin/rules/{rule_id}")
def update_rule(
    rule_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")

    if "severity" in payload:
        rule.severity = payload["severity"]
    if "weight" in payload:
        rule.weight = float(payload["weight"])
    if "is_active" in payload:
        rule.is_active = bool(payload["is_active"])

    db.commit()

    # Audit Log
    audit = AuditLog(
        officer_name="Admin",
        action="RULE_UPDATED",
        target_type="RULE",
        target_id=rule.rule_code,
        details=payload
    )
    db.add(audit)
    db.commit()

    return {"message": f"Rule {rule.rule_code} updated successfully."}


@router.get("/admin/audit-logs")
def get_audit_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "officer_name": l.officer_name,
            "action": l.action,
            "target_type": l.target_type,
            "target_id": l.target_id,
            "details": l.details,
            "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }
        for l in logs
    ]


@router.get("/stores")
def list_stores(db: Session = Depends(get_db)):
    stores = db.query(Store).order_by(Store.store_name.asc()).all()
    return [
        {
            "id": s.id,
            "store_code": s.store_code,
            "store_name": s.store_name,
            "owner_name": s.owner_name,
            "gstin": s.gstin,
            "fssai": s.fssai_license,
            "address": s.address,
            "city": s.city,
            "state": s.state,
            "pincode": s.pincode,
            "gps_lat": s.gps_lat,
            "gps_lng": s.gps_lng
        }
        for s in stores
    ]


@router.post("/stores")
def create_store(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    import uuid
    store = Store(
        store_code=f"STR-{uuid.uuid4().hex[:6].upper()}",
        store_name=payload.get("store_name", "Retail Store"),
        owner_name=payload.get("owner_name"),
        gstin=payload.get("gstin"),
        fssai_license=payload.get("fssai"),
        address=payload.get("address", "Market Area"),
        city=payload.get("city", "Bengaluru"),
        state=payload.get("state", "Karnataka"),
        pincode=payload.get("pincode", "560001"),
        gps_lat=float(payload.get("gps_lat", 12.9716)),
        gps_lng=float(payload.get("gps_lng", 77.5946))
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return {"message": "Store created successfully.", "store": {"id": store.id, "store_name": store.store_name}}


@router.get("/users")
def list_users(role: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    users = query.all()
    return [
        {
            "id": u.id,
            "officer_id": u.officer_id,
            "full_name": u.full_name,
            "designation": u.designation,
            "email": u.email,
            "role": u.role
        }
        for u in users
    ]
