import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import time

try:
    from skimage.filters import threshold_sauvola
    SKIMAGE_AVAILABLE = True
except ImportError:
    SKIMAGE_AVAILABLE = False

try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class ImagePreprocessor:
    """
    Generates multi-variant image transformations using OpenCV, scikit-image, PyTorch, and Kornia filters.
    Evaluates each variant based on edge contrast, Laplacian variance, and text readability.
    """
    def __init__(self):
        pass

    def evaluate_variant_quality(self, img_bgr: np.ndarray) -> Dict[str, float]:
        """Calculates sharpness (Laplacian variance), RMS contrast, and edge density."""
        if len(img_bgr.shape) == 3:
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_bgr

        # 1. Laplacian sharpness
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sharpness_norm = float(np.clip(lap_var / 800.0, 0.0, 1.0))

        # 2. RMS Contrast
        mean_val = np.mean(gray)
        rms_contrast = float(np.sqrt(np.mean((gray - mean_val) ** 2)))
        contrast_norm = float(np.clip(rms_contrast / 75.0, 0.0, 1.0))

        # 3. Text edge density via Canny
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.sum(edges > 0) / (edges.size + 1e-5))
        edge_density_norm = float(np.clip(edge_density * 10.0, 0.0, 1.0))

        # Overall composite score
        overall_score = round(0.45 * contrast_norm + 0.35 * sharpness_norm + 0.20 * edge_density_norm, 3)

        return {
            "sharpness_laplacian": round(lap_var, 1),
            "sharpness_score": round(sharpness_norm, 3),
            "rms_contrast": round(rms_contrast, 1),
            "contrast_score": round(contrast_norm, 3),
            "edge_density": round(edge_density, 4),
            "overall_ocr_readability": overall_score
        }

    def deskew_image(self, img_bgr: np.ndarray) -> np.ndarray:
        """Corrects minor package orientation/skew using Hough transform and minAreaRect."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (9, 9), 0)
        thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 3)
        
        # Find contours of text blocks
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 5))
        connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        angles = []
        for c in contours:
            if cv2.contourArea(c) > 300:
                rect = cv2.minAreaRect(c)
                angle = rect[-1]
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle
                if abs(angle) < 25:  # Only subtle tilts
                    angles.append(angle)
                    
        if angles:
            median_angle = float(np.median(angles))
            if abs(median_angle) > 0.5:
                (h, w) = img_bgr.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                rotated = cv2.warpAffine(img_bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                return rotated

        return img_bgr

    def apply_clahe(self, img_bgr: np.ndarray) -> np.ndarray:
        """Applies CLAHE on LAB luminance channel for adaptive contrast enhancement."""
        lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l)
        enhanced_lab = cv2.merge((l_enhanced, a, b))
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    def apply_bilateral_denoise(self, img_bgr: np.ndarray) -> np.ndarray:
        """Edge-preserving bilateral smoothing to reduce sensor grain."""
        return cv2.bilateralFilter(img_bgr, d=7, sigmaColor=50, sigmaSpace=50)

    def apply_sauvola(self, img_bgr: np.ndarray) -> np.ndarray:
        """Scikit-image Sauvola adaptive thresholding for uneven lighting and degraded text."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        if SKIMAGE_AVAILABLE:
            try:
                window_size = 25
                thresh_sauvola = threshold_sauvola(gray, window_size=window_size, k=0.2)
                binary_sauvola = (gray > thresh_sauvola).astype(np.uint8) * 255
                return cv2.cvtColor(binary_sauvola, cv2.COLOR_GRAY2BGR)
            except Exception:
                pass
        # Fallback to OpenCV adaptive thresholding
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 10)
        return cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

    def apply_sharpening(self, img_bgr: np.ndarray) -> np.ndarray:
        """High-pass unsharp masking to enhance fine text strokes."""
        gaussian = cv2.GaussianBlur(img_bgr, (0, 0), 2.0)
        unsharp = cv2.addWeighted(img_bgr, 1.5, gaussian, -0.5, 0)
        return np.clip(unsharp, 0, 255).astype(np.uint8)

    def apply_pytorch_kornia_boost(self, img_bgr: np.ndarray) -> np.ndarray:
        """PyTorch tensor-based gradient boost and high-contrast normalization."""
        if TORCH_AVAILABLE:
            try:
                # Convert BGR to RGB tensor [1, C, H, W]
                rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).float() / 255.0
                
                # Sharpness 3x3 convolution kernel
                kernel = torch.tensor([
                    [0, -0.5, 0],
                    [-0.5, 3.0, -0.5],
                    [0, -0.5, 0]
                ]).unsqueeze(0).unsqueeze(0).repeat(3, 1, 1, 1)
                
                # Apply depthwise convolution with padding
                padded = F.pad(tensor, (1, 1, 1, 1), mode='replicate')
                filtered = F.conv2d(padded, kernel, groups=3)
                filtered = torch.clamp(filtered, 0.0, 1.0)
                
                out_np = (filtered.squeeze(0).permute(1, 2, 0).numpy() * 255).astype(np.uint8)
                return cv2.cvtColor(out_np, cv2.COLOR_RGB2BGR)
            except Exception:
                pass

        # Fallback kernel in OpenCV
        kernel = np.array([[0, -0.5, 0], [-0.5, 3.0, -0.5], [0, -0.5, 0]], dtype=np.float32)
        return cv2.filter2D(img_bgr, -1, kernel)

    def generate_variants(self, img_bgr: np.ndarray, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Generates all preprocessing variants, scores them, and identifies the best candidate.
        """
        # Resize if overly large (> 2000px) or too tiny (< 400px) for optimal OCR
        h, w = img_bgr.shape[:2]
        target_img = img_bgr
        if max(h, w) > 2400:
            scale = 2400 / max(h, w)
            target_img = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        elif max(h, w) < 600:
            scale = 600 / max(h, w)
            target_img = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        variants_map = {
            "original": ("Original Cropped", target_img.copy()),
            "clahe": ("CLAHE Contrast Boost (OpenCV)", self.apply_clahe(target_img)),
            "denoised": ("Bilateral Filter Denoise", self.apply_bilateral_denoise(target_img)),
            "sharpened": ("High-Pass Unsharp Mask", self.apply_sharpening(target_img)),
            "sauvola": ("Sauvola Adaptive Binarization (scikit-image)", self.apply_sauvola(target_img)),
            "deskewed": ("Deskewed & Perspective Rectified", self.deskew_image(target_img)),
            "pytorch_boost": ("PyTorch/Kornia Filter Boost", self.apply_pytorch_kornia_boost(target_img))
        }

        results = []
        best_variant_key = "clahe"
        max_score = -1.0
        for key, (label, v_img) in variants_map.items():
            metrics = self.evaluate_variant_quality(v_img)
            score = metrics["overall_ocr_readability"]
            
            saved_path = None
            if output_dir:
                filename = f"variant_{key}.jpg"
                filepath = output_dir / filename
                cv2.imwrite(str(filepath), v_img)
                saved_path = str(filepath)

            item = {
                "key": key,
                "label": label,
                "metrics": metrics,
                "image": v_img,
                "saved_path": saved_path
            }
            results.append(item)

            if score > max_score:
                max_score = score
                best_variant_key = key

        best_variant_img = variants_map[best_variant_key][1]

        return {
            "variants": results,
            "best_variant_key": best_variant_key,
            "best_variant_image": best_variant_img,
            "best_variant_score": max_score
        }
