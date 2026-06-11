"""Cocking mechanism handhold for a Nerf-style (Zuru) blaster — CadQuery model, mm.

Coordinate system
-----------------
+Z : pin axis; bottom (pin end) at Z=0, top at Z=total_length
Pin center at X=Y=0

Dimensions and label text live in a YAML file; pass ``--config`` when running this script.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
import yaml

_HOLE_CLEARANCE = 0.5
_DOME_ARC_SEGMENTS = 16


@dataclass(frozen=True)
class CockingMechanismSettings:
    """User-facing dimensions loaded from YAML."""

    total_length: float
    od_at_pin: float
    od_max: float
    flare_length: float
    rounded_top_length: float

    pin_diameter: float
    pin_bore_depth: float
    pin_hole_clearance: float

    bottom_fillet_radius: float

    rib_count: int
    rib_width: float
    rib_depth: float

    screw_slot_width: float
    screw_slot_max_depth: float

    bottom_label_text: str
    bottom_label_height: float
    bottom_label_depth: float
    bottom_label_offset_from_pin: float

    @property
    def radius_at_pin(self) -> float:
        return self.od_at_pin / 2.0

    @property
    def max_radius(self) -> float:
        return self.od_max / 2.0

    @property
    def pin_bore_radius(self) -> float:
        return (self.pin_diameter + self.pin_hole_clearance) / 2.0

    @property
    def main_grip_length(self) -> float:
        return self.total_length - self.flare_length - self.rounded_top_length

    @property
    def rib_angular_spacing_deg(self) -> float:
        return 360.0 / self.rib_count

    @property
    def rib_circumferential_spacing(self) -> float:
        return math.pi * self.od_max / self.rib_count

    @property
    def rib_z_start(self) -> float:
        return self.flare_length

    @property
    def rib_z_end(self) -> float:
        return self.total_length - self.rounded_top_length

    @property
    def rib_length(self) -> float:
        return self.rib_z_end - self.rib_z_start

    @property
    def cylinder_top_z(self) -> float:
        return self.total_length - self.rounded_top_length

    @property
    def dome_sphere_radius(self) -> float:
        h = self.rounded_top_length
        r = self.max_radius
        return (r * r + h * h) / (2.0 * h)

    @property
    def dome_sphere_center_z(self) -> float:
        return self.total_length - self.dome_sphere_radius

    @property
    def bottom_label_center_radius(self) -> float:
        return self.pin_bore_radius + self.bottom_label_offset_from_pin


def load_settings(path: Path | str) -> CockingMechanismSettings:
    """Load and validate settings from a YAML mapping."""
    config_path = Path(path).expanduser().resolve()
    with config_path.open(encoding="utf-8") as f:
        raw: Any = yaml.safe_load(f)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"Settings YAML must be a mapping at top level, got {type(raw).__name__}"
        )
    return CockingMechanismSettings(**raw)


def _solid_cylinder_along_z(
    x: float,
    y: float,
    z_start: float,
    depth: float,
    radius: float,
    upward: bool = True,
) -> cq.Solid:
    """Cylinder with axis parallel to Z."""
    direction = cq.Vector(0.0, 0.0, 1.0 if upward else -1.0)
    return cq.Solid.makeCylinder(
        radius,
        depth,
        cq.Vector(x, y, z_start),
        direction,
    )


def _dome_profile_points(settings: CockingMechanismSettings) -> list[tuple[float, float]]:
    """Sample (radius, z) points along the spherical dome cap."""
    points: list[tuple[float, float]] = []
    z_start = settings.cylinder_top_z
    z_end = settings.total_length
    s = settings.dome_sphere_radius
    z_center = settings.dome_sphere_center_z
    for i in range(1, _DOME_ARC_SEGMENTS):
        t = i / _DOME_ARC_SEGMENTS
        z = z_start + t * (z_end - z_start)
        radius_sq = s * s - (z - z_center) ** 2
        radius = math.sqrt(max(0.0, radius_sq))
        points.append((radius, z))
    return points


def _revolved_body(settings: CockingMechanismSettings) -> cq.Workplane:
    """Revolve an XZ profile around Z: flare, cylinder, and rounded dome."""
    profile = (
        cq.Workplane("XZ")
        .moveTo(0.0, 0.0)
        .lineTo(settings.radius_at_pin, 0.0)
        .lineTo(settings.max_radius, settings.flare_length)
        .lineTo(settings.max_radius, settings.cylinder_top_z)
    )
    for radius, z in _dome_profile_points(settings):
        profile = profile.lineTo(radius, z)
    profile = profile.lineTo(0.0, settings.total_length).close()
    return profile.revolve()


def _pin_bore_cutter(settings: CockingMechanismSettings) -> cq.Workplane:
    """Pin bore along +Z from the bottom face."""
    cutter = _solid_cylinder_along_z(
        0.0,
        0.0,
        0.0,
        settings.pin_bore_depth + _HOLE_CLEARANCE,
        settings.pin_bore_radius,
        upward=True,
    )
    return cq.Workplane().newObject([cutter])


def _longitudinal_rib_cutter(
    settings: CockingMechanismSettings, index: int
) -> cq.Workplane:
    """Rounded longitudinal groove cutter at the given rib index."""
    half_width = settings.rib_width / 2.0
    depth = settings.rib_depth + _HOLE_CLEARANCE
    angle_deg = index * settings.rib_angular_spacing_deg

    groove = (
        cq.Workplane("XY")
        .moveTo(settings.max_radius, -half_width)
        .threePointArc((settings.max_radius - depth, 0.0), (settings.max_radius, half_width))
        .close()
        .extrude(settings.rib_length + _HOLE_CLEARANCE)
        .translate((0.0, 0.0, settings.rib_z_start - _HOLE_CLEARANCE / 2.0))
    )
    return groove.rotate((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), angle_deg)


def _apply_ribs(body: cq.Workplane, settings: CockingMechanismSettings) -> cq.Workplane:
    """Cut evenly spaced longitudinal grooves on the main grip section."""
    for index in range(settings.rib_count):
        body = body.cut(_longitudinal_rib_cutter(settings, index))
    return body


def _apply_bottom_fillet(
    body: cq.Workplane, settings: CockingMechanismSettings
) -> cq.Workplane:
    """Fillet the outer bottom edge; fall back to the un-filleted body on failure."""
    if settings.bottom_fillet_radius <= 0.0:
        return body
    try:
        return body.faces("<Z").edges("%Circle").fillet(settings.bottom_fillet_radius)
    except Exception:
        return body


def _bottom_label(body: cq.Workplane, settings: CockingMechanismSettings) -> cq.Workplane:
    """Engrave a single-letter label on the bottom face, offset from the pin bore."""
    if not settings.bottom_label_text:
        return body

    label_wp = cq.Workplane("XY").text(
        settings.bottom_label_text,
        settings.bottom_label_height,
        settings.bottom_label_depth,
        halign="center",
        valign="center",
        combine=False,
    )
    letters = label_wp.solids().vals()
    if not letters:
        return body

    cutter = letters[0]
    for letter in letters[1:]:
        cutter = cutter.fuse(letter)
    cutter = cutter.translate(
        (settings.bottom_label_center_radius, 0.0, 0.0)
    )
    return body.cut(cq.Workplane().newObject([cutter]))


def _screw_slot_cutter(settings: CockingMechanismSettings) -> cq.Workplane:
    """Cross-slot on the dome top, cut downward from the apex."""
    slot_span = settings.od_max + _HOLE_CLEARANCE
    depth = settings.screw_slot_max_depth + _HOLE_CLEARANCE
    cutter = (
        cq.Workplane("XY")
        .workplane(offset=settings.total_length)
        .box(
            settings.screw_slot_width + _HOLE_CLEARANCE,
            slot_span,
            depth,
            centered=(True, True, False),
        )
        .translate((0.0, 0.0, -depth))
    )
    return cutter


def build_cocking_mechanism(settings: CockingMechanismSettings) -> cq.Workplane:
    """Build the cocking mechanism handhold solid."""
    body = _revolved_body(settings)
    body = body.cut(_pin_bore_cutter(settings))
    body = _apply_ribs(body, settings)
    body = _apply_bottom_fillet(body, settings)
    body = _bottom_label(body, settings)
    body = body.cut(_screw_slot_cutter(settings))
    return body


def generate_stl(
    output_path: str | Path, settings: CockingMechanismSettings
) -> Path:
    """Build the solid and export binary STL."""
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(build_cocking_mechanism(settings), str(path))
    return path


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "cocking_mechanism.yaml"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the cocking mechanism handhold STL from YAML settings.",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=_default_config_path(),
        help="YAML file with part dimensions (default: cocking_mechanism.yaml beside this script)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output STL path (default: out/cocking_mechanism.stl beside this script)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> Path:
    args = _parse_args(argv)
    settings = load_settings(args.config)
    out = args.output
    if out is None:
        out = Path(__file__).resolve().parent / "out" / "cocking_mechanism.stl"
    path = generate_stl(out, settings)
    print(f"Wrote {path}")
    return path


if __name__ == "__main__":
    main()
