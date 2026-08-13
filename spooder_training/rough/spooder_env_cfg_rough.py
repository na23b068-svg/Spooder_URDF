from dbm import error
import math
import torch
import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.utils import configclass
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import LocomotionVelocityRoughEnvCfg
from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlPpoActorCriticCfg, RslRlPpoAlgorithmCfg
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.envs import ManagerBasedRLEnv

# --- for mild rough terrain #
#from isaaclab.terrains import (
    #TerrainGeneratorCfg,
    #HfRandomUniformTerrainCfg,
#)

# --- Custom Reward Functions ---

def track_lin_vel_x_exp_reward(env: ManagerBasedRLEnv, std: float, command_name: str = "base_velocity") -> torch.Tensor:
    """Reward tracking of linear velocity commands (x-axis/forward only) using exponential kernel."""
    robot = env.scene["robot"]
    # Compute error on local X-axis (index 0) only
    #logs/rsl_rl/spooder_flat/2026-07-10_18-01-52/model_300.pt
    lin_vel_error = torch.square(env.command_manager.get_command(command_name)[:, 0] - robot.data.root_lin_vel_w[:, 0])
    return torch.exp(-lin_vel_error / std ** 2)


def foot_slip_penalty(env: ManagerBasedRLEnv) -> torch.Tensor:
    """
    Penalize horizontal slipping of feet that are in contact with the ground.
    """

    FOOT_NAMES = "link_3_step_v1_.*"
    CONTACT_THRESHOLD = 2.0  # Newtons

    robot = env.scene["robot"]

    # Cache body indices
    if not hasattr(foot_slip_penalty, "foot_ids"):
        foot_slip_penalty.foot_ids = robot.find_bodies(FOOT_NAMES)[0]

    foot_ids = foot_slip_penalty.foot_ids

    # (num_envs, 6, 3)
    foot_vel = robot.data.body_lin_vel_w[:, foot_ids]

    # Horizontal speed only
    foot_speed_xy = torch.norm(foot_vel[:, :, :2], dim=-1)

    # Vertical contact force
    contact_force = env.scene["contact_forces"].data.net_forces_w[:, foot_ids, 2]
    #contact_force = env.scene["contact_forces"].data.net_forces_w[:, :, 2]
    in_contact = contact_force > CONTACT_THRESHOLD

    # Penalize only feet that are actually touching the ground
    slip = foot_speed_xy * in_contact.float()

    num_contact = in_contact.float().sum(dim=1).clamp(min=1.0)

    return slip.sum(dim=1) / num_contact

def excessive_swing_height_penalty(env: ManagerBasedRLEnv) -> torch.Tensor:
    """
    Penalize swing feet that are lifted unnecessarily high.

    Should be used together with a feet_drag penalty.
    """

    FOOT_NAMES = "link_3_step_v1_.*"

    MAX_CLEARANCE = 0.08      # 8 cm
    CONTACT_THRESHOLD = 2.0   # Newtons

    robot = env.scene["robot"]

    # Cache body ids on first call
    if not hasattr(excessive_swing_height_penalty, "foot_ids"):
        excessive_swing_height_penalty.foot_ids = robot.find_bodies(FOOT_NAMES)[0]

    foot_ids = excessive_swing_height_penalty.foot_ids

    # World-frame foot positions
    foot_height = robot.data.body_pos_w[:, foot_ids, 2]

    # Determine which feet are swinging
    contact_force = env.scene["contact_forces"].data.net_forces_w[:, foot_ids, 2]
    #contact_force = env.scene["contact_forces"].data.net_forces_w[:, :, 2]
    swing = contact_force < CONTACT_THRESHOLD

    # Penalize only the amount above the desired clearance
    excess = torch.relu(foot_height - MAX_CLEARANCE)

    penalty = (excess ** 2) * swing.float()

    num_swing = swing.float().sum(dim=1).clamp(min=1.0)

    return penalty.sum(dim=1) / num_swing

def spin_reward(env: ManagerBasedRLEnv) -> torch.Tensor:
    TARGET_YAW_RATE = 1.0  # rad/s

    omega = env.scene["robot"].data.root_ang_vel_w[:, 2]
    error = omega - TARGET_YAW_RATE

    return torch.exp(-(error**2) / 0.25)

def linear_motion_penalty(env: ManagerBasedRLEnv) -> torch.Tensor:
    robot = env.scene["robot"]
    return torch.norm(robot.data.root_lin_vel_w[:, :2], dim=1)

# --- Robot asset configuration ---

SPOODER_CFG = ArticulationCfg(
    spawn=sim_utils.UsdFileCfg(
        usd_path="/home/smeer/Downloads/Spooder_URDF-main/spooder.usd",
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
        joint_pos={
            "Revolute.*": 0.0,  # All 18 joints start at 0 radians
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

@configclass
class SpooderRoughEnvCfg(LocomotionVelocityRoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()

        print("=" * 60)
        print("Terrain type:", self.scene.terrain.terrain_type)
        print("Terrain generator:", self.scene.terrain.terrain_generator)
        print("=" * 60)        

        self.scene.terrain.terrain_type = "generator"

        # Spawn Spooder robot USD
        self.scene.robot = SPOODER_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")
        
        # Scanner path (base link name is base_link)
        self.scene.height_scanner.prim_path = "{ENV_REGEX_NS}/Robot/base_link"
        
        # Configure contact sensors
        self.scene.contact_forces.prim_path = "{ENV_REGEX_NS}/Robot/.*"

        # Action scale (reduce joint angle target magnitude from policy)
        self.actions.joint_pos.scale = 0.25

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

        # Rewards Overrides
        # Track feet links (link_3_step_v1_1 through link_3_step_v1_6)
        self.rewards.feet_air_time.params["sensor_cfg"].body_names = "link_3_step_v1_.*"
        self.rewards.feet_air_time.weight = 0.05
        
        # Undesired contact (legs above feet touching ground: link_2_step_v1_.* or link_1_step_v1_.*)
        self.rewards.undesired_contacts.params["sensor_cfg"].body_names = "link_2_step_v1_.*"
        self.rewards.undesired_contacts.weight = -1.0
        
        # Penalize tilting too much (tilt penalty matches user requirement)
        #self.rewards.flat_orientation_l2.weight = -2.5
        
        # Joint torque and acceleration penalties (to prevent jittering)
        self.rewards.dof_torques_l2.weight = -1.0e-5
        self.rewards.dof_acc_l2.weight = -2.5e-7
        
        #Forward velocity tracking reward
        self.rewards.track_lin_vel_x_exp = RewTerm(
            func=track_lin_vel_x_exp_reward,
            weight=3.0,
            params={"std": math.sqrt(0.25)}
        )

        self.rewards.foot_slip = RewTerm(
        func=foot_slip_penalty,
        weight=-0.5,
        )

        # Angular velocity tracking reward (yaw rate)
        #self.rewards.track_ang_vel_z_exp.weight = 5

        #self.rewards.high_step_penalty = RewTerm(
        #func=excessive_swing_height_penalty,
        #weight=-0.5,
        #)
        


        #self.rewards.linear_motion_penalty = RewTerm(
        #func=linear_motion_penalty,
        #weight=-0.5,
        #)

        #self.rewards.spin_reward = RewTerm(
        #func=spin_reward,
        #weight=5.0,
        #)   

        # --- Terminations Overrides ---

        # Terminate if the base_link touches the ground
        self.terminations.base_contact.params["sensor_cfg"].body_names = "base_link"

# --- Mild rough terrain configuration for training Spooder ---
#@configclass
#class SpooderFlatEnvCfg(SpooderRoughEnvCfg):
    #def __post_init__(self):
        #super().__post_init__()

        #self.scene.terrain.terrain_type = "generator"
        #self.scene.terrain.terrain_generator = None
        #self.scene.terrain.terrain_generator = TerrainGeneratorCfg(
            #size=(8.0, 8.0),
            #num_rows=10,
            #num_cols=10,
            #border_width=20.0,
            #curriculum=True,
            #sub_terrains={
                #"rough": HfRandomUniformTerrainCfg(
                #proportion=1.0,
                #noise_range=(0.0, 0.015),   # 1.5 cm initial roughness
                #noise_step=0.005,
                #)
            #}
        #)
        
        # no height scan needed for flat terrain
        #self.scene.height_scanner = None
        #self.observations.policy.height_scan = None
        
        # no terrain curriculum
        #self.curriculum.terrain_levels = None


@configclass
class SpooderFlatEnvCfg(SpooderRoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()

        # Flat terrain
        self.scene.terrain.terrain_type = "plane"
        self.scene.terrain.terrain_generator = None

        # Height scanner not needed on flat terrain
        self.scene.height_scanner = None
        self.observations.policy.height_scan = None

        # Disable terrain curriculum
        self.curriculum.terrain_levels = None

@configclass
class SpooderFlatPPORunnerCfg(RslRlOnPolicyRunnerCfg):
    num_steps_per_env = 128
    max_iterations = 5000 
    save_interval = 100
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

@configclass
class SpooderRoughPPORunnerCfg(RslRlOnPolicyRunnerCfg):
    num_steps_per_env = 128
    max_iterations = 5000 
    save_interval = 100
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
