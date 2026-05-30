"""Replacement drive wheel for a Nerf-style (Zuru) blaster — CadQuery model, mm.

Coordinate system
-----------------
+Y : wheel rotation axis; extension length (20 mm) along -Y from the lower face
+X : extension width (9 mm)
+Z : extension thickness (9.5 mm at wheel); Z = 0 mates the wheel lower flat face

Dimensions and label text live in a YAML file; pass ``--config`` when running this script.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
import yaml

_HOLE_CLEARANCE = 0.5


@dataclass(frozen=True)
class ZuruReplacementSettings:
    """User-facing dimensions loaded from YAML."""

    wheel_od: float
    wheel_thickness: float

    o_ring_cord_diameter: float
    o_ring_groove_radial_depth: float
    o_ring_groove_axial_width_factor: float

    extension_length: float
    extension_width: float
    extension_thickness_at_wheel: float
    extension_thickness_at_end: float
    extension_flat_under_start_y: float

    through_hole_diameter: float
    through_hole_edge_offset: float

    screw_hole_diameter: float
    screw_hole_center_from_wheel_face: float
    screw_ring_cutout_inner_diameter: float
    screw_ring_cutout_outer_diameter: float
    screw_ring_cutout_depth: float
    screw_ring_trim_depth: float

    wheel_label_text: str
    wheel_label_height: float
    wheel_label_depth: float

    @property
    def wheel_radius(self) -> float:
        return self.wheel_od / 2.0

    @property
    def wheel_half_thickness(self) -> float:
        return self.wheel_thickness / 2.0

    @property
    def wheel_lower_face_y(self) -> float:
        return -self.wheel_half_thickness

    @property
    def wheel_upper_face_y(self) -> float:
        return self.wheel_half_thickness

    @property
    def o_ring_groove_axial_width(self) -> float:
        return self.o_ring_cord_diameter * self.o_ring_groove_axial_width_factor

    @property
    def o_ring_groove_outer_radius(self) -> float:
        return self.wheel_radius

    @property
    def o_ring_groove_inner_radius(self) -> float:
        return self.wheel_radius - self.o_ring_groove_radial_depth

    @property
    def extension_bottom_at_wheel_z(self) -> float:
        return -self.extension_thickness_at_wheel

    @property
    def extension_bottom_at_end_z(self) -> float:
        return -self.extension_thickness_at_end

    @property
    def extension_half_width(self) -> float:
        return self.extension_width / 2.0

    @property
    def through_hole_center_along_length(self) -> float:
        return (
            self.extension_length
            - self.through_hole_edge_offset
            - self.through_hole_diameter / 2.0
        )

    @property
    def screw_hole_radius(self) -> float:
        return self.screw_hole_diameter / 2.0

    @property
    def screw_ring_cutout_inner_radius(self) -> float:
        return self.screw_ring_cutout_inner_diameter / 2.0

    @property
    def screw_ring_cutout_outer_radius(self) -> float:
        return self.screw_ring_cutout_outer_diameter / 2.0

    @property
    def screw_hole_center_y(self) -> float:
        return self.wheel_lower_face_y - self.screw_hole_center_from_wheel_face

    @property
    def through_hole_center_y(self) -> float:
        return self.wheel_lower_face_y - self.through_hole_center_along_length

    def extension_bottom_z_at_length(self, length: float) -> float:
        """Underside Z at distance along the extension from the wheel (length in mm)."""
        if length >= self.extension_flat_under_start_y:
            return self.extension_bottom_at_end_z
        t = length / self.extension_flat_under_start_y
        return self.extension_bottom_at_wheel_z + t * (
            self.extension_bottom_at_end_z - self.extension_bottom_at_wheel_z
        )

    @property
    def screw_bottom_z(self) -> float:
        return self.extension_bottom_z_at_length(self.screw_hole_center_from_wheel_face)

    @property
    def screw_mount_cut_depth(self) -> float:
        return -self.screw_bottom_z + _HOLE_CLEARANCE


def load_settings(path: Path | str) -> ZuruReplacementSettings:
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
    return ZuruReplacementSettings(**raw)


def _solid_cylinder_along_z(
    x: float,
    y: float,
    z_start: float,
    depth: float,
    radius: float,
    downward: bool = True,
) -> cq.Solid:
    """Cylinder with axis parallel to Z."""
    direction = cq.Vector(0.0, 0.0, -1.0 if downward else 1.0)
    return cq.Solid.makeCylinder(
        radius,
        depth,
        cq.Vector(x, y, z_start),
        direction,
    )


def _annulus_cut_along_z(
    x: float,
    y: float,
    z_start: float,
    depth: float,
    inner_radius: float,
    outer_radius: float,
    downward: bool = True,
) -> cq.Workplane:
    """Annular cutter with axis parallel to Z."""
    outer = _solid_cylinder_along_z(x, y, z_start, depth, outer_radius, downward)
    inner = _solid_cylinder_along_z(
        x,
        y,
        z_start,
        depth + _HOLE_CLEARANCE,
        inner_radius,
        downward,
    )
    return cq.Workplane().newObject([outer]).cut(cq.Workplane().newObject([inner]))


def _wheel_disk(settings: ZuruReplacementSettings) -> cq.Workplane:
    """Wheel disk; rotation axis Y, centered on the origin."""
    return cq.Workplane("XZ").cylinder(
        settings.wheel_thickness,
        settings.wheel_radius,
        centered=(True, True, True),
    )


def _oring_groove(wheel: cq.Workplane, settings: ZuruReplacementSettings) -> cq.Workplane:
    """Square-cornered groove on the OD; cuts inward only (axis Y, centered axially)."""
    groove_cutter = (
        cq.Workplane("XZ")
        .cylinder(
            settings.o_ring_groove_axial_width,
            settings.o_ring_groove_outer_radius,
            centered=(True, True, True),
        )
        .cut(
            cq.Workplane("XZ").cylinder(
                settings.o_ring_groove_axial_width + _HOLE_CLEARANCE,
                settings.o_ring_groove_inner_radius,
                centered=(True, True, True),
            )
        )
    )
    return wheel.cut(groove_cutter)


def _wheel_label(wheel: cq.Workplane, settings: ZuruReplacementSettings) -> cq.Workplane:
    """Engrave label on the upper flat face (+Y), opposite the extension."""
    if not settings.wheel_label_text:
        return wheel

    label_wp = cq.Workplane("XZ").text(
        settings.wheel_label_text,
        settings.wheel_label_height,
        settings.wheel_label_depth,
        halign="center",
        valign="center",
        combine=False,
    )
    letters = label_wp.solids().vals()
    if not letters:
        return wheel

    cutter = letters[0]
    for letter in letters[1:]:
        cutter = cutter.fuse(letter)
    cutter = cutter.translate((0.0, settings.wheel_upper_face_y, 0.0))
    return wheel.cut(cq.Workplane().newObject([cutter]))


def _cut_screw_mount(
    extension: cq.Workplane, settings: ZuruReplacementSettings
) -> cq.Workplane:
    """2 mm bore through; 4.5–8 mm pocket and 1 mm trim, all measured from Z=0 (top face)."""
    y = settings.screw_hole_center_y
    x = 0.0
    extension_top_z = 0.0

    screw_hole = cq.Workplane().newObject(
        [
            _solid_cylinder_along_z(
                x,
                y,
                extension_top_z,
                settings.screw_mount_cut_depth,
                settings.screw_hole_radius,
            )
        ]
    )
    ring_cutout = _annulus_cut_along_z(
        x,
        y,
        extension_top_z,
        settings.screw_ring_cutout_depth + _HOLE_CLEARANCE,
        settings.screw_ring_cutout_inner_radius,
        settings.screw_ring_cutout_outer_radius,
    )
    ring_trim = _annulus_cut_along_z(
        x,
        y,
        extension_top_z,
        settings.screw_ring_trim_depth + _HOLE_CLEARANCE,
        settings.screw_hole_radius,
        settings.screw_ring_cutout_inner_radius,
    )
    return extension.cut(screw_hole).cut(ring_cutout).cut(ring_trim)


def _extension_solid(settings: ZuruReplacementSettings) -> cq.Workplane:
    """Tab on wheel lower flat (y = -t/2); length -Y, width +X, 9.5 mm down in -Z."""
    extension = (
        cq.Workplane("YZ")
        .polyline(
            [
                (0.0, 0.0),
                (-settings.extension_length, 0.0),
                (-settings.extension_length, settings.extension_bottom_at_end_z),
                (
                    -settings.extension_flat_under_start_y,
                    settings.extension_bottom_at_end_z,
                ),
                (0.0, settings.extension_bottom_at_wheel_z),
            ]
        )
        .close()
        .extrude(settings.extension_width)
        .translate(
            (-settings.extension_half_width, settings.wheel_lower_face_y, 0.0)
        )
    )
    pin_bottom_z = settings.extension_bottom_z_at_length(
        settings.through_hole_center_along_length
    )
    pin_cutter = cq.Workplane().newObject(
        [
            _solid_cylinder_along_z(
                0.0,
                settings.through_hole_center_y,
                0.0,
                -pin_bottom_z + _HOLE_CLEARANCE,
                settings.through_hole_diameter / 2.0,
            )
        ]
    )
    extension = extension.cut(pin_cutter)
    return _cut_screw_mount(extension, settings)


def build_zuru_wheel(settings: ZuruReplacementSettings) -> cq.Workplane:
    """Union of grooved wheel and extension with holes."""
    wheel = _wheel_label(_oring_groove(_wheel_disk(settings), settings), settings)
    extension = _extension_solid(settings)
    return wheel.union(extension)


def generate_stl(
    output_path: str | Path, settings: ZuruReplacementSettings
) -> Path:
    """Build the solid and export binary STL."""
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(build_zuru_wheel(settings), str(path))
    return path


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "zuru_replacement.yaml"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Zuru replacement wheel STL from YAML settings.",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=_default_config_path(),
        help="YAML file with part dimensions (default: zuru_replacement.yaml beside this script)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output STL path (default: misc_parts/out/zuru_replacement.stl)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> Path:
    args = _parse_args(argv)
    settings = load_settings(args.config)
    out = args.output
    if out is None:
        out = Path(__file__).resolve().parent / "out" / "zuru_replacement.stl"
    path = generate_stl(out, settings)
    print(f"Wrote {path}")
    return path


if __name__ == "__main__":
    main()
