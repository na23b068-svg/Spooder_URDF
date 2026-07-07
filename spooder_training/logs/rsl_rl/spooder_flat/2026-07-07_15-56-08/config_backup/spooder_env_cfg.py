import os
import math
import torch
import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg

current_dir = os.path.dirname(os.path.abspath(__file__))
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.utils import configclass
from isaaclab.envs import ManagerBasedRLEnv
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import LocomotionVelocityRoughEnvCfg
from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlPpoActorCriticCfg, RslRlPpoAlgorithmCfg

# --- Custom Reward Functions ---

def stance_feet_contact_reward(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Rewards keeping stationary/support legs down on the floor to prevent floating."""
    # Net vertical contact forces on the 6 feet (shape: num_envs, 6)
    # sensor named "contact_forces" tracks contacts for the entire articulation
    # but we filter vertical force components (Z-axis is index 2)
    foot_forces = env.scene["contact_forces"].data.net_forces_w[:, :, 2]
    
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


def track_lin_vel_x_exp_reward(env: ManagerBasedRLEnv, std: float, command_name: str = "base_velocity") -> torch.Tensor:
    """Reward tracking of linear velocity commands (x-axis/forward only) using exponential kernel."""
    robot = env.scene["robot"]
    # Compute error on local X-axis (index 0) only
    lin_vel_error = torch.square(env.command_manager.get_command(command_name)[:, 0] - robot.data.root_lin_vel_b[:, 0])
    return torch.exp(-lin_vel_error / std ** 2)


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
        pos=(0.0, 0.0, 0.08),  # Spawn height (about 8cm)
        # Symmetrical design stance (Request 1 & 2):
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

        # Action scale & Stance Bias Offset (Request 1)
        self.actions.joint_pos.scale = 0.25
        self.actions.joint_pos.use_default_offset = True

        # Overrides for Events (Friction and base mass randomizations are already active)
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

        # Rewards Overrides
        # Track feet links (link_3_step_v1_1 through link_3_step_v1_6)
        self.rewards.feet_air_time.params["sensor_cfg"].body_names = "link_3_step_v1_.*"
        self.rewards.feet_air_time.weight = 0.05
        
        # Undesired contact (legs above feet touching ground: link_2_step_v1_.*)
        self.rewards.undesired_contacts.params["sensor_cfg"].body_names = "link_2_step_v1_.*"
        self.rewards.undesired_contacts.weight = -1.0
        
        # Penalize tilting too much
        self.rewards.flat_orientation_l2.weight = -2.5
        
        # Enable Soft Joint Limits Penalty (Request 3)
        self.rewards.dof_pos_limits.weight = -10.0
        
        # Custom Stance Leg Contact Force Reward (Floating legs prevention)
        self.rewards.stance_feet_contact = RewTerm(
            func=stance_feet_contact_reward,
            weight=1.5
        )
        
        # Joint torque and acceleration penalties
        self.rewards.dof_torques_l2.weight = -1.0e-5
        self.rewards.dof_acc_l2.weight = -2.5e-7
        
        # Forward velocity tracking reward (XY disabled, X-only active)
        self.rewards.track_lin_vel_xy_exp.weight = 0.0
        self.rewards.track_lin_vel_x_exp = RewTerm(
            func=track_lin_vel_x_exp_reward,
            weight=2.0,
            params={"std": math.sqrt(0.25)}
        )
        self.rewards.track_ang_vel_z_exp.weight = 0.5
        
        # Terminations Overrides
        # Terminate if the base_link touches the ground
        self.terminations.base_contact.params["sensor_cfg"].body_names = "base_link"

        # Remove encoder feedback and linear velocity tracking to train an IMU-only policy
        self.observations.policy.joint_pos = None      # No joint position encoders
        self.observations.policy.joint_vel = None      # No joint velocity encoders
        self.observations.policy.base_lin_vel = None   # No base linear velocity estimation


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
    num_steps_per_env = 128
    max_iterations = 1000
    save_interval = 50
    experiment_name = "spooder_flat"
    policy = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        actor_obs_normalization=False,
        critic_obs_normalization=False,
        actor_hidden_dims=[128, 128, 128],
        critic_hidden_dims=[128, 128, 128],
        activation="elu",
    )
    algorithm = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.01,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=1.0e-3,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )
