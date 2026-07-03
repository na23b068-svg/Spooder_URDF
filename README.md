# Spooder URDF Description Package

This repository contains the ROS URDF description package for the **Spooder** robot, automatically exported from Autodesk Fusion 360 using the `fusion2urdf` tool.

## Package Structure

The package is organized as a standard ROS description package:
* **`spooder_URDF_try1_description/`**:
  * **`urdf/`**: Contains the URDF/Xacro robot description (`spooder_URDF_try1.xacro`), gazebo configuration, transmissions, and materials.
  * **`meshes/`**: Contains the binary STL files for the visual and collision geometries of the robot links.
  * **`launch/`**: Contains launch files for visualization in RViz (`display.launch`) and simulation in Gazebo (`gazebo.launch` & `controller.launch`).
  * **`CMakeLists.txt`** & **`package.xml`**: ROS package configuration.

## Setup and Usage

1. **Place in ROS Workspace**:
   Clone or copy this repository into the `src/` directory of your ROS catkin workspace (e.g., `~/catkin_ws/src/`).

2. **Build the Workspace**:
   ```bash
   cd ~/catkin_ws
   catkin_make
   source devel/setup.bash
   ```

3. **Launch in RViz**:
   To visualize the robot and inspect its joints using the joint state publisher GUI:
   ```bash
   roslaunch spooder_URDF_try1_description display.launch
   ```

4. **Launch in Gazebo**:
   To spawn and simulate the robot in Gazebo:
   ```bash
   roslaunch spooder_URDF_try1_description gazebo.launch
   ```
