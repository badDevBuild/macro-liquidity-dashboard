from __future__ import annotations

import math
import unittest


def oklch_luminance(lightness: float, chroma: float, hue: float) -> float:
    """Convert an OKLCH color to clipped linear-sRGB relative luminance."""
    angle = math.radians(hue)
    a = chroma * math.cos(angle)
    b = chroma * math.sin(angle)
    l_root = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_root = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_root = lightness - 0.0894841775 * a - 1.2914855480 * b
    l_value, m_value, s_value = l_root**3, m_root**3, s_root**3
    red = 4.0767416621 * l_value - 3.3077115913 * m_value + 0.2309699292 * s_value
    green = -1.2684380046 * l_value + 2.6097574011 * m_value - 0.3413193965 * s_value
    blue = -0.0041960863 * l_value - 0.7034186147 * m_value + 1.707614701 * s_value
    red, green, blue = (max(0.0, min(1.0, channel)) for channel in (red, green, blue))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(
    foreground: tuple[float, float, float],
    background: tuple[float, float, float],
) -> float:
    foreground_luminance = oklch_luminance(*foreground)
    background_luminance = oklch_luminance(*background)
    lighter = max(foreground_luminance, background_luminance)
    darker = min(foreground_luminance, background_luminance)
    return (lighter + 0.05) / (darker + 0.05)


class DesignContrastTests(unittest.TestCase):
    def assert_contrast(
        self,
        foreground: tuple[float, float, float],
        background: tuple[float, float, float],
        minimum: float,
        label: str,
    ) -> None:
        ratio = contrast_ratio(foreground, background)
        self.assertGreaterEqual(ratio, minimum, f"{label}: contrast {ratio:.2f}:1")

    def test_small_text_pairs_meet_wcag_aa(self) -> None:
        canvas = (0.974, 0.009, 166)
        accent_soft = (0.91, 0.038, 166)
        positive_soft = (0.92, 0.035, 155)
        warning_soft = (0.94, 0.04, 72)
        negative_soft = (0.93, 0.035, 28)
        pairs = [
            ((0.25, 0.024, 166), canvas, "primary text"),
            ((0.43, 0.021, 166), canvas, "secondary text"),
            ((0.53, 0.018, 166), canvas, "metadata text"),
            ((0.48, 0.078, 166), accent_soft, "selected controls"),
            ((0.49, 0.09, 155), positive_soft, "success status"),
            ((0.52, 0.105, 72), warning_soft, "warning status"),
            ((0.52, 0.13, 28), negative_soft, "error status"),
        ]
        for foreground, background, label in pairs:
            with self.subTest(label=label):
                self.assert_contrast(foreground, background, 4.5, label)

    def test_layer_identifier_pairs_meet_wcag_aa(self) -> None:
        pairs = [
            ((0.50, 0.075, 235), (0.925, 0.025, 235), "Fed layer"),
            ((0.51, 0.08, 75), (0.93, 0.03, 75), "fiscal layer"),
            ((0.49, 0.072, 166), (0.92, 0.03, 166), "money-market layer"),
            ((0.51, 0.058, 315), (0.93, 0.022, 315), "transmission layer"),
        ]
        for foreground, background, label in pairs:
            with self.subTest(label=label):
                self.assert_contrast(foreground, background, 4.5, label)

    def test_focus_ring_meets_nontext_contrast(self) -> None:
        self.assert_contrast(
            (0.55, 0.12, 166),
            (0.974, 0.009, 166),
            3.0,
            "focus ring",
        )


if __name__ == "__main__":
    unittest.main()
