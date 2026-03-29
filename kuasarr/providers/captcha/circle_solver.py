# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)
"""
OpenCV-based Circle-Captcha solver for Filecrypt.

Uses computer vision to detect incomplete circles in CAPTCHA images
and calculates optimal click coordinates without external services.
"""

import random
from io import BytesIO
from typing import Optional, Tuple

import numpy as np
import requests
from PIL import Image

from kuasarr.providers.log import debug, info

# Constants for circle detection
CANNY_THRESHOLD1 = 30
CANNY_THRESHOLD2 = 100
CANNY_THRESHOLD1_ALT = 50
CANNY_THRESHOLD2_ALT = 150

HOUGH_DP = 1
HOUGH_MIN_DIST = 50
HOUGH_PARAM1 = 50
HOUGH_PARAM2 = 30
HOUGH_MIN_RADIUS = 30
HOUGH_MAX_RADIUS = 150

# Gap detection parameters
GAP_ANGLE_STEP = 15
GAP_RADIUS_FACTOR = 0.7


def load_captcha_image(session: requests.Session, domain: str) -> Optional[np.ndarray]:
    """
    Load circle captcha image from Filecrypt.

    Args:
        session: requests Session with valid cookies
        domain: Filecrypt domain (e.g., "filecrypt.cc")

    Returns:
        OpenCV image array (grayscale) or None if failed
    """
    try:
        url = f"https://{domain}/captcha/circle.php"
        response = session.get(url, timeout=10)
        if response.status_code != 200:
            info(f"Failed to load circle captcha image: HTTP {response.status_code}")
            return None

        # Convert to PIL Image then to OpenCV format
        image = Image.open(BytesIO(response.content))

        # Try to convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Convert PIL to numpy array (OpenCV format)
        import cv2
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

        return gray

    except Exception as e:
        info(f"Error loading captcha image: {e}")
        return None


def detect_circles(gray_image: np.ndarray) -> Optional[np.ndarray]:
    """
    Detect circles in the grayscale image using HoughCircles.

    Args:
        gray_image: Grayscale OpenCV image array

    Returns:
        Array of detected circles [x, y, radius] or None
    """
    try:
        import cv2

        # Preprocess: histogram equalization for better contrast
        equalized = cv2.equalizeHist(gray_image)

        # Try multiple Canny thresholds for better detection
        circles_list = []

        for thresh1, thresh2 in [
            (CANNY_THRESHOLD1, CANNY_THRESHOLD2),
            (CANNY_THRESHOLD1_ALT, CANNY_THRESHOLD2_ALT)
        ]:
            # Edge detection
            edges = cv2.Canny(equalized, thresh1, thresh2)

            # Hough Circle detection
            detected = cv2.HoughCircles(
                edges,
                cv2.HOUGH_GRADIENT,
                dp=HOUGH_DP,
                minDist=HOUGH_MIN_DIST,
                param1=HOUGH_PARAM1,
                param2=HOUGH_PARAM2,
                minRadius=HOUGH_MIN_RADIUS,
                maxRadius=HOUGH_MAX_RADIUS
            )

            if detected is not None:
                circles_list.append(detected)

        # Merge results from different thresholds
        if circles_list:
            # Flatten and combine all detected circles
            all_circles = np.vstack([c[0] for c in circles_list if c is not None and len(c) > 0])

            # Remove duplicates (circles that are very close to each other)
            unique_circles = []
            for circle in all_circles:
                x, y, r = circle
                is_duplicate = False
                for uc in unique_circles:
                    ux, uy, ur = uc
                    # Check if this circle is close to an existing one
                    distance = np.sqrt((x - ux) ** 2 + (y - uy) ** 2)
                    if distance < 20 and abs(r - ur) < 10:  # Threshold for duplicate
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_circles.append([x, y, r])

            if unique_circles:
                return np.array([unique_circles])

        return None

    except Exception as e:
        debug(f"Error detecting circles: {e}")
        return None


def find_incomplete_circle(
    gray_image: np.ndarray,
    circles: np.ndarray
) -> Optional[Tuple[float, float, float]]:
    """
    Find the incomplete circle by analyzing gaps in the circumference.

    Args:
        gray_image: Grayscale OpenCV image array
        circles: Detected circles array

    Returns:
        Tuple of (x, y, radius) for the incomplete circle or None
    """
    try:
        import cv2

        best_circle = None
        max_gap_score = -1

        for circle in circles[0]:
            x, y, radius = circle
            x, y, radius = int(x), int(y), int(radius)

            # Sample points around the circle
            gap_score = 0
            gap_angles = []

            for angle in range(0, 360, GAP_ANGLE_STEP):
                rad = np.radians(angle)
                # Calculate point on circle
                px = int(x + radius * np.cos(rad))
                py = int(y + radius * np.sin(rad))

                # Check if point is within image bounds
                h, w = gray_image.shape
                if 0 <= px < w and 0 <= py < h:
                    # Get pixel intensity
                    intensity = gray_image[py, px]
                    # Dark pixel indicates part of the circle is present
                    # Bright pixel indicates a gap
                    if intensity > 200:  # Threshold for gap detection
                        gap_score += 1
                        gap_angles.append(angle)

            # Also check inner/outer edges for thickness
            inner_gap = 0
            outer_gap = 0

            for angle in range(0, 360, GAP_ANGLE_STEP * 2):
                rad = np.radians(angle)
                # Inner point
                ix = int(x + (radius - 2) * np.cos(rad))
                iy = int(y + (radius - 2) * np.sin(rad))
                # Outer point
                ox = int(x + (radius + 2) * np.cos(rad))
                oy = int(y + (radius + 2) * np.sin(rad))

                h, w = gray_image.shape
                if 0 <= ix < w and 0 <= iy < h:
                    if gray_image[iy, ix] > 200:
                        inner_gap += 1
                if 0 <= ox < w and 0 <= oy < h:
                    if gray_image[oy, ox] > 200:
                        outer_gap += 1

            # Combined gap score (higher = more incomplete)
            total_gap = gap_score + (inner_gap + outer_gap) // 2

            # Calculate continuity - we want a circle with a clear single gap
            if gap_angles:
                # Sort angles and find consecutive gaps
                gap_angles.sort()
                max_consecutive = 1
                current_consecutive = 1

                for i in range(1, len(gap_angles)):
                    if gap_angles[i] - gap_angles[i - 1] <= GAP_ANGLE_STEP * 2:
                        current_consecutive += 1
                    else:
                        max_consecutive = max(max_consecutive, current_consecutive)
                        current_consecutive = 1

                max_consecutive = max(max_consecutive, current_consecutive)

                # Score: prefer circles with one clear gap (high consecutive gaps)
                # but not too many scattered gaps
                gap_quality = max_consecutive / max(len(gap_angles), 1)
                adjusted_score = total_gap * gap_quality

                if adjusted_score > max_gap_score:
                    max_gap_score = adjusted_score
                    best_circle = (float(x), float(y), float(radius))

        return best_circle

    except Exception as e:
        debug(f"Error finding incomplete circle: {e}")
        return None


def calculate_click_coordinates(
    circle: Tuple[float, float, float]
) -> Tuple[int, int]:
    """
    Calculate click coordinates within the incomplete circle.

    Args:
        circle: Tuple of (x, y, radius)

    Returns:
        Tuple of (x, y) click coordinates
    """
    cx, cy, radius = circle

    # Click at a random position within 70% of the radius
    # This should be inside the circle but not at the exact center
    click_radius = radius * GAP_RADIUS_FACTOR

    # Random angle for variety
    angle = random.uniform(0, 2 * np.pi)

    # Calculate position
    click_x = int(cx + click_radius * np.cos(angle))
    click_y = int(cy + click_radius * np.sin(angle))

    return click_x, click_y


def solve_circle_captcha(
    session: requests.Session,
    domain: str
) -> Optional[Tuple[int, int]]:
    """
    Solve Filecrypt circle captcha using computer vision.

    Args:
        session: requests Session with valid cookies
        domain: Filecrypt domain

    Returns:
        Tuple of (x, y) coordinates to click, or None if solving failed
    """
    try:
        import cv2
    except ImportError:
        info("OpenCV (cv2) not installed. Cannot solve circle captcha.")
        return None

    # Load the captcha image
    gray_image = load_captcha_image(session, domain)
    if gray_image is None:
        return None

    # Detect circles
    circles = detect_circles(gray_image)
    if circles is None or len(circles) == 0:
        debug("No circles detected in captcha image")
        return None

    debug(f"Detected {len(circles[0])} circles")

    # Find the incomplete circle (the one with a gap)
    incomplete = find_incomplete_circle(gray_image, circles)
    if incomplete is None:
        debug("Could not identify incomplete circle")
        return None

    # Calculate click coordinates
    click_x, click_y = calculate_click_coordinates(incomplete)

    debug(f"Circle captcha solution: ({click_x}, {click_y})")

    return click_x, click_y


def fallback_random_coordinates() -> Tuple[int, int]:
    """
    Generate random coordinates as fallback.

    Returns:
        Random (x, y) coordinates within typical button range
    """
    return random.randint(100, 200), random.randint(100, 200)
