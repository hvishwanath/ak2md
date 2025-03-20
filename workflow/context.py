#!/usr/bin/env python3

import os
import logging
import shutil
import yaml
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger('ak2md-workflow.context')

@dataclass
class WorkflowContext:
    """Maintains the state and configuration of the workflow"""
    workspace_dir: Path
    kafka_site_repo: str = "https://github.com/apache/kafka-site.git"
    kafka_site_branch: str = "main"
    source_dir: Optional[Path] = None
    interim_dir: Optional[Path] = None
    output_dir: Optional[Path] = None
    static_dir: Optional[Path] = None
    rules: Optional[dict] = None
    
    def __post_init__(self):
        # Initialize paths
        self.source_dir = self.workspace_dir / "source"
        self.interim_dir = self.workspace_dir / "interim"
        self.output_dir = self.workspace_dir / "output"
        self.static_dir = self.output_dir / "static"
        
        # Create necessary directories
        for dir_path in [self.workspace_dir, self.source_dir, self.interim_dir, self.output_dir, self.static_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Copy process.yaml to workspace if it doesn't exist
        self._setup_rules()
            
    def _setup_rules(self):
        """Setup rules file in the workspace"""
        rules_dest = self.workspace_dir / "process.yaml"
        
        # First try to copy from current directory
        rules_src = Path("process.yaml")
        if not rules_src.exists():
            # Try to find it relative to the script location
            script_dir = Path(__file__).parent.parent
            rules_src = script_dir / "process.yaml"
        
        if rules_src.exists():
            if not rules_dest.exists():
                shutil.copy2(rules_src, rules_dest)
                logger.info(f"Copied process.yaml to workspace: {rules_dest}")
        else:
            logger.error("process.yaml not found in current directory or script directory")
            raise FileNotFoundError("process.yaml not found. Please ensure it exists in the current directory or script directory.")
        
        # Load rules
        with open(rules_dest) as f:
            self.rules = yaml.safe_load(f)
            logger.debug("Loaded rules from process.yaml") 