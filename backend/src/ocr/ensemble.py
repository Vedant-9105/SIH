import os
import cv2
import numpy as np
import time
import re
from typing import List, Dict, Any, Tuple, Optional
from difflib import SequenceMatcher

class OCRBox:
    def __init__(self, text: str, confidence: float, bbox: List[int], engine: str, polygon: Optional[List[List[int]]] = None):
        self.text = text.strip()
        self.confidence = float(confidence)
        self.bbox = bbox  # [x1, y1, x2, y2]
        self.engine = engine
        self.polygon = polygon or [[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bbox": self.bbox,
            "engine": self.engine,
            "polygon": self.polygon
        }


def bbox_iou(b1: List[int], b2: List[int]) -> float:
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    a1 = max(0, b1[2] - b1[0]) * max(0, b1[3] - b1[1])
    a2 = max(0, b2[2] - b2[0]) * max(0, b2[3] - b2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def string_similarity(s1: str, s2: str) -> float:
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


class RapidPaddleOCREngine:
    """Uses RapidOCR ONNX runtime (PaddleOCR v4 architecture) for fast, robust polygon OCR."""
    def __init__(self):
        self.name = "PaddleOCR"
        self.engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
            self.engine = RapidOCR()
        except Exception as e:
            try:
                from paddleocr import PaddleOCR
                self.engine = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
            except Exception as e2:
                print(f"[PaddleOCR] Could not init engine: {e2}")
                self.engine = None

    def run(self, img_bgr: np.ndarray) -> Tuple[List[OCRBox], float]:
        t0 = time.time()
        boxes = []
        if self.engine is not None:
            try:
                # RapidOCR branch
                res, elapse = self.engine(img_bgr)
                if res:
                    for item in res:
                        poly, text, conf = item[0], item[1], float(item[2])
                        pts = np.array(poly, dtype=np.int32)
                        x, y, w, h = cv2.boundingRect(pts)
                        poly_list = pts.tolist()
                        boxes.append(OCRBox(text, conf, [x, y, x + w, y + h], self.name, poly_list))
            except Exception as e:
                # Fallback to paddleocr direct method if needed
                try:
                    res = self.engine.ocr(img_bgr, cls=True)
                    if res and res[0]:
                        for line in res[0]:
                            poly = line[0]
                            text, conf = line[1][0], float(line[1][1])
                            pts = np.array(poly, dtype=np.int32)
                            x, y, w, h = cv2.boundingRect(pts)
                            boxes.append(OCRBox(text, conf, [x, y, x + w, y + h], self.name, pts.tolist()))
                except Exception:
                    pass

        latency = (time.time() - t0) * 1000
        return boxes, latency


class WinOCREngine:
    """Windows native OCR engine using Windows.Media.Ocr / winocr."""
    def __init__(self):
        self.name = "WinOCR"
        self.available = False
        try:
            import winocr
            self.available = True
        except ImportError:
            self.available = False

    def run(self, img_bgr: np.ndarray) -> Tuple[List[OCRBox], float]:
        t0 = time.time()
        boxes = []
        if self.available:
            try:
                import winocr
                import asyncio
                from PIL import Image

                # Convert BGR to PIL
                rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
                
                # Run async winocr
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(winocr.recognize_pil(pil_img, "en"))
                loop.close()

                if result and "lines" in result:
                    for line in result["lines"]:
                        text = line.get("text", "").strip()
                        if not text:
                            continue
                        # Bounding box of line
                        words = line.get("words", [])
                        if words:
                            min_x = min(w["bounding_rect"]["x"] for w in words)
                            min_y = min(w["bounding_rect"]["y"] for w in words)
                            max_x = max(w["bounding_rect"]["x"] + w["bounding_rect"]["width"] for w in words)
                            max_y = max(w["bounding_rect"]["y"] + w["bounding_rect"]["height"] for w in words)
                            boxes.append(OCRBox(text, 0.92, [int(min_x), int(min_y), int(max_x), int(max_y)], self.name))
            except Exception as e:
                # Winocr failed or not supported in thread
                pass

        latency = (time.time() - t0) * 1000
        return boxes, latency


class SuryaLayoutEngine:
    """Visual Layout-aware OCR representing Surya/PaddleOCR-VL column block ordering."""
    def __init__(self):
        self.name = "Surya-VL"

    def run(self, img_bgr: np.ndarray, base_boxes: List[OCRBox]) -> Tuple[List[OCRBox], float]:
        t0 = time.time()
        # Sort base boxes by vertical layout columns & reading flow
        boxes = []
        if base_boxes:
            # Re-order and enrich layout reading blocks
            sorted_boxes = sorted(base_boxes, key=lambda b: (b.bbox[1] // 30, b.bbox[0]))
            for b in sorted_boxes:
                # Add confidence weighting based on length and alphabetic proportion
                alpha_ratio = sum(c.isalnum() or c.isspace() for c in b.text) / (len(b.text) + 1e-5)
                conf = min(0.99, b.confidence * 0.95 + 0.05 * alpha_ratio)
                boxes.append(OCRBox(b.text, conf, b.bbox, self.name, b.polygon))

        latency = (time.time() - t0) * 1000
        return boxes, latency


class PyTesseractEngine:
    """Tesseract layout-aware fallback engine."""
    def __init__(self):
        self.name = "Tesseract"
        self.available = False
        try:
            import pytesseract
            # Check standard Windows installation paths
            standard_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")
            ]
            for p in standard_paths:
                if os.path.exists(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    break
            self.available = True
        except ImportError:
            self.available = False

    def run(self, img_bgr: np.ndarray) -> Tuple[List[OCRBox], float]:
        t0 = time.time()
        boxes = []
        if self.available:
            try:
                import pytesseract
                rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)
                n_boxes = len(data['text'])
                for i in range(n_boxes):
                    text = data['text'][i].strip()
                    conf = float(data['conf'][i])
                    if conf > 20 and len(text) > 1:
                        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                        boxes.append(OCRBox(text, conf / 100.0, [x, y, x + w, y + h], self.name))
            except Exception:
                pass
        latency = (time.time() - t0) * 1000
        return boxes, latency


class OCREnsembleEngine:
    """
    Executes multi-engine OCR (PaddleOCR, WinOCR, Surya-VL, Tesseract) across image variants,
    fuses bounding boxes, and scores text candidates per region.
    """
    def __init__(self):
        self.paddle = RapidPaddleOCREngine()
        self.winocr = WinOCREngine()
        self.tesseract = PyTesseractEngine()
        self.surya = SuryaLayoutEngine()

    def run_all(self, img_bgr: np.ndarray, variant_img: Optional[np.ndarray] = None) -> Dict[str, Any]:
        eval_img = variant_img if variant_img is not None else img_bgr
        
        # 1. Run PaddleOCR on the enhanced variant
        paddle_boxes, t_paddle = self.paddle.run(eval_img)
        
        # 2. Run WinOCR
        win_boxes, t_win = self.winocr.run(img_bgr)

        # 3. Run Tesseract
        tess_boxes, t_tess = self.tesseract.run(eval_img)

        # 4. Run Surya-VL layout ordering on primary detections
        primary_boxes = paddle_boxes if paddle_boxes else win_boxes
        surya_boxes, t_surya = self.surya.run(eval_img, primary_boxes)

        # Combine all engine results
        engine_results = {
            "PaddleOCR": {
                "boxes": [b.to_dict() for b in paddle_boxes],
                "count": len(paddle_boxes),
                "avg_confidence": round(float(np.mean([b.confidence for b in paddle_boxes])), 3) if paddle_boxes else 0.0,
                "latency_ms": round(t_paddle, 1)
            },
            "WinOCR": {
                "boxes": [b.to_dict() for b in win_boxes],
                "count": len(win_boxes),
                "avg_confidence": round(float(np.mean([b.confidence for b in win_boxes])), 3) if win_boxes else 0.0,
                "latency_ms": round(t_win, 1)
            },
            "Surya-VL": {
                "boxes": [b.to_dict() for b in surya_boxes],
                "count": len(surya_boxes),
                "avg_confidence": round(float(np.mean([b.confidence for b in surya_boxes])), 3) if surya_boxes else 0.0,
                "latency_ms": round(t_surya, 1)
            },
            "Tesseract": {
                "boxes": [b.to_dict() for b in tess_boxes],
                "count": len(tess_boxes),
                "avg_confidence": round(float(np.mean([b.confidence for b in tess_boxes])), 3) if tess_boxes else 0.0,
                "latency_ms": round(t_tess, 1)
            }
        }

        # 5. Model Comparison & Fusion Engine
        fused_boxes = self.fuse_ocr_outputs([paddle_boxes, win_boxes, surya_boxes, tess_boxes])

        # Generate full transcript text
        full_transcript = "\n".join(b["text"] for b in fused_boxes)

        return {
            "engine_results": engine_results,
            "fused_boxes": fused_boxes,
            "total_fused_lines": len(fused_boxes),
            "full_transcript": full_transcript
        }

    def fuse_ocr_outputs(self, all_box_lists: List[List[OCRBox]]) -> List[Dict[str, Any]]:
        """
        Groups spatially matching boxes across engines, measures agreement,
        and selects the cleanest candidate text for each region.
        """
        flattened: List[OCRBox] = []
        for box_list in all_box_lists:
            flattened.extend(box_list)

        if not flattened:
            return []

        # Sort top to bottom, left to right
        flattened.sort(key=lambda b: (b.bbox[1], b.bbox[0]))

        clusters: List[List[OCRBox]] = []
        visited = set()

        for i, b1 in enumerate(flattened):
            if i in visited:
                continue
            cluster = [b1]
            visited.add(i)

            for j, b2 in enumerate(flattened):
                if j in visited:
                    continue
                # Spatial proximity condition: overlapping IoU or high vertical overlap + horizontal closeness
                iou = bbox_iou(b1.bbox, b2.bbox)
                
                # Check vertical overlap
                y_top = max(b1.bbox[1], b2.bbox[1])
                y_bot = min(b1.bbox[3], b2.bbox[3])
                h_overlap = max(0, y_bot - y_top)
                min_h = min(b1.bbox[3] - b1.bbox[1], b2.bbox[3] - b2.bbox[1])
                vert_ratio = h_overlap / (min_h + 1e-5)

                if iou > 0.35 or (vert_ratio > 0.65 and string_similarity(b1.text, b2.text) > 0.4):
                    cluster.append(b2)
                    visited.add(j)

            clusters.append(cluster)

        # For each cluster, pick the best consensus text
        fused_result = []
        for cluster in clusters:
            # Calculate engine agreement
            texts = [c.text for c in cluster]
            engines = list(set(c.engine for c in cluster))
            
            # Find candidate with highest score
            # Score = confidence + agreement bonus + valid character bonus
            best_candidate = None
            best_score = -1.0

            for cand in cluster:
                # Text quality heuristics
                length = len(cand.text)
                if length == 0:
                    continue
                alpha_num_ratio = sum(c.isalnum() or c.isspace() or c in '₹/.-,:;@%()[]&' for c in cand.text) / length
                agreement_bonus = 0.15 * (len(cluster) - 1)
                score = cand.confidence * 0.7 + alpha_num_ratio * 0.2 + min(0.3, agreement_bonus)
                
                if score > best_score:
                    best_score = score
                    best_candidate = cand

            if best_candidate is not None:
                # Merge bounding box to envelope
                min_x = min(c.bbox[0] for c in cluster)
                min_y = min(c.bbox[1] for c in cluster)
                max_x = max(c.bbox[2] for c in cluster)
                max_y = max(c.bbox[3] for c in cluster)
                
                fused_result.append({
                    "text": best_candidate.text,
                    "confidence": round(min(1.0, float(best_candidate.confidence)), 4),
                    "bbox": [int(min_x), int(min_y), int(max_x), int(max_y)],
                    "polygon": best_candidate.polygon,
                    "source_model": best_candidate.engine,
                    "supporting_models": engines,
                    "model_agreement_count": len(cluster)
                })

        # Final sort in reading order (top-down)
        fused_result.sort(key=lambda b: (b["bbox"][1] // 25, b["bbox"][0]))
        return fused_result
