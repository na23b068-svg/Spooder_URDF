#!/usr/bin/env python3
"""
Stress Test Harness for Posture Animation, Dynamic Motion Profiles, and WebSocket Sync
========================================================================================
Empirically stress-tests:
  1. Profile Math & Trajectory Integrity (Trapezoidal, S-Curve, Sinusoidal, Instant).
  2. Dynamic Profile Transition & Mid-Animation Re-target Behavior.
  3. Rapid Slider Movement Command Flooding & Concurrent Task Stacking Analysis.
  4. Multi-client WebSocket State Broadcast Consistency & Convergence.
"""

import unittest
import asyncio
import json
import math
import time
import websockets
import server
from server import SpooderServer, MotionProfileGenerator, LEG_COXA_CHANNELS, LEG_FEMUR_CHANNELS

class MotionProfileMathStressTests(unittest.TestCase):
    def test_trapezoidal_profile_continuity_and_bounds(self):
        """Test Trapezoidal profile position continuity, acceleration phase, coast phase, and decel phase."""
        distances = [1.0, 5.0, 15.0, 30.0, 45.0, 90.0]
        speeds = [0.1, 0.5, 1.0, 2.0, 5.0]
        
        for dist in distances:
            for speed in speeds:
                for direction in [1.0, -1.0]:
                    start_pos = 0.0
                    target_pos = direction * dist
                    gen = MotionProfileGenerator(start_pos, target_pos, profile_type="Trapezoidal", speed_scale=speed)
                    
                    self.assertEqual(gen.get_position(0.0), start_pos)
                    self.assertAlmostEqual(gen.get_position(gen.total_time), target_pos, places=5)
                    self.assertEqual(gen.get_position(gen.total_time + 1.0), target_pos)
                    
                    # Test monotonic movement
                    dt = gen.total_time / 100.0 if gen.total_time > 0 else 0.01
                    prev_pos = start_pos
                    for step in range(101):
                        t = step * dt
                        pos = gen.get_position(t)
                        if direction > 0:
                            self.assertGreaterEqual(pos, prev_pos - 1e-5, f"Non-monotonic dec at t={t}, dist={dist}, speed={speed}")
                        else:
                            self.assertLessEqual(pos, prev_pos + 1e-5, f"Non-monotonic inc at t={t}, dist={dist}, speed={speed}")
                        prev_pos = pos

    def test_scurve_profile_smoothness(self):
        """Test S-Curve profile smoothstep properties and low initial velocity ratio."""
        speeds = [0.5, 1.0, 3.0]
        for speed in speeds:
            gen = MotionProfileGenerator(0.0, -45.0, profile_type="S-Curve", speed_scale=speed)
            self.assertEqual(gen.get_position(0.0), 0.0)
            self.assertAlmostEqual(gen.get_position(gen.total_time), -45.0, places=5)
            
            # Peak velocity occurs at midpoint tau = 0.5
            # s(t) = delta * (3*tau^2 - 2*tau^3), ds/dt = (delta/total_time) * (6*tau - 6*tau^2)
            v_peak = abs((-45.0 / gen.total_time) * 1.5)
            
            # Calculate initial velocity over first 0.5% of total time
            eps = gen.total_time * 0.005
            v_start = abs((gen.get_position(eps) - gen.get_position(0.0)) / eps)
            
            # Initial velocity ratio (v_start / v_peak) must be < 5% (near zero start)
            ratio = v_start / v_peak
            self.assertLess(ratio, 0.05, f"S-Curve initial velocity ratio {ratio:.4f} too high for speed {speed}")

    def test_sinusoidal_profile_harmonic_wave(self):
        """Test Sinusoidal profile harmonic wave interpolation."""
        gen = MotionProfileGenerator(0.0, 45.0, profile_type="Sinusoidal", speed_scale=1.0)
        self.assertEqual(gen.get_position(0.0), 0.0)
        self.assertAlmostEqual(gen.get_position(gen.total_time), 45.0, places=5)
        # At midpoint t = total_time / 2, harmonic wave should be exactly 50% of distance (22.5)
        mid_pos = gen.get_position(gen.total_time / 2.0)
        self.assertAlmostEqual(mid_pos, 22.5, places=4)

    def test_instant_profile_zero_delay(self):
        """Test Instant profile returns target position immediately."""
        gen = MotionProfileGenerator(10.0, -30.0, profile_type="Instant", speed_scale=1.0)
        self.assertEqual(gen.total_time, 0.0)
        self.assertEqual(gen.get_position(0.0), -30.0)
        self.assertEqual(gen.get_position(0.1), -30.0)


class ProfileTransitionAndInterruptionStressTests(unittest.TestCase):
    def test_sequential_profile_transitions(self):
        """Test dynamic profile switching between animations (Trapezoidal -> S-Curve -> Sinusoidal -> Instant)."""
        async def _run():
            server_inst = SpooderServer()
            
            # 1. Trapezoidal animation to -45
            server_inst.active_motion_profile = "Trapezoidal"
            targets1 = {ch: -45 for ch in LEG_FEMUR_CHANNELS}
            await server_inst.animate_motion_targets(targets1, dt=0.005)
            for ch in LEG_FEMUR_CHANNELS:
                self.assertEqual(server_inst.servo_offsets[ch], -45)
            
            # 2. Switch profile to S-Curve and animate to +30
            server_inst.active_motion_profile = "S-Curve"
            targets2 = {ch: 30 for ch in LEG_FEMUR_CHANNELS}
            await server_inst.animate_motion_targets(targets2, dt=0.005)
            for ch in LEG_FEMUR_CHANNELS:
                self.assertEqual(server_inst.servo_offsets[ch], 30)
            
            # 3. Switch profile to Sinusoidal and animate to -15
            server_inst.active_motion_profile = "Sinusoidal"
            targets3 = {ch: -15 for ch in LEG_FEMUR_CHANNELS}
            await server_inst.animate_motion_targets(targets3, dt=0.005)
            for ch in LEG_FEMUR_CHANNELS:
                self.assertEqual(server_inst.servo_offsets[ch], -15)
                
            # 4. Switch profile to Instant and set to 0
            server_inst.active_motion_profile = "Instant"
            targets4 = {ch: 0 for ch in LEG_FEMUR_CHANNELS}
            await server_inst.animate_motion_targets(targets4, dt=0.005)
            for ch in LEG_FEMUR_CHANNELS:
                self.assertEqual(server_inst.servo_offsets[ch], 0)

        asyncio.run(_run())

    def test_task_stacking_finding_on_unawaited_animations(self):
        """Empirically test and document task contention when new animations are launched without task cancellation."""
        async def _run():
            server_inst = SpooderServer()
            server_inst.active_motion_profile = "Trapezoidal"
            server_inst.pose_speed = 1.0
            
            # Launch Task 1: animate to -45 (takes ~0.3s)
            t1 = asyncio.create_task(server_inst.animate_motion_targets({0: -45}, dt=0.01))
            await asyncio.sleep(0.05)
            
            # Launch Task 2: animate to 0 while Task 1 is still running
            t2 = asyncio.create_task(server_inst.animate_motion_targets({0: 0}, dt=0.01))
            
            # Wait for Task 2 to complete
            await t2
            # At this point, Task 1 may still be running in background and overwrite position!
            await asyncio.sleep(0.3)
            await t1
            
            # Document finding: Without task tracking/cancellation, Task 1 overrides Task 2's final position!
            stuck_pos = server_inst.servo_offsets[0]
            # Empirical assertion: Confirm that position was overwritten back to Task 1 target (-45)
            self.assertEqual(stuck_pos, -45, "Task stacking confirmed: earlier uncancelled task overwrote final target")

        asyncio.run(_run())


class WebSocketRapidSliderStressTests(unittest.TestCase):
    def test_rapid_slider_flooding_with_settle_delay(self):
        """Simulate rapid slider movement commands over WebSocket server connection with animation task completion."""
        async def _run():
            server_inst = SpooderServer()
            port = 8766
            async with websockets.serve(server_inst.handler, "127.0.0.1", port):
                uri = f"ws://127.0.0.1:{port}"
                async with websockets.connect(uri) as ws:
                    init_msg = await ws.recv()
                    
                    # Set profile to Instant for high-frequency slider testing
                    profile_cmd = {"type": "set_motion_profile", "profile": "Instant"}
                    await ws.send(json.dumps(profile_cmd))
                    await asyncio.sleep(0.01)
                    
                    # Flood 50 set_crouch commands with rapid value sweeps (-25 to +25)
                    for val in range(-25, 25):
                        cmd = {"type": "set_crouch", "offset": val, "active": True}
                        await ws.send(json.dumps(cmd))
                        await asyncio.sleep(0.002)
                    
                    # Send final target set_crouch command to 0
                    final_cmd = {"type": "set_crouch", "offset": 0, "active": False}
                    await ws.send(json.dumps(final_cmd))
                    await asyncio.sleep(0.05)
                    
                    # Verify final state convergence
                    for ch in range(12):
                        self.assertEqual(server_inst.servo_offsets[ch], 0, f"Channel {ch} failed to converge to 0")

        asyncio.run(_run())

    def test_multiclient_ws_broadcast_consistency(self):
        """Stress test multiple WebSocket clients receiving broadcast updates under high frequency state changes."""
        async def _run():
            server_inst = SpooderServer()
            port = 8767
            async with websockets.serve(server_inst.handler, "127.0.0.1", port):
                uri = f"ws://127.0.0.1:{port}"
                
                # Connect 3 clients
                ws1 = await websockets.connect(uri)
                ws2 = await websockets.connect(uri)
                ws3 = await websockets.connect(uri)
                
                # Read initial state
                await ws1.recv()
                await ws2.recv()
                await ws3.recv()
                
                # Trigger posture change with Instant profile
                await ws1.send(json.dumps({"type": "set_motion_profile", "profile": "Instant"}))
                cmd = {"type": "set_crouch", "offset": -30, "active": True}
                await ws1.send(json.dumps(cmd))
                
                received_ws2 = []
                received_ws3 = []
                
                async def recv_loop(ws, target_list):
                    try:
                        while True:
                            msg = await asyncio.wait_for(ws.recv(), timeout=0.15)
                            target_list.append(json.loads(msg))
                    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                        pass

                await asyncio.gather(
                    recv_loop(ws2, received_ws2),
                    recv_loop(ws3, received_ws3),
                    return_exceptions=True
                )
                
                await ws1.close()
                await ws2.close()
                await ws3.close()
                
                self.assertGreater(len(received_ws2), 0)
                self.assertGreater(len(received_ws3), 0)
                
                last_msg_2 = received_ws2[-1]
                last_msg_3 = received_ws3[-1]
                
                self.assertEqual(last_msg_2["type"], "state")
                self.assertEqual(last_msg_3["type"], "state")
                self.assertEqual(last_msg_2["crouch_offset"], -30)
                self.assertEqual(last_msg_3["crouch_offset"], -30)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
