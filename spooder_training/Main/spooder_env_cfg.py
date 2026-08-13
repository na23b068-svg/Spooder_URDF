import math
import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.utils import configclass
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import LocomotionVelocityRoughEnvCfg
from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlPpoActorCriticCfg, RslRlPpoAlgorithmCfg

# Robot asset configuration
SPOODER_CFG = ArticulationCfg(
    spawn=sim_utils.UsdFileCfg(
        usd_path="/home/smeer/Downloads/spooder_training/spooder.usd",
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
        self.rewards.flat_orientation_l2.weight = -2.5
        
        # Joint torque and acceleration penalties (to prevent jittering)
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
