#!/usr/bin/env python3
"""Synthetic handwritten-style marking and grime textures for the Isaac shipyard panel scene.

Outputs (all synthetic and generated from a seed; nothing is transcribed from a photograph):

* ``panel_center_albedo.png`` centre panel base colour with the hand-drawn memo baked in
* ``panel_side_albedo.png``   side-wing base colour (no text)
* ``marking_layer.png``       the memo alone as straight-alpha RGBA for inspection/provenance
* ``marking_preview.png``     crop around the memo for quick visual checks
* ``marking.json``            seed, parameters, glyph-set version and SHA-256 of every file

Glyphs are hand-authored single-stroke polylines (no TrueType font). Each run jitters slant,
spacing, baseline, pressure and adds skips, grain, smudges and drips so the result reads as
paint-marker or chalk handwriting rather than rotated print. Plain numpy + Pillow only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

GLYPH_SET_VERSION = "shipyard-stroke-glyphs.v2"
SUPERSAMPLE = 2


def _ellipse(cx: float, cy: float, rx: float, ry: float, n: int = 14, start_deg: float = 90.0,
             turn: float = 1.05, clockwise: bool = False) -> list[tuple[float, float]]:
    sweep = -1.0 if clockwise else 1.0
    return [(cx + rx * math.cos(math.radians(start_deg) + sweep * turn * 2 * math.pi * i / n),
             cy + ry * math.sin(math.radians(start_deg) + sweep * turn * 2 * math.pi * i / n))
            for i in range(n + 1)]


def _s(pts: list[tuple[float, float]]) -> dict[str, Any]:
    return {"pts": pts, "smooth": False}


def _c(pts: list[tuple[float, float]]) -> dict[str, Any]:
    return {"pts": pts, "smooth": True}


# Unit glyphs: baseline y=0, cap height y=1, pen advance ``adv`` (fraction of height).
GLYPHS: dict[str, dict[str, Any]] = {
    "0": {"adv": 0.72, "strokes": [_c(_ellipse(0.36, 0.5, 0.27, 0.5))]},
    "1": {"adv": 0.50, "strokes": [_s([(0.12, 0.74), (0.36, 1.0), (0.36, 0.0)])]},
    "2": {"adv": 0.72, "strokes": [_c([(0.08, 0.76), (0.2, 0.96), (0.42, 1.0), (0.62, 0.88), (0.62, 0.66),
                                        (0.4, 0.42), (0.08, 0.04)]), _s([(0.06, 0.02), (0.7, 0.0)])]},
    "3": {"adv": 0.72, "strokes": [_c([(0.1, 0.9), (0.3, 1.0), (0.58, 0.92), (0.6, 0.7), (0.42, 0.56)]),
                                   _c([(0.4, 0.56), (0.64, 0.46), (0.66, 0.18), (0.42, 0.0), (0.1, 0.1)])]},
    "4": {"adv": 0.74, "strokes": [_s([(0.52, 0.0), (0.52, 1.0), (0.06, 0.32), (0.72, 0.32)])]},
    "5": {"adv": 0.72, "strokes": [_s([(0.64, 1.0), (0.16, 1.0), (0.1, 0.56)]),
                                   _c([(0.1, 0.56), (0.36, 0.66), (0.62, 0.54), (0.66, 0.24), (0.42, 0.0), (0.08, 0.12)])]},
    "6": {"adv": 0.72, "strokes": [_c([(0.6, 0.96), (0.36, 1.0), (0.14, 0.72), (0.08, 0.3), (0.24, 0.02), (0.56, 0.04),
                                        (0.66, 0.3), (0.52, 0.5), (0.24, 0.48), (0.1, 0.34)])]},
    "7": {"adv": 0.68, "strokes": [_s([(0.06, 1.0), (0.68, 1.0), (0.3, 0.0)])]},
    "8": {"adv": 0.72, "strokes": [_c([(0.4, 0.52), (0.18, 0.7), (0.22, 0.94), (0.44, 1.0), (0.62, 0.9), (0.6, 0.68),
                                        (0.38, 0.52), (0.14, 0.36), (0.12, 0.1), (0.4, 0.0), (0.66, 0.1), (0.66, 0.36), (0.4, 0.52)])]},
    "9": {"adv": 0.72, "strokes": [_c([(0.62, 0.62), (0.44, 0.52), (0.18, 0.6), (0.1, 0.84), (0.34, 1.0), (0.6, 0.9),
                                        (0.66, 0.6), (0.58, 0.26), (0.36, 0.0), (0.12, 0.06)])]},
    "A": {"adv": 0.80, "strokes": [_s([(0.04, 0.0), (0.4, 1.0), (0.78, 0.0)]), _s([(0.2, 0.38), (0.62, 0.38)])]},
    "B": {"adv": 0.72, "strokes": [_s([(0.12, 0.0), (0.14, 1.0)]),
                                   _c([(0.14, 1.0), (0.46, 1.0), (0.62, 0.86), (0.58, 0.62), (0.14, 0.54)]),
                                   _c([(0.14, 0.54), (0.54, 0.52), (0.7, 0.3), (0.6, 0.06), (0.12, 0.0)])]},
    "C": {"adv": 0.72, "strokes": [_c([(0.68, 0.84), (0.5, 1.0), (0.2, 0.9), (0.08, 0.5), (0.2, 0.1), (0.5, 0.0), (0.7, 0.14)])]},
    "D": {"adv": 0.74, "strokes": [_s([(0.12, 0.0), (0.14, 1.0)]),
                                   _c([(0.14, 1.0), (0.44, 1.0), (0.7, 0.76), (0.72, 0.28), (0.48, 0.0), (0.12, 0.0)])]},
    "E": {"adv": 0.66, "strokes": [_s([(0.64, 1.0), (0.12, 1.0), (0.12, 0.0), (0.66, 0.0)]), _s([(0.12, 0.52), (0.52, 0.52)])]},
    "F": {"adv": 0.64, "strokes": [_s([(0.64, 1.0), (0.12, 1.0), (0.12, 0.0)]), _s([(0.12, 0.52), (0.5, 0.52)])]},
    "G": {"adv": 0.76, "strokes": [_c([(0.7, 0.84), (0.5, 1.0), (0.2, 0.9), (0.08, 0.5), (0.2, 0.1), (0.5, 0.0), (0.72, 0.14),
                                        (0.74, 0.44), (0.46, 0.44)])]},
    "H": {"adv": 0.76, "strokes": [_s([(0.12, 0.0), (0.12, 1.0)]), _s([(0.68, 0.0), (0.68, 1.0)]), _s([(0.12, 0.5), (0.68, 0.5)])]},
    "I": {"adv": 0.50, "strokes": [_s([(0.3, 1.0), (0.3, 0.0)]), _s([(0.1, 1.0), (0.5, 1.0)]), _s([(0.1, 0.0), (0.52, 0.0)])]},
    "J": {"adv": 0.64, "strokes": [_s([(0.22, 1.0), (0.66, 1.0)]),
                                   _c([(0.5, 1.0), (0.5, 0.28), (0.38, 0.02), (0.16, 0.04), (0.04, 0.24)])]},
    "K": {"adv": 0.72, "strokes": [_s([(0.12, 0.0), (0.12, 1.0)]), _s([(0.68, 1.0), (0.12, 0.42)]), _s([(0.28, 0.56), (0.72, 0.0)])]},
    "L": {"adv": 0.62, "strokes": [_s([(0.12, 1.0), (0.12, 0.0), (0.64, 0.0)])]},
    "M": {"adv": 0.90, "strokes": [_s([(0.06, 0.0), (0.1, 1.0), (0.46, 0.3), (0.8, 1.0), (0.86, 0.0)])]},
    "N": {"adv": 0.78, "strokes": [_s([(0.12, 0.0), (0.12, 1.0), (0.68, 0.0), (0.7, 1.0)])]},
    "O": {"adv": 0.80, "strokes": [_c(_ellipse(0.4, 0.5, 0.33, 0.5))]},
    "P": {"adv": 0.70, "strokes": [_s([(0.12, 0.0), (0.14, 1.0)]),
                                   _c([(0.14, 1.0), (0.5, 1.0), (0.66, 0.8), (0.58, 0.56), (0.14, 0.5)])]},
    "R": {"adv": 0.72, "strokes": [_s([(0.12, 0.0), (0.14, 1.0)]),
                                   _c([(0.14, 1.0), (0.5, 1.0), (0.66, 0.8), (0.58, 0.56), (0.14, 0.5)]), _s([(0.4, 0.5), (0.72, 0.0)])]},
    "S": {"adv": 0.70, "strokes": [_c([(0.66, 0.86), (0.46, 1.0), (0.18, 0.9), (0.14, 0.68), (0.4, 0.52), (0.64, 0.38), (0.66, 0.12),
                                        (0.4, 0.0), (0.1, 0.12)])]},
    "T": {"adv": 0.70, "strokes": [_s([(0.04, 1.0), (0.7, 1.0)]), _s([(0.38, 1.0), (0.36, 0.0)])]},
    "U": {"adv": 0.76, "strokes": [_c([(0.12, 1.0), (0.12, 0.26), (0.32, 0.0), (0.56, 0.0), (0.7, 0.26), (0.7, 1.0)])]},
    "V": {"adv": 0.76, "strokes": [_s([(0.04, 1.0), (0.38, 0.0), (0.74, 1.0)])]},
    "W": {"adv": 1.00, "strokes": [_s([(0.02, 1.0), (0.22, 0.0), (0.46, 0.66), (0.68, 0.0), (0.9, 1.0)])]},
    "X": {"adv": 0.72, "strokes": [_s([(0.06, 1.0), (0.68, 0.0)]), _s([(0.68, 1.0), (0.06, 0.0)])]},
    "Y": {"adv": 0.72, "strokes": [_s([(0.06, 1.0), (0.38, 0.5), (0.7, 1.0)]), _s([(0.38, 0.5), (0.36, 0.0)])]},
    "Z": {"adv": 0.70, "strokes": [_s([(0.06, 1.0), (0.68, 1.0), (0.06, 0.0), (0.72, 0.0)])]},
    "-": {"adv": 0.60, "strokes": [_s([(0.1, 0.5), (0.54, 0.52)])]},
    "/": {"adv": 0.60, "strokes": [_s([(0.1, 0.0), (0.6, 1.0)])]},
    ".": {"adv": 0.35, "strokes": [_s([(0.14, 0.04), (0.2, 0.06)])]},
    " ": {"adv": 0.50, "strokes": []},
}

STYLES: dict[str, dict[str, float]] = {
    # Paint marker: solid strokes, crisp but ragged edges, pooling at stroke starts, occasional drips.
    "paint_marker": {"grain_floor": 0.72, "edge_lo": 0.10, "edge_hi": 0.62, "width_var": 0.42,
                     "pool": 0.28, "drips": 2, "skip_count": 4, "dry_fraction": 0.16, "smudge": 0.45},
    # Chalk: grainy coverage, softer edges, more dropout, no drips.
    "chalk": {"grain_floor": 0.38, "edge_lo": 0.18, "edge_hi": 0.95, "width_var": 0.55,
              "pool": 0.05, "drips": 0, "skip_count": 6, "dry_fraction": 0.30, "smudge": 0.5},
}


def chaikin(points: np.ndarray, iterations: int = 3) -> np.ndarray:
    pts = points
    for _ in range(iterations):
        if len(pts) < 3:
            break
        q = 0.75 * pts[:-1] + 0.25 * pts[1:]
        r = 0.25 * pts[:-1] + 0.75 * pts[1:]
        pts = np.concatenate([pts[:1], np.stack([q, r], axis=1).reshape(-1, 2), pts[-1:]])
    return pts


def resample(points: np.ndarray, spacing: float) -> np.ndarray:
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    length = float(seg.sum())
    if length < 1e-6:
        return points[:1]
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    samples = np.linspace(0.0, length, max(2, int(length / spacing) + 1))
    return np.stack([np.interp(samples, cum, points[:, 0]), np.interp(samples, cum, points[:, 1])], axis=1)


def smooth_noise(n: int, rng: np.random.Generator, knots: int) -> np.ndarray:
    """Smooth 1-D noise in [0, 1] built from cubic-interpolated random knots."""
    knots = max(2, knots)
    values = rng.random(knots + 3)
    x = np.linspace(0, knots, n)
    i = np.clip(x.astype(int), 0, knots - 1)
    t = x - i
    p0, p1, p2, p3 = values[i], values[i + 1], values[i + 2], values[i + 3]
    # Catmull-Rom between p1 and p2.
    out = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
    return np.clip(out, 0.0, 1.0)


def value_noise(height: int, width: int, rng: np.random.Generator, scale_px: float, octaves: int = 1,
                stretch_x: float = 1.0) -> np.ndarray:
    """Multi-octave value noise in [0, 1]; ``stretch_x`` > 1 elongates features horizontally."""
    total = np.zeros((height, width), dtype=np.float32)
    weight_sum = 0.0
    for octave in range(octaves):
        cell = max(1.0, scale_px / (2 ** octave))
        grid_h = max(2, int(math.ceil(height / cell)) + 1)
        grid_w = max(2, int(math.ceil(width / (cell * stretch_x))) + 1)
        grid = rng.random((grid_h, grid_w)).astype(np.float32)
        layer = np.asarray(Image.fromarray(grid, mode="F").resize((width, height), Image.Resampling.BICUBIC), dtype=np.float32)
        weight = 0.5 ** octave
        total += weight * layer
        weight_sum += weight
    total /= weight_sum
    lo, hi = float(total.min()), float(total.max())
    return (total - lo) / max(hi - lo, 1e-6)


def smoothstep(lo: float, hi: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _box1d(array: np.ndarray, radius: int, axis: int) -> np.ndarray:
    if radius <= 0:
        return array
    pad = [(0, 0), (0, 0)]
    pad[axis] = (radius, radius)
    padded = np.pad(array, pad, mode="edge")
    cum = np.cumsum(padded, axis=axis, dtype=np.float64)
    window = 2 * radius + 1
    if axis == 0:
        head = np.concatenate([np.zeros((1, cum.shape[1])), cum[:-window, :]], axis=0)
        total = cum[window - 1:, :] - head
    else:
        head = np.concatenate([np.zeros((cum.shape[0], 1)), cum[:, :-window]], axis=1)
        total = cum[:, window - 1:] - head
    return (total / window).astype(np.float32)


def gaussian_blur(array: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian approximation by three separable box blurs; works on float arrays of any range."""
    if sigma <= 0.0:
        return array.astype(np.float32)
    width = max(1, int(round(math.sqrt(12.0 * sigma * sigma / 3.0 + 1.0))))
    radius = max(1, width // 2)
    out = array.astype(np.float32)
    for _ in range(3):
        out = _box1d(_box1d(out, radius, 0), radius, 1)
    return out


class InkCanvas:
    """Float coverage canvas at supersampled resolution; strokes are stamped as soft discs."""

    def __init__(self, height: int, width: int) -> None:
        self.canvas = np.zeros((height, width), dtype=np.float32)
        self.stamps = 0

    def stamp(self, points: np.ndarray, widths: np.ndarray, pressure: np.ndarray,
              normals: np.ndarray | None = None, dry: np.ndarray | None = None,
              streak_profile: np.ndarray | None = None) -> None:
        """Stamp soft discs; where ``dry`` is set the disc is modulated across the stroke by
        ``streak_profile`` (constant along the stroke) so a marker running dry leaves fibrous streaks."""
        h, w = self.canvas.shape
        for index, ((x, y), width, press) in enumerate(zip(points, widths, pressure)):
            if press <= 0.0 or width <= 0.0:
                continue
            r = width / 2.0
            x0, x1 = int(math.floor(x - r - 1)), int(math.ceil(x + r + 1))
            y0, y1 = int(math.floor(y - r - 1)), int(math.ceil(y + r + 1))
            if x1 < 0 or y1 < 0 or x0 >= w or y0 >= h:
                continue
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
            ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            dist = np.hypot(xs - x, ys - y)
            coverage = np.clip(r + 0.5 - dist, 0.0, 1.0) * press
            if dry is not None and dry[index] and normals is not None and streak_profile is not None:
                perp = ((xs - x) * normals[index, 0] + (ys - y) * normals[index, 1]) / max(r, 1e-6)
                bins = np.clip(((perp + 1.0) * 0.5 * (len(streak_profile) - 1)).round().astype(int), 0, len(streak_profile) - 1)
                coverage = coverage * streak_profile[bins]
            region = self.canvas[y0:y1 + 1, x0:x1 + 1]
            np.maximum(region, coverage, out=region)
            self.stamps += 1


class HandwritingRenderer:
    """Renders text/arrows/loops into an InkCanvas with per-seed handwriting irregularities."""

    def __init__(self, canvas: InkCanvas, rng: np.random.Generator, style: dict[str, float], base_slant: float) -> None:
        self.canvas, self.rng, self.style, self.base_slant = canvas, rng, style, base_slant
        self.thick_points: list[tuple[float, float, float]] = []
        self.skips_left = int(style["skip_count"])
        self.glyph_skipped = False

    def stroke(self, unit_points: np.ndarray, transform, width_px: float, smooth: bool) -> None:
        pts = chaikin(unit_points, 3) if smooth else unit_points
        pts = np.asarray([transform(x, y) for x, y in pts], dtype=np.float64)
        pts = resample(pts, 1.0)
        n = len(pts)
        if n < 2:
            return
        rng, style = self.rng, self.style
        # Perpendicular wobble: slow drift plus a faint tremor.
        tangent = np.gradient(pts, axis=0)
        norm = np.linalg.norm(tangent, axis=1, keepdims=True)
        tangent = tangent / np.maximum(norm, 1e-6)
        normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
        drift = (smooth_noise(n, rng, max(2, n // 90)) - 0.5) * width_px * 0.55
        tremor = (smooth_noise(n, rng, max(2, n // 9)) - 0.5) * width_px * 0.12
        pts = pts + normal * (drift + tremor)[:, None]
        # Width profile: pressure variation, pooling at the start, slight thinning at the end.
        profile = 1.0 - style["width_var"] / 2 + style["width_var"] * smooth_noise(n, rng, max(2, n // 40))
        s = np.linspace(0.0, 1.0, n)
        profile *= 1.0 + style["pool"] * np.exp(-s * 14.0)
        profile *= 1.0 - 0.18 * np.clip((s - 0.85) / 0.15, 0.0, 1.0)
        # Break the "chain of equal discs" outline: slow radius drift plus fine per-sample jitter.
        profile *= 1.0 + 0.08 * (smooth_noise(n, rng, max(2, n // 3)) - 0.5) * 2 + (rng.random(n) - 0.5) * 0.05
        widths = width_px * profile
        pressure = 0.9 + 0.1 * smooth_noise(n, rng, max(2, n // 30))
        dry = np.zeros(n, dtype=bool)
        streak = None
        if rng.random() < style["dry_fraction"] and n > 24:
            span = max(8, n // 4)
            start = int(rng.integers(0, max(1, n - span)))
            dry[start:start + span] = True
            # Fibrous streaks across the nib: a smooth random profile over the perpendicular offset.
            streak = np.clip(0.15 + 1.1 * smooth_noise(24, rng, 7), 0.0, 1.0)
            streak[[0, -1]] *= 0.4
            fade = np.ones(n)
            ramp = max(2, span // 5)
            fade[start:start + ramp] = np.linspace(1.0, 0.75, ramp)
            pressure[start:start + span] *= 0.85
            pressure *= fade
        gap = int(width_px * float(rng.uniform(1.3, 2.6)))
        if self.skips_left > 0 and not self.glyph_skipped and n > 4 * gap and rng.random() < 0.5:
            # A real pen skip: the open gap must exceed the stamp disc diameter, so size it in stroke
            # widths; only long strokes skip, and at most once per glyph so letters stay legible.
            self.glyph_skipped = True
            if n - gap - 2 * (n // 8) > 1:
                start = int(rng.integers(n // 8, n - gap - n // 8))
                pressure[start:start + gap] = 0.0
                ramp = max(2, int(width_px * 0.6))
                for k in range(ramp):
                    if start - 1 - k >= 0:
                        pressure[start - 1 - k] *= k / ramp
                    if start + gap + k < n:
                        pressure[start + gap + k] *= k / ramp
                self.skips_left -= 1
        self.canvas.stamp(pts, widths, pressure, normals=normal, dry=dry, streak_profile=streak)
        for index in range(0, n, 7):
            if widths[index] > width_px * 1.05:
                self.thick_points.append((float(pts[index, 0]), float(pts[index, 1]), float(widths[index])))

    def text(self, text: str, origin: tuple[float, float], height_px: float, width_px: float,
             baseline_angle_deg: float, spacing: float = 1.0) -> dict[str, float]:
        """Write ``text`` with its first glyph's left edge at ``origin`` (pixel x, baseline y)."""
        missing = sorted({ch for ch in text if ch not in GLYPHS})
        if missing:
            raise ValueError(f"No stroke glyph for characters: {missing}")
        rng = self.rng
        cos_b, sin_b = math.cos(math.radians(baseline_angle_deg)), math.sin(math.radians(baseline_angle_deg))
        pen = 0.0
        xs: list[float] = []
        ys: list[float] = []
        for ch in text:
            glyph = GLYPHS[ch]
            scale = height_px * float(rng.uniform(0.93, 1.07))
            slant = self.base_slant + float(rng.uniform(-0.05, 0.05))
            rot = math.radians(float(rng.uniform(-3.5, 3.5)))
            rise = float(rng.uniform(-0.035, 0.035)) * height_px
            cx, cy = glyph["adv"] * 0.5, 0.5
            pen_here = pen
            self.glyph_skipped = False

            def transform(x: float, y: float, scale=scale, slant=slant, rot=rot, rise=rise, cx=cx, cy=cy, pen_here=pen_here):
                # Unit glyph -> slanted, rotated about its centre, scaled, placed along the baseline.
                ux, uy = x + slant * y - cx, y - cy
                rx = ux * math.cos(rot) - uy * math.sin(rot) + cx
                ry = ux * math.sin(rot) + uy * math.cos(rot) + cy
                lx, ly = pen_here + rx * scale, -(ry * scale + rise)
                return origin[0] + lx * cos_b - ly * sin_b, origin[1] + lx * sin_b + ly * cos_b

            for stroke in glyph["strokes"]:
                self.stroke(np.asarray(stroke["pts"], dtype=np.float64), transform, width_px, stroke["smooth"])
            for stroke in glyph["strokes"]:
                for x, y in stroke["pts"]:
                    px, py = transform(x, y)
                    xs.append(px)
                    ys.append(py)
            pen += glyph["adv"] * scale * spacing * float(rng.uniform(0.9, 1.12)) + 0.08 * height_px
        if not xs:
            return {"x0": origin[0], "y0": origin[1], "x1": origin[0], "y1": origin[1]}
        return {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}

    def arrow(self, start: tuple[float, float], end: tuple[float, float], width_px: float, head_px: float) -> None:
        rng = self.rng
        self.glyph_skipped = False
        sx, sy = start
        ex, ey = end
        mid = ((sx + ex) / 2 + float(rng.uniform(-0.02, 0.02)) * abs(ex - sx),
               (sy + ey) / 2 + float(rng.uniform(-0.06, 0.06)) * max(abs(ex - sx), 1.0))
        shaft = np.asarray([start, mid, end], dtype=np.float64)
        self.stroke(shaft, lambda x, y: (x, y), width_px, True)
        angle = math.atan2(ey - sy, ex - sx)
        for sign in (1.0, -1.0):
            a = angle + math.pi + sign * math.radians(float(rng.uniform(22, 32)))
            tip = (ex + float(rng.uniform(-0.1, 0.1)) * width_px, ey + float(rng.uniform(-0.1, 0.1)) * width_px)
            tail = (ex + head_px * math.cos(a), ey + head_px * math.sin(a))
            self.stroke(np.asarray([tail, tip], dtype=np.float64), lambda x, y: (x, y), width_px * 0.95, False)

    def loop(self, bbox: dict[str, float], width_px: float, pad: float) -> None:
        self.glyph_skipped = False
        cx, cy = (bbox["x0"] + bbox["x1"]) / 2, (bbox["y0"] + bbox["y1"]) / 2
        rx, ry = (bbox["x1"] - bbox["x0"]) / 2 + pad * 1.5, (bbox["y1"] - bbox["y0"]) / 2 + pad
        pts = np.asarray(_ellipse(cx, cy, rx, ry, n=18, start_deg=float(self.rng.uniform(150, 200)), turn=1.08,
                                  clockwise=bool(self.rng.random() < 0.5)), dtype=np.float64)
        self.stroke(pts, lambda x, y: (x, y), width_px * 0.85, True)

    def drips(self, count: int, width_px: float) -> None:
        if count <= 0 or not self.thick_points:
            return
        rng = self.rng
        candidates = sorted(self.thick_points, key=lambda item: -item[1])[: max(6, len(self.thick_points) // 3)]
        for _ in range(count):
            x, y, w = candidates[int(rng.integers(0, len(candidates)))]
            length = float(rng.uniform(1.0, 2.8)) * width_px
            n = max(4, int(length))
            ys = y + np.linspace(0.0, length, n)
            xs = x + (smooth_noise(n, rng, 3) - 0.5) * width_px * 0.15
            widths = np.linspace(w * 0.45, w * 0.2, n)
            widths[-1] = w * 0.42  # bead at the end of the drip
            self.canvas.stamp(np.stack([xs, ys], axis=1), widths, np.full(n, 0.85))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _panel_px(marking: dict[str, Any], panel: dict[str, Any], tex_w: int, tex_h: int):
    """World (y, z) on the centre panel face -> texture pixel. +y is the viewer's left (robot faces +x)."""
    width, height, bottom = float(panel["width"]), float(panel["height"]), float(panel["bottom_z"])

    def to_px(yz):
        u = (width / 2 - float(yz[0])) / width
        v = (float(yz[1]) - bottom) / height
        return u * tex_w, (1.0 - v) * tex_h

    return to_px, tex_w / width, tex_h / height


def make_plate_base(height: int, width: int, rng: np.random.Generator, color_rgb, rust_seam_u: float | None,
                    metres_per_px: float) -> np.ndarray:
    """Shop-primed steel: mottled primer, roller streaks, rust bloom, scuffs and bottom dust."""
    base = np.asarray(color_rgb, dtype=np.float32)[None, None, :] / 255.0
    px_per_m = 1.0 / metres_per_px
    mottle = value_noise(height, width, rng, 0.45 * px_per_m, octaves=3)
    streaks = value_noise(height, width, rng, 0.06 * px_per_m, octaves=2, stretch_x=9.0)
    grain = value_noise(height, width, rng, 0.0025 * px_per_m, octaves=2)
    shade = 1.0 + 0.16 * (mottle - 0.5) + 0.08 * (streaks - 0.5) + 0.05 * (grain - 0.5)
    img = base * shade[:, :, None]
    # Dust and dullness near the floor.
    v = np.linspace(1.0, 0.0, height, dtype=np.float32)[:, None]
    img *= (1.0 - 0.12 * np.clip((0.22 - v) / 0.22, 0.0, 1.0))[:, :, None]
    # Rust bloom: random blotches, plus weeping streaks below the top edge and beside the seam.
    rust = np.zeros((height, width), dtype=np.float32)
    blotch = value_noise(height, width, rng, 0.12 * px_per_m, octaves=3)
    rust += smoothstep(0.78, 0.92, blotch) * 0.7
    top = value_noise(height, width, rng, 0.03 * px_per_m, octaves=2, stretch_x=0.08)
    rust += smoothstep(0.6, 0.95, top) * np.clip((v - 0.86) / 0.14, 0.0, 1.0) * 0.6
    if rust_seam_u is not None:
        u = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
        near = np.exp(-((u - rust_seam_u) * width * metres_per_px / 0.025) ** 2)
        seam_noise = value_noise(height, width, rng, 0.04 * px_per_m, octaves=2, stretch_x=0.15)
        rust += near * smoothstep(0.35, 0.8, seam_noise) * 0.55
    rust = np.clip(rust, 0.0, 1.0)
    rust_color = np.asarray([0.42, 0.24, 0.13], dtype=np.float32) * (0.8 + 0.4 * grain)[:, :, None]
    img = img * (1 - rust[:, :, None]) + rust_color * rust[:, :, None]
    # Light scuffs and scratches.
    scuff = np.zeros((height, width), dtype=np.float32)
    for _ in range(int(rng.integers(18, 30))):
        x0, y0 = rng.uniform(0, width), rng.uniform(0, height)
        length = rng.uniform(0.05, 0.4) * px_per_m
        angle = rng.uniform(-0.35, 0.35) + (math.pi / 2 if rng.random() < 0.15 else 0.0)
        n = max(2, int(length))
        xs = np.clip((x0 + np.cos(angle) * np.linspace(0, length, n)).astype(int), 0, width - 1)
        ys = np.clip((y0 + np.sin(angle) * np.linspace(0, length, n)).astype(int), 0, height - 1)
        scuff[ys, xs] = rng.uniform(0.25, 0.6)
    scuff = gaussian_blur(scuff, 0.8)
    img = img * (1 - scuff[:, :, None] * 0.5) + np.asarray([0.62, 0.64, 0.62], dtype=np.float32) * scuff[:, :, None] * 0.5
    return np.clip(img, 0.0, 1.0)


def generate_panel_textures(marking: dict[str, Any], panels: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seed = int(marking["seed"])
    style_name = marking.get("style", "paint_marker")
    if style_name not in STYLES:
        raise ValueError(f"Unknown marking style {style_name!r}; choose from {sorted(STYLES)}")
    style = STYLES[style_name]
    strings = [marking["text"], marking["joint_label"], *[n["text"] for n in marking.get("aux_notes", [])]]
    missing = sorted({ch for text in strings for ch in text if ch not in GLYPHS})
    if missing:
        raise ValueError(f"No stroke glyph for characters {missing}; available: {''.join(sorted(GLYPHS))!r}")
    rng = np.random.default_rng(seed)
    center = panels["center"]
    tex_w, tex_h = (int(v) for v in center.get("texture_size", [4096, 3072]))
    to_px, px_per_m_x, px_per_m_y = _panel_px(marking, center, tex_w, tex_h)
    metres_per_px = float(center["width"]) / tex_w
    seam_u = None
    if center.get("seam_y") is not None:
        seam_u = (float(center["width"]) / 2 - float(center["seam_y"])) / float(center["width"])

    base = make_plate_base(tex_h, tex_w, rng, marking.get("primer_rgb", [122, 128, 122]), seam_u, metres_per_px)

    # Memo region of interest in texels (with margin), rendered supersampled then pasted back.
    text_c = to_px(marking["text_center_yz"])
    label_c = to_px(marking["label_center_yz"])
    arrow_a = to_px(marking["arrow_from_yz"])
    arrow_b = to_px(marking["arrow_to_yz"])
    text_h = float(marking["text_height_m"]) * px_per_m_y
    label_h = float(marking["label_height_m"]) * px_per_m_y
    stroke_w = float(marking.get("stroke_width_m", 0.013)) * px_per_m_x
    est_text_w = sum(GLYPHS[ch]["adv"] for ch in marking["text"]) * text_h * 1.08 + 0.08 * text_h * len(marking["text"])
    xs = [text_c[0] - est_text_w / 2, text_c[0] + est_text_w / 2, label_c[0] - label_h * 2, label_c[0] + label_h * 2, arrow_a[0], arrow_b[0]]
    ys = [text_c[1] - text_h, text_c[1] + text_h, label_c[1] - label_h * 1.5, label_c[1] + label_h * 1.5, arrow_a[1], arrow_b[1]]
    for note in marking.get("aux_notes", []):
        note_c = to_px(note["center_yz"])
        note_h = float(note["height_m"]) * px_per_m_y
        note_w = sum(GLYPHS[ch]["adv"] for ch in note["text"]) * note_h * 1.08 + 0.08 * note_h * len(note["text"])
        xs += [note_c[0] - note_w / 2, note_c[0] + note_w / 2]
        ys += [note_c[1] - note_h, note_c[1] + note_h]
    margin = 1.6 * text_h
    if min(xs) - margin < 0 or max(xs) + margin > tex_w or min(ys) - margin < 0 or max(ys) + margin > tex_h:
        raise ValueError("Memo (with margin) does not fit on the centre panel texture; move text_center_yz/label/arrow/notes "
                         f"inward (px bounds x {min(xs) - margin:.0f}..{max(xs) + margin:.0f}, y {min(ys) - margin:.0f}..{max(ys) + margin:.0f}, texture {tex_w}x{tex_h})")
    rx0, ry0 = int(min(xs) - margin), int(min(ys) - margin)
    rx1, ry1 = int(max(xs) + margin), int(max(ys) + margin)
    roi_w, roi_h = rx1 - rx0, ry1 - ry0
    if roi_w <= 0 or roi_h <= 0:
        raise ValueError("Memo region is empty")
    ss = SUPERSAMPLE
    canvas = InkCanvas(roi_h * ss, roi_w * ss)
    base_slant = float(marking.get("slant", 0.12)) + float(rng.uniform(-0.03, 0.03))
    writer = HandwritingRenderer(canvas, rng, style, base_slant)

    def roi(p):
        return ((p[0] - rx0) * ss, (p[1] - ry0) * ss)

    # Main identifier: centred on text_center, baseline slightly off-level like a quick hand note.
    text_angle = float(marking.get("text_angle_deg", -1.2)) + float(rng.uniform(-0.8, 0.8))
    text_origin = roi((text_c[0] - est_text_w / 2, text_c[1] + text_h * 0.5))
    text_box = writer.text(marking["text"], text_origin, text_h * ss, stroke_w * ss, text_angle)
    # Joint label on its own line with a different slant/angle, optionally circled.
    label_angle = float(marking.get("label_angle_deg", 1.8)) + float(rng.uniform(-1.0, 1.0))
    est_label_w = sum(GLYPHS[ch]["adv"] for ch in marking["joint_label"]) * label_h * 1.08
    label_origin = roi((label_c[0] - est_label_w / 2, label_c[1] + label_h * 0.5))
    label_box = writer.text(marking["joint_label"], label_origin, label_h * ss, stroke_w * 0.9 * ss, label_angle)
    if marking.get("circle_label", True):
        writer.loop(label_box, stroke_w * ss, pad=stroke_w * 2.0 * ss)
    writer.arrow(roi(arrow_a), roi(arrow_b), stroke_w * 0.95 * ss, head_px=stroke_w * 3.2 * ss)
    for note in marking.get("aux_notes", []):
        note_c = to_px(note["center_yz"])
        note_h = float(note["height_m"]) * px_per_m_y
        est_w = sum(GLYPHS[ch]["adv"] for ch in note["text"]) * note_h * 1.08
        writer.text(note["text"], roi((note_c[0] - est_w / 2, note_c[1] + note_h * 0.5)), note_h * ss,
                    stroke_w * 0.75 * ss, float(note.get("angle_deg", 0.0)) + float(rng.uniform(-1.5, 1.5)))
    writer.drips(int(style["drips"]), stroke_w * ss)

    ink_ss = canvas.canvas
    ink = ink_ss.reshape(roi_h, ss, roi_w, ss).mean(axis=(1, 3))
    # Coverage texture: grain, ragged edges, then a localised smudge where a glove brushed the wet paint.
    grain = value_noise(roi_h, roi_w, rng, 2.6, octaves=2)
    grain_med = value_noise(roi_h, roi_w, rng, 11.0, octaves=2)
    coverage = ink * (style["grain_floor"] + (1.0 - style["grain_floor"]) * (0.6 * grain + 0.4 * grain_med))
    edge_noise = value_noise(roi_h, roi_w, rng, max(2.0, stroke_w / 3.0), octaves=2)
    alpha = smoothstep(style["edge_lo"], style["edge_hi"], coverage * 1.15 - 0.18 * (edge_noise - 0.5))
    # Directional smear: a glove wiped across the wet paint 10-20 degrees off horizontal over part of the text.
    wipe = math.radians(float(rng.uniform(10, 20)) * (1 if rng.random() < 0.5 else -1))
    wipe_len = int(stroke_w * float(rng.uniform(3.0, 5.0)))
    smudge = np.zeros_like(ink)
    base_blur = gaussian_blur(ink, stroke_w * 0.35)
    for k in range(1, wipe_len + 1):
        dx, dy = int(round(k * math.cos(wipe))), int(round(k * math.sin(wipe)))
        shifted = np.zeros_like(ink)
        ys0, ys1 = max(dy, 0), roi_h + min(dy, 0)
        xs0, xs1 = max(dx, 0), roi_w + min(dx, 0)
        shifted[ys0:ys1, xs0:xs1] = base_blur[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
        smudge += shifted * (1.0 - k / (wipe_len + 1))
    smudge /= max(1.0, wipe_len * 0.5)
    yy, xx = np.mgrid[0:roi_h, 0:roi_w]
    smudge_cx = (text_box["x0"] + text_box["x1"]) / 2 / ss + float(rng.uniform(0.1, 0.35)) * (text_box["x1"] - text_box["x0"]) / ss
    smudge_cy = (text_box["y0"] + text_box["y1"]) / 2 / ss
    blob = np.exp(-(((xx - smudge_cx) / (text_h * 1.1)) ** 2 + ((yy - smudge_cy) / (text_h * 0.7)) ** 2))
    streaky = value_noise(roi_h, roi_w, rng, max(2.0, stroke_w / 2.5), octaves=1, stretch_x=6.0)
    alpha = np.maximum(alpha, np.clip(smudge, 0.0, 1.0) * style["smudge"] * blob * (0.55 + 0.45 * streaky))
    alpha = np.clip(alpha, 0.0, 1.0).astype(np.float32)

    ink_rgb = np.asarray(marking.get("color_rgb", [238, 231, 196]), dtype=np.float32) / 255.0
    tint = (grain_med - 0.5)[:, :, None] * np.asarray([0.03, 0.04, 0.09], dtype=np.float32)
    # Paint pools darker where strokes are dense (starts, overlaps, drip beads) and thins lighter in dry spans.
    density = gaussian_blur(ink, stroke_w * 0.6)
    density = density / max(float(density.max()), 1e-6)
    shade = (1.0 - 0.07 * density + 0.04 * (1.0 - ink) * (ink > 0.05))[:, :, None]
    color = np.clip((ink_rgb[None, None, :] - tint) * shade - 0.05 * (1.0 - ink)[:, :, None] * np.asarray([0.0, 0.02, 0.08]), 0.0, 1.0)
    region = base[ry0:ry1, rx0:rx1]
    base[ry0:ry1, rx0:rx1] = region * (1 - alpha[:, :, None]) + color * alpha[:, :, None]

    layer = np.zeros((tex_h, tex_w, 4), dtype=np.uint8)
    layer[ry0:ry1, rx0:rx1, :3] = (color * 255).astype(np.uint8)
    layer[ry0:ry1, rx0:rx1, 3] = (alpha * 255).astype(np.uint8)

    side = panels["sides"]
    side_w, side_h = (int(v) for v in side.get("texture_size", [2048, 1536]))
    side_base = make_plate_base(side_h, side_w, rng, marking.get("primer_rgb", [122, 128, 122]), None,
                                float(side["width"]) / side_w)

    files = {
        "panel_center_albedo.png": Image.fromarray((base * 255).round().astype(np.uint8), mode="RGB"),
        "panel_side_albedo.png": Image.fromarray((side_base * 255).round().astype(np.uint8), mode="RGB"),
        "marking_layer.png": Image.fromarray(layer, mode="RGBA"),
        "marking_preview.png": Image.fromarray((base[ry0:ry1, rx0:rx1] * 255).round().astype(np.uint8), mode="RGB"),
    }
    hashes = {}
    for name, image in files.items():
        image.save(out_dir / name)
        hashes[name] = _sha256(out_dir / name)
    text_bbox_px = {k: round(v / ss + (rx0 if k[0] == "x" else ry0), 1) for k, v in text_box.items()}
    label_bbox_px = {k: round(v / ss + (rx0 if k[0] == "x" else ry0), 1) for k, v in label_box.items()}
    # Control-point boxes exclude half the stroke width, wobble and pooling; dilate by one stroke width.
    dilate = stroke_w
    text_bbox_px = {"x0": text_bbox_px["x0"] - dilate, "y0": text_bbox_px["y0"] - dilate, "x1": text_bbox_px["x1"] + dilate, "y1": text_bbox_px["y1"] + dilate}
    ink_rows, ink_cols = np.nonzero(alpha > 0.5)
    memo_ink_bbox_px = ({"x0": int(ink_cols.min()) + rx0, "y0": int(ink_rows.min()) + ry0, "x1": int(ink_cols.max()) + rx0, "y1": int(ink_rows.max()) + ry0}
                        if len(ink_rows) else None)
    import PIL
    import sys as _sys

    def px_to_yz(x, y):
        return [round(float(center["width"]) / 2 - x / px_per_m_x, 4), round(float(center["bottom_z"]) + (tex_h - y) / px_per_m_y, 4)]

    provenance = {
        "generator": "scripts/isaac/isaac_shipyard_marking.py",
        "generator_sha256": _sha256(Path(__file__)),
        "glyph_set_version": GLYPH_SET_VERSION,
        "source": marking.get("source", "procedural synthetic handwriting-style strokes; not a transcription of a real steel photo"),
        "synthetic": True,
        "seed": seed,
        "style": style_name,
        "style_parameters": style,
        "text": marking["text"],
        "joint_label": marking["joint_label"],
        "aux_notes": [n["text"] for n in marking.get("aux_notes", [])],
        "base_slant": round(base_slant, 4),
        "text_angle_deg": round(text_angle, 3),
        "label_angle_deg": round(label_angle, 3),
        "stroke_width_m": float(marking.get("stroke_width_m", 0.013)),
        "ink_rgb": marking.get("color_rgb", [238, 231, 196]),
        "primer_rgb": marking.get("primer_rgb", [122, 128, 122]),
        "center_texture_size": [tex_w, tex_h],
        "center_panel_metres_per_texel": round(metres_per_px, 6),
        "side_texture_size": [side_w, side_h],
        "memo_roi_px": [rx0, ry0, rx1, ry1],
        "text_bbox_px": text_bbox_px,
        "text_bbox_note": "glyph control-point box dilated by one stroke width; excludes drips and smudge",
        "label_bbox_px": label_bbox_px,
        "text_bbox_world_yz": {"top_left": px_to_yz(text_bbox_px["x0"], text_bbox_px["y0"]),
                               "bottom_right": px_to_yz(text_bbox_px["x1"], text_bbox_px["y1"])},
        "memo_ink_bbox_px": memo_ink_bbox_px,
        "memo_ink_bbox_world_yz": ({"top_left": px_to_yz(memo_ink_bbox_px["x0"], memo_ink_bbox_px["y0"]),
                                    "bottom_right": px_to_yz(memo_ink_bbox_px["x1"], memo_ink_bbox_px["y1"])} if memo_ink_bbox_px else None),
        "inputs": {"marking": marking, "panels": {"center": center, "sides": side}},
        "library_versions": {"python": _sys.version.split()[0], "numpy": np.__version__, "pillow": PIL.__version__},
        "pixel_sha256": {"panel_center_albedo": hashlib.sha256(np.ascontiguousarray((base * 255).round().astype(np.uint8)).tobytes()).hexdigest(),
                         "marking_layer_alpha": hashlib.sha256(np.ascontiguousarray(layer[:, :, 3]).tobytes()).hexdigest()},
        "stamps": canvas.stamps,
        "files": hashes,
    }
    (out_dir / "marking.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path("configs/isaac_scene/shipyard_handwriting.json"))
    parser.add_argument("--out", type=Path, required=True, help="Directory for generated textures (created if missing)")
    parser.add_argument("--seed", type=int, help="Override marking.seed from the config")
    parser.add_argument("--style", choices=sorted(STYLES), help="Override marking.style from the config")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    marking = dict(cfg["marking"])
    if args.seed is not None:
        marking["seed"] = args.seed
    if args.style:
        marking["style"] = args.style
    result = generate_panel_textures(marking, cfg["panels"], args.out)
    print(json.dumps({k: result[k] for k in ("seed", "style", "text", "joint_label", "text_bbox_world_yz", "files")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
