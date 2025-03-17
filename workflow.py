#!/usr/bin/env python3

import os
import sys
import logging
import shutil
import subprocess
import yaml
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from enum import Enum, auto

from utils import HandleBarsContextBuilder
from convert import pre_process
from post_process import post_process

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ak2md-workflow')

class StageStatus(Enum):
    NOT_STARTED = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()

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
            script_dir = Path(__file__).parent
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

class WorkflowStage:
    """Base class for all workflow stages"""
    
    def __init__(self, name: str, context: WorkflowContext):
        self.name = name
        self.context = context
        self.status = StageStatus.NOT_STARTED
        self.logger = logging.getLogger(f'ak2md-workflow.{name}')
    
    def execute(self) -> bool:
        """Execute the stage and return success status"""
        try:
            self.status = StageStatus.IN_PROGRESS
            self.logger.info(f"Starting stage: {self.name}")
            
            success = self._do_execute()
            
            self.status = StageStatus.COMPLETED if success else StageStatus.FAILED
            self.logger.info(f"Completed stage: {self.name} with status: {self.status}")
            
            return success
        except Exception as e:
            self.status = StageStatus.FAILED
            self.logger.error(f"Stage {self.name} failed with error: {str(e)}", exc_info=True)
            return False
    
    def _do_execute(self) -> bool:
        """Implementation specific to each stage"""
        raise NotImplementedError

class CloneStage(WorkflowStage):
    """Clones or updates the Kafka site repository"""
    
    def _do_execute(self) -> bool:
        if not (self.context.source_dir / ".git").exists():
            # Fresh clone
            self.logger.info(f"Cloning {self.context.kafka_site_repo}")
            result = subprocess.run(
                ["git", "clone", self.context.kafka_site_repo, str(self.context.source_dir)],
                capture_output=True,
                text=True
            )
        else:
            # Update existing repo
            self.logger.info("Updating existing repository")
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(self.context.source_dir),
                capture_output=True,
                text=True
            )
        
        if result.returncode != 0:
            self.logger.error(f"Git operation failed: {result.stderr}")
            return False
            
        # Checkout specific branch if needed
        if self.context.kafka_site_branch != "main":
            result = subprocess.run(
                ["git", "checkout", self.context.kafka_site_branch],
                cwd=str(self.context.source_dir),
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                self.logger.error(f"Failed to checkout branch: {result.stderr}")
                return False
        
        # Copy process.yaml to workspace if it doesn't exist
        rules_dest = self.context.workspace_dir / "process.yaml"
        if not rules_dest.exists():
            shutil.copy2("process.yaml", rules_dest)
            self.logger.info(f"Copied process.yaml to workspace: {rules_dest}")
        
        return True

class PreProcessStage(WorkflowStage):
    """Converts HTML to Markdown"""
    
    def _do_execute(self) -> bool:
        try:
            # Build HandleBars context
            self.logger.info("Building Handlebars context")
            hb = HandleBarsContextBuilder(str(self.context.source_dir))
            
            self.logger.info("Starting HTML to Markdown conversion")
            pre_process(
                input_path=str(self.context.source_dir),
                output_path=str(self.context.interim_dir),
                static_path=str(self.context.static_dir),
                hb=hb,
                rules=self.context.rules
            )
            return True
        except Exception as e:
            self.logger.error(f"Pre-processing failed: {str(e)}")
            return False

class PostProcessStage(WorkflowStage):
    """Restructures and reformats the Markdown"""
    
    def _do_execute(self) -> bool:
        try:
            self.logger.info("Starting Markdown restructuring")
            post_process(
                input_path=str(self.context.interim_dir),
                output_path=str(self.context.output_dir),
                static_path=str(self.context.static_dir),
                rules=self.context.rules
            )
            return True
        except Exception as e:
            self.logger.error(f"Post-processing failed: {str(e)}")
            return False

class ValidationStage(WorkflowStage):
    """Validates the generated output"""
    
    def _do_execute(self) -> bool:
        # Basic validation checks
        if not self.context.output_dir.exists():
            self.logger.error("Output directory does not exist")
            return False
            
        # Check if we have generated files
        md_files = list(self.context.output_dir.rglob("*.md"))
        if not md_files:
            self.logger.error("No markdown files were generated")
            return False
            
        self.logger.info(f"Found {len(md_files)} markdown files")
        
        # Check if static files were copied
        static_files = list(self.context.static_dir.rglob("*"))
        if not static_files:
            self.logger.warning("No static files were copied")
        else:
            self.logger.info(f"Found {len(static_files)} static files")
        
        # Check for doc version directories
        doc_dirs = [d for d in self.context.output_dir.iterdir() if d.is_dir() and d.name != "static"]
        if not doc_dirs:
            self.logger.error("No documentation version directories found")
            return False
            
        self.logger.info(f"Found {len(doc_dirs)} documentation versions")
        
        return True

class Workflow:
    """Main workflow orchestrator"""
    
    def __init__(self, workspace_dir: str):
        self.context = WorkflowContext(Path(workspace_dir))
        self.stages = [
            CloneStage("clone", self.context),
            PreProcessStage("pre-process", self.context),
            PostProcessStage("post-process", self.context),
            ValidationStage("validate", self.context)
        ]
    
    def run(self, start_stage: Optional[str] = None) -> bool:
        """Run the workflow, optionally starting from a specific stage"""
        
        start_idx = 0
        if start_stage:
            try:
                start_idx = next(i for i, stage in enumerate(self.stages) 
                               if stage.name == start_stage)
            except StopIteration:
                logger.error(f"Invalid stage name: {start_stage}")
                return False
        
        for stage in self.stages[start_idx:]:
            if not stage.execute():
                return False
        
        return True

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert Kafka site from HTML to Markdown')
    parser.add_argument('--workspace', default='./workspace',
                       help='Workspace directory for the conversion')
    parser.add_argument('--start-stage', 
                       choices=['clone', 'pre-process', 'post-process', 'validate'],
                       help='Start from a specific stage')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    workflow = Workflow(args.workspace)
    success = workflow.run(args.start_stage)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 