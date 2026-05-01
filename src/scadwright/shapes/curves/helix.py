"""Helix and Spring Components built on path_extrude."""

from __future__ import annotations

import math

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.shapes.curves.paths import helix_path
from scadwright.shapes.curves.sweep import circle_profile, path_extrude


class Helix(Component):
    """Solid helix: a circular cross-section swept along a helical path.

    The helix rises along the z-axis, centered on the origin.
    """

    equations = """
        r, wire_r, pitch, turns > 0
        ?points_per_turn:int = ?points_per_turn or 36
    """

    def build(self):
        path = helix_path(
            r=self.r,
            pitch=self.pitch,
            turns=self.turns,
            points_per_turn=self.points_per_turn,
        )
        profile = circle_profile(self.wire_r, segments=max(8, self.points_per_turn // 3))
        return path_extrude(profile, path)


class Spring(Component):
    """Compression spring: a helix with flat ends for stable resting.

    The spring rises along the z-axis, centered on the origin. Flat
    ends are achieved by adding partial turns at zero pitch at each end.
    """

    equations = """
        r, wire_r, pitch, turns > 0
        ?flat_ends:bool = True if ?flat_ends is None else ?flat_ends
        ?points_per_turn:int = ?points_per_turn or 36
    """

    def build(self):
        ppt = self.points_per_turn
        profile = circle_profile(self.wire_r, segments=max(8, ppt // 3))

        if not self.flat_ends:
            path = helix_path(r=self.r, pitch=self.pitch, turns=self.turns,
                              points_per_turn=ppt)
            return path_extrude(profile, path)

        # Flat ends: half-turn at zero pitch at bottom and top.
        flat_turn = 0.5
        flat_points = max(2, int(flat_turn * ppt))
        body_points = max(2, int(self.turns * ppt))
        total_body_height = self.turns * self.pitch

        path = []
        # Bottom flat half-turn.
        for i in range(flat_points):
            t = i / flat_points
            angle = t * flat_turn * 2 * math.pi
            path.append((
                self.r * math.cos(angle),
                self.r * math.sin(angle),
                0.0,
            ))
        # Body helix.
        start_angle = flat_turn * 2 * math.pi
        for i in range(body_points + 1):
            t = i / body_points
            angle = start_angle + t * self.turns * 2 * math.pi
            z = t * total_body_height
            path.append((
                self.r * math.cos(angle),
                self.r * math.sin(angle),
                z,
            ))
        # Top flat half-turn.
        top_start_angle = start_angle + self.turns * 2 * math.pi
        for i in range(1, flat_points + 1):
            t = i / flat_points
            angle = top_start_angle + t * flat_turn * 2 * math.pi
            path.append((
                self.r * math.cos(angle),
                self.r * math.sin(angle),
                total_body_height,
            ))

        return path_extrude(profile, path)
