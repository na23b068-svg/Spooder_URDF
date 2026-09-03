#!/usr/bin/env python3
"""
Adversarial White-Box Stress Test Harness for Spooder Web Dashboard (server.py)
================================================================================
Target: server.py WebSocket handler and backend state engine.

This harness empirically probes server.py for vulnerabilities, edge cases, and logic bugs:
  1. Payload Parsing Robustness: non-numeric offset strings ("abc", "12.5", ""), invalid types, malformed JSON.
  2. Boundary & OOB Bounds: OOB crouch offsets (-100, +100), invalid leg/channel indices (10, -10, 99).
  3. Unknown WS Command Types: resilience against unhandled type fields.
  4. Concurrency & Rapid Toggling: rapid crouch ON/OFF during active gait, task collisions.
  5. Gait Baseline & State Calculations: positive crouch slider femur baseline in gait loop,
     post-gait baseline reset for positive crouch slider.
"""

import asyncio
import json
import unittest
import sys
import os

# Ensure backend can be imported
sys.path.insert(0, '/home/smeer/Downloads/Spooder/web_dashboard')
import server
from server import SpooderServer, LEG_COXA_CHANNELS, LEG_FEMUR_CHANNELS


class MockWebSocket:
    def __init__(self):
        self.sent_messages = []
        self.closed = False

    async def send(self, message):
        if self.closed:
            raise RuntimeError("WebSocket closed")
        self.sent_messages.append(json.loads(message))

    def close(self):
        self.closed = True


class SingleMessageWS:
    def __init__(self, msg, mock_ws):
        self.msg = msg
        self.mock_ws = mock_ws
        self.closed = False

    def __aiter__(self):
        self._yielded = False
        return self

    async def __anext__(self):
        if not self._yielded:
            self._yielded = True
            return self.msg
        raise StopAsyncIteration

    async def send(self, data):
        await self.mock_ws.send(data)


class BackendAdversarialHarness(unittest.TestCase):

    def setUp(self):
        self.server = SpooderServer()
        self.ws = MockWebSocket()

    async def _send_payload(self, payload_dict_or_str):
        if isinstance(payload_dict_or_str, dict):
            raw_msg = json.dumps(payload_dict_or_str)
        else:
            raw_msg = payload_dict_or_str

        single_ws = SingleMessageWS(raw_msg, self.ws)
        await self.server.handler(single_ws)

    # --------------------------------------------------------------------------
    # 1. PAYLOAD PARSER ROBUSTNESS
    # --------------------------------------------------------------------------
    def test_01_non_numeric_crouch_offset_strings(self):
        """EXPOSE BUG 1: Unhandled ValueError/TypeError when offset is non-numeric string ('abc', '12.5', '')."""
        invalid_offsets = ["abc", "12.5", "", [1, 2], {"val": 10}]
        failures = []
        
        for inv in invalid_offsets:
            payload = {"type": "set_crouch", "offset": inv, "active": True}
            try:
                asyncio.run(self._send_payload(payload))
            except Exception as e:
                failures.append((inv, type(e).__name__, str(e)))

        if failures:
            details = "\n".join([f"  - offset={inv!r} raised {err_t}: {err_m}" for inv, err_t, err_m in failures])
            self.fail(f"server.py set_crouch crashed on non-numeric offset inputs:\n{details}")

    def test_02_malformed_json_payload(self):
        """EXPOSE BUG 2: Unhandled JSONDecodeError and AttributeError on malformed JSON payload."""
        malformed = "{\"type\": \"set_crouch\", \"offset\":"
        try:
            asyncio.run(self._send_payload(malformed))
        except Exception as e:
            self.fail(f"server.py handler crashed on malformed JSON payload with {type(e).__name__}: {e}")

    # --------------------------------------------------------------------------
    # 2. BOUNDARY & OUT-OF-BOUNDS INDEXES
    # --------------------------------------------------------------------------
    def test_03_out_of_bounds_crouch_offset_clamping(self):
        """Verify OOB offset values (-100, +100) are clamped to [-45, +45]."""
        asyncio.run(self._send_payload({"type": "set_crouch", "offset": -100, "active": True}))
        self.assertEqual(self.server.crouch_offset, -45, "Lower OOB offset -100 was not clamped to -45")

        asyncio.run(self._send_payload({"type": "set_crouch", "offset": 100, "active": True}))
        self.assertEqual(self.server.crouch_offset, 45, "Upper OOB offset 100 was not clamped to +45")

    def test_04_invalid_leg_index_handling(self):
        """EXPOSE BUG 3: Unhandled IndexError on invalid leg index (10, -10, 99)."""
        invalid_legs = [10, -10, 99]
        failures = []
        for leg in invalid_legs:
            try:
                asyncio.run(self._send_payload({"type": "center_leg", "leg": leg}))
            except Exception as e:
                failures.append((leg, type(e).__name__, str(e)))

        if failures:
            details = "\n".join([f"  - leg={leg} raised {err_t}: {err_m}" for leg, err_t, err_m in failures])
            self.fail(f"server.py handler crashed on invalid leg index inputs:\n{details}")

    def test_05_invalid_channel_index_handling(self):
        """EXPOSE BUG: Unhandled KeyError/IndexError on invalid channel index (99)."""
        try:
            asyncio.run(self._send_payload({"type": "set_servo", "channel": 99, "offset": 0}))
        except Exception as e:
            self.fail(f"server.py handler crashed on invalid channel index 99 with {type(e).__name__}: {e}")

    # --------------------------------------------------------------------------
    # 3. UNKNOWN COMMAND TYPES
    # --------------------------------------------------------------------------
    def test_06_unknown_command_type_resilience(self):
        """Verify server handles unknown command types or missing type field gracefully without crash."""
        unknown_payloads = [
            {"type": "unknown_command_foo"},
            {"type": None},
            {"type": 12345},
            {}
        ]
        for p in unknown_payloads:
            try:
                asyncio.run(self._send_payload(p))
            except Exception as e:
                self.fail(f"server.py handler crashed on unknown command payload {p} with {type(e).__name__}: {e}")

    # --------------------------------------------------------------------------
    # 4. CONCURRENCY & RAPID TOGGLING
    # --------------------------------------------------------------------------
    def test_07_rapid_posture_toggling_during_active_gait(self):
        """EXPOSE BUG 6: Task collision and race condition during rapid posture toggling during active gait."""
        async def _run_rapid_toggle():
            # Start gait
            await self._send_payload({"type": "set_gait", "active": True, "speed": 1.0})
            self.assertTrue(self.server.gait_active)

            # Rapid posture toggling
            for i in range(10):
                active = (i % 2 == 0)
                offset = -45 if active else 0
                await self._send_payload({"type": "set_crouch", "active": active, "offset": offset})
                await asyncio.sleep(0.002)

            await asyncio.sleep(0.05)

        try:
            asyncio.run(_run_rapid_toggle())
        except Exception as e:
            self.fail(f"Rapid posture toggling during active gait caused exception: {e}")

    # --------------------------------------------------------------------------
    # 5. GAIT BASELINE & STATE CALCULATIONS ACROSS BOUNDARIES
    # --------------------------------------------------------------------------
    def test_08_positive_crouch_slider_gait_femur_baseline(self):
        """
        EXPOSE BUG 4:
        When crouch_offset is positive (e.g. +30), posture set_crouch moves femurs to -30.
        However, run_gait calculates:
            femur_baseline = self.crouch_offset ...
        Which evaluates to +30 instead of -30!
        """
        async def _check_baseline():
            # Set crouch to +30
            await self._send_payload({"type": "set_crouch", "active": True, "offset": 30})
            self.assertEqual(self.server.crouch_offset, 30)

            # Start gait loop
            self.server.gait_active = True
            gait_task = asyncio.create_task(self.server.run_gait())
            await asyncio.sleep(0.05)
            self.server.gait_active = False
            await gait_task

            # Femur baseline for positive crouch (+30) must be -30!
            # If femur_offset in self.server.servo_offsets is > 0, femur_baseline was +30 (BUG).
            femur_ch = LEG_FEMUR_CHANNELS[0]
            current_femur_off = self.server.servo_offsets[femur_ch]

            self.assertLessEqual(
                current_femur_off, 0,
                f"Femur baseline during gait with +30 crouch slider was positive ({current_femur_off}) instead of -30!"
            )

        asyncio.run(_check_baseline())

    def test_09_gait_deactivation_positive_crouch_baseline(self):
        """
        EXPOSE BUG 5:
        When set_gait active=False is called with crouch_active=True and crouch_offset=+30:
        set_gait calculates:
            crouch_baseline = self.crouch_offset if self.crouch_offset != 0 else -45
        Which evaluates to +30 for femurs, pushing them up to +30 instead of down (-30).
        """
        async def _check_deactivation():
            self.server.crouch_active = True
            self.server.crouch_offset = 30
            self.server.gait_active = True

            # Stop gait via set_gait active=False
            await self._send_payload({"type": "set_gait", "active": False})
            if self.server._animation_task:
                await self.server._animation_task

            femur_ch = LEG_FEMUR_CHANNELS[0]
            femur_off = self.server.servo_offsets[femur_ch]
            self.assertEqual(
                femur_off, -30,
                f"Gait deactivation with +30 crouch offset set femur offset to {femur_off} instead of -30"
            )

        asyncio.run(_check_deactivation())


def run_harness():
    print("======================================================================")
    print(" 🛡️ SPOODER BACKEND ADVERSARIAL STRESS TEST HARNESS RUNNER")
    print("======================================================================")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(BackendAdversarialHarness)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("\n----------------------------------------------------------------------")
    print(f"Total Harness Tests Run: {result.testsRun}")
    print(f"Errors: {len(result.errors)}, Failures: {len(result.failures)}")
    print("----------------------------------------------------------------------")
    return result


if __name__ == "__main__":
    run_harness()
