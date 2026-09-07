import math
from typing import Dict, List, Any, Optional, Tuple

class SpatialBox:
    def __init__(self, text: str, bbox: List[int], confidence: float, source_model: str, id_idx: int = 0):
        self.text = text.strip()
        self.bbox = bbox  # [x1, y1, x2, y2]
        self.confidence = float(confidence)
        self.source_model = source_model
        self.id_idx = id_idx

        # Geometric properties
        self.x1, self.y1, self.x2, self.y2 = bbox
        self.w = max(1, self.x2 - self.x1)
        self.h = max(1, self.y2 - self.y1)
        self.xc = (self.x1 + self.x2) / 2.0
        self.yc = (self.y1 + self.y2) / 2.0


def compute_spatial_relation(label_box: SpatialBox, value_box: SpatialBox) -> Tuple[str, float, float, float, str]:
    """
    Computes spatial direction, Euclidean center distance, alignment score, and relationship tag.
    Returns: (relation_type, distance_px, alignment_score, proximity_score, detailed_reason)
    """
    dx = value_box.xc - label_box.xc
    dy = value_box.yc - label_box.yc
    dist = math.sqrt(dx**2 + dy**2)

    # Line height reference
    ref_h = max(10.0, (label_box.h + value_box.h) / 2.0)
    norm_dist = dist / ref_h

    # Horizontal & vertical overlaps
    y_overlap = max(0, min(label_box.y2, value_box.y2) - max(label_box.y1, value_box.y1))
    x_overlap = max(0, min(label_box.x2, value_box.x2) - max(label_box.x1, value_box.x1))

    horiz_overlap_ratio = y_overlap / ref_h
    vert_overlap_ratio = x_overlap / max(10.0, min(label_box.w, value_box.w))

    relation = "UNALIGNED_NEIGHBOR"
    alignment_score = 0.5
    reason = f"Distance: {dist:.1f}px (dx={dx:.1f}, dy={dy:.1f})"

    # 1. IN SAME BOX / COMPOSITE ELEMENT
    if label_box.id_idx == value_box.id_idx:
        return "SAME_LINE_COMPOSITE", 0.0, 1.0, 1.0, "Label and value detected inside the exact same OCR line/box"

    # Vertical dominant relationship (|dy| > |dx| and significant vertical displacement)
    if abs(dy) > abs(dx) and abs(dy) >= ref_h * 0.5:
        if dy > 0 and abs(dx) <= max(label_box.w, value_box.w) * 1.5:
            relation = "VERTICAL_BELOW"
            horiz_misalignment = abs(dx) / (max(label_box.w, value_box.w) * 1.5)
            alignment_score = max(0.2, 1.0 - horiz_misalignment)
            reason = f"Positioned directly BELOW in column stack (dy={dy:.0f}px, dx={dx:.0f}px)"
        elif dy < 0 and abs(dx) <= max(label_box.w, value_box.w) * 1.5:
            relation = "VERTICAL_ABOVE"
            horiz_misalignment = abs(dx) / (max(label_box.w, value_box.w) * 1.5)
            alignment_score = max(0.2, 0.85 - horiz_misalignment)
            reason = f"Positioned directly ABOVE label in column stack (dy={dy:.0f}px, dx={dx:.0f}px)"

    # Horizontal dominant relationship (|dx| >= |dy| and within vertical line height)
    elif abs(dy) <= ref_h * 1.2:
        if dx > 0:
            relation = "HORIZONTAL_RIGHT"
            vert_misalignment = abs(dy) / (ref_h * 1.2)
            alignment_score = max(0.2, 1.0 - vert_misalignment)
            reason = f"Positioned to the RIGHT on the same horizontal row (dx={dx:.0f}px, dy={dy:.0f}px)"
        elif dx < 0:
            relation = "HORIZONTAL_LEFT"
            vert_misalignment = abs(dy) / (ref_h * 1.2)
            alignment_score = max(0.2, 0.9 - vert_misalignment)
            reason = f"Positioned to the LEFT in reversed order (dx={dx:.0f}px, dy={dy:.0f}px)"

    # Grid / Table Cell fallback
    elif norm_dist <= 5.0:
        relation = "GRID_TABLE_CELL"
        alignment_score = 0.65
        reason = f"Nearby cell in table/coding matrix (distance={dist:.0f}px)"
        reason = f"Nearby cell in table/coding matrix (distance={dist:.0f}px)"

    # Compute proximity score (exponential decay over distance)
    proximity_score = max(0.05, math.exp(-norm_dist / 4.0))

    return relation, dist, alignment_score, proximity_score, reason


class SpatialAssociationEngine:
    """
    Finds the most probable value box for a given semantic label using 2D spatial geometry,
    alignment constraints, distance normalization, and expected pattern scoring.
    """
    def __init__(self):
        pass

    def evaluate_candidates(
        self,
        label_box: SpatialBox,
        candidate_boxes: List[SpatialBox],
        pattern_validator_fn,
        max_search_dist_norm: float = 12.0
    ) -> List[Dict[str, Any]]:
        """
        Evaluates all candidate text boxes in the 2D plane against a semantic label box.
        """
        scored_candidates = []

        for c_box in candidate_boxes:
            # Skip the label box itself when searching for associated external value
            if c_box.id_idx == label_box.id_idx:
                continue

            # 1. Test value validity via pattern validator function
            val_result = pattern_validator_fn(c_box.text)
            if not val_result:
                continue

            # 2. Compute spatial relation & geometry
            relation, dist, align_score, prox_score, reason = compute_spatial_relation(label_box, c_box)

            ref_h = max(10.0, (label_box.h + c_box.h) / 2.0)
            norm_dist = dist / ref_h

            if norm_dist > max_search_dist_norm:
                continue

            # Spatial relationship multiplier
            rel_multiplier = {
                "SAME_LINE_COMPOSITE": 1.0,
                "HORIZONTAL_RIGHT": 0.95,
                "VERTICAL_BELOW": 0.92,
                "HORIZONTAL_LEFT": 0.85,
                "VERTICAL_ABOVE": 0.80,
                "GRID_TABLE_CELL": 0.70,
                "UNALIGNED_NEIGHBOR": 0.40
            }.get(relation, 0.40)

            # Composite confidence score
            # Score = 0.35 * Proximity + 0.30 * Alignment + 0.20 * RelMultiplier + 0.15 * OCRConfidence
            total_conf = (
                0.35 * prox_score +
                0.30 * align_score +
                0.20 * rel_multiplier +
                0.15 * min(1.0, c_box.confidence)
            )

            scored_candidates.append({
                "value_data": val_result,
                "raw_text": c_box.text,
                "value_box": c_box,
                "relation": relation,
                "distance_px": round(dist, 1),
                "alignment_score": round(align_score, 3),
                "proximity_score": round(prox_score, 3),
                "confidence": round(total_conf, 3),
                "reason": reason
            })

        # Sort by composite confidence score descending
        scored_candidates.sort(key=lambda x: x["confidence"], reverse=True)
        return scored_candidates
