import os
import cv2
import numpy as np
from pathlib import Path
import json

from src.pipeline import MultiModelProductPipeline
from src.config import OUTPUT_DIR, UPLOAD_DIR

def create_synthetic_test_image():
    """Generates a realistic synthetic packaged-product image for test validation."""
    img = np.ones((800, 600, 3), dtype=np.uint8) * 240
    # Background border
    cv2.rectangle(img, (20, 20), (580, 780), (220, 220, 220), -1)
    
    # Package box
    cv2.rectangle(img, (60, 80), (540, 720), (255, 255, 255), -1)
    cv2.rectangle(img, (60, 80), (540, 720), (70, 50, 200), 4)

    # Brand & Title
    cv2.putText(img, "MOKSH PREMIUM AGARBATTI", (90, 160), cv2.FONT_HERSHEY_DUPLEX, 0.9, (120, 20, 20), 2)
    cv2.putText(img, "Flora Natural Incense Sticks", (90, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 50, 50), 2)

    # Declarations
    cv2.putText(img, "NET QTY: 120 g (60 Sticks)", (90, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
    cv2.putText(img, "MRP Rs. 150.00 (Incl. of all taxes)", (90, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
    cv2.putText(img, "BATCH NO: MK-2026-09A", (90, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
    cv2.putText(img, "MFG DATE: 08/2026", (90, 430), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
    cv2.putText(img, "EXP DATE: 08/2028 (Best Before 24 Months)", (90, 480), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(img, "MFD BY: Moksh Agarbatti Co. Pvt. Ltd.", (90, 540), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(img, "Plot 42, Industrial Area, Bengaluru, Karnataka, India", (90, 575), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1)
    cv2.putText(img, "CONSUMER CARE: 1800-123-4567 | care@moksh.com", (90, 630), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(img, "COUNTRY OF ORIGIN: INDIA", (90, 670), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    test_img_path = UPLOAD_DIR / "synthetic_test_product.jpg"
    cv2.imwrite(str(test_img_path), img)
    return str(test_img_path)


def test_pipeline():
    print("--- 1. Generating Test Image ---")
    img_path = create_synthetic_test_image()
    print(f"Test image created at: {img_path}")

    print("--- 2. Initializing Master Pipeline ---")
    pipeline = MultiModelProductPipeline()

    print("--- 3. Executing Pipeline ---")
    result = pipeline.process_image(img_path)

    print("\n--- Pipeline Execution Summary ---")
    print(f"Total Time: {result['timings']['total_ms']} ms")
    print(f"Detection Agreement: {result['detection']['average_agreement']}")
    print(f"Best Preprocessing Variant: {result['preprocessing']['best_variant_key']}")
    print(f"Total OCR Fused Lines: {result['ocr']['total_lines']}")
    print(f"Audit Summary: {result['audit_summary']}")

    print("\n--- Extracted Fields ---")
    for k, v in result['extracted_fields'].items():
        print(f"[{v['status']:<14}] {k:<22}: {v['value']} (Source: {v['source_model']}, Conf: {v['confidence']})")

    # Verify key fields
    assert result['extracted_fields']['net_quantity']['value'] is not None, "Net quantity should be extracted"
    assert result['extracted_fields']['mrp']['value'] is not None, "MRP should be extracted"
    assert result['extracted_fields']['batch_number']['value'] is not None, "Batch number should be extracted"
    print("\n[SUCCESS] All pipeline assertions passed!")

if __name__ == "__main__":
    test_pipeline()
