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
from isaaclab.managers import SceneEntityCfg
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import LocomotionVelocityRoughEnvCfg
from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlPpoActorCriticCfg, RslRlPpoAlgorithmCfg

current_dir = os.path.dirname(os.path.abspath(__file__))

# --- Custom Terrain Config for Small Robot (8cm height) ---
# We scale down all height properties to 1/10th scale to match Spooder's physical limits.
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
            noise_range=(0.005, 0.025),        # 0.5cm to 2.5cm height bumps (must be multiple of vertical_scale)
            noise_step=0.005,                  # 0.5cm noise step (avoid ZeroDivisionError)
            border_width=0.25
        ),
        "hf_pyramid_slope": terrain_gen.HfPyramidSlopedTerrainCfg(
            proportion=0.1, 
            slope_range=(0.0, 0.15),           # Up to 15% slope (was 40%)
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


# --- Custom Reward Functions ---

def stance_feet_contact_reward(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Rewards keeping stationary/support legs down on the floor to prevent floating."""
    # Net vertical contact forces on the 6 feet (shape: num_envs, 6)
    # sensor named "contact_forces" tracks contacts for the entire articulation
    # but we filter vertical force components (Z-axis is index 2)
    foot_forces = env.scene.sensors["contact_forces"].data.net_forces_w[:, :, 2]

    # Count feet with firm contact (force > 1.0 Newton)
    in_contact = foot_forces > 1.0
    num_contacts = torch.sum(in_contact.float(), dim=-1)

    # Check if the robot is standing still (command velocity is zero)
    commands = env.command_manager.get_command("base_velocity")
    is_standing = torch.norm(commands[:, 0:2], dim=-1) < 0.1

    # If standing still: reward having all 6 feet on the ground
    # If walking: reward having at least 3 feet on the ground (tripod gait support phase)
    reward = torch.where(
        is_standing,
        num_contacts / 6.0,
        torch.clamp(num_contacts, max=3.0) / 3.0
    )

    return reward


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

        # --- Rewards Configuration (Backtracked to original working config) ---
        
        # 1. Stepping Air Time
        self.rewards.feet_air_time.params["sensor_cfg"] = SceneEntityCfg("contact_forces", body_names="link_3_step_v1_.*")
        self.rewards.feet_air_time.weight = 0.05
        
        # 2. Undesired contact (legs above feet touching ground)
        self.rewards.undesired_contacts.params["sensor_cfg"].body_names = "link_2_step_v1_.*"
        self.rewards.undesired_contacts.weight = -1.0
        
        # 3. Custom Stance Leg Contact Force Reward (Floating legs prevention)
        self.rewards.stance_feet_contact = RewTerm(
            func=stance_feet_contact_reward,
            weight=1.5
        )
        
        # 4. Locomotion rewards & Penalties
        self.rewards.flat_orientation_l2.weight = -2.5
        self.rewards.dof_pos_limits.weight = -10.0
        self.rewards.dof_torques_l2.weight = -1.0e-5
        self.rewards.dof_acc_l2.weight = -2.5e-7
        
        # Forward velocity tracking reward
        self.rewards.track_lin_vel_xy_exp.weight = 2.0
        self.rewards.track_ang_vel_z_exp.weight = 0.5
        
        # Terminations Overrides
        # Terminate if the base_link touches the ground
        self.terminations.base_contact.params["sensor_cfg"].body_names = "base_link"


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
    num_steps_per_env = 32  # Shorter steps for robust trajectory updates on rough terrain
    max_iterations = 1500
    save_interval = 50
    experiment_name = "spooder_flat"
    policy = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
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
