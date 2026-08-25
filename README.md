# Spooder Hexapod: URDF, IsaacLab RL & Web Telemetry Dashboard

This repository contains the complete software stack, ROS URDF descriptions, IsaacLab reinforcement learning workspace, and real-time Web Telemetry HUD / Control Dashboard for the **Spooder** 12-DOF hexapod robot.

---

## 📹 Hardware Demonstration

https://github.com/user-attachments/assets/spooder_demo

> **Physical Hardware Demo:** Watch Spooder execute symmetrical **Sit**, **Stand**, and **Crouch ON/OFF** pose transitions.

<div align="center">
  <video src="media/Spooder.mp4" width="100%" controls autoplay loop muted></video>
</div>

---

## Recent Developments & Features

### Real-Time Web Control Dashboard (`web_dashboard/`)
A modern control interface and live 3D telemetry dashboard built for PC.

* **Slider-Control for Joint-Angles**: 12 in Total
* **Live 3D STL URDF Viewer:** Real-time WebGL visualization (powered by Three.js) syncing 3D chassis and leg joint angles with physical robot state.
* **Manual Trim, Pitch and Roll Calibration (To be automated soon, using proximity sensors on the base):** *"Set Zero (Recalibrate)"* feature on the dashboard that bakes manual servo center adjustments into `trim_calibration.json` on disk, preserving custom 90° zero points across reboots.
* **Multi-Directional Gait:** 60FPS tripod gait controller supporting `Forward`, `Backward`, `Spin Clockwise (CW)`, `Spin Anti-Clockwise (CCW)`, `Turn Left`, and `Turn Right`.
* **System Presets & Poses:**
  * **SIT / STAND:** Symmetrical 3-pair stance control (-90° femur sit / 0° femur stand).
  * **CROUCH ON / OFF:** Instant -45° crouch entry and decoupled 2-stage mechanical release for crouch exit (Coxas return to 0° first under zero vertical load, 80ms pause, Femurs extend to 0° second).
* **Per-Leg Diagnostics & Precision Control:** Per-leg sweep testing, per-leg speed multipliers (0.2x–3.0x), per-leg centering, and mouse-wheel control for joint-angle sliders with adjustable scroll sensitivity (1° to 20° / scroll-angle).

---

## Running Web Dashboard on Raspberry Pi

To deploy only the lightweight control dashboard (~2.5 MB) on your Raspberry Pi over SSH:

```bash
# 1. Download and enter web_dashboard
mkdir -p ~/spooder_dashboard && cd ~/spooder_dashboard
curl -L https://github.com/na23b068-svg/Spooder_URDF/archive/refs/heads/main.tar.gz | tar -xz --strip-components=1 Spooder_URDF-main/web_dashboard
cd web_dashboard

# 2. Enable RPi Hardware I2C and install dependencies
sudo raspi-config nonint do_i2c 0
sudo apt update && sudo apt install -y python3-websockets python3-serial python3-smbus

# 3. Start the Dashboard (Frontend + Backend)
chmod +x start.sh && ./start.sh
```

Open **`http://<rpi-ip-address>:8080`** (or `http://spooder.local:8080`) in your browser!

---

## Hardware Architecture & Power Specifications
* **Raspberry Pi 4B:** Wireless communication with laptop via SSH and I2C communication with the PCA9685 board  for low-latency servo driving.
* **Servo Controller:** PCA9685 16-Channel 12-bit PWM Driver over I2C (`0x40`).
* **Power Supply & Regulation:** 12V 5A SMPS connected to an **XL4016E1 10A DC-DC Buck Converter** set to 5.2V.
* **Power Distribution & Protection:** 12 AWG wiring, DEGSON DG128 7.5mm 20A Screw Terminals, and a **3900µF / 4700µF Low-ESR Electrolytic Capacitor (Nippon Chemi-Con KYB 21mΩ)** directly across the 5.2V rail to absorb 7.2A 12-servo peak inrush current surges.
* **Microcontroller Upgrade Path:** Upgrading to a custom-PCB with ESP32 for wireless connectivity / high number of GPIO pins, separate power and ground rails, arranged in a similar 3-pin fashion as the PCA board to allow plug-and-play connectivity of upto 18 servos. 
* **Other Upgrade Paths:** 
  * Adding wireless / pogo-pin based charging 
  * Battery-sizing based on actual recorded current draws over a HIL simulated walking pattern that simulates the bot walking across a 10ft x       10ft room space for at least 1-2 hours. 
  * BMS for the battery-pack and adding a rectifier circuit / ferrite shielding for the battery to implement a qi wireless charging pad. 
  * Adding Mapping and Localisation (SLAM) to the bot so that it can dock itself for charging from time-to-time.

---

## IsaacLab Reinforcement Learning (Yet to reach a proper refined result) (`spooder_training/`)

Requires [IsaacLab](https://isaac-sim.github.io/IsaacLab/) installed.

### 1. View / Play Pre-Trained Policy (GUI Visualization)
```bash
cd spooder_training
/path/to/isaaclab/isaaclab.sh -p play_spooder.py --checkpoint logs/rsl_rl/spooder_flat/2026-07-05_01-54-46/model_999.pt
```

### 2. View Training Results (TensorBoard)
```bash
cd spooder_training
/path/to/isaaclab/isaaclab.sh -p -m tensorboard.main --logdir=logs/rsl_rl/spooder_flat
```
Open `http://localhost:6006` in browser.

### 3. Start PPO Training Session
```bash
cd spooder_training
DISPLAY="" /path/to/isaaclab/isaaclab.sh -p train.py --task Isaac-Velocity-Flat-Spooder-v0 --headless --num_envs 512
```

---

## ⚙️ ROS Workspace Setup (`Spooder_Files/`)

1. **Clone to ROS Workspace:**
   ```bash
   cd ~/catkin_ws/src/
   git clone https://github.com/na23b068-svg/Spooder_URDF.git
   ```

2. **Build and Source:**
   ```bash
   cd ~/catkin_ws
   catkin_make
   source devel/setup.bash
   ```

3. **Launch RViz / Gazebo:**
   ```bash
   roslaunch Spooder_Files display.launch   # RViz visualization
   roslaunch Spooder_Files gazebo.launch    # Gazebo simulation
   ```

---

## 📁 Repository Structure

```
├── web_dashboard/           # Web Control Dashboard & Telemetry HUD
│   ├── server.py            # RPi Direct I2C & WebSocket Server
│   ├── start.sh             # 1-click startup script (Frontend + Backend)
│   └── public/              # HTML5, CSS3, JS, Three.js 3D STL Models
├── spooder_training/        # IsaacLab PPO Reinforcement Learning Workspace
│   ├── spooder_env_cfg.py   # Gym environment rewards, terminations, actions
│   ├── train.py             # PPO training runner
│   ├── play_spooder.py      # Policy playback runner
│   └── logs/                # Checkpoints & TensorBoard curves
├── Spooder_Files/           # ROS URDF Package
│   ├── urdf/                # Robot URDF description
│   ├── meshes/              # STL meshes for visual & collision
│   └── launch/              # RViz & Gazebo launch files
└── README.md                # Project documentation
```
