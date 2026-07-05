import argparse
import os
import sys
from datetime import datetime

# Add isaaclab scripts directory to sys.path for importing cli_args and utilities
import isaaclab
isaaclab_dir = list(isaaclab.__path__)[0]
isaaclab_root = os.path.abspath(os.path.join(isaaclab_dir, "..", "..", ".."))
sys.path.append(os.path.join(isaaclab_root, "scripts", "reinforcement_learning", "rsl_rl"))

from isaaclab.app import AppLauncher

# Set up argument parser
parser = argparse.ArgumentParser(description="Train an RL agent with RSL-RL for Spooder.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during training.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video (in steps).")
parser.add_argument("--video_interval", type=int, default=2000, help="Interval between video recordings (in steps).")
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default="Isaac-Velocity-Flat-Spooder-v0", help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment")
parser.add_argument("--max_iterations", type=int, default=None, help="RL Policy training iterations.")

# Add RSL-RL and AppLauncher arguments
import cli_args
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)

args_cli = parser.parse_args()

# Launch Omniverse App (This starts the simulation engine)
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# --- Rest of imports follow after app is launched ---
import gymnasium as gym
import torch
from rsl_rl.runners import OnPolicyRunner
from isaaclab.envs import ManagerBasedRLEnvCfg
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper, handle_deprecated_rsl_rl_cfg
from isaaclab.utils.assets import retrieve_file_path

# Import our custom environment configs
from spooder_env_cfg import SpooderFlatEnvCfg, SpooderRoughEnvCfg, SpooderFlatPPORunnerCfg

# Register both Flat and Rough environments in Gym
gym.register(
    id="Isaac-Velocity-Flat-Spooder-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": SpooderFlatEnvCfg,
        "rsl_rl_cfg_entry_point": SpooderFlatPPORunnerCfg,
    },
)

gym.register(
    id="Isaac-Velocity-Rough-Spooder-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": SpooderRoughEnvCfg,
        "rsl_rl_cfg_entry_point": SpooderFlatPPORunnerCfg,
    },
)

def main():
    # parse configuration
    env_cfg: ManagerBasedRLEnvCfg = gym.spec(args_cli.task).kwargs["env_cfg_entry_point"]()
    agent_cfg = gym.spec(args_cli.task).kwargs["rsl_rl_cfg_entry_point"]()

    # Override configurations from CLI
    if args_cli.max_iterations is not None:
        agent_cfg.max_iterations = args_cli.max_iterations
    if args_cli.num_envs is not None:
        env_cfg.scene.num_envs = args_cli.num_envs
    if args_cli.seed is not None:
        env_cfg.seed = args_cli.seed
        agent_cfg.seed = args_cli.seed
    
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device

    # Handle deprecated RSL-RL configurations (converts 'policy' to 'actor' and 'critic')
    import importlib.metadata as metadata
    installed_version = metadata.version("rsl-rl-lib")
    agent_cfg = handle_deprecated_rsl_rl_cfg(agent_cfg, installed_version)

    # Setup logging directory inside our local folder
    log_root_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "rsl_rl", agent_cfg.experiment_name)
    log_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if agent_cfg.run_name:
        log_dir += f"_{agent_cfg.run_name}"
    log_dir = os.path.join(log_root_path, log_dir)
    env_cfg.log_dir = log_dir

    print(f"[INFO] Logging experiment in directory: {log_dir}")

    # Create the environment
    env = gym.make(args_cli.task, cfg=env_cfg)

    # Wrap for video recording if specified
    if args_cli.video:
        video_kwargs = {
            "video_folder": os.path.join(log_dir, "videos", "train"),
            "step_trigger": lambda step: step % args_cli.video_interval == 0,
            "video_length": args_cli.video_length,
            "disable_logger": True,
        }
        env = gym.wrappers.RecordVideo(env, **video_kwargs)

    # Wrap for RSL-RL
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

    # Create OnPolicy runner
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=log_dir, device=agent_cfg.device)

    # Load checkpoint if resuming
    if args_cli.resume:
        if args_cli.checkpoint:
            resume_path = retrieve_file_path(args_cli.checkpoint)
        else:
            from isaaclab_tasks.utils import get_checkpoint_path
            resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)
        print(f"[INFO] Resuming training from checkpoint: {resume_path}")
        runner.load(resume_path)

    # Start learning
    num_iterations = agent_cfg.max_iterations
    if args_cli.resume:
        num_iterations = max(0, agent_cfg.max_iterations - runner.current_learning_iteration)
        
    runner.learn(num_learning_iterations=num_iterations, init_at_random_ep_len=True)

    # Close environment
    env.close()

if __name__ == "__main__":
    main()
    simulation_app.close()
