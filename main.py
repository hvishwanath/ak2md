#!/usr/bin/env python3

import sys
import logging
import argparse
from pathlib import Path

from workflow.context import WorkflowContext
from workflow import (
    CloneStage, 
    PreProcessStage, 
    PostProcessStage, 
    ValidationStage,
    ProcessSpecialFilesStage
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ak2md-workflow')

class Workflow:
    """Main workflow orchestrator"""
    
    def __init__(self, workspace_dir: str):
        self.context = WorkflowContext(Path(workspace_dir))
        
        # Define special files to process
        special_files = [
            {
                'file': 'committers.md',
                'processor': 'committers',
                'input_dir': 'interim'
            },
            {
                'file': 'powered-by.html',
                'processor': 'powered-by',
                'input_dir': 'source'
            },
            {
                'file': 'blog.md',
                'processor': 'blog',
                'input_dir': 'interim'
            }
            # More special files can be added here
        ]
        
        # Or load from process.yaml if present
        if self.context.rules and 'special_files' in self.context.rules:
            special_files = self.context.rules.get('special_files')
        
        self.stages = [
            CloneStage("clone", self.context),
            PreProcessStage("pre-process", self.context),
            PostProcessStage("post-process", self.context),
            ProcessSpecialFilesStage("special-files", self.context, special_files),
            ValidationStage("validate", self.context)
        ]
    
    def run(self, start_stage=None) -> bool:
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
    parser = argparse.ArgumentParser(description='Convert Kafka site from HTML to Markdown')
    parser.add_argument('--workspace', default='./workspace',
                       help='Workspace directory for the conversion')
    parser.add_argument('--start-stage', 
                       choices=['clone', 'pre-process', 'post-process', 'special-files', 'validate'],
                       help='Start from a specific stage')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--skip-validation', action='store_true',
                       help='Skip validation stage')
    
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
        # Set debug logging for other loggers
        logging.getLogger('ak2md-workflow.steps').setLevel(logging.DEBUG)
        logging.getLogger('ak2md-workflow.stages').setLevel(logging.DEBUG)
        logging.getLogger('ak2md-workflow.processors').setLevel(logging.DEBUG)
    
    workflow = Workflow(args.workspace)
    
    if args.skip_validation:
        workflow.stages = [s for s in workflow.stages if s.name != "validate"]
    
    success = workflow.run(args.start_stage)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 