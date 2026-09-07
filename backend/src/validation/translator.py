import re
from typing import Dict, Any, List, Optional

class MultilingualTranslator:
    """
    Translates non-English or multilingual OCR text using Google Translate (deep-translator).
    Strictly preserves the original raw OCR text and uses translation solely for semantic understanding.
    """
    def __init__(self):
        self.translator = None
        self._init_translator()

    def _init_translator(self):
        try:
            from deep_translator import GoogleTranslator
            self.translator = GoogleTranslator(source='auto', target='en')
        except Exception:
            self.translator = None

    def is_non_english(self, text: str) -> bool:
        """Checks if text contains non-ASCII or Indic / foreign script characters."""
        if not text:
            return False
        # Match Devanagari (\u0900-\u097F), Tamil (\u0B80-\u0BFF), Telugu (\u0C00-\u0C7F), Bengali (\u0980-\u09FF), etc.
        indic_regex = re.compile(r'[\u0900-\u0D7F\u0600-\u06FF\u4E00-\u9FFF]')
        return bool(indic_regex.search(text))

    def translate_text(self, text: str) -> Dict[str, Any]:
        """Translates text to English if needed, preserving original raw text."""
        if not text or not text.strip():
            return {
                "original_text": text,
                "translated_text": text,
                "is_translated": False,
                "source_language": "en"
            }

        if not self.is_non_english(text):
            return {
                "original_text": text,
                "translated_text": text,
                "is_translated": False,
                "source_language": "en"
            }

        if self.translator is not None:
            try:
                translated = self.translator.translate(text)
                return {
                    "original_text": text,
                    "translated_text": translated,
                    "is_translated": True,
                    "source_language": "auto_detected"
                }
            except Exception as e:
                pass

        return {
            "original_text": text,
            "translated_text": text,
            "is_translated": False,
            "source_language": "unknown"
        }

    def process_ocr_boxes(self, ocr_boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Scans OCR boxes and annotates multilingual fields with translation."""
        annotated = []
        for box in ocr_boxes:
            box_copy = dict(box)
            raw = box_copy.get("text", "")
            if self.is_non_english(raw):
                trans_res = self.translate_text(raw)
                box_copy["translated_text"] = trans_res["translated_text"]
                box_copy["is_multilingual"] = True
            else:
                box_copy["translated_text"] = raw
                box_copy["is_multilingual"] = False
            annotated.append(box_copy)
        return annotated
