import argparse
import os
import sys
import time

# Add isaaclab scripts directory to sys.path for importing cli_args and utilities
possible_paths = [
    "/home/smeer/Downloads/isaaclab/scripts/reinforcement_learning/rsl_rl",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "isaaclab", "scripts", "reinforcement_learning", "rsl_rl")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "isaaclab", "scripts", "reinforcement_learning", "rsl_rl")),
]
for p in possible_paths:
    if os.path.exists(p):
        sys.path.append(p)
        break

from isaaclab.app import AppLauncher

# Set up argument parser
parser = argparse.ArgumentParser(description="Play a trained RL policy for Spooder.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during play.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video (in steps).")
parser.add_argument("--num_envs", type=int, default=16, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default="Isaac-Velocity-Flat-Spooder-v0", help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment")

# Add RSL-RL and AppLauncher arguments
import cli_args
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)

args_cli = parser.parse_args()

# Launch Omniverse App (GUI is active by default during play)
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# --- Rest of imports follow after app is launched ---
import gymnasium as gym
import torch
from packaging import version
import importlib.metadata as metadata
from rsl_rl.runners import OnPolicyRunner
from isaaclab.envs import ManagerBasedRLEnvCfg
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper, handle_deprecated_rsl_rl_cfg
from isaaclab.utils.assets import retrieve_file_path

# Import our custom environment config
from spooder_env_cfg import SpooderFlatEnvCfg, SpooderFlatPPORunnerCfg

# Register environment in Gym
gym.register(
    id="Isaac-Velocity-Flat-Spooder-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": SpooderFlatEnvCfg,
        "rsl_rl_cfg_entry_point": SpooderFlatPPORunnerCfg,
    },
)

def main():
    installed_version = metadata.version("rsl-rl-lib")

    # Load configs
    env_cfg = SpooderFlatEnvCfg()
    agent_cfg = SpooderFlatPPORunnerCfg()

    # Smaller scene settings for play
    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else 16
    env_cfg.scene.env_spacing = 2.5
    env_cfg.observations.policy.enable_corruption = False

    # Override with command line arguments
    if args_cli.seed is not None:
        env_cfg.seed = args_cli.seed
        agent_cfg.seed = args_cli.seed
    
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device

    # Handle deprecated RSL-RL configurations
    agent_cfg = handle_deprecated_rsl_rl_cfg(agent_cfg, installed_version)

    # Find checkpoint path
    if args_cli.checkpoint:
        resume_path = retrieve_file_path(args_cli.checkpoint)
    else:
        # Load from our workspace logs directory
        log_root_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "rsl_rl", agent_cfg.experiment_name)
        # Find latest checkpoint
        from isaaclab_tasks.utils import get_checkpoint_path
        resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)

    print(f"[INFO] Loading model checkpoint from: {resume_path}")
    log_dir = os.path.dirname(resume_path)
    env_cfg.log_dir = log_dir

    # Create environment
    env = gym.make(args_cli.task, cfg=env_cfg)

    # Wrap for RSL-RL
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

    # Load runner
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    runner.load(resume_path)

    # Obtain policy
    policy = runner.get_inference_policy(device=env.unwrapped.device)

    dt = env.unwrapped.step_dt
    obs = env.get_observations()

    # Play loop
    while simulation_app.is_running():
        start_time = time.time()
        with torch.inference_mode():
            actions = policy(obs)
            obs, _, dones, _ = env.step(actions)
            if version.parse(installed_version) >= version.parse("4.0.0"):
                policy.reset(dones)
        
        # Real-time synchronization
        sleep_time = dt - (time.time() - start_time)
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Close environment
    env.close()

if __name__ == "__main__":
    main()
    simulation_app.close()
