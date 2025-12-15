#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Configuration
# Each item can be a string (version) or a dict with "version" and optional "upstream_branch".
# If "upstream_branch" is omitted, it defaults to the version string.
VERSIONS_CONFIG = [
    {"version": "3.5"},
    {"version": "3.6"},
    {"version": "3.7"},
    {"version": "3.8"},
    {"version": "3.9"},
    {"version": "4.0"},
    {"version": "4.1"},
    {"version": "4.2"},
    {"version": "4.3", "upstream_branch": "trunk"},
]

VERSIONS_CONFIG = [{"version": "4.3", "upstream_branch": "trunk"}]

def get_dir_suffix(version):
    return version.replace(".", "")

def run_git_cmd(repo_path, args, check=True):
    """Run a git command in the specified repo."""
    cmd = ["git"] + args
    print(f"   [CMD] {' '.join(cmd)}")
    result = subprocess.run(
        cmd, 
        cwd=repo_path, 
        capture_output=True, 
        text=True
    )
    if check and result.returncode != 0:
        print(f"   [ERROR] Command failed: {' '.join(cmd)}")
        print(f"   [STDERR] {result.stderr}")
        sys.exit(1)
    return result

def main():
    # Resolve paths relative to this script location
    # Script is in <root>/misc/prepare_pr_branches.py
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent # ak2md
    workspace_root = project_root.parent # projects
    
    kafka_repo = workspace_root / "kafka"
    kafka_site_repo = workspace_root / "kafka-site"
    
    print(f"Script Path: {script_path}")
    print(f"Project Root: {project_root}")
    print(f"Kafka Repo: {kafka_repo}")
    print(f"Kafka Site Repo: {kafka_site_repo}")
    print("-" * 40)

    if not kafka_repo.exists():
        print(f"Error: Kafka repo not found at {kafka_repo}")
        sys.exit(1)

    if not kafka_site_repo.exists():
        print(f"Error: Kafka site repo not found at {kafka_site_repo}")
        sys.exit(1)

    for config in VERSIONS_CONFIG:
        # Handle mixed types if necessary, but here we enforce dicts for consistency
        if isinstance(config, str):
            version = config
            upstream_branch = config
        else:
            version = config["version"]
            upstream_branch = config.get("upstream_branch", version)
            
        dir_suffix = get_dir_suffix(version)
        print(f"Processing version: {version} (Upstream: {upstream_branch}, Content dir: {dir_suffix})")
        
        # 1. Update Kafka Repo
        print(" > Updating Kafka repo...")
        
        # Fetch all
        run_git_cmd(kafka_repo, ["fetch", "--all", "--quiet"], check=False)
        
        # Checkout upstream branch
        # Try upstream/{upstream_branch}, then origin/{upstream_branch}, then local {upstream_branch}
        print(f" > Checking out upstream/{upstream_branch}...")
        res = run_git_cmd(kafka_repo, ["checkout", f"upstream/{upstream_branch}"], check=False)
        if res.returncode != 0:
            print(f"   'upstream/{upstream_branch}' failed, trying 'origin/{upstream_branch}'...")
            res = run_git_cmd(kafka_repo, ["checkout", f"origin/{upstream_branch}"], check=False)
            if res.returncode != 0:
                print(f"   'origin/{upstream_branch}' failed, trying local '{upstream_branch}'...")
                # Note: If local branch exists but tracks something else, this might be just switching to it.
                # Assuming this is what we want if remotes fail.
                run_git_cmd(kafka_repo, ["checkout", upstream_branch]) # Fail if this also fails

        # Create new local branch d-{ver} (still based on version number)
        branch_name = f"d-{version}"
        print(f" > Creating/Resetting branch {branch_name}...")
        
        # Check if branch exists
        res = run_git_cmd(kafka_repo, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], check=False)
        if res.returncode == 0:
            print(f"   Branch {branch_name} exists. Deleting it first...")
            run_git_cmd(kafka_repo, ["branch", "-D", branch_name])
        
        run_git_cmd(kafka_repo, ["checkout", "-b", branch_name])
        
        # 2. File Operations
        print(" > Updating documentation content...")
        docs_dir = kafka_repo / "docs"
        if not docs_dir.exists():
            print(f"   'docs' directory not found at {docs_dir}! Creating it...")
            docs_dir.mkdir(parents=True, exist_ok=True)
            
        print("   Cleaning docs directory (preserving images)...")
        # Remove everything except 'images'
        for item in docs_dir.iterdir():
            if item.name in ['.', '..', 'images']:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
                
        # Copy new content
        source_content_dir = kafka_site_repo / "content" / "en" / dir_suffix
        if not source_content_dir.exists():
            print(f"   [WARNING] Source content directory not found: {source_content_dir}")
            choice = input("   Skip this version? (y/n): ")
            if choice.lower() == 'y':
                continue
            else:
                print("   Exiting...")
                sys.exit(1)
        
        print(f"   Copying content from {source_content_dir} to {docs_dir}...")
        shutil.copytree(source_content_dir, docs_dir, dirs_exist_ok=True)
        
        print(f" > Done for version {version}.")
        print("-" * 40)
        
        # Show status
        run_git_cmd(kafka_repo, ["status", "--short"], check=False)
        print("-" * 40)
        
        # 3. Interactive Pause
        print(f"Branch '{branch_name}' is ready in '{kafka_repo}'.")
        print("You can now inspect the changes, commit, and push PR.")
        print(f"Suggested: cd {kafka_repo} && git add . && git commit -m \"Sync docs for {version}\"")
        print("")
        try:
            input("Press Enter to proceed to the next version (or Ctrl+C to stop)...")
        except KeyboardInterrupt:
            print("\nStopping...")
            sys.exit(0)
        print("-" * 40)

    print("All versions processed!")

if __name__ == "__main__":
    main()
