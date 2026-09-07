import os
import json
import base64
import cv2
import numpy as np
from typing import Dict, Any, Optional, List
from src.config import GEMINI_API_KEY

class GeminiMultimodalValidator:
    """
    Multimodal visual verification layer.
    Cross-checks OCR candidate fields directly against the image visual features.
    Strictly prevents hallucinations: never invents missing fields.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.client = None
        self._init_client()

    def _init_client(self):
        if not self.api_key:
            return
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
        except Exception:
            try:
                import google.generativeai as gai
                gai.configure(api_key=self.api_key)
                self.client = "google.generativeai"
            except Exception:
                self.client = None

    def validate(self, img_bgr: np.ndarray, candidate_fields: Dict[str, Any], raw_ocr_lines: List[str]) -> Dict[str, Any]:
        """
        Runs multimodal visual validation on the cropped product image and extracted candidate fields.
        """
        if not self.client:
            return {
                "status": "SKIPPED_NO_API_KEY",
                "message": "Gemini API key not configured. Using deterministic ensemble verification.",
                "verified_fields": candidate_fields,
                "corrections": {},
                "hallucination_flags": []
            }

        # Encode image to JPEG base64
        _, buffer = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
        img_bytes = buffer.tobytes()

        prompt = f"""
You are a Packaged-Product Multimodal Verification Engine.
You have been provided:
1. The cropped image of a packaged commodity.
2. The candidate fields extracted by a multi-model OCR ensemble.

CANDIDATE FIELDS EXTRACTED BY OCR:
{json.dumps(candidate_fields, indent=2)}

RAW OCR TRANSCRIPT DETECTED:
{chr(10).join(f"- {line}" for line in raw_ocr_lines[:40])}

YOUR TASK (STRICT RULES):
1. Visually inspect the image and verify every single candidate field.
2. Accuracy > Completeness. If a field is NOT clearly visible on the packaging, DO NOT invent or guess it. Set value to null and status to 'MISSING'.
3. If OCR has minor typos (e.g. '80g' misread as '809', 'MRP Rs.' misread as 'MRP Hs.', 'g' vs 'q'), correct it and set status to 'CONFIRMED' with a correction note.
4. If a field is partially visible or blurry, set status to 'LOW_CONFIDENCE'.
5. For each field, provide:
   - "value": string or null
   - "raw_text": exact text visible on image
   - "status": "CONFIRMED" | "LOW_CONFIDENCE" | "CONFLICTING" | "MISSING"
   - "visual_notes": brief rationale of what is visible

Respond ONLY with a valid JSON object in this exact schema:
{{
  "verified_fields": {{
     "product_name": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "brand_name": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "manufacturer_name": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "manufacturer_address": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "net_quantity": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "mrp": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "currency": {{"value": "INR", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "batch_number": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "manufacturing_date": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "expiry_date": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "consumer_care": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "country_of_origin": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "barcode_or_qr": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}},
     "other_declarations": {{"value": "...", "raw_text": "...", "status": "CONFIRMED", "visual_notes": "..."}}
  }},
  "corrections": {{}},
  "overall_visual_confidence": 0.95
}}
"""

        # Candidate model names in priority order supported by Google AI Studio
        model_candidates = [
            'gemini-3.6-flash',
            'gemini-2.5-flash',
            'gemini-flash-latest',
            'gemini-flash-lite-latest',
            'gemini-pro-latest'
        ]
        res_text = None
        last_err = None

        # Try cached working model first if known
        if hasattr(self, '_working_model') and self._working_model:
            model_candidates = [self._working_model] + [m for m in model_candidates if m != self._working_model]

        for m_name in model_candidates:
            try:
                if hasattr(self.client, "models"):
                    # google.genai Client
                    from google.genai import types
                    response = self.client.models.generate_content(
                        model=m_name,
                        contents=[
                            types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg'),
                            prompt
                        ]
                    )
                    res_text = response.text
                    self._working_model = m_name
                    break
                else:
                    # google.generativeai legacy
                    import google.generativeai as gai
                    from PIL import Image
                    import io
                    pil_img = Image.open(io.BytesIO(img_bytes))
                    model = gai.GenerativeModel(m_name)
                    response = model.generate_content([prompt, pil_img])
                    res_text = response.text
                    self._working_model = m_name
                    break
            except Exception as e:
                last_err = e
                continue

        if not res_text:
            return {
                "status": "FALLBACK_RULE_VALIDATION",
                "message": f"Gemini visual verification error: {str(last_err)}",
                "verified_fields": candidate_fields,
                "corrections": {},
                "hallucination_flags": []
            }

        try:
            # Parse JSON from markdown code block or plain text
            cleaned = res_text.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            parsed = json.loads(cleaned)
            parsed["status"] = "SUCCESS_GEMINI_VERIFIED"
            return parsed
        except Exception as e:
            return {
                "status": "FALLBACK_RULE_VALIDATION",
                "message": f"Gemini JSON parse error: {str(e)}",
                "verified_fields": candidate_fields,
                "corrections": {},
                "hallucination_flags": []
            }
