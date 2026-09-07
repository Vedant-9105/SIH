import time
import os
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional

from src.detection.ensemble import ProductDetectionEnsemble
from src.preprocessing.pipeline import ImagePreprocessor
from src.ocr.ensemble import OCREnsembleEngine
from src.validation.gemini_validator import GeminiMultimodalValidator
from src.validation.translator import MultilingualTranslator
from src.extraction.fields_parser import FieldExtractionEngine
from src.config import OUTPUT_DIR, UPLOAD_DIR

class MultiModelProductPipeline:
    """
    End-to-End Packaged-Product Analysis Pipeline:
    1. Product Detection Ensemble (YOLO11, RT-DETR, RF-DETR)
    2. Multi-variant Image Preprocessing & Quality Evaluation (OpenCV, scikit-image, PyTorch)
    3. Multi-Engine OCR Ensemble & Fusion (PaddleOCR, WinOCR, Surya-VL, Tesseract)
    4. Multilingual Translation (Google Translate)
    5. Structured Field Extraction & Legal Metrology Parsing
    6. Multimodal Gemini Visual Verification
    """
    def __init__(self):
        print("[Pipeline] Initializing models and engines...")
        self.detector = ProductDetectionEnsemble()
        self.preprocessor = ImagePreprocessor()
        self.ocr = OCREnsembleEngine()
        self.translator = MultilingualTranslator()
        self.extractor = FieldExtractionEngine()
        self.gemini = GeminiMultimodalValidator()
        print("[Pipeline] All components initialized.")

    def process_image(self, image_path: str) -> Dict[str, Any]:
        total_start = time.time()
        img_bgr = cv2.imread(image_path)
        if img_bgr is None:
            raise ValueError(f"Could not read image from path: {image_path}")

        session_id = int(time.time() * 1000)
        session_out_dir = OUTPUT_DIR / f"run_{session_id}"
        session_out_dir.mkdir(parents=True, exist_ok=True)

        # ----------------------------------------------------
        # Stage 1: Product / Object Detection Ensemble
        # ----------------------------------------------------
        t0 = time.time()
        detection_res = self.detector.run(img_bgr, output_dir=session_out_dir)
        detection_time = round((time.time() - t0) * 1000, 1)

        cropped_bgr = detection_res["cropped_image"]

        # ----------------------------------------------------
        # Stage 2: Image Preprocessing Suite & Quality Evaluation
        # ----------------------------------------------------
        t0 = time.time()
        preproc_res = self.preprocessor.generate_variants(cropped_bgr, output_dir=session_out_dir)
        best_variant_img = preproc_res["best_variant_image"]
        best_variant_key = preproc_res["best_variant_key"]
        preprocessing_time = round((time.time() - t0) * 1000, 1)

        # ----------------------------------------------------
        # Stage 3: Text Extraction & OCR Ensemble
        # ----------------------------------------------------
        t0 = time.time()
        ocr_res = self.ocr.run_all(cropped_bgr, variant_img=best_variant_img)
        fused_boxes = ocr_res["fused_boxes"]
        ocr_time = round((time.time() - t0) * 1000, 1)

        # ----------------------------------------------------
        # Stage 4: Multilingual Translation
        # ----------------------------------------------------
        t0 = time.time()
        annotated_boxes = self.translator.process_ocr_boxes(fused_boxes)
        translation_time = round((time.time() - t0) * 1000, 1)

        # ----------------------------------------------------
        # Stage 5: Canonical Field Extraction
        # ----------------------------------------------------
        t0 = time.time()
        extraction_res = self.extractor.parse_all(annotated_boxes, cropped_bgr, source_frame_name=f"variant_{best_variant_key}")
        fields = extraction_res["fields"]
        extraction_time = round((time.time() - t0) * 1000, 1)

        # ----------------------------------------------------
        # Stage 6: Gemini Multimodal Visual Validation Layer
        # ----------------------------------------------------
        t0 = time.time()
        raw_lines = [b.get("text", "") for b in annotated_boxes]
        gemini_res = self.gemini.validate(cropped_bgr, fields, raw_lines)
        gemini_time = round((time.time() - t0) * 1000, 1)

        # Merge Gemini validations if available
        if gemini_res.get("status") == "SUCCESS_GEMINI_VERIFIED" and "verified_fields" in gemini_res:
            v_fields = gemini_res["verified_fields"]
            for f_key, v_data in v_fields.items():
                if f_key in fields and isinstance(v_data, dict):
                    # If Gemini visually confirmed or corrected
                    if v_data.get("value") is not None:
                        fields[f_key]["value"] = v_data.get("value")
                        fields[f_key]["normalized_value"] = str(v_data.get("value"))
                    if v_data.get("raw_text"):
                        fields[f_key]["raw_text"] = v_data.get("raw_text")
                    if v_data.get("status"):
                        fields[f_key]["status"] = v_data.get("status")
                    if v_data.get("visual_notes"):
                        fields[f_key]["visual_notes"] = v_data.get("visual_notes")
                    fields[f_key]["source_model"] += " + GeminiVision"
                    fields[f_key]["confidence"] = max(fields[f_key]["confidence"], 0.95)

        # Final audit refresh
        missing_count = sum(1 for v in fields.values() if v.get("status") == "MISSING")
        low_conf_count = sum(1 for v in fields.values() if v.get("status") == "LOW_CONFIDENCE")
        confirmed_count = sum(1 for v in fields.values() if v.get("status") == "CONFIRMED")
        total_time = round((time.time() - total_start) * 1000, 1)

        # Prepare serializable variant metadata (strip numpy arrays)
        variants_meta = []
        for v in preproc_res["variants"]:
            saved_p = v.get("saved_path")
            variants_meta.append({
                "key": v["key"],
                "label": v["label"],
                "metrics": v["metrics"],
                "relative_path": f"/outputs/run_{session_id}/{Path(saved_p).name}" if saved_p else None
            })

        # Save annotated OCR image
        annotated_ocr_img = cropped_bgr.copy()
        for b in annotated_boxes:
            bx = b["bbox"]
            cv2.rectangle(annotated_ocr_img, (bx[0], bx[1]), (bx[2], bx[3]), (0, 255, 255), 1)
        ocr_overlay_filename = f"ocr_overlay_{session_id}.jpg"
        cv2.imwrite(str(session_out_dir / ocr_overlay_filename), annotated_ocr_img)

        # Format relative paths for frontend
        crop_rel_path = f"/outputs/run_{session_id}/{Path(detection_res['crop_path']).name}" if detection_res['crop_path'] else None
        det_overlay_rel_path = f"/outputs/run_{session_id}/{Path(detection_res['annotated_path']).name}" if detection_res['annotated_path'] else None
        ocr_overlay_rel_path = f"/outputs/run_{session_id}/{ocr_overlay_filename}"

        # Format individual detector crop URLs
        det_models = []
        for m in detection_res["models"]:
            m_copy = dict(m)
            if m_copy.get("crop_filename"):
                m_copy["crop_url"] = f"/outputs/run_{session_id}/{m_copy['crop_filename']}"
            else:
                m_copy["crop_url"] = crop_rel_path
            det_models.append(m_copy)

        return {
            "session_id": session_id,
            "timings": {
                "detection_ms": detection_time,
                "preprocessing_ms": preprocessing_time,
                "ocr_ms": ocr_time,
                "translation_ms": translation_time,
                "extraction_ms": extraction_time,
                "gemini_ms": gemini_time,
                "total_ms": total_time
            },
            "detection": {
                "models": det_models,
                "iou_matrix": detection_res["iou_matrix"],
                "average_agreement": detection_res["average_agreement"],
                "consensus_bbox": detection_res["consensus_bbox"],
                "crop_quality": detection_res["crop_quality"],
                "crop_image_url": crop_rel_path,
                "overlay_image_url": det_overlay_rel_path,
                "original_dimensions": detection_res["original_dimensions"],
                "cropped_dimensions": detection_res["cropped_dimensions"]
            },
            "preprocessing": {
                "variants": variants_meta,
                "best_variant_key": preproc_res["best_variant_key"],
                "best_variant_score": preproc_res["best_variant_score"]
            },
            "ocr": {
                "engine_results": ocr_res["engine_results"],
                "fused_boxes": annotated_boxes,
                "total_lines": len(annotated_boxes),
                "overlay_image_url": ocr_overlay_rel_path,
                "full_transcript": ocr_res["full_transcript"]
            },
            "gemini_validation": gemini_res,
            "extracted_fields": fields,
            "audit_summary": {
                "total_fields": len(fields),
                "confirmed_count": confirmed_count,
                "low_confidence_count": low_conf_count,
                "missing_count": missing_count,
                "overall_confidence": round(float(np.mean([v.get("confidence", 0.0) for v in fields.values()])), 3)
            }
        }
