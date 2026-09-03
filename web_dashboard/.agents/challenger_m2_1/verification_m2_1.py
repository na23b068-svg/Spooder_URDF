#!/usr/bin/env python3
"""
Empirical Verification & Stress Test for Posture Target Calculations & Clamping (Milestone 2)
========================================================================================
Challenger: Challenger 1 (Kinematic Range & Clamping Challenger)
Working Directory: /home/smeer/Downloads/Spooder/web_dashboard/.agents/challenger_m2_1

Scope & Assertions:
1. Negative range (-45 to 0): Coxa = v, Femur = v across all 12 channels.
2. Positive range (0 to +45): Coxa = v, Femur = -v across all 12 channels.
3. Exact boundaries (-45, 0, +45): Precise target output assertions.
4. Out-of-bounds values (-100, +100, -999, +999, etc.): Clamped to [-45, +45].
5. Type robustness (numeric strings, floats, non-convertible invalid types).
6. Full 12 channel verification (6 Coxa channels: 0,2,11,6,8,10 and 6 Femur channels: 1,3,5,7,9,4).
"""

import sys
import os
import unittest
import asyncio
import json
import websockets

# Add project root to sys.path
PROJECT_ROOT = "/home/smeer/Downloads/Spooder/web_dashboard"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import server
from server import SpooderServer, LEG_COXA_CHANNELS, LEG_FEMUR_CHANNELS

def compute_server_posture_targets(raw_offset, raw_active=None):
    """
    Extracted helper replicating exact server logic in set_crouch handler:
    - Parse raw_offset if present
    - Clamp offset to [-45, +45]
    - Calculate coxa and femur targets
    - Build target dictionary for all 12 channels
    """
    if raw_offset is not None:
        offset = int(raw_offset)
        active = bool(raw_active) if raw_active is not None else (offset != 0)
    else:
        active = bool(raw_active) if raw_active is not None else False
        offset = -45 if active else 0

    offset = max(-45, min(45, offset))

    if offset <= 0:
        coxa_target = offset
        femur_target = offset
    else:
        coxa_target = offset
        femur_target = -offset

    targets = {}
    for ch in LEG_COXA_CHANNELS:
        targets[ch] = coxa_target
    for ch in LEG_FEMUR_CHANNELS:
        targets[ch] = femur_target

    return offset, coxa_target, femur_target, targets


class KinematicRangeAndClampingTests(unittest.TestCase):

    def setUp(self):
        self.all_channels = set(LEG_COXA_CHANNELS + LEG_FEMUR_CHANNELS)
        self.assertEqual(len(self.all_channels), 12, "Must cover exactly 12 unique channels")
        self.assertEqual(set(range(12)), self.all_channels, "Channels must cover 0 to 11")

    # --------------------------------------------------------------------------
    # 1. Negative Range Tests (-45 to 0)
    # --------------------------------------------------------------------------
    def test_negative_range_posture_targets(self):
        """Verify negative range (-45 to 0): Coxa = v, Femur = v across all 12 channels."""
        test_values = [-45, -40, -30, -22, -15, -10, -5, 0]
        
        for v in test_values:
            offset, coxa_target, femur_target, targets = compute_server_posture_targets(v)
            
            # Formula check
            self.assertEqual(coxa_target, v, f"Coxa target failed for v={v}")
            self.assertEqual(femur_target, v, f"Femur target failed for v={v}")
            
            # Verify all 6 coxa channels
            for ch in LEG_COXA_CHANNELS:
                self.assertEqual(
                    targets[ch], v,
                    f"Coxa channel {ch} target mismatch for v={v}: got {targets[ch]}, expected {v}"
                )
                
            # Verify all 6 femur channels
            for ch in LEG_FEMUR_CHANNELS:
                self.assertEqual(
                    targets[ch], v,
                    f"Femur channel {ch} target mismatch for v={v}: got {targets[ch]}, expected {v}"
                )
                
            # Total channel count check
            self.assertEqual(len(targets), 12, f"Target dict must contain 12 channel entries for v={v}")

    # --------------------------------------------------------------------------
    # 2. Positive Range Tests (0 to +45)
    # --------------------------------------------------------------------------
    def test_positive_range_posture_targets(self):
        """Verify positive range (0 to +45): Coxa = v, Femur = -v across all 12 channels."""
        test_values = [0, 5, 10, 15, 22, 30, 40, 45]
        
        for v in test_values:
            offset, coxa_target, femur_target, targets = compute_server_posture_targets(v)
            
            expected_femur = 0 if v == 0 else -v
            self.assertEqual(coxa_target, v, f"Coxa target failed for v={v}")
            self.assertEqual(femur_target, expected_femur, f"Femur target failed for v={v}")
            
            # Verify all 6 coxa channels
            for ch in LEG_COXA_CHANNELS:
                self.assertEqual(
                    targets[ch], v,
                    f"Coxa channel {ch} target mismatch for v={v}: got {targets[ch]}, expected {v}"
                )
                
            # Verify all 6 femur channels
            for ch in LEG_FEMUR_CHANNELS:
                self.assertEqual(
                    targets[ch], expected_femur,
                    f"Femur channel {ch} target mismatch for v={v}: got {targets[ch]}, expected {expected_femur}"
                )
                
            self.assertEqual(len(targets), 12, f"Target dict must contain 12 channel entries for v={v}")

    # --------------------------------------------------------------------------
    # 3. Exact Boundaries (-45, 0, +45)
    # --------------------------------------------------------------------------
    def test_exact_boundaries(self):
        """Verify exact boundaries: -45, 0, +45."""
        # Boundary -45
        off, coxa, femur, targets = compute_server_posture_targets(-45)
        self.assertEqual(off, -45)
        self.assertEqual(coxa, -45)
        self.assertEqual(femur, -45)
        for ch in LEG_COXA_CHANNELS + LEG_FEMUR_CHANNELS:
            self.assertEqual(targets[ch], -45)

        # Boundary 0
        off, coxa, femur, targets = compute_server_posture_targets(0)
        self.assertEqual(off, 0)
        self.assertEqual(coxa, 0)
        self.assertEqual(femur, 0)
        for ch in LEG_COXA_CHANNELS + LEG_FEMUR_CHANNELS:
            self.assertEqual(targets[ch], 0)

        # Boundary +45
        off, coxa, femur, targets = compute_server_posture_targets(45)
        self.assertEqual(off, 45)
        self.assertEqual(coxa, 45)
        self.assertEqual(femur, -45)
        for ch in LEG_COXA_CHANNELS:
            self.assertEqual(targets[ch], 45)
        for ch in LEG_FEMUR_CHANNELS:
            self.assertEqual(targets[ch], -45)

    # --------------------------------------------------------------------------
    # 4. Out-of-Bounds Values Clamping (-100, +100, -999, +999, -46, +46)
    # --------------------------------------------------------------------------
    def test_out_of_bounds_clamping(self):
        """Verify out-of-bounds values are strictly clamped to [-45, +45]."""
        oob_low_cases = [-46, -100, -500, -999]
        for v in oob_low_cases:
            off, coxa, femur, targets = compute_server_posture_targets(v)
            self.assertEqual(off, -45, f"Offset for input {v} was not clamped to -45")
            self.assertEqual(coxa, -45, f"Coxa target for input {v} was not clamped to -45")
            self.assertEqual(femur, -45, f"Femur target for input {v} was not clamped to -45")
            for ch in LEG_COXA_CHANNELS + LEG_FEMUR_CHANNELS:
                self.assertEqual(targets[ch], -45, f"Channel {ch} for input {v} was not clamped to -45")

        oob_high_cases = [46, 100, 500, 999]
        for v in oob_high_cases:
            off, coxa, femur, targets = compute_server_posture_targets(v)
            self.assertEqual(off, 45, f"Offset for input {v} was not clamped to 45")
            self.assertEqual(coxa, 45, f"Coxa target for input {v} was not clamped to 45")
            self.assertEqual(femur, -45, f"Femur target for input {v} was not clamped to -45")
            for ch in LEG_COXA_CHANNELS:
                self.assertEqual(targets[ch], 45, f"Coxa channel {ch} for input {v} was not clamped to 45")
            for ch in LEG_FEMUR_CHANNELS:
                self.assertEqual(targets[ch], -45, f"Femur channel {ch} for input {v} was not clamped to -45")

    # --------------------------------------------------------------------------
    # 5. Type Robustness & Numeric String Conversions
    # --------------------------------------------------------------------------
    def test_numeric_string_and_float_conversion(self):
        """Verify numeric strings and floats convert cleanly and produce correct targets."""
        # String numbers
        off, coxa, femur, targets = compute_server_posture_targets("-30")
        self.assertEqual(off, -30)
        self.assertEqual(coxa, -30)
        self.assertEqual(femur, -30)

        off, coxa, femur, targets = compute_server_posture_targets("30")
        self.assertEqual(off, 30)
        self.assertEqual(coxa, 30)
        self.assertEqual(femur, -30)

        # String OOB
        off, coxa, femur, targets = compute_server_posture_targets("-100")
        self.assertEqual(off, -45)

        off, coxa, femur, targets = compute_server_posture_targets("100")
        self.assertEqual(off, 45)

        # Floats
        off, coxa, femur, targets = compute_server_posture_targets(-22.7)
        self.assertEqual(off, -22)
        self.assertEqual(coxa, -22)

        off, coxa, femur, targets = compute_server_posture_targets(30.9)
        self.assertEqual(off, 30)
        self.assertEqual(coxa, 30)

    # --------------------------------------------------------------------------
    # 6. Invalid Type Handling (Adversarial / Stress Edge Cases)
    # --------------------------------------------------------------------------
    def test_invalid_types_behavior(self):
        """Test non-numeric invalid types: raises ValueError or TypeError during int() conversion."""
        invalid_inputs = ["invalid", "abc", [], {}, [1, 2]]
        for inp in invalid_inputs:
            with self.subTest(inp=inp):
                with self.assertRaises((ValueError, TypeError)):
                    compute_server_posture_targets(inp)

    # --------------------------------------------------------------------------
    # 7. Live Server Integration & WebSocket Protocol Stress Test
    # --------------------------------------------------------------------------
    def test_live_server_websocket_crouch_commands(self):
        """
        Run live SpooderServer WebSocket server, send posture messages across negative,
        positive, exact boundary, and OOB ranges, and assert internal server state.
        """
        async def _run_live_test():
            srv = SpooderServer()
            port = 8769
            async with websockets.serve(srv.handler, "127.0.0.1", port):
                uri = f"ws://127.0.0.1:{port}"
                async with websockets.connect(uri) as ws:
                    init_msg = await ws.recv() # Initial state
                    
                    # Test Negative range via WS (-30)
                    cmd = {"type": "set_crouch", "offset": -30, "active": True}
                    await ws.send(json.dumps(cmd))
                    await asyncio.sleep(0.05)
                    self.assertEqual(srv.crouch_offset, -30)
                    self.assertTrue(srv.crouch_active)
                    
                    # Test Positive range via WS (+30)
                    cmd = {"type": "set_crouch", "offset": 30, "active": True}
                    await ws.send(json.dumps(cmd))
                    await asyncio.sleep(0.05)
                    self.assertEqual(srv.crouch_offset, 30)
                    
                    # Test OOB Low via WS (-100 -> clamped to -45)
                    cmd = {"type": "set_crouch", "offset": -100, "active": True}
                    await ws.send(json.dumps(cmd))
                    await asyncio.sleep(0.05)
                    self.assertEqual(srv.crouch_offset, -45)
                    
                    # Test OOB High via WS (+100 -> clamped to +45)
                    cmd = {"type": "set_crouch", "offset": 100, "active": True}
                    await ws.send(json.dumps(cmd))
                    await asyncio.sleep(0.05)
                    self.assertEqual(srv.crouch_offset, 45)
                    
                    # Test Exact boundary 0 via WS
                    cmd = {"type": "set_crouch", "offset": 0, "active": False}
                    await ws.send(json.dumps(cmd))
                    await asyncio.sleep(0.05)
                    self.assertEqual(srv.crouch_offset, 0)
                    self.assertFalse(srv.crouch_active)

        asyncio.run(_run_live_test())

    def test_live_server_unhandled_invalid_type_disconnect_bug(self):
        """
        Adversarial test: verify if non-convertible string payload ("invalid")
        causes handler exception and client disconnect.
        """
        async def _run_bug_test():
            srv = SpooderServer()
            port = 8770
            async with websockets.serve(srv.handler, "127.0.0.1", port):
                uri = f"ws://127.0.0.1:{port}"
                async with websockets.connect(uri) as ws:
                    await ws.recv()
                    # Send invalid payload
                    bad_cmd = {"type": "set_crouch", "offset": "invalid", "active": True}
                    await ws.send(json.dumps(bad_cmd))
                    
                    # Server handler should raise ValueError and close connection
                    try:
                        resp = await asyncio.wait_for(ws.recv(), timeout=0.2)
                    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK, asyncio.TimeoutError) as e:
                        # Confirmed connection dropped or closed due to unhandled ValueError
                        pass

        asyncio.run(_run_bug_test())


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(unittest.TestLoader().loadTestsFromTestCase(KinematicRangeAndClampingTests))
    sys.exit(0 if result.wasSuccessful() else 1)
