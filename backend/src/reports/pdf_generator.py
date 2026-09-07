import os
import hashlib
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from src.config import OUTPUT_DIR, BASE_DIR

REPORTS_DIR = BASE_DIR / "outputs" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

class LegalMetrologyPDFGenerator:
    """
    Generates official Government of India / State Legal Metrology format
    Inspection Memo & Statutory Compliance Reports with evidence and tamper-evident SHA-256 fingerprint.
    """

    @classmethod
    def generate_inspection_report(
        cls,
        inspection_data: Dict[str, Any],
        output_filename: Optional[str] = None
    ) -> str:
        insp_num = inspection_data.get("inspection_number", f"INSP-{int(datetime.datetime.utcnow().timestamp())}")
        if not output_filename:
            output_filename = f"Inspection_Report_{insp_num}.pdf"
        
        pdf_path = REPORTS_DIR / output_filename

        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom Typography
        header_gov = ParagraphStyle(
            'GovHeader',
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=16,
            alignment=1, # Center
            textColor=colors.HexColor('#0F172A')
        )
        header_sub = ParagraphStyle(
            'GovSubHeader',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=colors.HexColor('#475569')
        )
        title_style = ParagraphStyle(
            'DocTitle',
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=15,
            alignment=1,
            textColor=colors.HexColor('#1E3A8A')
        )
        section_heading = ParagraphStyle(
            'SectionHead',
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=13,
            textColor=colors.HexColor('#0F172A')
        )
        cell_bold = ParagraphStyle(
            'CellBold',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#1E293B')
        )
        cell_normal = ParagraphStyle(
            'CellNormal',
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#334155')
        )
        cell_badge_pass = ParagraphStyle(
            'BadgePass',
            fontName='Helvetica-Bold',
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor('#15803D')
        )
        cell_badge_fail = ParagraphStyle(
            'BadgeFail',
            fontName='Helvetica-Bold',
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor('#B91C1C')
        )

        story = []

        # ----------------------------------------------------
        # 1. Official Header
        # ----------------------------------------------------
        story.append(Paragraph("GOVERNMENT OF INDIA &bull; MINISTRY OF CONSUMER AFFAIRS", header_gov))
        story.append(Paragraph("DEPARTMENT OF LEGAL METROLOGY &bull; CENTRAL ENFORCEMENT WING", header_sub))
        story.append(Paragraph("STATUTORY INSPECTION MEMO &amp; COMPLIANCE NOTICE (FORM I)", title_style))
        story.append(Paragraph("Under Legal Metrology Act, 2009 &amp; Packaged Commodities Rules, 2011", header_sub))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=10))

        # ----------------------------------------------------
        # 2. Metadata Table (Inspection & Store & Officer Details)
        # ----------------------------------------------------
        store = inspection_data.get("store", {})
        officer = inspection_data.get("officer", {})
        meta_data = [
            [
                Paragraph("<b>Inspection Memo No:</b>", cell_bold),
                Paragraph(insp_num, cell_normal),
                Paragraph("<b>Date &amp; Time (UTC):</b>", cell_bold),
                Paragraph(str(inspection_data.get("inspection_date", datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M"))), cell_normal)
            ],
            [
                Paragraph("<b>Store / Premises:</b>", cell_bold),
                Paragraph(store.get("store_name", "Retail Establishment"), cell_normal),
                Paragraph("<b>GSTIN / License:</b>", cell_bold),
                Paragraph(store.get("gstin", "Unregistered / N/A"), cell_normal)
            ],
            [
                Paragraph("<b>Premises Address:</b>", cell_bold),
                Paragraph(f"{store.get('address', 'Market Zone')}, {store.get('city', 'Bengaluru')}", cell_normal),
                Paragraph("<b>GPS Coordinates:</b>", cell_bold),
                Paragraph(f"{store.get('gps_lat', 12.9716)} N, {store.get('gps_lng', 77.5946)} E", cell_normal)
            ],
            [
                Paragraph("<b>Inspecting Officer:</b>", cell_bold),
                Paragraph(f"{officer.get('full_name', 'Inspector')} ({officer.get('officer_id', 'LMO001')})", cell_normal),
                Paragraph("<b>Officer Role:</b>", cell_bold),
                Paragraph(officer.get("designation", "Legal Metrology Officer"), cell_normal)
            ]
        ]
        t_meta = Table(meta_data, colWidths=[110, 150, 110, 150])
        t_meta.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_meta)
        story.append(Spacer(1, 12))

        # ----------------------------------------------------
        # 3. Product & AI Screening Summary
        # ----------------------------------------------------
        score = inspection_data.get("compliance_score", 0.0)
        status = inspection_data.get("compliance_status", "PENDING")
        status_color = "#15803D" if status == "COMPLIANT" else ("#B91C1C" if status == "NON_COMPLIANT" else "#D97706")

        prod_summary_data = [
            [
                Paragraph("<b>Inspected Commodity:</b>", cell_bold),
                Paragraph(inspection_data.get("product_name", "Packaged Commodity"), cell_normal),
                Paragraph("<b>Overall Compliance Score:</b>", cell_bold),
                Paragraph(f"<font color='{status_color}'><b>{score}% ({status})</b></font>", cell_bold)
            ],
            [
                Paragraph("<b>Category:</b>", cell_bold),
                Paragraph(inspection_data.get("category", "Packaged Goods"), cell_normal),
                Paragraph("<b>AI Ensemble Confidence:</b>", cell_bold),
                Paragraph(f"{round(inspection_data.get('overall_confidence', 0.95) * 100, 1)}%", cell_normal)
            ]
        ]
        t_prod = Table(prod_summary_data, colWidths=[110, 150, 120, 140])
        t_prod.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EFF6FF')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#BFDBFE')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DBEAFE')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_prod)
        story.append(Spacer(1, 12))

        # ----------------------------------------------------
        # 4. Mandatory Declarations Verification Table
        # ----------------------------------------------------
        story.append(Paragraph("1. STATUTORY PACKAGING DECLARATIONS AUDIT (Rule 6, LM PCR 2011)", section_heading))
        story.append(Spacer(1, 4))

        fields = inspection_data.get("extracted_fields", {})
        dec_table_rows = [
            [
                Paragraph("<b>Mandatory Declaration</b>", cell_bold),
                Paragraph("<b>Stamped / Detected Value</b>", cell_bold),
                Paragraph("<b>Source / Model</b>", cell_bold),
                Paragraph("<b>Confidence</b>", cell_bold),
                Paragraph("<b>Compliance</b>", cell_bold)
            ]
        ]

        display_fields = [
            ("product_name", "Product Common Name (6(1)(a))"),
            ("manufacturer_name", "Manufacturer / Packer (6(1)(b))"),
            ("manufacturer_address", "Complete Address (6(1)(b))"),
            ("net_quantity", "Net Quantity (6(1)(c) & R12)"),
            ("mrp", "MRP (Incl. of all taxes) (6(1)(e))"),
            ("manufacturing_date", "Mfg / Pkg Date (6(1)(d))"),
            ("consumer_care", "Consumer Care Details (6(1)(n))"),
            ("country_of_origin", "Country of Origin (6(1)(f))"),
            ("batch_number", "Batch / Lot No.")
        ]

        for f_key, label in display_fields:
            f_data = fields.get(f_key, {})
            val = f_data.get("value") or "NOT DETECTED"
            src = f_data.get("source_model", "Ensemble")
            conf = f"{round(f_data.get('confidence', 0.0) * 100, 1)}%"
            f_stat = f_data.get("status", "MISSING")
            badge = Paragraph("PASS", cell_badge_pass) if f_stat == "CONFIRMED" else Paragraph("FLAGGED / MISSING", cell_badge_fail)
            
            dec_table_rows.append([
                Paragraph(label, cell_normal),
                Paragraph(str(val)[:45], cell_normal),
                Paragraph(str(src)[:20], cell_normal),
                Paragraph(conf, cell_normal),
                badge
            ])

        t_dec = Table(dec_table_rows, colWidths=[150, 180, 80, 50, 60])
        t_dec.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_dec)
        story.append(Spacer(1, 12))

        # ----------------------------------------------------
        # 5. Detected Statutory Violations Table
        # ----------------------------------------------------
        violations = inspection_data.get("violations", [])
        story.append(Paragraph(f"2. STATUTORY VIOLATIONS DETECTED ({len(violations)} Non-Compliances)", section_heading))
        story.append(Spacer(1, 4))

        if violations:
            viol_table_rows = [
                [
                    Paragraph("<b>Rule Code</b>", cell_bold),
                    Paragraph("<b>Statutory Reference</b>", cell_bold),
                    Paragraph("<b>Specific Non-Compliance Issue</b>", cell_bold),
                    Paragraph("<b>Severity</b>", cell_bold),
                    Paragraph("<b>Fee (₹)</b>", cell_bold)
                ]
            ]
            for v in violations:
                sev = v.get("severity", "HIGH")
                sev_color = "#B91C1C" if sev == "CRITICAL" else ("#D97706" if sev == "HIGH" else "#475569")
                viol_table_rows.append([
                    Paragraph(v.get("rule_code", "LM-PC"), cell_bold),
                    Paragraph(v.get("legal_reference", "LM PCR 2011"), cell_normal),
                    Paragraph(v.get("issue", ""), cell_normal),
                    Paragraph(f"<font color='{sev_color}'><b>{sev}</b></font>", cell_bold),
                    Paragraph(f"₹{int(v.get('compounding_amount', 5000)):,}", cell_normal)
                ])

            t_viol = Table(viol_table_rows, colWidths=[65, 140, 200, 55, 60])
            t_viol.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FEF2F2')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#FCA5A5')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#FECACA')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_viol)
        else:
            story.append(Paragraph("<font color='#15803D'><b>No statutory violations detected. All mandatory Legal Metrology packaging declarations comply with Rule 6.</b></font>", cell_normal))

        story.append(Spacer(1, 14))

        # ----------------------------------------------------
        # 6. Legal Adjudication & Compounding Guidance (Section 36 & 48)
        # ----------------------------------------------------
        total_compounding = inspection_data.get("estimated_compounding_fee", sum(v.get("compounding_amount", 0) for v in violations))
        prosecution = inspection_data.get("prosecution_recommended", False)
        
        pros_text = '<font color="#B91C1C"><b>YES — Refer to Judicial Magistrate First Class</b></font>' if prosecution else '<font color="#15803D"><b>Eligible for Compounding under Section 48</b></font>'
        adjudication_text = f"""
        <b>REGULATORY ACTION &amp; STATUTORY GUIDANCE:</b><br/>
        Under Section 36(1) of the Legal Metrology Act, 2009, manufacturing, packing or selling non-standard packages attracts a penalty up to ₹25,000 for the first offence, ₹50,000 for the second, and up to ₹1,00,000 or imprisonment for subsequent offences.<br/>
        <b>Compounding Eligibility (Section 48):</b> Estimated compounding composition fee: <b>₹{int(total_compounding):,}</b>.<br/>
        <b>Prosecution Recommendation:</b> {pros_text}.
        """
        story.append(Paragraph(adjudication_text, cell_normal))
        story.append(Spacer(1, 14))

        # ----------------------------------------------------
        # 7. Tamper-Evident SHA-256 Fingerprint & Sign-off
        # ----------------------------------------------------
        # Compute SHA-256 hash of inspection payload for chain of custody
        record_str = f"{insp_num}|{store.get('store_code')}|{score}|{len(violations)}|{total_compounding}"
        sha_hash = hashlib.sha256(record_str.encode()).hexdigest()

        sign_data = [
            [
                Paragraph(f"<b>Tamper-Evident SHA-256 Digest:</b><br/><font color='#64748B'>{sha_hash[:32]}...{sha_hash[-16:]}</font>", cell_normal),
                Paragraph("<b>Inspecting Officer Digital Signature:</b><br/><br/>_______________________________<br/><b>Legal Metrology Enforcement Officer</b>", cell_normal)
            ]
        ]
        t_sign = Table(sign_data, colWidths=[320, 200])
        t_sign.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEABOVE', (0, 0), (-1, -1), 0.5, colors.HexColor('#94A3B8'))
        ]))
        story.append(t_sign)

        # Build document
        doc.build(story)
        return str(pdf_path)
