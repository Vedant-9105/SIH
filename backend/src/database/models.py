import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship
from src.database.connection import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    officer_id = Column(String(50), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    designation = Column(String(100), default='Legal Metrology Officer')
    email = Column(String(100), unique=True, index=True, nullable=False)
    role = Column(String(50), default='INSPECTOR')  # INSPECTOR, SUPERVISOR, ADMIN, LEGAL_REVIEWER
    hashed_password = Column(String(255), default='admin123')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inspections = relationship('Inspection', back_populates='officer', foreign_keys='Inspection.officer_id')
    assigned_inspections = relationship('Inspection', back_populates='assigned_officer', foreign_keys='Inspection.assigned_to_id')
    audit_logs = relationship('AuditLog', back_populates='officer')


class Store(Base):
    __tablename__ = 'stores'

    id = Column(Integer, primary_key=True, index=True)
    store_code = Column(String(50), unique=True, index=True, nullable=False)
    store_name = Column(String(150), nullable=False, index=True)
    owner_name = Column(String(100), nullable=True)
    gstin = Column(String(50), nullable=True)
    fssai_license = Column(String(50), nullable=True)
    address = Column(Text, nullable=False)
    city = Column(String(100), default='Bengaluru')
    state = Column(String(100), default='Karnataka')
    pincode = Column(String(20), default='560001')
    gps_lat = Column(Float, nullable=True)
    gps_lng = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inspections = relationship('Inspection', back_populates='store')


class Product(Base):
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    manufacturer_name = Column(String(150), nullable=True)
    manufacturer_address = Column(Text, nullable=True)
    standard_mrp = Column(Float, nullable=True)
    net_quantity = Column(String(50), nullable=True)
    image_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inspections = relationship('Inspection', back_populates='product')


class Rule(Base):
    __tablename__ = 'rules'

    id = Column(Integer, primary_key=True, index=True)
    rule_code = Column(String(50), unique=True, index=True, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=False)
    legal_reference = Column(String(150), nullable=False)
    requirement_text = Column(Text, nullable=False)
    validation_type = Column(String(50), default='TEXT_PRESENCE')
    severity = Column(String(20), default='HIGH')  # CRITICAL, HIGH, MEDIUM, LOW
    weight = Column(Float, default=20.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    violations = relationship('Violation', back_populates='rule')


class Inspection(Base):
    __tablename__ = 'inspections'

    id = Column(Integer, primary_key=True, index=True)
    inspection_number = Column(String(50), unique=True, index=True, nullable=False)
    store_id = Column(Integer, ForeignKey('stores.id'), nullable=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=True)
    officer_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    assigned_to_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    category = Column(String(100), default='Packaged Commodity')
    image_path = Column(String(255), nullable=False)
    evidence_image_path = Column(String(255), nullable=True)
    
    compliance_status = Column(String(50), default='PENDING')  # COMPLIANT, NON-COMPLIANT, NEEDS_MANUAL_VERIFICATION
    compliance_score = Column(Float, default=0.0)
    score_breakdown = Column(JSON, nullable=True)
    
    inspection_date = Column(DateTime, default=datetime.datetime.utcnow)
    remarks = Column(Text, nullable=True)
    officer_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    
    supervisor_status = Column(String(50), default='PENDING')  # PENDING, APPROVED, COMPOUNDED, REFERRED_FOR_PROSECUTION
    compounding_fee = Column(Float, default=0.0)
    supervisor_notes = Column(Text, nullable=True)
    
    sync_status = Column(String(50), default='SYNCED')  # SYNCED, OFFLINE_PENDING
    sha256_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    store = relationship('Store', back_populates='inspections')
    product = relationship('Product', back_populates='inspections')
    officer = relationship('User', back_populates='inspections', foreign_keys=[officer_id])
    assigned_officer = relationship('User', back_populates='assigned_inspections', foreign_keys=[assigned_to_id])
    declarations = relationship('ExtractedDeclaration', back_populates='inspection', cascade='all, delete-orphan')
    violations = relationship('Violation', back_populates='inspection', cascade='all, delete-orphan')
    evidence_items = relationship('InspectionEvidence', back_populates='inspection', cascade='all, delete-orphan')


class ExtractedDeclaration(Base):
    __tablename__ = 'extracted_declarations'

    id = Column(Integer, primary_key=True, index=True)
    inspection_id = Column(Integer, ForeignKey('inspections.id'), nullable=False)
    field_name = Column(String(100), nullable=False)
    detected_value = Column(Text, nullable=True)
    normalized_value = Column(Text, nullable=True)
    unit = Column(String(50), nullable=True)
    is_present = Column(Boolean, default=True)
    confidence = Column(Float, default=0.90)
    readability_status = Column(String(50), default='PASS')
    raw_bounding_box = Column(JSON, nullable=True)
    is_officer_edited = Column(Boolean, default=False)
    officer_notes = Column(Text, nullable=True)

    inspection = relationship('Inspection', back_populates='declarations')


class Violation(Base):
    __tablename__ = 'violations'

    id = Column(Integer, primary_key=True, index=True)
    inspection_id = Column(Integer, ForeignKey('inspections.id'), nullable=False)
    rule_id = Column(Integer, ForeignKey('rules.id'), nullable=True)
    rule_code = Column(String(50), nullable=False)
    category = Column(String(100), nullable=False)
    issue = Column(Text, nullable=False)
    expected_requirement = Column(Text, nullable=False)
    detected_value = Column(Text, nullable=True)
    severity = Column(String(20), default='HIGH')  # CRITICAL, HIGH, MEDIUM, LOW
    confidence = Column(Float, default=0.95)
    legal_reference = Column(String(150), nullable=False)
    evidence_zone = Column(String(100), nullable=True)
    compounding_amount = Column(Float, default=5000.0)
    status = Column(String(50), default='OPEN')  # OPEN, COMPOUNDED, DISMISSED, PROSECUTED

    inspection = relationship('Inspection', back_populates='violations')
    rule = relationship('Rule', back_populates='violations')


class InspectionEvidence(Base):
    __tablename__ = 'inspection_evidence'

    id = Column(Integer, primary_key=True, index=True)
    inspection_id = Column(Integer, ForeignKey('inspections.id'), nullable=False)
    evidence_type = Column(String(50), default='PDP')  # PDP, BACK_PANEL, MRP_STAMP, BARCODE, CROP
    file_path = Column(String(255), nullable=False)
    sha256_hash = Column(String(64), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inspection = relationship('Inspection', back_populates='evidence_items')


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, index=True)
    officer_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    officer_name = Column(String(100), default='System')
    action = Column(String(100), nullable=False)  # INSPECTION_CREATED, AI_RUN, FIELD_EDITED, VERIFIED, COMPOUNDED, RULE_UPDATED
    target_type = Column(String(50), default='INSPECTION')
    target_id = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(50), default='127.0.0.1')
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    officer = relationship('User', back_populates='audit_logs')
