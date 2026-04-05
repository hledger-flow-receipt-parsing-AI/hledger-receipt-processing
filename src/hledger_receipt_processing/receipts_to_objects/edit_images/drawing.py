"""Drawing utilities for image editing TUIs.

This module contains drawing functions used by the rotation and cropping TUIs.
These are extracted here so they can be reused by demos and tests without
importing the full application (which has heavy dependencies like torch).
"""

from typing import List

import cv2
import numpy as np


def draw_crop_overlay(
    image: np.ndarray, coords: List[float], active_corner: int
) -> np.ndarray:
    """Draw crop rectangle and crosshair overlay on an image.

    Args:
        image: BGR image (numpy array)
        coords: [x1, y1, x2, y2] normalized coordinates (0.0 to 1.0)
        active_corner: 0 for top-left, 1 for bottom-right

    Returns:
        Image with crop overlay drawn
    """
    img_copy = image.copy()
    h, w = img_copy.shape[:2]
    x1, y1, x2, y2 = (int(c * dim) for c, dim in zip(coords, [w, h, w, h]))
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    # Draw green rectangle for crop boundary
    if x2 > x1 and y2 > y1:
        cv2.rectangle(img_copy, (x1, y1), (x2, y2), (0, 255, 0), 2)

    # Draw red crosshair at active corner
    crosshair_x, crosshair_y = (x1, y1) if active_corner == 0 else (x2, y2)
    cv2.drawMarker(
        img_copy,
        (crosshair_x, crosshair_y),
        (0, 0, 255),
        markerType=cv2.MARKER_CROSS,
        markerSize=10,
        thickness=2,
    )
    return img_copy

