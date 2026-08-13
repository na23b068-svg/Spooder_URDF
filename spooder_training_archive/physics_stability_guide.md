# 🕷️ Spooder RL: Physics & Simulation Stability Guide

This document summarizes the diagnosed physics instabilities encountered during rough terrain training, the software safety nets implemented to prevent training crashes, and the proposed simulation tuning parameters for the next iteration.

---

## 1. Diagnosed Instabilities
When training Spooder on rough terrain (stairs, box grids, slopes), the thin, high-stiffness joint legs frequently collide with rigid obstacle boundaries (mesh corners and crevices).

1. **Discrete Collisions:** Under discrete physics steps (200Hz), a leg can deeply penetrate a ground collider. The physics engine resolves this penetration by calculating an instantaneous impulsive force.
2. **Under-damped Joints:** With high joint stiffness (`50.0`) and low damping (`1.0`), joint positions oscillate rapidly when in contact. This vibration accumulates kinetic energy.
3. **Solver Overshoot:** Because the velocity solver iterations were set to `0`, the solver could not resolve velocity-level constraints (like damping and joint limits) accurately, causing linear/angular velocities to explode to infinity/NaN.

---

## 2. Implemented Safeguards (Active)
To prevent these instabilities from terminating the training process, the following safety nets are currently active:

### A. Environment `nan_check` Termination
Located in `spooder_env_cfg.py`. If a robot's state explodes to `NaN` or `Inf`, the environment resets it on the next frame before compiling observations:
```python
def check_nan_termination(env: ManagerBasedRLEnv) -> torch.Tensor:
    robot = env.scene["robot"]
    nan_root = torch.isnan(robot.data.root_pos_w).any(dim=-1)
    nan_joints = torch.isnan(robot.data.joint_pos).any(dim=-1) | torch.isnan(robot.data.joint_vel).any(dim=-1)
    inf_root = torch.isinf(robot.data.root_pos_w).any(dim=-1)
    inf_joints = torch.isinf(robot.data.joint_pos).any(dim=-1) | torch.isinf(robot.data.joint_vel).any(dim=-1)
    return nan_root | nan_joints | inf_root | inf_joints
```

### B. Wrapper Sanitization
Located in `vecenv_wrapper.py`. All observations and rewards returned by the environment are run through `torch.nan_to_num` to replace any residual `NaN` or `Inf` values with `0.0`:
```python
obs_dict[key] = torch.nan_to_num(obs_dict[key], nan=0.0, posinf=0.0, neginf=0.0)
rew = torch.nan_to_num(rew, nan=0.0, posinf=0.0, neginf=0.0)
```

### C. PPO Gradient Sanity Interceptor
Located in `ppo.py`. If a mathematical anomaly occurs in a mini-batch update (e.g. division by zero in reward variance), PPO logs a warning and skips the optimizer step:
```python
if torch.isnan(loss) or torch.isinf(loss) or has_nan_grad:
    print("[WARNING]: NaN/Inf detected in PPO update! Skipping mini-batch.")
    self.optimizer.zero_grad()
    continue
```

---

## 3. Proposed Refinements (The Cures)
To physically stabilize the simulation in the next iteration and reduce the reset rate, implement the following changes in `spooder_env_cfg.py`:

### A. Increase Physics Solver Accuracy
Change the solver iteration counts from `(4, 0)` to `(8, 4)`. This forces the PhysX engine to calculate joint velocity dampings and friction dynamics much more precisely.
```diff
         articulation_props=sim_utils.ArticulationRootPropertiesCfg(
             enabled_self_collisions=False,
-            solver_position_iteration_count=4,
-            solver_velocity_iteration_count=0,
+            solver_position_iteration_count=8,
+            solver_velocity_iteration_count=4,
         ),
```

### B. Stabilize Joint Motor Drive (Increase Damping)
Increase joint damping coefficients (e.g., from `1.0` to `3.0` or `4.0`) to absorb high-frequency impact vibrations.
```diff
     actuators={
         "base_legs": ImplicitActuatorCfg(
             joint_names_expr=["Revolute.*"],
             effort_limit=100.0,
             velocity_limit=100.0,
             stiffness=50.0,
-            damping=1.0,
+            damping=3.0,
         ),
     },
```

### C. Decrease Simulation Timestep (Optional)
If instabilities persist, increase the simulation loop frequency by decreasing decimation (e.g. from `4` to `2`) or changing `sim.dt` to `0.002` (500Hz).
