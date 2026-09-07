import datetime
from sqlalchemy.orm import Session
from src.database.models import User, Store, Rule, Product

def seed_database(db: Session):
    # 1. Seed Users if not present
    if db.query(User).count() == 0:
        users = [
            User(officer_id='LMO001', full_name='Rajesh Kumar', designation='Legal Metrology Inspector', email='lmo001@legalmetrology.gov.in', role='INSPECTOR'),
            User(officer_id='LMO002', full_name='Snehal Patil', designation='Legal Metrology Inspector', email='lmo002@legalmetrology.gov.in', role='INSPECTOR'),
            User(officer_id='SUP001', full_name='Sunita Sharma', designation='Assistant Controller of Legal Metrology', email='sup001@legalmetrology.gov.in', role='SUPERVISOR'),
            User(officer_id='ADM001', full_name='Vikram Malhotra', designation='Chief Enforcement Administrator', email='adm001@legalmetrology.gov.in', role='ADMIN'),
            User(officer_id='LEG001', full_name='Adv. Meenakshi Rao', designation='Senior Legal & Compliance Advisor', email='leg001@legalmetrology.gov.in', role='LEGAL_REVIEWER')
        ]
        db.add_all(users)
        db.commit()

    # 2. Seed Stores if not present
    if db.query(Store).count() == 0:
        stores = [
            Store(store_code='STR-BLR-001', store_name='Daily Needs Supermarket', owner_name='Ramesh Gupta', gstin='29ABCDE1234F1Z5', fssai_license='11223344556677', address='No 14, 100 Feet Road, Indiranagar', city='Bengaluru', state='Karnataka', pincode='560038', gps_lat=12.9716, gps_lng=77.5946),
            Store(store_code='STR-BLR-002', store_name='Krishna Provision & General Store', owner_name='K. Venkat', gstin='29XYZAB5678C1Z2', fssai_license='21223344556688', address='Shop 5, Market Road, Malleshwaram', city='Bengaluru', state='Karnataka', pincode='560003', gps_lat=13.0031, gps_lng=77.5643),
            Store(store_code='STR-MUM-001', store_name='Metro HyperMart Kurla', owner_name='Metro Retail Ltd', gstin='27AAACM1234A1Z1', fssai_license='11520023000456', address='LBS Marg, Kurla West', city='Mumbai', state='Maharashtra', pincode='400070', gps_lat=19.0688, gps_lng=72.8700),
            Store(store_code='STR-DEL-001', store_name='Apex E-Commerce Fulfillment Hub', owner_name='Apex Logistics', gstin='07AABCA5678B1Z9', fssai_license='13321005000789', address='Plot 88, Okhla Phase 3', city='New Delhi', state='Delhi', pincode='110020', gps_lat=28.5355, gps_lng=77.2732)
        ]
        db.add_all(stores)
        db.commit()

    # 3. Seed Statutory Rules (LM PCR 2011) if not present
    if db.query(Rule).count() == 0:
        rules = [
            Rule(
                rule_code='LM-PC-001',
                category='Product Identification',
                description='Generic or common name of commodity must be prominently declared on principal display panel.',
                legal_reference='Rule 6(1)(a), Legal Metrology (Packaged Commodities) Rules, 2011',
                requirement_text='The common or generic names of the commodity contained in the package must be legible and distinct.',
                validation_type='TEXT_PRESENCE',
                severity='CRITICAL',
                weight=15.0
            ),
            Rule(
                rule_code='LM-PC-002',
                category='Manufacturer Details',
                description='Name and complete address of the manufacturer, packer or importer must be clearly declared.',
                legal_reference='Rule 6(1)(b), Legal Metrology (Packaged Commodities) Rules, 2011',
                requirement_text='Name and factory/registered office address of manufacturer or packer must be stated.',
                validation_type='TEXT_PRESENCE',
                severity='HIGH',
                weight=15.0
            ),
            Rule(
                rule_code='LM-PC-003',
                category='Manufacturer Address',
                description='Complete address must include street, city, state and PIN code to guarantee consumer traceability.',
                legal_reference='Rule 6(1)(b), Legal Metrology (Packaged Commodities) Rules, 2011',
                requirement_text='Address must not be vague or abbreviated; must provide full contact traceability.',
                validation_type='PATTERN',
                severity='HIGH',
                weight=10.0
            ),
            Rule(
                rule_code='LM-PC-004',
                category='Net Quantity & Standard Units',
                description='Net quantity must be declared in standardized SI units (g, kg, ml, l). Forbidden: gm, gms, ltrs, kilos.',
                legal_reference='Rule 6(1)(c) & Rule 12, Legal Metrology (Packaged Commodities) Rules, 2011',
                requirement_text='Standard units of weight/measure must follow strict legal symbols without colloquial suffixes.',
                validation_type='PATTERN',
                severity='CRITICAL',
                weight=20.0
            ),
            Rule(
                rule_code='LM-PC-005',
                category='MRP Declaration',
                description='Maximum Retail Price (MRP) must be clearly stated and must include (Inclusive of all taxes).',
                legal_reference='Rule 6(1)(e), Legal Metrology (Packaged Commodities) Rules, 2011',
                requirement_text='MRP declaration must include the exact phrase (inclusive of all taxes) or (incl. of all taxes).',
                validation_type='PATTERN',
                severity='CRITICAL',
                weight=15.0
            ),
            Rule(
                rule_code='LM-PC-006',
                category='Manufacturing Date',
                description='Month and year in which commodity is manufactured, packed or imported must be declared.',
                legal_reference='Rule 6(1)(d), Legal Metrology (Packaged Commodities) Rules, 2011',
                requirement_text='Month and year must be stated in words or numerals (MM/YYYY or Month YYYY).',
                validation_type='PATTERN',
                severity='HIGH',
                weight=10.0
            ),
            Rule(
                rule_code='LM-PC-007',
                category='Consumer Care Details',
                description='Consumer grievance cell details including person name/designation, address, telephone and email must be stated.',
                legal_reference='Rule 6(1)(n), Legal Metrology (Packaged Commodities) Rules, 2011',
                requirement_text='Both a telephone helpline (or toll-free) and a valid email ID must be provided.',
                validation_type='PATTERN',
                severity='HIGH',
                weight=15.0
            ),
            Rule(
                rule_code='LM-PC-008',
                category='Country of Origin',
                description='Country of origin or manufacture must be clearly stated on all commodities.',
                legal_reference='Rule 6(1)(f), Legal Metrology (Packaged Commodities) Rules, 2011',
                requirement_text='Country of origin declaration is mandatory for domestic and imported goods alike.',
                validation_type='TEXT_PRESENCE',
                severity='HIGH',
                weight=10.0
            ),
            Rule(
                rule_code='LM-PC-009',
                category='Unit Sale Price (USP)',
                description='Unit Sale Price must be declared per g/kg or per ml/l for retail packaged commodities.',
                legal_reference='Rule 6(11), Legal Metrology (Packaged Commodities) Rules, 2011 (Amendment 2022)',
                requirement_text='Retail packages containing more than 1 unit/kg/litre must display USP rounded to two decimal places.',
                validation_type='NUMERICAL',
                severity='MEDIUM',
                weight=10.0
            ),
            Rule(
                rule_code='LM-PC-010',
                category='Readability & Font Size',
                description='Declarations must adhere to minimum numeral height standards under Schedule III and be clearly readable.',
                legal_reference='Rule 12 & Schedule III, Legal Metrology (Packaged Commodities) Rules, 2011',
                requirement_text='Contrast, font size, and layout must meet regulatory thresholds; declarations must not be smudged or hidden.',
                validation_type='READABILITY',
                severity='MEDIUM',
                weight=10.0
            )
        ]
        db.add_all(rules)
        db.commit()

if __name__ == '__main__':
    from src.database.connection import SessionLocal, Base, engine
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_database(db)
    db.close()
    print('Database created and seeded successfully!')
