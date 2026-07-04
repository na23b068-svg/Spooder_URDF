# Spooder URDF Description & Reinforcement Learning Package

This repository contains the ROS description files and IsaacLab reinforcement learning workspace for the **Spooder** hexapod robot.

## Repository Structure

* **`Spooder_Files/`**: Renamed ROS URDF package folder.
  * **`urdf/`**: Robot description file (`spooder_URDF_try1.urdf`), materials, transmissions, and Gazebo definitions.
  * **`meshes/`**: STL mesh files for visual and collision properties.
  * **`launch/`**: Launch configurations for RViz and Gazebo.
  * **`CMakeLists.txt`** & **`package.xml`**: ROS package configuration.
* **`spooder_training/`**: IsaacLab RL workspace.
  * **`spooder_env_cfg.py`**: Custom environment configurations including rewards (e.g. stance-contact support, soft joint limits), actions, events, and terminations.
  * **`train.py`**: PPO training runner.
  * **`play_spooder.py`**: Policy playback and visualization script.
  * **`spooder.usd`**: Converted NVIDIA OpenUSD model of the robot.
  * **`logs/`**: Training checkpoints (`.pt` weights) and TensorBoard curves.

---

## 🤖 IsaacLab Reinforcement Learning

To simulate, train, and run policies, you must have [IsaacLab](https://isaac-sim.github.io/IsaacLab/) installed on your machine.

### 1. View / Play Pre-Trained Walks (GUI Visualization)
To launch Isaac Sim with the GUI active and watch the pre-trained Spooder policy (`model_999.pt`) walk:
```bash
# Navigate to the training directory
cd spooder_training

# Run the playback script using the IsaacLab launcher script
/path/to/your/isaaclab/isaaclab.sh -p play_spooder.py --checkpoint logs/rsl_rl/spooder_flat/2026-07-05_01-54-46/model_999.pt
```

### 2. View Training Results & Curves (TensorBoard)
To view learning curves, rewards, and gait metrics:
```bash
# Navigate to training directory
cd spooder_training

# Run TensorBoard inside the IsaacLab environment
/path/to/your/isaaclab/isaaclab.sh -p -m tensorboard.main --logdir=logs/rsl_rl/spooder_flat
```
Open `http://localhost:6006` in your web browser.

### 3. Start a New Training Session
To launch PPO training from scratch (headless mode):
```bash
# Navigate to training directory
cd spooder_training

# Start training with 512 environment instances
DISPLAY="" /path/to/your/isaaclab/isaaclab.sh -p train.py --task Isaac-Velocity-Flat-Spooder-v0 --headless --num_envs 512
```

---

## ⚙️ ROS Setup and Usage (RViz/Gazebo)

1. **Place in ROS Workspace**:
   Clone or copy the `Spooder_Files` directory into the `src/` directory of your ROS workspace (e.g., `~/catkin_ws/src/`).

2. **Build the Workspace**:
   ```bash
   cd ~/catkin_ws
   catkin_make
   source devel/setup.bash
   ```

3. **Launch in RViz**:
   ```bash
   roslaunch Spooder_Files display.launch
   ```

4. **Launch in Gazebo**:
   ```bash
   roslaunch Spooder_Files gazebo.launch
   ```
