import os
import asyncio
import websockets
import serial
import serial.tools.list_ports
import math
import json
import time

# Hexapod Channel Layout mapping
# Leg indices: 0: LF, 1: LM, 2: LB, 3: RF, 4: RM, 5: RB
LEG_COXA_CHANNELS = [0, 2, 11, 6, 8, 10]
LEG_FEMUR_CHANNELS = [1, 3, 5, 7, 9, 4]
FEMUR_LIFT_DIRS = [1, 1, 1, -1, -1, -1]

try:
    import smbus2 as smbus
except ImportError:
    try:
        import smbus
    except ImportError:
        smbus = None

class RPiPCA9685:
    def __init__(self, bus_num=1, address=0x40):
        self.bus = smbus.SMBus(bus_num)
        self.address = address
        # Reset MODE1
        self.bus.write_byte_data(self.address, 0x00, 0x00)
        time.sleep(0.01)
        # Set 50Hz Prescale (121 = 0x79)
        self.bus.write_byte_data(self.address, 0x00, 0x10) # Enter sleep to set prescale
        self.bus.write_byte_data(self.address, 0xFE, 121)   # PRESCALE 50Hz
        self.bus.write_byte_data(self.address, 0x00, 0x20) # Auto-increment mode
        time.sleep(0.01)

    def set_angle(self, channel, angle):
        angle = max(0, min(180, angle))
        pulse_us = 500 + (angle / 180.0) * 2000
        off_tick = int(pulse_us * 4096 / 20000)
        
        reg = 0x06 + (4 * channel)
        try:
            self.bus.write_byte_data(self.address, reg, 0)
            self.bus.write_byte_data(self.address, reg + 1, 0)
            self.bus.write_byte_data(self.address, reg + 2, off_tick & 0xFF)
            self.bus.write_byte_data(self.address, reg + 3, (off_tick >> 8) & 0xFF)
        except Exception as e:
            # Catch transient I2C bus glitches (e.g. Remote I/O error) to prevent task crash
            print(f"[I2C Glitch] Channel {channel}: {e}")

class MotionProfileGenerator:
    """
    Generates time-series position interpolation according to the selected profile:
    - Trapezoidal (Linear Acceleration Ramp + Coast + Deceleration)
    - S-Curve (Smooth Cubic Step with zero jerk at start/stop: 3t^2 - 2t^3)
    - Sinusoidal (Harmonic Wave: 0.5 * (1 - cos(pi * t)))
    - Instant (Step change)
    """
    def __init__(self, start_pos, target_pos, profile_type="Trapezoidal", speed_scale=1.0):
        self.start_pos = float(start_pos)
        self.target_pos = float(target_pos)
        self.delta = self.target_pos - self.start_pos
        self.dist = abs(self.delta)
        self.direction = 1.0 if self.delta >= 0 else -1.0
        self.profile_type = profile_type
        
        if self.dist < 1e-3 or profile_type == "Instant":
            self.total_time = 0.0
            return
            
        speed_scale = max(0.1, min(5.0, float(speed_scale)))
        
        if self.profile_type == "Trapezoidal":
            max_v = 240.0 * speed_scale
            max_a = 480.0 * speed_scale
            t_a = max_v / max_a
            s_a = max_a * (t_a ** 2)
            
            if self.dist >= s_a:
                self.t_acc = t_a
                self.t_flat = (self.dist - s_a) / max_v
                self.t_dec = t_a
                self.v_peak = max_v
            else:
                self.v_peak = math.sqrt(self.dist * max_a)
                self.t_acc = self.v_peak / max_a
                self.t_flat = 0.0
                self.t_dec = self.t_acc
                
            self.max_a = max_a
            self.total_time = self.t_acc + self.t_flat + self.t_dec
        else: # S-Curve or Sinusoidal
            base_v = 150.0 * speed_scale
            self.total_time = max(0.1, self.dist / base_v)

    def get_position(self, t):
        if self.dist < 1e-3 or self.profile_type == "Instant":
            return self.target_pos
        if t <= 0.0:
            return self.start_pos
        if t >= self.total_time:
            return self.target_pos
            
        if self.profile_type == "Trapezoidal":
            if t <= self.t_acc:
                s = 0.5 * self.max_a * (t ** 2)
            elif t <= (self.t_acc + self.t_flat):
                s_acc = 0.5 * self.max_a * (self.t_acc ** 2)
                s = s_acc + self.v_peak * (t - self.t_acc)
            else:
                t_rem = self.total_time - t
                s = self.dist - 0.5 * self.max_a * (t_rem ** 2)
            return self.start_pos + self.direction * s
            
        tau = t / self.total_time
        if self.profile_type == "S-Curve":
            # Cubic smoothstep: 3*tau^2 - 2*tau^3
            s_norm = 3.0 * (tau ** 2) - 2.0 * (tau ** 3)
        elif self.profile_type == "Sinusoidal":
            # 0.5 * (1 - cos(pi * tau))
            s_norm = 0.5 * (1.0 - math.cos(math.pi * tau))
        else:
            s_norm = 1.0
            
        return self.start_pos + self.delta * s_norm

class SpooderServer:
    def __init__(self):
        self.ser = None
        self.pca = None
        self.init_hardware()
        
        self.servo_offsets = {i: 0 for i in range(12)}
        self.servo_trim_offsets = {i: 0 for i in range(12)}
        self.load_calibration()
        
        # State
        self.active_motion_profile = "Trapezoidal"
        self.pose_speed = 1.0
        self.gait_active = False
        self.gait_speed = 1.0
        self.gait_sweep = 30.0
        self.gait_lift = 30.0
        self.gait_direction = "Forward"
        self.crouch_active = False
        self.crouch_offset = 0
        
        self.sweep_active = False
        self.sweep_speed = 1.0
        self.sweep_mode = "one-by-one"
        self.leg_sweeps = [False] * 6
        self.leg_speeds = [1.0] * 6
        self.pose_active = False
        
        self.connected_clients = set()
        self._broadcast_task = None
        self._animation_task = None

    def load_calibration(self):
        try:
            if os.path.exists("trim_calibration.json"):
                with open("trim_calibration.json", "r") as f:
                    data = json.load(f)
                    self.servo_trim_offsets = {int(k): int(v) for k, v in data.items()}
                print(f"[Calibration] Loaded trim offsets: {self.servo_trim_offsets}")
        except Exception as e:
            print(f"[Calibration] Error loading calibration: {e}")

    def save_calibration(self):
        try:
            with open("trim_calibration.json", "w") as f:
                json.dump(self.servo_trim_offsets, f, indent=2)
            print(f"[Calibration] Saved trim offsets to trim_calibration.json: {self.servo_trim_offsets}")
        except Exception as e:
            print(f"[Calibration] Error saving calibration: {e}")
        
    def init_hardware(self):
        # 1. Try Direct RPi I2C
        if smbus is not None:
            try:
                self.pca = RPiPCA9685(bus_num=1, address=0x40)
                print("[RPi Direct I2C] Connected directly to PCA9685 at 0x40 on /dev/i2c-1!")
                return
            except Exception as e:
                print(f"[RPi Direct I2C] Could not open /dev/i2c-1: {e}")

        # 2. Fallback to USB Serial (Arduino)
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if "ttyUSB" in port.device or "ttyACM" in port.device or "CH340" in port.description:
                try:
                    self.ser = serial.Serial(port.device, 115200, timeout=1)
                    print(f"Connected to Arduino on {port.device}")
                    time.sleep(2)
                    return
                except Exception as e:
                    print(f"Failed to connect to {port.device}: {e}")
                    
        print("Running in simulation mode (no hardware detected).")

    def send_command(self, channel, angle):
        trimmed_angle = angle + self.servo_trim_offsets.get(channel, 0)
        trimmed_angle = max(0, min(180, trimmed_angle))
        
        if self.pca:
            try:
                self.pca.set_angle(channel, trimmed_angle)
            except Exception as e:
                print(f"I2C write error: {e}")
        elif self.ser and self.ser.is_open:
            command = f"{channel}:{trimmed_angle}\n"
            try:
                self.ser.write(command.encode('utf-8'))
            except Exception as e:
                print(f"Serial write error: {e}")

    async def broadcast_state(self):
        if not self.connected_clients:
            return
        if self._broadcast_task and not self._broadcast_task.done():
            return
        
        async def _send():
            state = {
                "type": "state",
                "offsets": self.servo_offsets,
                "crouch_active": self.crouch_active,
                "crouch_offset": self.crouch_offset,
            }
            message = json.dumps(state)
            await asyncio.gather(*[client.send(message) for client in self.connected_clients], return_exceptions=True)
            
        self._broadcast_task = asyncio.create_task(_send())

    async def animate_motion_targets(self, target_offsets_dict, dt=0.015):
        """
        Smoothly moves one or multiple servos to target offsets using the active motion profile (Trapezoidal, S-Curve, Sinusoidal, or Instant).
        All servos in target_offsets_dict are time-synchronized.
        """
        try:
            profile_type = self.active_motion_profile
            speed_scale = self.pose_speed
            
            if profile_type == "Instant":
                for ch, target_off in target_offsets_dict.items():
                    self.servo_offsets[ch] = target_off
                    self.send_command(ch, 90 + target_off)
                await self.broadcast_state()
                return

            profiles = {}
            max_duration = 0.0
            
            for ch, target_off in target_offsets_dict.items():
                start_off = self.servo_offsets[ch]
                prof = MotionProfileGenerator(start_off, target_off, profile_type=profile_type, speed_scale=speed_scale)
                profiles[ch] = prof
                if prof.total_time > max_duration:
                    max_duration = prof.total_time
                    
            if max_duration < 1e-3:
                for ch, target_off in target_offsets_dict.items():
                    self.servo_offsets[ch] = target_off
                    self.send_command(ch, 90 + target_off)
                await self.broadcast_state()
                return

            t = 0.0
            start_time = time.time()
            
            while t < max_duration:
                t = time.time() - start_time
                if t > max_duration:
                    t = max_duration
                    
                for ch, prof in profiles.items():
                    scale = prof.total_time / max_duration if max_duration > 0 else 1.0
                    t_scaled = t * scale
                    current_off = int(prof.get_position(t_scaled))
                    self.servo_offsets[ch] = current_off
                    self.send_command(ch, 90 + current_off)
                    
                await self.broadcast_state()
                await asyncio.sleep(dt)

            # Final exact snap to target offsets
            for ch, target_off in target_offsets_dict.items():
                self.servo_offsets[ch] = target_off
                self.send_command(ch, 90 + target_off)
            await self.broadcast_state()
        except asyncio.CancelledError:
            pass

    def stop_all_motions(self):
        self.gait_active = False
        self.sweep_active = False
        self.pose_active = False
        for i in range(6):
            self.leg_sweeps[i] = False
        if hasattr(self, '_animation_task') and self._animation_task and not self._animation_task.done():
            self._animation_task.cancel()
            self._animation_task = None

    def center_all(self):
        targets = {ch: 0 for ch in range(12)}
        self._animation_task = asyncio.create_task(self.animate_motion_targets(targets))
    
    def get_coxa_multiplier(self, leg_index, direction):
        is_right_side = leg_index in [3, 4, 5]
        
        if direction == "Forward":
            return -1.0 if is_right_side else 1.0
        elif direction == "Backward":
            return 1.0 if is_right_side else -1.0
        elif direction in ["Turn Left", "Spin Anti-Clockwise", "Spin Anti-Clockwise (CCW)"]:
            return -1.0
        elif direction in ["Turn Right", "Spin Clockwise", "Spin Clockwise (CW)"]:
            return 1.0
        return 1.0

    async def run_gait(self):
        t = 0.0
        last_time = time.time()
        while self.gait_active:
            try:
                current_time = time.time()
                dt = current_time - last_time
                last_time = current_time
                
                omega = 2.0 * math.pi * self.gait_speed
                t += dt
                theta = (omega * t) % (2.0 * math.pi)
                
                if self.crouch_offset != 0:
                    femur_baseline = -abs(self.crouch_offset)
                elif self.crouch_active:
                    femur_baseline = -45
                else:
                    femur_baseline = 0
                
                for leg in range(6):
                    if leg in [0, 4, 2]:
                        theta_leg = theta
                    else:
                        theta_leg = theta + math.pi
                    
                    coxa_multiplier = self.get_coxa_multiplier(leg, self.gait_direction)
                    lift = max(0.0, math.sin(theta_leg)) * self.gait_lift
                    sweep = -math.cos(theta_leg) * self.gait_sweep * coxa_multiplier
                    femur_dir = FEMUR_LIFT_DIRS[leg]
                    
                    coxa_angle = 90 + int(sweep)
                    femur_angle = 90 + femur_baseline + int(lift * femur_dir)
                    
                    coxa_ch = LEG_COXA_CHANNELS[leg]
                    femur_ch = LEG_FEMUR_CHANNELS[leg]
                    
                    self.servo_offsets[coxa_ch] = int(sweep)
                    self.servo_offsets[femur_ch] = femur_baseline + int(lift * femur_dir)

                    self.send_command(coxa_ch, coxa_angle)
                    self.send_command(femur_ch, femur_angle)
                    
                await self.broadcast_state()
            except Exception as e:
                print(f"[Gait Loop Exception] Recovered from error: {e}")
            await asyncio.sleep(0.03)

    async def run_sweep(self):
        t = 0.0
        dt = 0.03
        current_ch = 0
        while self.sweep_active:
            if self.sweep_mode == "all":
                offset = int(45.0 * math.sin(t))
                for ch in range(12):
                    self.servo_offsets[ch] = offset
                    self.send_command(ch, 90 + offset)
                    await asyncio.sleep(0.001)
                t += dt * self.sweep_speed
            else:  # "one-by-one"
                offset = int(45.0 * math.sin(t))
                self.servo_offsets[current_ch] = offset
                self.send_command(current_ch, 90 + offset)
                
                # Keep other channels centered
                for ch in range(12):
                    if ch != current_ch and self.servo_offsets[ch] != 0:
                        self.servo_offsets[ch] = 0
                        self.send_command(ch, 90)
                        await asyncio.sleep(0.001)
                
                t += dt * self.sweep_speed
                if t >= 2.0 * math.pi:
                    self.servo_offsets[current_ch] = 0
                    self.send_command(current_ch, 90)
                    t = 0.0
                    current_ch = (current_ch + 1) % 12
            
            await self.broadcast_state()
            await asyncio.sleep(dt)

    async def run_leg_sweep(self, leg):
        t = 0.0
        dt = 0.03
        coxa_ch = LEG_COXA_CHANNELS[leg]
        femur_ch = LEG_FEMUR_CHANNELS[leg]
        while self.leg_sweeps[leg]:
            offset = int(30.0 * math.sin(t))
            self.servo_offsets[coxa_ch] = offset
            self.servo_offsets[femur_ch] = offset
            
            self.send_command(coxa_ch, 90 + offset)
            await asyncio.sleep(0.001)
            self.send_command(femur_ch, 90 + offset)
            await asyncio.sleep(0.001)
            
            await self.broadcast_state()
            t += dt * 1.5 * self.leg_speeds[leg]
            await asyncio.sleep(dt)

    async def animate_pose(self, target_offset, delay_between_pairs=0.06):
        # Symmetrical pair groupings: Rear (2,5), Middle (1,4), Front (0,3)
        pairs = [
            [LEG_FEMUR_CHANNELS[2], LEG_FEMUR_CHANNELS[5]],  # Rear pair
            [LEG_FEMUR_CHANNELS[1], LEG_FEMUR_CHANNELS[4]],  # Middle pair
            [LEG_FEMUR_CHANNELS[0], LEG_FEMUR_CHANNELS[3]]   # Front pair
        ]
        
        for pair in pairs:
            if not self.pose_active: return
            for ch in pair:
                self.servo_offsets[ch] = target_offset
                self.send_command(ch, 90 + target_offset)
            await self.broadcast_state()
            await asyncio.sleep(delay_between_pairs)
            
        self.pose_active = False

    async def handler(self, websocket):
        self.connected_clients.add(websocket)
        try:
            # Send initial state
            await self.broadcast_state()
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    cmd = data.get("type")
                    
                    if cmd == "set_servo":
                        ch = int(data["channel"])
                        if not (0 <= ch < 12):
                            continue
                        offset = int(data["offset"])
                        self.servo_offsets[ch] = offset
                        self.send_command(ch, 90 + offset)
                        await self.broadcast_state()
                        
                    elif cmd == "set_gait":
                        self.stop_all_motions()
                        self.gait_active = data.get("active", self.gait_active)
                        self.gait_speed = float(data.get("speed", self.gait_speed))
                        self.gait_sweep = float(data.get("sweep", self.gait_sweep))
                        self.gait_lift = float(data.get("lift", self.gait_lift))
                        self.gait_direction = data.get("direction", self.gait_direction)
                        
                        if self.gait_active:
                            asyncio.create_task(self.run_gait())
                        else:
                            if self.crouch_active:
                                if self.crouch_offset <= 0:
                                    coxa_target = self.crouch_offset
                                    femur_target = self.crouch_offset if self.crouch_offset != 0 else -45
                                else:
                                    coxa_target = self.crouch_offset
                                    femur_target = -self.crouch_offset
                                targets = {}
                                for leg in range(6):
                                    targets[LEG_COXA_CHANNELS[leg]] = coxa_target
                                    targets[LEG_FEMUR_CHANNELS[leg]] = femur_target
                                self._animation_task = asyncio.create_task(self.animate_motion_targets(targets))
                            else:
                                self.center_all()
                            await self.broadcast_state()
                            
                    elif cmd == "set_sweep":
                        self.stop_all_motions()
                        self.sweep_active = data.get("active", self.sweep_active)
                        self.sweep_speed = float(data.get("speed", self.sweep_speed))
                        self.sweep_mode = data.get("mode", self.sweep_mode)
                        
                        if self.sweep_active:
                            asyncio.create_task(self.run_sweep())
                        else:
                            self.center_all()
                            await self.broadcast_state()
                            
                    elif cmd == "center_all":
                        self.stop_all_motions()
                        self.center_all()
                        await self.broadcast_state()
                        
                    elif cmd == "recalibrate":
                        self.stop_all_motions()
                        for ch in range(12):
                            self.servo_trim_offsets[ch] += self.servo_offsets[ch]
                            self.servo_offsets[ch] = 0
                        self.save_calibration()
                        await self.broadcast_state()
                        
                    elif cmd == "set_motion_profile":
                        self.active_motion_profile = data.get("profile", "Trapezoidal")
                        print(f"[Motion Profile] Switched active profile to: {self.active_motion_profile}")

                    elif cmd == "set_pose_speed":
                        self.pose_speed = float(data.get("speed", 1.0))
                        print(f"[Motion Speed] Pose speed multiplier set to: {self.pose_speed}x")

                    elif cmd == "set_pose":
                        self.stop_all_motions()
                        pose = data.get("pose")
                        target_femur_offset = -90 if pose == "sit" else 0
                        targets = {ch: target_femur_offset for ch in LEG_FEMUR_CHANNELS}
                        self._animation_task = asyncio.create_task(self.animate_motion_targets(targets))

                    elif cmd == "set_crouch":
                        self.stop_all_motions()
                        raw_active = data.get("active")
                        raw_offset = data.get("offset")

                        if raw_offset is not None:
                            try:
                                offset = int(round(float(raw_offset)))
                            except (ValueError, TypeError):
                                offset = 0
                            active = bool(raw_active) if raw_active is not None else (offset != 0)
                        else:
                            active = bool(raw_active) if raw_active is not None else False
                            offset = -45 if active else 0

                        offset = max(-45, min(45, offset))
                        self.crouch_active = active
                        self.crouch_offset = offset

                        coxa_target = offset
                        femur_target = -abs(offset)

                        targets = {}
                        for ch in LEG_COXA_CHANNELS:
                            targets[ch] = coxa_target
                        for ch in LEG_FEMUR_CHANNELS:
                            targets[ch] = femur_target

                        if hasattr(self, '_animation_task') and self._animation_task and not self._animation_task.done():
                            self._animation_task.cancel()
                        self._animation_task = asyncio.create_task(self.animate_motion_targets(targets))

                    elif cmd == "center_leg":
                        leg = int(data["leg"])
                        if not (0 <= leg < 6):
                            continue
                        coxa_ch = LEG_COXA_CHANNELS[leg]
                        femur_ch = LEG_FEMUR_CHANNELS[leg]
                        targets = {coxa_ch: 0, femur_ch: 0}
                        self._animation_task = asyncio.create_task(self.animate_motion_targets(targets))

                    elif cmd == "set_leg_sweep":
                        leg = int(data["leg"])
                        if not (0 <= leg < 6):
                            continue
                        active = data.get("active", False)
                        speed = float(data.get("speed", 1.0))
                        self.leg_speeds[leg] = speed
                        if active:
                            self.stop_all_motions()
                            self.leg_sweeps[leg] = True
                            asyncio.create_task(self.run_leg_sweep(leg))
                        else:
                            self.leg_sweeps[leg] = False
                            # Center just this leg
                            coxa_ch = LEG_COXA_CHANNELS[leg]
                            femur_ch = LEG_FEMUR_CHANNELS[leg]
                            self.servo_offsets[coxa_ch] = 0
                            self.servo_offsets[femur_ch] = 0
                            self.send_command(coxa_ch, 90)
                            await asyncio.sleep(0.001)
                            self.send_command(femur_ch, 90)
                            await self.broadcast_state()
                except Exception as e:
                    print(f"[WebSocket Error] Exception processing message: {e}")
                    
        except websockets.ConnectionClosed:
            pass
        finally:
            self.connected_clients.remove(websocket)

async def main():
    server = SpooderServer()
    async with websockets.serve(server.handler, "0.0.0.0", 8765):
        print("WebSocket server running on ws://0.0.0.0:8765")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
