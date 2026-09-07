import re
import cv2
import numpy as np
from typing import Dict, List, Any, Optional, Tuple

from src.config import MANDATORY_FIELDS, FIELD_LABELS, OCR_CONF_THRESHOLD
from src.extraction.spatial_engine import SpatialBox, SpatialAssociationEngine
from src.extraction.semantic_patterns import (
    NET_QUANTITY_LABELS, MRP_LABELS, BATCH_LABELS, MFG_DATE_LABELS, EXPIRY_DATE_LABELS,
    MANUFACTURER_LABELS, CONSUMER_CARE_LABELS, COUNTRY_ORIGIN_LABELS,
    parse_quantity_value, parse_mrp_value, parse_date_value, normalize_unit, normalize_currency
)

class BarcodeScanner:
    """Scans 1D and 2D Barcodes / QR codes using pyzbar or OpenCV detectors."""
    def scan(self, img_bgr: np.ndarray) -> List[Dict[str, Any]]:
        codes = []
        try:
            from pyzbar.pyzbar import decode
            decoded = decode(img_bgr)
            for d in decoded:
                data = d.data.decode('utf-8', errors='ignore')
                b_type = d.type
                rect = d.rect
                codes.append({
                    "data": data,
                    "type": b_type,
                    "bbox": [rect.left, rect.top, rect.left + rect.width, rect.top + rect.height]
                })
        except Exception:
            pass

        if not codes:
            try:
                qr_detector = cv2.QRCodeDetector()
                data, points, _ = qr_detector.detectAndDecode(img_bgr)
                if data and points is not None:
                    pts = points[0].astype(int)
                    x1 = int(np.min(pts[:, 0]))
                    y1 = int(np.min(pts[:, 1]))
                    x2 = int(np.max(pts[:, 0]))
                    y2 = int(np.max(pts[:, 1]))
                    codes.append({
                        "data": data,
                        "type": "QR_CODE",
                        "bbox": [x1, y1, x2, y2]
                    })
            except Exception:
                pass
        return codes


class SemanticSpatialFieldExtractor:
    """
    Semantic + Spatial + Multi-Engine OCR Packaged Commodity Extraction Pipeline.
    Associates semantic entity labels with values across 2D spatial layouts:
    - Horizontal Right (Label -> Value)
    - Horizontal Left (Value <- Label reversed)
    - Vertical Below (Label \\n Value stacked)
    - Vertical Above (Value \\n Label stacked)
    - Same Line Composite & Grid/Table Matrix
    """
    def __init__(self):
        self.spatial_engine = SpatialAssociationEngine()
        self.barcode_scanner = BarcodeScanner()

    def parse_all(
        self,
        ocr_boxes: List[Dict[str, Any]],
        img_bgr: np.ndarray,
        source_frame_name: str = "best_preprocessed"
    ) -> Dict[str, Any]:
        h, w = img_bgr.shape[:2]

        # 1. Convert input OCR boxes to SpatialBoxes with unique indices
        spatial_boxes: List[SpatialBox] = []
        for idx, b in enumerate(ocr_boxes):
            bbox = b.get("bbox", [0, 0, 0, 0])
            txt = b.get("text", "")
            conf = b.get("confidence", 0.8)
            src_m = b.get("source_model", "EnsembleOCR")
            spatial_boxes.append(SpatialBox(txt, bbox, conf, src_m, idx))

        # 2. Barcode & QR Scan
        barcodes = self.barcode_scanner.scan(img_bgr)

        # Extracted fields accumulator
        extracted_fields: Dict[str, Any] = {}

        # ----------------------------------------------------------------------
        # Helper to format output schema matching requirements
        # ----------------------------------------------------------------------
        def build_field_entry(
            value: Optional[Any],
            raw_text: Optional[str],
            confidence: float,
            ocr_conf: float,
            source_model: str,
            bounding_box: Optional[List[int]],
            spatial_rel: str,
            evidence: str,
            status: str = "CONFIRMED",
            extra_meta: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            entry = {
                "value": value,
                "raw_text": raw_text,
                "normalized_value": str(value) if value is not None else None,
                "confidence": round(float(confidence), 3),
                "ocr_confidence": round(float(ocr_conf), 3),
                "extraction_confidence": round(float(confidence), 3),
                "source_model": source_model,
                "source_frame": source_frame_name,
                "bounding_box": bounding_box if bounding_box else [0, 0, 0, 0],
                "spatial_relationship": spatial_rel,
                "evidence": evidence,
                "status": status
            }
            if extra_meta:
                entry.update(extra_meta)
            return entry

        # ----------------------------------------------------------------------
        # 1. NET QUANTITY (Semantic + Spatial)
        # ----------------------------------------------------------------------
        net_qty = self._extract_semantic_spatial_quantity(spatial_boxes)
        if net_qty:
            extracted_fields["net_quantity"] = build_field_entry(
                value=net_qty["value_num"],
                raw_text=net_qty["raw_text"],
                confidence=net_qty["confidence"],
                ocr_conf=net_qty["ocr_confidence"],
                source_model=net_qty["source_model"],
                bounding_box=net_qty["bounding_box"],
                spatial_rel=net_qty["spatial_rel"],
                evidence=net_qty["evidence"],
                status="CONFIRMED" if net_qty["confidence"] >= OCR_CONF_THRESHOLD else "LOW_CONFIDENCE",
                extra_meta={"unit": net_qty["unit"], "entity_type": "net_quantity"}
            )
        else:
            extracted_fields["net_quantity"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None",
                bounding_box=None, spatial_rel="NONE", evidence="Net quantity declaration not detected on package",
                status="MISSING", extra_meta={"unit": None, "entity_type": "net_quantity"}
            )

        # ----------------------------------------------------------------------
        # 2. MRP & CURRENCY (Semantic + Spatial)
        # ----------------------------------------------------------------------
        mrp_data = self._extract_semantic_spatial_mrp(spatial_boxes)
        if mrp_data:
            extracted_fields["mrp"] = build_field_entry(
                value=mrp_data["value_num"],
                raw_text=mrp_data["raw_text"],
                confidence=mrp_data["confidence"],
                ocr_conf=mrp_data["ocr_confidence"],
                source_model=mrp_data["source_model"],
                bounding_box=mrp_data["bounding_box"],
                spatial_rel=mrp_data["spatial_rel"],
                evidence=mrp_data["evidence"],
                status="CONFIRMED" if mrp_data["confidence"] >= OCR_CONF_THRESHOLD else "LOW_CONFIDENCE",
                extra_meta={"currency": mrp_data["currency"], "entity_type": "maximum_retail_price"}
            )
            extracted_fields["currency"] = build_field_entry(
                value=mrp_data["currency"],
                raw_text=mrp_data["raw_text"],
                confidence=mrp_data["confidence"],
                ocr_conf=mrp_data["ocr_confidence"],
                source_model=mrp_data["source_model"],
                bounding_box=mrp_data["bounding_box"],
                spatial_rel=mrp_data["spatial_rel"],
                evidence="Currency derived from MRP declaration",
                status="CONFIRMED",
                extra_meta={"entity_type": "currency"}
            )
        else:
            extracted_fields["mrp"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None",
                bounding_box=None, spatial_rel="NONE", evidence="MRP declaration not detected",
                status="MISSING", extra_meta={"currency": None, "entity_type": "maximum_retail_price"}
            )
            extracted_fields["currency"] = build_field_entry(
                value="INR", raw_text=None, confidence=0.5, ocr_conf=0.0, source_model="Default",
                bounding_box=None, spatial_rel="DEFAULT", evidence="Defaulted currency",
                status="LOW_CONFIDENCE", extra_meta={"entity_type": "currency"}
            )

        # ----------------------------------------------------------------------
        # 3. BATCH / LOT NUMBER (Semantic + Spatial)
        # ----------------------------------------------------------------------
        batch_data = self._extract_semantic_spatial_batch(spatial_boxes)
        if batch_data:
            extracted_fields["batch_number"] = build_field_entry(
                value=batch_data["value"],
                raw_text=batch_data["raw_text"],
                confidence=batch_data["confidence"],
                ocr_conf=batch_data["ocr_confidence"],
                source_model=batch_data["source_model"],
                bounding_box=batch_data["bounding_box"],
                spatial_rel=batch_data["spatial_rel"],
                evidence=batch_data["evidence"],
                status="CONFIRMED" if batch_data["confidence"] >= OCR_CONF_THRESHOLD else "LOW_CONFIDENCE",
                extra_meta={"entity_type": "batch_lot_number"}
            )
        else:
            extracted_fields["batch_number"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None",
                bounding_box=None, spatial_rel="NONE", evidence="Batch or Lot number not detected",
                status="MISSING", extra_meta={"entity_type": "batch_lot_number"}
            )

        # ----------------------------------------------------------------------
        # 4. MANUFACTURING / PACKING DATE (Semantic + Spatial)
        # ----------------------------------------------------------------------
        mfg_data = self._extract_semantic_spatial_mfg_date(spatial_boxes)
        if mfg_data:
            extracted_fields["manufacturing_date"] = build_field_entry(
                value=mfg_data["value"],
                raw_text=mfg_data["raw_text"],
                confidence=mfg_data["confidence"],
                ocr_conf=mfg_data["ocr_confidence"],
                source_model=mfg_data["source_model"],
                bounding_box=mfg_data["bounding_box"],
                spatial_rel=mfg_data["spatial_rel"],
                evidence=mfg_data["evidence"],
                status="CONFIRMED" if mfg_data["confidence"] >= OCR_CONF_THRESHOLD else "LOW_CONFIDENCE",
                extra_meta={"type": mfg_data["type"], "entity_type": "manufacturing_packing_date"}
            )
        else:
            extracted_fields["manufacturing_date"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None",
                bounding_box=None, spatial_rel="NONE", evidence="Manufacturing or Packing date not detected",
                status="MISSING", extra_meta={"type": "unknown", "entity_type": "manufacturing_packing_date"}
            )

        # ----------------------------------------------------------------------
        # 5. EXPIRY / BEST BEFORE DATE (Semantic + Spatial)
        # ----------------------------------------------------------------------
        exp_data = self._extract_semantic_spatial_expiry_date(spatial_boxes, mfg_data)
        if exp_data:
            extracted_fields["expiry_date"] = build_field_entry(
                value=exp_data["value"],
                raw_text=exp_data["raw_text"],
                confidence=exp_data["confidence"],
                ocr_conf=exp_data["ocr_confidence"],
                source_model=exp_data["source_model"],
                bounding_box=exp_data["bounding_box"],
                spatial_rel=exp_data["spatial_rel"],
                evidence=exp_data["evidence"],
                status="CONFIRMED" if exp_data["confidence"] >= OCR_CONF_THRESHOLD else "LOW_CONFIDENCE",
                extra_meta={"type": exp_data["type"], "entity_type": "expiry_best_before_date"}
            )
        else:
            extracted_fields["expiry_date"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None",
                bounding_box=None, spatial_rel="NONE", evidence="Expiry or Best Before declaration not detected",
                status="MISSING", extra_meta={"type": "unknown", "entity_type": "expiry_best_before_date"}
            )

        # ----------------------------------------------------------------------
        # 6. MANUFACTURER NAME & ADDRESS (Semantic + Spatial)
        # ----------------------------------------------------------------------
        mfd_name, mfd_addr, mfd_raw, mfd_box, mfd_src, mfd_conf, mfd_rel, mfd_ev = self._extract_semantic_spatial_manufacturer(spatial_boxes)
        if mfd_name:
            extracted_fields["manufacturer_name"] = build_field_entry(
                value=mfd_name, raw_text=mfd_raw, confidence=mfd_conf, ocr_conf=mfd_conf, source_model=mfd_src,
                bounding_box=mfd_box, spatial_rel=mfd_rel, evidence=mfd_ev, status="CONFIRMED"
            )
            extracted_fields["manufacturer_address"] = build_field_entry(
                value=mfd_addr if mfd_addr else mfd_name, raw_text=mfd_raw, confidence=mfd_conf * 0.9, ocr_conf=mfd_conf * 0.9,
                source_model=mfd_src, bounding_box=mfd_box, spatial_rel=mfd_rel, evidence="Derived from manufacturer declaration block",
                status="CONFIRMED" if mfd_addr else "LOW_CONFIDENCE"
            )
        else:
            extracted_fields["manufacturer_name"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None", bounding_box=None,
                spatial_rel="NONE", evidence="Manufacturer name not detected", status="MISSING"
            )
            extracted_fields["manufacturer_address"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None", bounding_box=None,
                spatial_rel="NONE", evidence="Manufacturer address not detected", status="MISSING"
            )

        # ----------------------------------------------------------------------
        # 7. PRODUCT & BRAND NAME
        # ----------------------------------------------------------------------
        prod_name, brand_name, p_raw, p_box, p_src, p_conf = self._extract_product_brand(spatial_boxes)
        if prod_name:
            extracted_fields["product_name"] = build_field_entry(
                value=prod_name, raw_text=p_raw, confidence=p_conf, ocr_conf=p_conf, source_model=p_src,
                bounding_box=p_box, spatial_rel="TOP_HEADER_PROMINENCE", evidence="Extracted from prominent top title block", status="CONFIRMED"
            )
            extracted_fields["brand_name"] = build_field_entry(
                value=brand_name if brand_name else prod_name.split()[0], raw_text=p_raw, confidence=p_conf, ocr_conf=p_conf,
                source_model=p_src, bounding_box=p_box, spatial_rel="TOP_HEADER_PROMINENCE", evidence="Extracted from brand mark", status="CONFIRMED"
            )
        else:
            extracted_fields["product_name"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None", bounding_box=None,
                spatial_rel="NONE", evidence="Product title not detected", status="MISSING"
            )
            extracted_fields["brand_name"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None", bounding_box=None,
                spatial_rel="NONE", evidence="Brand name not detected", status="MISSING"
            )

        # ----------------------------------------------------------------------
        # 8. CONSUMER CARE
        # ----------------------------------------------------------------------
        care_val, care_raw, care_box, care_src, care_conf, care_rel = self._extract_consumer_care(spatial_boxes)
        if care_val:
            extracted_fields["consumer_care"] = build_field_entry(
                value=care_val, raw_text=care_raw, confidence=care_conf, ocr_conf=care_conf, source_model=care_src,
                bounding_box=care_box, spatial_rel=care_rel, evidence="Identified consumer care helpline / email block", status="CONFIRMED"
            )
        else:
            extracted_fields["consumer_care"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None", bounding_box=None,
                spatial_rel="NONE", evidence="Consumer care details not found", status="MISSING"
            )

        # ----------------------------------------------------------------------
        # 9. COUNTRY OF ORIGIN
        # ----------------------------------------------------------------------
        coo_val, coo_raw, coo_box, coo_src, coo_conf, coo_rel = self._extract_country_of_origin(spatial_boxes)
        if coo_val:
            extracted_fields["country_of_origin"] = build_field_entry(
                value=coo_val, raw_text=coo_raw, confidence=coo_conf, ocr_conf=coo_conf, source_model=coo_src,
                bounding_box=coo_box, spatial_rel=coo_rel, evidence="Country of origin declaration found", status="CONFIRMED"
            )
        else:
            # Geographic fallback inference from Indian address
            full_txt = " ".join(b.text for b in spatial_boxes)
            if any(k in full_txt.upper() for k in ["INDIA", "PIN", "DELHI", "BENGALURU", "MUMBAI", "KARNATAKA", "TAMIL NADU", "GUJARAT"]):
                extracted_fields["country_of_origin"] = build_field_entry(
                    value="India", raw_text="Manufactured in India (Inferred from address)", confidence=0.85, ocr_conf=0.85,
                    source_model="SpatialInference", bounding_box=mfd_box, spatial_rel="INFERRED_FROM_ADDRESS",
                    evidence="Inferred from manufacturer address location", status="CONFIRMED"
                )
            else:
                extracted_fields["country_of_origin"] = build_field_entry(
                    value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="None", bounding_box=None,
                    spatial_rel="NONE", evidence="Country of origin declaration not found", status="MISSING"
                )

        # ----------------------------------------------------------------------
        # 10. BARCODE / QR
        # ----------------------------------------------------------------------
        if barcodes:
            b_info = barcodes[0]
            extracted_fields["barcode_or_qr"] = build_field_entry(
                value=f"{b_info['type']}: {b_info['data']}", raw_text=b_info['data'], confidence=0.99, ocr_conf=0.99,
                source_model="BarcodeScanner", bounding_box=b_info['bbox'], spatial_rel="SCANNED_OPTICAL_CODE",
                evidence="1D/2D optical barcode symbol successfully decoded", status="CONFIRMED"
            )
        else:
            extracted_fields["barcode_or_qr"] = build_field_entry(
                value=None, raw_text=None, confidence=0.0, ocr_conf=0.0, source_model="BarcodeScanner", bounding_box=None,
                spatial_rel="NONE", evidence="No 1D/2D barcode or QR code visible on package (Zero-hallucination)", status="MISSING"
            )

        # ----------------------------------------------------------------------
        # 11. OTHER DECLARATIONS
        # ----------------------------------------------------------------------
        other_decls = self._extract_other_declarations(spatial_boxes)
        extracted_fields["other_declarations"] = build_field_entry(
            value="; ".join(other_decls) if other_decls else None,
            raw_text="; ".join(other_decls) if other_decls else None,
            confidence=0.80 if other_decls else 0.0,
            ocr_conf=0.80 if other_decls else 0.0,
            source_model="EnsembleOCR",
            bounding_box=None,
            spatial_rel="DECLARATION_BLOCK",
            evidence="Categorical declarations and quality marks extracted",
            status="CONFIRMED" if other_decls else "MISSING"
        )

        # ----------------------------------------------------------------------
        # Summary & Classification
        # ----------------------------------------------------------------------
        missing_fields = [k for k, v in extracted_fields.items() if v["status"] == "MISSING"]
        low_conf_fields = [k for k, v in extracted_fields.items() if v["status"] == "LOW_CONFIDENCE"]
        confirmed_fields = [k for k, v in extracted_fields.items() if v["status"] == "CONFIRMED"]
        overall_conf = float(np.mean([v["confidence"] for v in extracted_fields.values()]))

        return {
            "fields": extracted_fields,
            "summary": {
                "total_fields": len(extracted_fields),
                "confirmed_count": len(confirmed_fields),
                "low_confidence_count": len(low_conf_fields),
                "missing_count": len(missing_fields),
                "missing_fields": missing_fields,
                "low_confidence_fields": low_conf_fields,
                "overall_confidence": round(overall_conf, 3),
                "barcodes_detected": len(barcodes)
            }
        }

    # ==========================================================================
    # SEMANTIC + SPATIAL EXTRACTION METHODS
    # ==========================================================================

    def _extract_semantic_spatial_quantity(self, boxes: List[SpatialBox]) -> Optional[Dict[str, Any]]:
        label_regex = re.compile("|".join(NET_QUANTITY_LABELS), re.IGNORECASE)

        # 1. Look for boxes containing the semantic label
        for l_box in boxes:
            if label_regex.search(l_box.text):
                # Check if value is already in same composite box (e.g. "Net Wt: 500 g")
                same_box_val = parse_quantity_value(l_box.text)
                if same_box_val:
                    val_num, unit = same_box_val
                    return {
                        "value_num": val_num,
                        "unit": unit,
                        "raw_text": l_box.text,
                        "confidence": min(0.98, l_box.confidence * 1.05),
                        "ocr_confidence": l_box.confidence,
                        "source_model": l_box.source_model,
                        "bounding_box": l_box.bbox,
                        "spatial_rel": "SAME_LINE_COMPOSITE",
                        "evidence": f"Found label and value '{val_num} {unit}' in same text line"
                    }

                # 2. Search surrounding 2D spatial plane for the value box
                candidates = self.spatial_engine.evaluate_candidates(
                    label_box=l_box,
                    candidate_boxes=boxes,
                    pattern_validator_fn=parse_quantity_value
                )
                if candidates:
                    top_cand = candidates[0]
                    val_num, unit = top_cand["value_data"]
                    v_box = top_cand["value_box"]
                    return {
                        "value_num": val_num,
                        "unit": unit,
                        "raw_text": f"{l_box.text} -> {v_box.text}",
                        "confidence": top_cand["confidence"],
                        "ocr_confidence": v_box.confidence,
                        "source_model": v_box.source_model,
                        "bounding_box": v_box.bbox,
                        "spatial_rel": top_cand["relation"],
                        "evidence": f"Associated label '{l_box.text}' with '{v_box.text}' ({top_cand['reason']})"
                    }

        # 3. Fallback: Search for standalone quantity value if prominent
        for b in boxes:
            val = parse_quantity_value(b.text)
            if val and not any(k in b.text.upper() for k in ["MRP", "RS", "BATCH", "EXP", "MFD"]):
                val_num, unit = val
                return {
                    "value_num": val_num,
                    "unit": unit,
                    "raw_text": b.text,
                    "confidence": b.confidence * 0.85,
                    "ocr_confidence": b.confidence,
                    "source_model": b.source_model,
                    "bounding_box": b.bbox,
                    "spatial_rel": "STANDALONE_QUANTITY_MATCH",
                    "evidence": f"Identified standalone standard quantity representation: {val_num} {unit}"
                }

        return None

    def _extract_semantic_spatial_mrp(self, boxes: List[SpatialBox]) -> Optional[Dict[str, Any]]:
        label_regex = re.compile("|".join(MRP_LABELS), re.IGNORECASE)

        for l_box in boxes:
            if label_regex.search(l_box.text):
                # 1. Same box composite (e.g. "MRP Rs. 150.00")
                same_val = parse_mrp_value(l_box.text)
                if same_val:
                    price, curr = same_val
                    return {
                        "value_num": price,
                        "currency": curr,
                        "raw_text": l_box.text,
                        "confidence": min(0.99, l_box.confidence * 1.05),
                        "ocr_confidence": l_box.confidence,
                        "source_model": l_box.source_model,
                        "bounding_box": l_box.bbox,
                        "spatial_rel": "SAME_LINE_COMPOSITE",
                        "evidence": f"Found MRP label and price '{curr} {price}' in same text line"
                    }

                # 2. Search surrounding 2D spatial plane (right, below, left reversed)
                candidates = self.spatial_engine.evaluate_candidates(
                    label_box=l_box,
                    candidate_boxes=boxes,
                    pattern_validator_fn=parse_mrp_value
                )
                if candidates:
                    top_cand = candidates[0]
                    price, curr = top_cand["value_data"]
                    v_box = top_cand["value_box"]
                    return {
                        "value_num": price,
                        "currency": curr,
                        "raw_text": f"{l_box.text} | {v_box.text}",
                        "confidence": top_cand["confidence"],
                        "ocr_confidence": v_box.confidence,
                        "source_model": v_box.source_model,
                        "bounding_box": v_box.bbox,
                        "spatial_rel": top_cand["relation"],
                        "evidence": f"Associated MRP label '{l_box.text}' with '{v_box.text}' ({top_cand['reason']})"
                    }

        # 3. Fallback: Search for any standalone currency symbol + price
        for b in boxes:
            if any(k in b.text for k in ['₹', 'Rs.', 'RS', 'INR']):
                val = parse_mrp_value(b.text)
                if val:
                    price, curr = val
                    return {
                        "value_num": price,
                        "currency": curr,
                        "raw_text": b.text,
                        "confidence": b.confidence * 0.88,
                        "ocr_confidence": b.confidence,
                        "source_model": b.source_model,
                        "bounding_box": b.bbox,
                        "spatial_rel": "STANDALONE_CURRENCY_PRICE",
                        "evidence": f"Found standalone price marker '{curr} {price}'"
                    }

        return None

    def _extract_semantic_spatial_batch(self, boxes: List[SpatialBox]) -> Optional[Dict[str, Any]]:
        label_regex = re.compile("|".join(BATCH_LABELS), re.IGNORECASE)

        for l_box in boxes:
            if label_regex.search(l_box.text):
                # 1. Clean same line
                cleaned = label_regex.sub('', l_box.text).replace(':', '').replace('.', '').strip()
                if len(cleaned) >= 3 and not any(k in cleaned.upper() for k in ["DATE", "MRP", "QTY", "EXP", "MFD"]):
                    return {
                        "value": cleaned,
                        "raw_text": l_box.text,
                        "confidence": min(0.96, l_box.confidence * 1.05),
                        "ocr_confidence": l_box.confidence,
                        "source_model": l_box.source_model,
                        "bounding_box": l_box.bbox,
                        "spatial_rel": "SAME_LINE_COMPOSITE",
                        "evidence": f"Extracted batch code '{cleaned}' on same line as label"
                    }

                # 2. Search surrounding 2D space (below, right)
                def batch_val_fn(txt: str):
                    clean = txt.strip()
                    # Disqualify if it's another field label header
                    disqualified = ["MRP", "MFD", "PKD", "EXP", "DATE", "NET", "QTY", "QUANTITY", "SELLING", "PRICE", "COMMODITY", "TAXES", "INCL", "STICKS", "RS", "INR"]
                    if any(k in clean.upper() for k in disqualified):
                        return None
                    # Batch numbers should have alphanumeric character mix or numbers
                    if len(clean) >= 3 and any(ch.isdigit() for ch in clean):
                        return clean
                    return None

                candidates = self.spatial_engine.evaluate_candidates(
                    label_box=l_box,
                    candidate_boxes=boxes,
                    pattern_validator_fn=batch_val_fn
                )
                if candidates:
                    top_cand = candidates[0]
                    v_box = top_cand["value_box"]
                    return {
                        "value": v_box.text,
                        "raw_text": f"{l_box.text} -> {v_box.text}",
                        "confidence": top_cand["confidence"],
                        "ocr_confidence": v_box.confidence,
                        "source_model": v_box.source_model,
                        "bounding_box": v_box.bbox,
                        "spatial_rel": top_cand["relation"],
                        "evidence": f"Associated batch label '{l_box.text}' with '{v_box.text}' ({top_cand['reason']})"
                    }

        return None

    def _extract_semantic_spatial_mfg_date(self, boxes: List[SpatialBox]) -> Optional[Dict[str, Any]]:
        label_regex = re.compile("|".join(MFG_DATE_LABELS), re.IGNORECASE)

        for l_box in boxes:
            if label_regex.search(l_box.text):
                # Disambiguate if expiry is also mentioned in the same text
                if any(k in l_box.text.upper() for k in ["EXP", "BEST BEFORE", "USE BY"]):
                    continue

                date_type = "packing_date" if any(k in l_box.text.upper() for k in ["PKD", "PACKED", "PACKING"]) else "manufacturing_date"

                # 1. Same line date
                same_val = parse_date_value(l_box.text)
                if same_val:
                    date_str, d_type = same_val
                    return {
                        "value": date_str,
                        "type": date_type,
                        "raw_text": l_box.text,
                        "confidence": min(0.98, l_box.confidence * 1.05),
                        "ocr_confidence": l_box.confidence,
                        "source_model": l_box.source_model,
                        "bounding_box": l_box.bbox,
                        "spatial_rel": "SAME_LINE_COMPOSITE",
                        "evidence": f"Found {date_type} label and date '{date_str}' in same text line"
                    }

                # 2. Search surrounding 2D space (below, right)
                candidates = self.spatial_engine.evaluate_candidates(
                    label_box=l_box,
                    candidate_boxes=boxes,
                    pattern_validator_fn=parse_date_value
                )
                if candidates:
                    top_cand = candidates[0]
                    date_str, _ = top_cand["value_data"]
                    v_box = top_cand["value_box"]
                    return {
                        "value": date_str,
                        "type": date_type,
                        "raw_text": f"{l_box.text} -> {v_box.text}",
                        "confidence": top_cand["confidence"],
                        "ocr_confidence": v_box.confidence,
                        "source_model": v_box.source_model,
                        "bounding_box": v_box.bbox,
                        "spatial_rel": top_cand["relation"],
                        "evidence": f"Associated {date_type} label '{l_box.text}' with '{v_box.text}' ({top_cand['reason']})"
                    }

        return None

    def _extract_semantic_spatial_expiry_date(self, boxes: List[SpatialBox], mfg_info: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        label_regex = re.compile("|".join(EXPIRY_DATE_LABELS), re.IGNORECASE)

        for l_box in boxes:
            if label_regex.search(l_box.text):
                # 1. Same line date or relative duration
                same_val = parse_date_value(l_box.text)
                if same_val:
                    date_val, d_format = same_val
                    return {
                        "value": date_val,
                        "type": "relative_duration" if d_format == "relative_duration" else "exact_date",
                        "raw_text": l_box.text,
                        "confidence": min(0.96, l_box.confidence * 1.05),
                        "ocr_confidence": l_box.confidence,
                        "source_model": l_box.source_model,
                        "bounding_box": l_box.bbox,
                        "spatial_rel": "SAME_LINE_COMPOSITE",
                        "evidence": f"Found expiry declaration '{date_val}' in same text line"
                    }

                # 2. Search surrounding 2D space
                candidates = self.spatial_engine.evaluate_candidates(
                    label_box=l_box,
                    candidate_boxes=boxes,
                    pattern_validator_fn=parse_date_value
                )
                if candidates:
                    top_cand = candidates[0]
                    date_val, d_format = top_cand["value_data"]
                    v_box = top_cand["value_box"]
                    return {
                        "value": date_val,
                        "type": "relative_duration" if d_format == "relative_duration" else "exact_date",
                        "raw_text": f"{l_box.text} -> {v_box.text}",
                        "confidence": top_cand["confidence"],
                        "ocr_confidence": v_box.confidence,
                        "source_model": v_box.source_model,
                        "bounding_box": v_box.bbox,
                        "spatial_rel": top_cand["relation"],
                        "evidence": f"Associated expiry label '{l_box.text}' with '{v_box.text}' ({top_cand['reason']})"
                    }

        return None

    def _extract_semantic_spatial_manufacturer(self, boxes: List[SpatialBox]):
        label_regex = re.compile("|".join(MANUFACTURER_LABELS), re.IGNORECASE)

        for i, l_box in enumerate(boxes):
            if label_regex.search(l_box.text):
                name = label_regex.sub('', l_box.text).replace(':', '').strip()
                
                # Check stacked lines underneath for address block
                addr_lines = []
                for j, other in enumerate(boxes):
                    if j != i and other.yc > l_box.yc and (other.yc - l_box.yc) <= l_box.h * 5.0:
                        if abs(other.xc - l_box.xc) <= max(l_box.w, other.w) * 1.5:
                            txt = other.text
                            if any(k in txt.upper() for k in ["ROAD", "STREET", "PLOT", "DIST", "PIN", "NAGAR", "ESTATE", "INDUSTRIAL", "INDIA", "KARNATAKA", "MAHARASHTRA", "DELHI"]):
                                addr_lines.append(txt)

                full_addr = ", ".join(addr_lines) if addr_lines else None
                m_name = name if name else "Manufactured on Package"
                evidence = f"Identified manufacturer block starting at label '{l_box.text}'"

                return m_name, full_addr, l_box.text, l_box.bbox, l_box.source_model, l_box.confidence, "VERTICAL_STACK_BLOCK", evidence

        return None, None, None, None, None, 0.0, "NONE", "None"

    def _extract_product_brand(self, boxes: List[SpatialBox]):
        if not boxes:
            return None, None, None, None, "None", 0.0
        # Filter out obvious declaration labels
        candidates = [
            b for b in boxes
            if len(b.text) > 3 and not any(
                k in b.text.upper()
                for k in ["NET", "MRP", "MFD", "PKD", "BATCH", "EXP", "BEST BEFORE", "CONSUMER", "CARE", "LIC", "FSSAI"]
            )
        ]
        if candidates:
            # Topmost box
            top_box = sorted(candidates, key=lambda b: (b.y1, b.x1))[0]
            prod = top_box.text
            brand = prod.split()[0]
            return prod, brand, prod, top_box.bbox, top_box.source_model, top_box.confidence
        return None, None, None, None, "None", 0.0

    def _extract_consumer_care(self, boxes: List[SpatialBox]):
        label_regex = re.compile("|".join(CONSUMER_CARE_LABELS), re.IGNORECASE)
        for b in boxes:
            if label_regex.search(b.text) or "@" in b.text or any(k in b.text for k in ["1800", "CUSTOMERCARE", "care@"]):
                return b.text, b.text, b.bbox, b.source_model, b.confidence, "SAME_LINE_COMPOSITE"
        return None, None, None, "None", 0.0, "NONE"

    def _extract_country_of_origin(self, boxes: List[SpatialBox]):
        label_regex = re.compile("|".join(COUNTRY_ORIGIN_LABELS), re.IGNORECASE)
        for b in boxes:
            if label_regex.search(b.text):
                cleaned = label_regex.sub('', b.text).replace(':', '').strip()
                val = cleaned if cleaned else "India"
                return val, b.text, b.bbox, b.source_model, b.confidence, "SAME_LINE_COMPOSITE"
        return None, None, None, "None", 0.0, "NONE"

    def _extract_other_declarations(self, boxes: List[SpatialBox]) -> List[str]:
        decls = []
        for b in boxes:
            txt_u = b.text.upper()
            if "FSSAI" in txt_u or "LIC NO" in txt_u:
                decls.append(f"FSSAI / Lic: {b.text}")
            elif "INGREDIENTS" in txt_u:
                decls.append(f"Ingredients: {b.text}")
            elif "VEGETARIAN" in txt_u or "GREEN DOT" in txt_u:
                decls.append(f"Dietary: {b.text}")
            elif "STORAGE" in txt_u or "COOL AND DRY" in txt_u:
                decls.append(f"Storage: {b.text}")
            elif "AGARBATTI" in txt_u or "INCENSE" in txt_u:
                decls.append(f"Product Category: {b.text}")
        return decls


# Maintain alias for pipeline compatibility
FieldExtractionEngine = SemanticSpatialFieldExtractor
