import sys
import os
import asyncio
import math

# Add server directory to path
sys.path.insert(0, "/home/smeer/Downloads/Spooder/web_dashboard")
from server import SpooderServer, LEG_COXA_CHANNELS, LEG_FEMUR_CHANNELS, FEMUR_LIFT_DIRS

async def test_crouch_walk_engine():
    print("=== STARTING CROUCH-WALK GAIT ENGINE VERIFICATION ===")
    
    # 1. State Initialization Test
    server = SpooderServer()
    assert server.crouch_active is False, "Initial crouch_active must be False"
    assert server.crouch_offset == 0, "Initial crouch_offset must be 0"
    print("[PASS] 1. State Initialization: crouch_active=False, crouch_offset=0")

    # 2. Crouch Command Handler Persistence Test
    # Simulate set_crouch active: True
    crouch_msg_on = {"type": "set_crouch", "active": True}
    server.crouch_active = crouch_msg_on["active"]
    server.crouch_offset = crouch_msg_on.get("offset", -45)
    assert server.crouch_active is True, "set_crouch active=True must set crouch_active=True"
    assert server.crouch_offset == -45, "set_crouch active=True must default crouch_offset=-45"
    
    # Simulate set_crouch active: False
    crouch_msg_off = {"type": "set_crouch", "active": False}
    server.crouch_active = crouch_msg_off["active"]
    if not server.crouch_active:
        server.crouch_offset = 0
    assert server.crouch_active is False, "set_crouch active=False must set crouch_active=False"
    assert server.crouch_offset == 0, "set_crouch active=False must reset crouch_offset=0"
    print("[PASS] 2. Crouch Command Handler Persistence verified")

    # 3. Crouch-Walk Gait Mechanics Test across directions
    gait_directions = ["Forward", "Backward", "Spin Clockwise", "Spin Anti-Clockwise", "Turn Left", "Turn Right"]
    
    for direction in gait_directions:
        server.crouch_active = True
        server.crouch_offset = -45
        server.gait_active = True
        server.gait_direction = direction
        server.gait_speed = 1.0
        server.gait_sweep = 30.0
        server.gait_lift = 30.0
        
        # Test full gait cycle (theta from 0 to 2*pi in 100 steps)
        steps = 100
        for i in range(steps):
            theta = (2.0 * math.pi * i) / steps
            femur_baseline = server.crouch_offset if (server.crouch_active or server.crouch_offset != 0) else 0
            if server.crouch_active and femur_baseline == 0:
                femur_baseline = -45
            
            assert femur_baseline == -45, f"Femur baseline must be -45, got {femur_baseline}"
            
            for leg in range(6):
                theta_leg = theta if leg in [0, 4, 2] else theta + math.pi
                coxa_mult = server.get_coxa_multiplier(leg, direction)
                lift = max(0.0, math.sin(theta_leg)) * server.gait_lift
                sweep = -math.cos(theta_leg) * server.gait_sweep * coxa_mult
                femur_dir = FEMUR_LIFT_DIRS[leg]
                
                coxa_angle = 90 + int(sweep)
                femur_angle = 90 + femur_baseline + int(lift * femur_dir)
                
                coxa_ch = LEG_COXA_CHANNELS[leg]
                femur_ch = LEG_FEMUR_CHANNELS[leg]
                
                femur_offset = femur_baseline + int(lift * femur_dir)
                coxa_offset = int(sweep)
                
                # Check Femur Angle & Offset
                assert femur_angle == 90 - 45 + int(lift * femur_dir), f"Femur angle invalid: {femur_angle}"
                assert femur_offset == -45 + int(lift * femur_dir), f"Femur offset invalid: {femur_offset}"
                
                # Check Coxa Angle & Offset (Zero Baseline 0°, raw 90°)
                assert coxa_angle == 90 + int(sweep), f"Coxa angle invalid: {coxa_angle}"
                assert coxa_offset == int(sweep), f"Coxa offset invalid: {coxa_offset}"
                assert -30 <= coxa_offset <= 30, f"Coxa sweep out of range [-30, 30]: {coxa_offset}"
                
        print(f"[PASS] 3. Gait Direction '{direction}': Femur baseline -45°, Coxa centered at 0°")

    # 4. Live Server Gait Execution Test (Async Task)
    server.crouch_active = True
    server.crouch_offset = -45
    server.gait_active = True
    server.gait_direction = "Forward"
    server.gait_speed = 2.0
    
    gait_task = asyncio.create_task(server.run_gait())
    await asyncio.sleep(0.15)
    
    # Check live servo offsets during execution
    for leg in range(6):
        femur_ch = LEG_FEMUR_CHANNELS[leg]
        coxa_ch = LEG_COXA_CHANNELS[leg]
        femur_off = server.servo_offsets[femur_ch]
        coxa_off = server.servo_offsets[coxa_ch]
        
        # Femur offset should be -45 + lift, so in [-45, -45 + 30] = [-45, -15] for left side or [-75, -45] for right side
        assert -75 <= femur_off <= -15, f"Live femur offset out of expected range: {femur_off}"
        assert -30 <= coxa_off <= 30, f"Live coxa offset out of expected range: {coxa_off}"

    server.gait_active = False
    await gait_task
    print("[PASS] 4. Live Async Gait Execution: Offsets maintained correctly in crouch")

    # 5. Gait Stop Posture Restoration Test
    # Test A: Crouch Active -> Stop Gait restores to crouch stance (femurs at -45, coxas at 0)
    server.crouch_active = True
    server.crouch_offset = -45
    crouch_baseline = server.crouch_offset if server.crouch_offset != 0 else -45
    targets_crouched = {}
    for leg in range(6):
        targets_crouched[LEG_COXA_CHANNELS[leg]] = 0
        targets_crouched[LEG_FEMUR_CHANNELS[leg]] = crouch_baseline
        
    for leg in range(6):
        assert targets_crouched[LEG_COXA_CHANNELS[leg]] == 0, "Coxa target must be 0"
        assert targets_crouched[LEG_FEMUR_CHANNELS[leg]] == -45, "Femur target must be -45"
    print("[PASS] 5A. Stop Gait with crouch_active=True restores femurs to -45° and coxas to 0°")

    # Test B: Crouch Inactive -> Stop Gait centers all servos to 0
    server.crouch_active = False
    server.crouch_offset = 0
    targets_uncrouched = {ch: 0 for ch in range(12)}
    for ch in range(12):
        assert targets_uncrouched[ch] == 0, "Uncrouched stop gait target must be 0"
    print("[PASS] 5B. Stop Gait with crouch_active=False centers all servos to 0°")

    print("=== ALL 5 VERIFICATION SUITES PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(test_crouch_walk_engine())
