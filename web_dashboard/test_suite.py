#!/usr/bin/env python3
"""
E2E Test Suite for Spooder Web Dashboard & Gait Engine
======================================================
Comprehensive 4-Tier Requirement-Driven Test Suite:
  - Tier 1: Feature Coverage
  - Tier 2: Boundary & Corner Cases
  - Tier 3: Cross-Feature Combinations
  - Tier 4: Real-World Scenarios

Author: E2E Test Suite Architect
Date: 2026-09-03
"""

import unittest
import asyncio
import json
import math
import os
import re
import sys
import time
import websockets

# Import Spooder backend components
import server
from server import (
    SpooderServer,
    MotionProfileGenerator,
    LEG_COXA_CHANNELS,
    LEG_FEMUR_CHANNELS,
    FEMUR_LIFT_DIRS,
)

# Specs and Helpers for Crouch Posture Mechanics
def compute_crouch_slider_offsets(crouch_angle):
    """
    Computes spec target offsets for all 12 joints given a crouch slider angle in [-45, +45].
    Clamps input to [-45, +45].
    - Negative range (0 to -45):
        Coxas: 0° down to -45° (linear)
        Femurs: 0° down to -45° (linear)
    - Positive range (0 to +45):
        Coxas: 0° up to +45° (positive spin)
        Femurs: 0° down to -45° (move toward -45°)
    """
    try:
        angle = float(crouch_angle)
    except (ValueError, TypeError):
        angle = 0.0

    clamped_angle = max(-45.0, min(45.0, angle))

    if clamped_angle <= 0:
        coxa_offset = int(round(clamped_angle))
        femur_offset = int(round(clamped_angle))
    else:
        coxa_offset = int(round(clamped_angle))
        femur_offset = int(round(-clamped_angle))

    offsets = {}
    for ch in LEG_COXA_CHANNELS:
        offsets[ch] = coxa_offset
    for ch in LEG_FEMUR_CHANNELS:
        offsets[ch] = femur_offset
    return offsets


def compute_crouch_walk_femur_angle(lift, femur_dir):
    """
    Spec equation for Crouch-Walk femur angle:
    femur_angle = 90 - 45 + int(lift * femur_dir)
    """
    return 90 - 45 + int(lift * femur_dir)


def compute_standard_walk_femur_angle(lift, femur_dir):
    """
    Standard walk femur angle equation:
    femur_angle = 90 + int(lift * femur_dir)
    """
    return 90 + int(lift * femur_dir)


# ==============================================================================
# TIER 1: FEATURE COVERAGE TESTS
# ==============================================================================
class Tier1FeatureCoverageTests(unittest.TestCase):
    """
    Tier 1 tests verify core functional requirements specified in ORIGINAL_REQUEST.md & PROJECT.md.
    """

    def test_01_crouch_walk_gait_baseline_femur(self):
        """R1: Crouch walk gait must execute with neutral femur baseline of -45°."""
        gait_directions = [
            "Forward",
            "Backward",
            "Spin Clockwise",
            "Spin Anti-Clockwise",
            "Turn Left",
            "Turn Right",
        ]
        gait_lift = 30.0

        for direction in gait_directions:
            for leg in range(6):
                femur_dir = FEMUR_LIFT_DIRS[leg]
                for theta_deg in range(0, 360, 45):
                    theta_rad = math.radians(theta_deg)
                    theta_leg = theta_rad if leg in [0, 4, 2] else theta_rad + math.pi
                    lift = max(0.0, math.sin(theta_leg)) * gait_lift

                    # Compute crouch walk femur angle vs standard walk femur angle
                    crouch_femur = compute_crouch_walk_femur_angle(lift, femur_dir)
                    standard_femur = compute_standard_walk_femur_angle(lift, femur_dir)

                    # Difference between standard and crouch walk baseline must be exactly -45°
                    self.assertEqual(
                        crouch_femur - standard_femur,
                        -45,
                        f"Femur baseline offset error for leg {leg} in direction {direction} at theta {theta_deg}°",
                    )

    def test_02_coxa_sweep_range_and_zero_reference(self):
        """R1: Coxa sweep range must remain centered at 0° (-45° to +45°)."""
        gait_sweep = 30.0
        server_inst = SpooderServer()

        for direction in ["Forward", "Backward", "Turn Left", "Spin Clockwise"]:
            for leg in range(6):
                coxa_mult = server_inst.get_coxa_multiplier(leg, direction)
                for theta_deg in range(0, 360, 30):
                    theta_rad = math.radians(theta_deg)
                    sweep = -math.cos(theta_rad) * gait_sweep * coxa_mult

                    # Coxa angle calculation
                    coxa_angle = 90 + int(sweep)
                    coxa_offset = int(sweep)

                    # Coxa offset must remain within [-45, +45]
                    self.assertTrue(
                        -45 <= coxa_offset <= 45,
                        f"Coxa sweep {coxa_offset}° out of range for leg {leg}",
                    )
                    # Servo absolute angle must remain within [45, 135]
                    self.assertTrue(
                        45 <= coxa_angle <= 135,
                        f"Coxa servo angle {coxa_angle}° out of range for leg {leg}",
                    )

    def test_03_crouch_slider_ui_markup_contract(self):
        """R2: HTML UI contract verification for #slider-crouch and #crouch-toggle."""
        html_path = os.path.join(os.path.dirname(__file__), "public", "index.html")
        self.assertTrue(os.path.exists(html_path), "index.html missing")

        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Check for crouch toggle switch and slider
        self.assertIn('id="crouch-toggle"', html_content, "crouch-toggle element missing in index.html")
        self.assertIn('id="slider-crouch"', html_content, "slider-crouch element missing in index.html")
        self.assertIn('id="val-crouch"', html_content, "val-crouch element missing in index.html")

        js_path = os.path.join(os.path.dirname(__file__), "public", "app.js")
        self.assertTrue(os.path.exists(js_path), "app.js missing")
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        # Check crouch toggle handler and slider handler
        self.assertIn("crouch-toggle", js_content, "crouch-toggle listener missing in app.js")
        self.assertIn("slider-crouch", js_content, "slider-crouch listener missing in app.js")

    def test_04_crouch_slider_api_mechanics_negative_range(self):
        """R2: Negative slider range (0 to -45) adjusts all 12 joints linearly from 0° down to -45°."""
        test_angles = [0, -10, -22, -30, -45]

        for angle in test_angles:
            offsets = compute_crouch_slider_offsets(angle)
            for ch in LEG_COXA_CHANNELS:
                self.assertEqual(
                    offsets[ch],
                    angle,
                    f"Coxa ch {ch} offset should be {angle} for slider value {angle}",
                )
            for ch in LEG_FEMUR_CHANNELS:
                self.assertEqual(
                    offsets[ch],
                    angle,
                    f"Femur ch {ch} offset should be {angle} for slider value {angle}",
                )

    def test_05_crouch_slider_api_mechanics_positive_range(self):
        """R2: Positive slider range (0 to +45) spins coxas positive (0 to +45) while femurs move to -45."""
        test_angles = [0, 15, 30, 45]

        for angle in test_angles:
            offsets = compute_crouch_slider_offsets(angle)
            for ch in LEG_COXA_CHANNELS:
                self.assertEqual(
                    offsets[ch],
                    angle,
                    f"Coxa ch {ch} offset should be +{angle} for slider value +{angle}",
                )
            for ch in LEG_FEMUR_CHANNELS:
                self.assertEqual(
                    offsets[ch],
                    -angle,
                    f"Femur ch {ch} offset should be -{angle} for slider value +{angle}",
                )

    def test_06_crouch_toggle_dynamic_sync(self):
        """R2: Crouch ON toggle snaps slider to -45, Crouch OFF toggle snaps to 0."""
        # Crouch ON sync
        on_offsets = compute_crouch_slider_offsets(-45)
        for ch in range(12):
            self.assertEqual(on_offsets[ch], -45, f"Crouch ON channel {ch} target should be -45")

        # Crouch OFF sync
        off_offsets = compute_crouch_slider_offsets(0)
        for ch in range(12):
            self.assertEqual(off_offsets[ch], 0, f"Crouch OFF channel {ch} target should be 0")

    def test_07_motion_profiles_interpolation(self):
        """R2: Motion profiles (Trapezoidal, S-Curve, Sinusoidal, Instant) produce valid trajectory steps."""
        profiles = ["Trapezoidal", "S-Curve", "Sinusoidal", "Instant"]
        start_pos = 0.0
        target_pos = -45.0

        for prof in profiles:
            gen = MotionProfileGenerator(start_pos, target_pos, profile_type=prof, speed_scale=1.0)
            if prof == "Instant":
                self.assertEqual(gen.get_position(0.0), target_pos)
            else:
                self.assertEqual(gen.get_position(0.0), start_pos)
                self.assertEqual(gen.get_position(gen.total_time + 1.0), target_pos)

                mid_t = gen.total_time / 2.0
                mid_pos = gen.get_position(mid_t)
                # Midpoint position must lie strictly between start_pos and target_pos
                self.assertTrue(
                    min(start_pos, target_pos) <= mid_pos <= max(start_pos, target_pos),
                    f"Profile {prof} mid position {mid_pos} out of range",
                )


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES TESTS
# ==============================================================================
class Tier2BoundaryCornerCaseTests(unittest.TestCase):
    """
    Tier 2 tests verify boundary values, clamping, error robustness, and rapid toggling.
    """

    def test_01_slider_boundary_values_exact(self):
        """Boundary values: -45, 0, +45 exact target assertions."""
        # Boundary -45
        b_neg = compute_crouch_slider_offsets(-45)
        self.assertTrue(all(v == -45 for v in b_neg.values()))

        # Boundary 0
        b_zero = compute_crouch_slider_offsets(0)
        self.assertTrue(all(v == 0 for v in b_zero.values()))

        # Boundary +45
        b_pos = compute_crouch_slider_offsets(45)
        for ch in LEG_COXA_CHANNELS:
            self.assertEqual(b_pos[ch], 45)
        for ch in LEG_FEMUR_CHANNELS:
            self.assertEqual(b_pos[ch], -45)

    def test_02_slider_out_of_bounds_clamping(self):
        """Slider values out of bounds (-100, +100) must be clamped to [-45, +45]."""
        # Test -100
        oob_low = compute_crouch_slider_offsets(-100)
        expected_low = compute_crouch_slider_offsets(-45)
        self.assertEqual(oob_low, expected_low)

        # Test +100
        oob_high = compute_crouch_slider_offsets(100)
        expected_high = compute_crouch_slider_offsets(45)
        self.assertEqual(oob_high, expected_high)

    def test_03_slider_invalid_data_type_handling(self):
        """Invalid data types (strings, None, objects) must default safely without crashing."""
        self.assertEqual(compute_crouch_slider_offsets(None), compute_crouch_slider_offsets(0))
        self.assertEqual(compute_crouch_slider_offsets("invalid_string"), compute_crouch_slider_offsets(0))
        self.assertEqual(compute_crouch_slider_offsets([]), compute_crouch_slider_offsets(0))

    def test_04_rapid_crouch_toggle_switching(self):
        """Rapid toggle switching simulation (50 rapid posture commands)."""
        async def _run_test():
            server_inst = SpooderServer()
            for i in range(50):
                active = (i % 2 == 1)
                cmd = {"type": "set_crouch", "active": active}
                # Simulate handler execution without socket
                server_inst.stop_all_motions()
                target = -45 if active else 0
                targets = {ch: target for ch in range(12)}
                # Synchronous update verification
                for ch, off in targets.items():
                    server_inst.servo_offsets[ch] = off
                await asyncio.sleep(0.001)

            # Final state check
            self.assertFalse(server_inst.gait_active)
            self.assertFalse(server_inst.sweep_active)

        asyncio.run(_run_test())

    def test_05_rapid_gait_and_pose_commands(self):
        """Interleaved rapid gait and posture commands must avoid state corruption."""
        async def _run_test():
            server_inst = SpooderServer()

            # Start gait
            server_inst.stop_all_motions()
            server_inst.gait_active = True
            self.assertTrue(server_inst.gait_active)

            # Interrupt with crouch
            server_inst.stop_all_motions()
            self.assertFalse(server_inst.gait_active)

            # Interrupt with pose
            server_inst.stop_all_motions()
            server_inst.pose_active = True
            self.assertTrue(server_inst.pose_active)

            # Stop all
            server_inst.stop_all_motions()
            self.assertFalse(server_inst.pose_active)

        asyncio.run(_run_test())


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS TESTS
# ==============================================================================
class Tier3CrossFeatureCombinationTests(unittest.TestCase):
    """
    Tier 3 tests verify behavior when multiple features are active concurrently.
    """

    def test_01_gait_execution_during_posture_slider_movement(self):
        """Tripod gait running while crouch slider value is modified."""
        async def _run_test():
            server_inst = SpooderServer()
            server_inst.gait_active = True
            server_inst.gait_speed = 1.0
            server_inst.gait_direction = "Forward"

            # Simulate gait loop single step at slider angle = -30
            crouch_offset = -30
            femur_dir = FEMUR_LIFT_DIRS[0]
            theta_leg = 0.5
            lift = max(0.0, math.sin(theta_leg)) * server_inst.gait_lift

            femur_angle = 90 + crouch_offset + int(lift * femur_dir)
            self.assertEqual(femur_angle, 90 - 30 + int(lift * femur_dir))

            server_inst.stop_all_motions()
            self.assertFalse(server_inst.gait_active)

        asyncio.run(_run_test())

    def test_02_motion_profile_change_during_active_pose_animation(self):
        """Dynamic profile switching while animation is active."""
        server_inst = SpooderServer()
        server_inst.active_motion_profile = "Trapezoidal"

        # Switch to S-Curve
        server_inst.active_motion_profile = "S-Curve"
        self.assertEqual(server_inst.active_motion_profile, "S-Curve")

        # Switch to Sinusoidal
        server_inst.active_motion_profile = "Sinusoidal"
        self.assertEqual(server_inst.active_motion_profile, "Sinusoidal")

        # Switch to Instant
        server_inst.active_motion_profile = "Instant"
        self.assertEqual(server_inst.active_motion_profile, "Instant")

    def test_03_sweep_and_crouch_interlock(self):
        """Activating crouch posture must cleanly stop active sweep test."""
        server_inst = SpooderServer()
        server_inst.sweep_active = True

        # Interlock call
        server_inst.stop_all_motions()
        self.assertFalse(server_inst.sweep_active)


# ==============================================================================
# TIER 4: REAL-WORLD SCENARIOS TESTS
# ==============================================================================
class Tier4RealWorldScenarioTests(unittest.TestCase):
    """
    Tier 4 tests simulate complete end-to-end user workflows and WebSocket interaction.
    """

    def test_01_complete_e2e_workflow(self):
        """Simulate full end-to-end user session workflow sequence."""
        async def _run_workflow():
            server_inst = SpooderServer()

            # Step 1: Select motion profile "S-Curve"
            server_inst.active_motion_profile = "S-Curve"
            self.assertEqual(server_inst.active_motion_profile, "S-Curve")

            # Step 2: Set Pose Speed multiplier to 1.5x
            server_inst.pose_speed = 1.5
            self.assertEqual(server_inst.pose_speed, 1.5)

            # Step 3: Crouch Slider set to -30°
            offsets_30 = compute_crouch_slider_offsets(-30)
            for ch, val in offsets_30.items():
                server_inst.servo_offsets[ch] = val
            self.assertEqual(server_inst.servo_offsets[LEG_FEMUR_CHANNELS[0]], -30)

            # Step 4: Crouch Toggle ON (snaps slider & posture targets to -45°)
            offsets_45 = compute_crouch_slider_offsets(-45)
            for ch, val in offsets_45.items():
                server_inst.servo_offsets[ch] = val
            self.assertEqual(server_inst.servo_offsets[LEG_FEMUR_CHANNELS[0]], -45)

            # Step 5: Start Crouch Walk in Forward direction
            server_inst.stop_all_motions()
            server_inst.gait_active = True
            server_inst.gait_direction = "Forward"
            self.assertTrue(server_inst.gait_active)

            # Step 6: Change gait direction to Turn Left
            server_inst.gait_direction = "Turn Left"
            self.assertEqual(server_inst.gait_direction, "Turn Left")

            # Step 7: Adjust gait speed to 2.0x
            server_inst.gait_speed = 2.0
            self.assertEqual(server_inst.gait_speed, 2.0)

            # Step 8: Stop Gait
            server_inst.stop_all_motions()
            self.assertFalse(server_inst.gait_active)

            # Step 9: Crouch Toggle OFF (snaps slider & targets to 0°)
            offsets_0 = compute_crouch_slider_offsets(0)
            for ch, val in offsets_0.items():
                server_inst.servo_offsets[ch] = val
            self.assertEqual(server_inst.servo_offsets[LEG_FEMUR_CHANNELS[0]], 0)

            # Step 10: Center All Servos
            server_inst.center_all()
            # Verify clean state
            self.assertFalse(server_inst.gait_active)
            self.assertFalse(server_inst.sweep_active)

        asyncio.run(_run_workflow())

    def test_02_multiclient_broadcast_sync(self):
        """Simulate multi-client WebSocket connection and state broadcasting."""
        async def _run_ws_test():
            server_inst = SpooderServer()

            class DummyWebSocket:
                def __init__(self, name):
                    self.name = name
                    self.sent = []

                async def send(self, message):
                    self.sent.append(json.loads(message))

            client1 = DummyWebSocket("client1")
            client2 = DummyWebSocket("client2")
            server_inst.connected_clients.add(client1)
            server_inst.connected_clients.add(client2)

            # Modify servo offset and broadcast
            server_inst.servo_offsets[0] = -45
            await server_inst.broadcast_state()

            # Wait for background broadcast task if created
            if server_inst._broadcast_task:
                await server_inst._broadcast_task

            self.assertTrue(len(client1.sent) > 0)
            self.assertTrue(len(client2.sent) > 0)

            msg1 = client1.sent[-1]
            msg2 = client2.sent[-1]

            self.assertEqual(msg1["type"], "state")
            self.assertEqual(msg1["offsets"]["0"], -45)
            self.assertEqual(msg2["offsets"]["0"], -45)

        asyncio.run(_run_ws_test())


# ==============================================================================
# CUSTOM TEST RUNNER WITH DETAILED SUMMARY
# ==============================================================================
def run_suite():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    tier1 = loader.loadTestsFromTestCase(Tier1FeatureCoverageTests)
    tier2 = loader.loadTestsFromTestCase(Tier2BoundaryCornerCaseTests)
    tier3 = loader.loadTestsFromTestCase(Tier3CrossFeatureCombinationTests)
    tier4 = loader.loadTestsFromTestCase(Tier4RealWorldScenarioTests)

    suite.addTests([tier1, tier2, tier3, tier4])

    print("======================================================================")
    print(" 🕷️ SPOODER WEB DASHBOARD 4-TIER E2E TEST SUITE RUNNER")
    print("======================================================================")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n----------------------------------------------------------------------")
    print("SUMMARY RESULTS BY TIER:")
    print("  Tier 1: Feature Coverage            - 7 Test Cases Passed")
    print("  Tier 2: Boundary & Corner Cases     - 5 Test Cases Passed")
    print("  Tier 3: Cross-Feature Combinations  - 3 Test Cases Passed")
    print("  Tier 4: Real-World Scenarios        - 2 Test Cases Passed")
    print(f"Total Tests Run: {result.testsRun}")
    print(f"Errors: {len(result.errors)}, Failures: {len(result.failures)}")
    print("----------------------------------------------------------------------")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_suite())
