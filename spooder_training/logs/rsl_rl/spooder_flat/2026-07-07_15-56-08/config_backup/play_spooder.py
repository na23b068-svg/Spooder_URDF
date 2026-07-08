import argparse
import os
import sys
import time
import traceback

# Add isaaclab scripts directory to sys.path for importing cli_args and utilities
possible_paths = [
    "/home/smeer/Downloads/isaaclab/scripts/reinforcement_learning/rsl_rl",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "isaaclab", "scripts", "reinforcement_learning", "rsl_rl")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "isaaclab", "scripts", "reinforcement_learning", "rsl_rl")),
]
for p in possible_paths:
    if os.path.exists(p):
        sys.path.append(p)
        print(f"[INFO] Found cli_args at: {p}")
        break
else:
    print("[ERROR] Could not find cli_args path! Check isaaclab installation.")

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

# --- Rest of imports follow AFTER app is launched ---
try:
    import gymnasium as gym
    import torch
    from packaging import version
    import importlib.metadata as metadata
    from rsl_rl.runners import OnPolicyRunner
    from isaaclab.envs import ManagerBasedRLEnvCfg
    from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper, handle_deprecated_rsl_rl_cfg
    from isaaclab.utils.assets import retrieve_file_path
    print("[INFO] ✅ All core imports succeeded.")
except Exception as e:
    print(f"\n[FATAL] Import failed after AppLauncher:\n{traceback.format_exc()}")
    simulation_app.close()
    sys.exit(1)

# Dynamically import our custom environment config
try:
    import spooder_env_cfg
    print(f"[INFO] ✅ spooder_env_cfg loaded from: {spooder_env_cfg.__file__}")
except Exception as e:
    print(f"\n[FATAL] Failed to import spooder_env_cfg:\n{traceback.format_exc()}")
    simulation_app.close()
    sys.exit(1)

# Register Flat environment (always available)
try:
    gym.register(
        id="Isaac-Velocity-Flat-Spooder-v0",
        entry_point="isaaclab.envs:ManagerBasedRLEnv",
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": getattr(spooder_env_cfg, "SpooderFlatEnvCfg"),
            "rsl_rl_cfg_entry_point": getattr(spooder_env_cfg, "SpooderFlatPPORunnerCfg"),
        },
    )
    print("[INFO] ✅ Registered Isaac-Velocity-Flat-Spooder-v0")
except Exception as e:
    print(f"\n[FATAL] Failed to register flat env:\n{traceback.format_exc()}")
    simulation_app.close()
    sys.exit(1)

# Register Rough environment (only if config classes exist)
try:
    gym.register(
        id="Isaac-Velocity-Rough-Spooder-v0",
        entry_point="isaaclab.envs:ManagerBasedRLEnv",
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": getattr(spooder_env_cfg, "SpooderRoughEnvCfg"),
            "rsl_rl_cfg_entry_point": getattr(spooder_env_cfg, "SpooderRoughPPORunnerCfg"),
        },
    )
    print("[INFO] ✅ Registered Isaac-Velocity-Rough-Spooder-v0")
except AttributeError:
    print("[INFO] ⚠️  Rough env config not in this backup — skipping rough registration.")
except Exception as e:
    print(f"[WARNING] Could not register rough env: {e}")


def main():
    try:
        installed_version = metadata.version("rsl-rl-lib")
        print(f"[INFO] rsl-rl-lib version: {installed_version}")

        # Load configs dynamically based on task
        if "Flat" in args_cli.task:
            env_cfg = getattr(spooder_env_cfg, "SpooderFlatEnvCfg")()
            agent_cfg = getattr(spooder_env_cfg, "SpooderFlatPPORunnerCfg")()
            print("[INFO] ✅ Loaded flat terrain config")
        else:
            env_cfg = getattr(spooder_env_cfg, "SpooderRoughEnvCfg")()
            agent_cfg = getattr(spooder_env_cfg, "SpooderRoughPPORunnerCfg")()
            print("[INFO] ✅ Loaded rough terrain config")

        # Smaller scene settings for play
        env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else 16
        env_cfg.scene.env_spacing = 2.5
        env_cfg.observations.policy.enable_corruption = False
        # Force USD rendering instead of Fabric to ensure meshes move in visualizer
        env_cfg.sim.use_fabric = False

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
            log_root_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "rsl_rl", agent_cfg.experiment_name)
            from isaaclab_tasks.utils import get_checkpoint_path
            resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)

        print(f"[INFO] ✅ Loading checkpoint: {resume_path}")
        log_dir = os.path.dirname(resume_path)
        env_cfg.log_dir = log_dir

        # Create environment
        print("[INFO] Creating environment...")
        env = gym.make(args_cli.task, cfg=env_cfg)
        print("[INFO] ✅ Environment created.")

        # Wrap for RSL-RL
        env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

        # Load runner and policy
        runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
        runner.load(resume_path)
        policy = runner.get_inference_policy(device=env.unwrapped.device)
        print("[INFO] ✅ Policy loaded. Starting play loop...")

        dt = env.unwrapped.step_dt
        obs = env.get_observations()

        # Play loop
        step_count = 0
        while simulation_app.is_running():
            start_time = time.time()
            with torch.inference_mode():
                actions = policy(obs)
                obs, _, dones, _ = env.step(actions)
                if version.parse(installed_version) >= version.parse("4.0.0"):
                    policy.reset(dones)

            step_count += 1
            if step_count % 50 == 0:
                print(f"🔄 Step: {step_count} | Actions Mean: {actions.mean().item():.4f} | Resets: {dones.sum().item()}")

            # Real-time synchronization
            sleep_time = dt - (time.time() - start_time)
            if sleep_time > 0:
                time.sleep(sleep_time)

        env.close()

    except Exception as e:
        print(f"\n[FATAL] Exception in main():\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
    simulation_app.close()
