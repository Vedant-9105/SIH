import os
import sys
import cv2
import numpy as np
from pathlib import Path
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from src.extraction.fields_parser import SemanticSpatialFieldExtractor
from src.extraction.spatial_engine import SpatialBox

def test_semantic_spatial_associations():
    print("--- Testing Semantic + Spatial Association Engine ---")
    extractor = SemanticSpatialFieldExtractor()

    # Create synthetic spatial test boxes representing challenging non-linear packaging layouts
    # Scenario:
    # 1. Reversed horizontal MRP: "₹ 120.00" at [50, 100, 140, 130] and "MRP (Incl. taxes)" at [150, 100, 260, 130]
    # 2. Stacked Column PKD: "PKD" at [50, 160, 100, 185] and "06/2026" at [48, 195, 120, 220] (VERTICAL_BELOW)
    # 3. Stacked Batch: "BATCH NO:" at [200, 160, 290, 185] and "B240615" at [198, 195, 270, 220] (VERTICAL_BELOW)
    # 4. Relative Expiry: "Best Before 24 Months" at [50, 250, 320, 280]
    # 5. Net Quantity synonym: "Net Weight:" at [50, 310, 140, 335] and "500 g" at [150, 310, 210, 335] (HORIZONTAL_RIGHT)

    test_ocr_boxes = [
        {"text": "₹ 120.00", "bbox": [50, 100, 140, 130], "confidence": 0.95, "source_model": "PaddleOCR"},
        {"text": "MRP (Incl. taxes)", "bbox": [150, 100, 260, 130], "confidence": 0.96, "source_model": "PaddleOCR"},
        {"text": "PKD", "bbox": [50, 160, 100, 185], "confidence": 0.94, "source_model": "PaddleOCR"},
        {"text": "06/2026", "bbox": [48, 195, 120, 220], "confidence": 0.97, "source_model": "WinOCR"},
        {"text": "BATCH NO:", "bbox": [200, 160, 290, 185], "confidence": 0.92, "source_model": "PaddleOCR"},
        {"text": "B240615", "bbox": [198, 195, 270, 220], "confidence": 0.96, "source_model": "Surya-VL"},
        {"text": "Best Before 24 Months", "bbox": [50, 250, 320, 280], "confidence": 0.93, "source_model": "PaddleOCR"},
        {"text": "Net Weight:", "bbox": [50, 310, 140, 335], "confidence": 0.95, "source_model": "PaddleOCR"},
        {"text": "500 g", "bbox": [150, 310, 210, 335], "confidence": 0.98, "source_model": "Surya-VL"},
        {"text": "Moksh Agarbatti Co. Pvt. Ltd.", "bbox": [50, 380, 350, 410], "confidence": 0.91, "source_model": "PaddleOCR"}
    ]

    dummy_img = np.zeros((600, 600, 3), dtype=np.uint8)
    res = extractor.parse_all(test_ocr_boxes, dummy_img, source_frame_name="test_frame")
    fields = res["fields"]

    print("\n--- Spatial Extraction Results ---")
    for k in ["net_quantity", "mrp", "batch_number", "manufacturing_date", "expiry_date", "barcode_or_qr"]:
        v = fields[k]
        print(f"\n[{k.upper()}]")
        print(f"  Value         : {v['value']}")
        if "unit" in v:
            print(f"  Unit          : {v['unit']}")
        if "currency" in v:
            print(f"  Currency      : {v['currency']}")
        if "type" in v:
            print(f"  Type          : {v['type']}")
        print(f"  Spatial Rel   : {v['spatial_relationship']}")
        print(f"  Evidence      : {v['evidence']}")
        print(f"  Confidence    : {v['confidence']}")
        print(f"  Status        : {v['status']}")

    # Assertions
    assert fields["net_quantity"]["value"] == 500.0, f"Expected 500.0, got {fields['net_quantity']['value']}"
    assert fields["net_quantity"]["unit"] == "g", f"Expected 'g', got {fields['net_quantity']['unit']}"
    assert fields["mrp"]["value"] == 120.00, f"Expected 120.00, got {fields['mrp']['value']}"
    assert fields["mrp"]["currency"] == "INR", f"Expected 'INR', got {fields['mrp']['currency']}"
    assert fields["batch_number"]["value"] == "B240615", f"Expected B240615, got {fields['batch_number']['value']}"
    assert fields["manufacturing_date"]["value"] == "06/2026", f"Expected 06/2026, got {fields['manufacturing_date']['value']}"
    assert fields["manufacturing_date"]["type"] == "packing_date", "Expected type packing_date"
    assert "VERTICAL_BELOW" in fields["manufacturing_date"]["spatial_relationship"], "Expected vertical below relationship"
    assert "24 months" in fields["expiry_date"]["value"].lower() or "24 months" in str(fields["expiry_date"]["raw_text"]).lower(), "Expected relative expiry"
    assert fields["barcode_or_qr"]["value"] is None, "Barcode must be null without hallucination"

    print("\n[SUCCESS] All Semantic + Spatial association assertions passed!")

if __name__ == "__main__":
    test_semantic_spatial_associations()
