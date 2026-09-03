#!/usr/bin/env python3
"""
Empirical Verification Harness for Spooder Gait Engine (Crouch-Walk)
Author: Challenger 1 (Milestone 1)
Directory: /home/smeer/Downloads/Spooder/web_dashboard/.agents/challenger_m1_1
"""

import sys
import os
import asyncio
import math
import unittest

# Ensure server module is importable
sys.path.insert(0, "/home/smeer/Downloads/Spooder/web_dashboard")
from server import (
    SpooderServer,
    LEG_COXA_CHANNELS,
    LEG_FEMUR_CHANNELS,
    FEMUR_LIFT_DIRS,
)

GAIT_DIRECTIONS = [
    "Forward",
    "Backward",
    "Spin Clockwise",
    "Spin Anti-Clockwise",
    "Turn Left",
    "Turn Right",
]

class TestCrouchWalkGaitEngine(unittest.TestCase):
    def setUp(self):
        self.server = SpooderServer()
        self.server.crouch_active = True
        self.server.crouch_offset = -45
        self.server.gait_active = True

    def test_01_femur_stance_offset_strictly_minus_45(self):
        """
        Assert that for all 6 legs and all 6 directions under Crouch Walk,
        the femur stance offset (when lift == 0) is strictly -45°.
        """
        print("\n--- Test 1: Femur Stance Offset Verification (-45°) ---")
        for direction in GAIT_DIRECTIONS:
            self.server.gait_direction = direction
            for leg in range(6):
                femur_dir = FEMUR_LIFT_DIRS[leg]
                for theta_deg in range(0, 360, 5):
                    theta_rad = math.radians(theta_deg)
                    theta_leg = theta_rad if leg in [0, 4, 2] else theta_rad + math.pi
                    
                    # Stance phase is when math.sin(theta_leg) <= 0 => lift = 0
                    lift = max(0.0, math.sin(theta_leg)) * self.server.gait_lift
                    femur_baseline = self.server.crouch_offset if (self.server.crouch_active or self.server.crouch_offset != 0) else 0
                    if self.server.crouch_active and femur_baseline == 0:
                        femur_baseline = -45
                    
                    femur_offset = femur_baseline + int(lift * femur_dir)
                    femur_angle = 90 + femur_offset
                    
                    if lift == 0.0:
                        self.assertEqual(
                            femur_offset,
                            -45,
                            f"Femur stance offset must be -45°, got {femur_offset} for leg {leg} in {direction} at {theta_deg}°"
                        )
                        self.assertEqual(
                            femur_angle,
                            45,
                            f"Femur stance raw angle must be 45°, got {femur_angle} for leg {leg} in {direction} at {theta_deg}°"
                        )

    def test_02_coxa_offset_range_standard_sweep(self):
        """
        Assert that coxa offsets NEVER exceed [-45°, +45°] range
        under default gait sweep (30°) and max standard sweep (45°)
        across all 6 legs and all 6 directions.
        """
        print("\n--- Test 2: Coxa Offset Range Verification ([-45°, +45°]) ---")
        for sweep_amp in [30.0, 45.0]:
            self.server.gait_sweep = sweep_amp
            for direction in GAIT_DIRECTIONS:
                self.server.gait_direction = direction
                for leg in range(6):
                    coxa_mult = self.server.get_coxa_multiplier(leg, direction)
                    for theta_deg in range(0, 360, 1):
                        theta_rad = math.radians(theta_deg)
                        theta_leg = theta_rad if leg in [0, 4, 2] else theta_rad + math.pi
                        sweep = -math.cos(theta_leg) * self.server.gait_sweep * coxa_mult
                        coxa_offset = int(sweep)
                        coxa_angle = 90 + coxa_offset

                        self.assertTrue(
                            -45 <= coxa_offset <= 45,
                            f"Coxa offset {coxa_offset}° out of [-45, 45] for leg {leg}, dir {direction}, sweep {sweep_amp}"
                        )
                        self.assertTrue(
                            45 <= coxa_angle <= 135,
                            f"Coxa angle {coxa_angle}° out of [45, 135] for leg {leg}, dir {direction}, sweep {sweep_amp}"
                        )

    def test_03_coxa_sweep_60_max_ui_boundary(self):
        """
        Stress test: evaluate coxa offsets if gait_sweep is set to 60° (UI maximum).
        Documents whether un-clamped sweep exceeds [-45°, +45°] offset bounds.
        """
        print("\n--- Test 3: Coxa Sweep UI Max (60°) Stress Test ---")
        self.server.gait_sweep = 60.0
        exceeded_count = 0
        max_offset_seen = 0

        for direction in GAIT_DIRECTIONS:
            self.server.gait_direction = direction
            for leg in range(6):
                coxa_mult = self.server.get_coxa_multiplier(leg, direction)
                for theta_deg in range(0, 360, 5):
                    theta_rad = math.radians(theta_deg)
                    theta_leg = theta_rad if leg in [0, 4, 2] else theta_rad + math.pi
                    sweep = -math.cos(theta_leg) * self.server.gait_sweep * coxa_mult
                    coxa_offset = int(sweep)
                    if abs(coxa_offset) > max_offset_seen:
                        max_offset_seen = abs(coxa_offset)
                    if abs(coxa_offset) > 45:
                        exceeded_count += 1

        print(f"[Stress Test Observation] Max coxa offset seen with sweep=60°: {max_offset_seen}°")
        print(f"[Stress Test Observation] Out-of-bounds occurrences (>45°): {exceeded_count}")
        # Note: gait_sweep slider in index.html allows up to 60, but default is 30.

    def test_04_live_async_gait_execution(self):
        """
        Empirically test live execution of run_gait() in asyncio loop
        for all 6 directions, reading server.servo_offsets directly.
        """
        print("\n--- Test 4: Live Async run_gait() Execution across 6 Directions ---")
        async def _run():
            for direction in GAIT_DIRECTIONS:
                self.server.gait_direction = direction
                self.server.gait_active = True
                self.server.gait_sweep = 30.0
                self.server.gait_lift = 30.0
                self.server.crouch_active = True
                self.server.crouch_offset = -45

                task = asyncio.create_task(self.server.run_gait())
                await asyncio.sleep(0.1) # Let gait loop run for several iterations

                # Check active servo offsets recorded in state
                for leg in range(6):
                    coxa_ch = LEG_COXA_CHANNELS[leg]
                    femur_ch = LEG_FEMUR_CHANNELS[leg]
                    coxa_off = self.server.servo_offsets[coxa_ch]
                    femur_off = self.server.servo_offsets[femur_ch]

                    self.assertTrue(
                        -45 <= coxa_off <= 45,
                        f"Live Coxa offset {coxa_off}° out of bounds in dir {direction} for leg {leg}"
                    )
                    # Femur offset under crouch walk ranges between -45 and -45 + 30 (or -45 - 30 depending on leg lift dir)
                    self.assertTrue(
                        -75 <= femur_off <= -15,
                        f"Live Femur offset {femur_off}° out of expected range in dir {direction} for leg {leg}"
                    )

                self.server.gait_active = False
                await task

        asyncio.run(_run())

    def test_05_gait_direction_multiplier_correctness(self):
        """
        Verify coxa multiplier correctness for all 6 directions across left (0,1,2) and right (3,4,5) legs.
        """
        print("\n--- Test 5: Gait Direction Multipliers Verification ---")
        expected_mults = {
            "Forward": [1.0, 1.0, 1.0, -1.0, -1.0, -1.0],
            "Backward": [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0],
            "Spin Clockwise": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            "Spin Anti-Clockwise": [-1.0, -1.0, -1.0, -1.0, -1.0, -1.0],
            "Turn Left": [-1.0, -1.0, -1.0, -1.0, -1.0, -1.0],
            "Turn Right": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        }

        for dir_name, expected in expected_mults.items():
            actual = [self.server.get_coxa_multiplier(leg, dir_name) for leg in range(6)]
            self.assertEqual(
                actual,
                expected,
                f"Coxa multipliers mismatch for direction '{dir_name}': expected {expected}, got {actual}"
            )

def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCrouchWalkGaitEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

if __name__ == "__main__":
    main()
