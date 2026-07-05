import os
import math
import torch
import isaaclab.sim as sim_utils
import isaaclab.envs.mdp as mdp
import isaaclab.terrains as terrain_gen
from isaaclab.terrains.terrain_generator_cfg import TerrainGeneratorCfg
from isaaclab.assets import ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.utils import configclass
from isaaclab.envs import ManagerBasedRLEnv
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import LocomotionVelocityRoughEnvCfg
from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlPpoActorCriticCfg, RslRlPpoAlgorithmCfg

current_dir = os.path.dirname(os.path.abspath(__file__))

# --- Custom Terrain Config for Small Robot (8cm height) ---
SPOODER_ROUGH_TERRAINS_CFG = TerrainGeneratorCfg(
    size=(8.0, 8.0),
    border_width=20.0,
    num_rows=10,
    num_cols=20,
    horizontal_scale=0.1,
    vertical_scale=0.005,
    slope_threshold=0.75,
    use_cache=False,
    sub_terrains={
        "pyramid_stairs": terrain_gen.MeshPyramidStairsTerrainCfg(
            proportion=0.2,
            step_height_range=(0.005, 0.02),   # 0.5cm to 2.0cm step height
            step_width=0.2,                    # 20cm step width
            platform_width=3.0,
            border_width=1.0,
            holes=False,
        ),
        "pyramid_stairs_inv": terrain_gen.MeshInvertedPyramidStairsTerrainCfg(
            proportion=0.2,
            step_height_range=(0.005, 0.02),
            step_width=0.2,
            platform_width=3.0,
            border_width=1.0,
            holes=False,
        ),
        "boxes": terrain_gen.MeshRandomGridTerrainCfg(
            proportion=0.2, 
            grid_width=0.3, 
            grid_height_range=(0.005, 0.015),   # 0.5cm to 1.5cm box height
            platform_width=2.0
        ),
        "random_rough": terrain_gen.HfRandomUniformTerrainCfg(
            proportion=0.2, 
            noise_range=(0.005, 0.025),        # 0.5cm to 2.5cm height bumps
            noise_step=0.005,                  # 0.5cm noise step
            border_width=0.25
        ),
        "hf_pyramid_slope": terrain_gen.HfPyramidSlopedTerrainCfg(
            proportion=0.1, 
            slope_range=(0.0, 0.15),           # Up to 15% slope
            platform_width=2.0, 
            border_width=0.25
        ),
        "hf_pyramid_slope_inv": terrain_gen.HfInvertedPyramidSlopedTerrainCfg(
            proportion=0.1, 
            slope_range=(0.0, 0.15),
            platform_width=2.0, 
            border_width=0.25
        ),
    },
)


# --- Custom Termination Functions ---

def check_nan_termination(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Terminates and resets the environment immediately if any physics values blow up to NaN or Inf."""
    robot = env.scene["robot"]
    
    # Check if robot base coordinates or joint positions/velocities are NaN
    nan_root = torch.isnan(robot.data.root_pos_w).any(dim=-1)
    nan_joints = torch.isnan(robot.data.joint_pos).any(dim=-1) | torch.isnan(robot.data.joint_vel).any(dim=-1)
    
    # Check if robot base coordinates or joint positions/velocities are Inf
    inf_root = torch.isinf(robot.data.root_pos_w).any(dim=-1)
    inf_joints = torch.isinf(robot.data.joint_pos).any(dim=-1) | torch.isinf(robot.data.joint_vel).any(dim=-1)
    
    nan_or_inf = nan_root | nan_joints | inf_root | inf_joints
    
    # Check contact sensor forces for NaN/Inf
    contact_sensor = env.scene.sensors.get("contact_forces")
    if contact_sensor is not None:
        nan_contacts = torch.isnan(contact_sensor.data.net_forces_w).any(dim=-1).any(dim=-1)
        inf_contacts = torch.isinf(contact_sensor.data.net_forces_w).any(dim=-1).any(dim=-1)
        nan_or_inf |= nan_contacts | inf_contacts
        
    return nan_or_inf


# --- Robot Asset Configuration ---

SPOODER_CFG = ArticulationCfg(
    spawn=sim_utils.UsdFileCfg(
        usd_path=os.path.join(current_dir, "spooder.usd"),
        activate_contact_sensors=True,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            retain_accelerations=False,
            linear_damping=0.0,
            angular_damping=0.0,
            max_linear_velocity=1000.0,
            max_angular_velocity=1000.0,
            max_depenetration_velocity=1.0,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=False,
            solver_position_iteration_count=4,
            solver_velocity_iteration_count=0,
        ),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.09),  # Spawn height adjusted to 9cm to prevent immediate base contact on slopes
        joint_pos={
            "Revolute.*": 0.0,  # All 18 joints start at 0.0 radians
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.9,
    actuators={
        "base_legs": ImplicitActuatorCfg(
            joint_names_expr=["Revolute.*"],
            effort_limit=100.0,
            velocity_limit=100.0,
            stiffness=50.0,
            damping=1.0,
        ),
    },
)

# --- Environment Configuration ---

@configclass
class SpooderRoughEnvCfg(LocomotionVelocityRoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()

        # Spawn Spooder robot USD
        self.scene.robot = SPOODER_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")
        
        # Scanner path (base link name is base_link)
        self.scene.height_scanner.prim_path = "{ENV_REGEX_NS}/Robot/base_link"
        
        # Configure contact sensors
        self.scene.contact_forces.prim_path = "{ENV_REGEX_NS}/Robot/.*"
        
        # Apply the micro-rough terrain generator scaled for Spooder
        self.scene.terrain.terrain_generator = SPOODER_ROUGH_TERRAINS_CFG

        # Action scale & Stance Bias Offset
        self.actions.joint_pos.scale = 0.25
        self.actions.joint_pos.use_default_offset = True

        # Overrides for Events
        self.events.add_base_mass.params["asset_cfg"].body_names = "base_link"
        self.events.add_base_mass.params["mass_distribution_params"] = (-0.1, 0.3)
        self.events.base_external_force_torque.params["asset_cfg"].body_names = "base_link"
        self.events.base_com = None
        self.events.reset_robot_joints.params["position_range"] = (0.9, 1.1)
        self.events.reset_base.params = {
            "pose_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5), "yaw": (-3.14, 3.14)},
            "velocity_range": {
                "x": (0.0, 0.0),
                "y": (0.0, 0.0),
                "z": (0.0, 0.0),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (0.0, 0.0),
            },
        }

        # --- Rewards Configuration (EXACT ORIGINAL COMMIT REWARDS) ---
        
        # Track feet links (link_3_step_v1_1 through link_3_step_v1_6)
        self.rewards.feet_air_time.params["sensor_cfg"].body_names = "link_3_step_v1_.*"
        self.rewards.feet_air_time.weight = 0.05
        
        # Undesired contact (legs above feet touching ground: link_2_step_v1_.*)
        self.rewards.undesired_contacts.params["sensor_cfg"].body_names = "link_2_step_v1_.*"
        self.rewards.undesired_contacts.weight = -1.0
        
        # Penalize tilting too much
        self.rewards.flat_orientation_l2.weight = -2.5
        
        # Joint torque and acceleration penalties
        self.rewards.dof_torques_l2.weight = -1.0e-5
        self.rewards.dof_acc_l2.weight = -2.5e-7
        
        # Forward velocity tracking reward
        self.rewards.track_lin_vel_xy_exp.weight = 2.0
        self.rewards.track_ang_vel_z_exp.weight = 0.5
        
        # Terminations Overrides
        # Terminate if the base_link touches the ground
        self.terminations.base_contact.params["sensor_cfg"].body_names = "base_link"
        
        # Terminate if the robot falls off the terrain grid cliff (prevents NaN values)
        self.terminations.height_below_minimum = DoneTerm(
            func=mdp.root_height_below_minimum,
            params={"minimum_height": -0.2}
        )
        
        # Terminate if any state explodes to NaN/Inf (prevents numerical instability crashes)
        self.terminations.nan_check = DoneTerm(
            func=check_nan_termination
        )


@configclass
class SpooderFlatEnvCfg(SpooderRoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()

        # change terrain to flat plane
        self.scene.terrain.terrain_type = "plane"
        self.scene.terrain.terrain_generator = None
        
        # no height scan needed for flat terrain
        self.scene.height_scanner = None
        self.observations.policy.height_scan = None
        
        # no terrain curriculum
        self.curriculum.terrain_levels = None


@configclass
class SpooderFlatPPORunnerCfg(RslRlOnPolicyRunnerCfg):
    num_steps_per_env = 128  # 128 steps per rollout (~5s iteration time for stable walking trajectories)
    max_iterations = 1500
    save_interval = 50
    experiment_name = "spooder_flat"
    policy = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        noise_std_type="log",
        actor_obs_normalization=False,
        critic_obs_normalization=False,
        actor_hidden_dims=[512, 256, 128],  # Wider network for processing the 187 height scan dimensions
        critic_hidden_dims=[512, 256, 128],
        activation="elu",
    )
    algorithm = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.005,  # Slightly lower entropy for stable convergence
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=5.0e-4,  # Lower learning rate (was 1e-3) to prevent value loss explosion
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )
