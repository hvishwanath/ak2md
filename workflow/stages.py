#!/usr/bin/env python3

import logging
import subprocess
from typing import Optional, List, Dict
from pathlib import Path

from workflow.base import WorkflowStage
from workflow.registry import WorkflowStepRegistry
from workflow.processors import (
    PreProcessDirectory, 
    ProcessDocVersion,
    ProcessSpecialFiles,
    special_file_processors
)
from utils import HandleBarsContextBuilder

logger = logging.getLogger('ak2md-workflow.stages')

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
        
        return True

class PreProcessStage(WorkflowStage):
    """Converts HTML to Markdown"""
    
    def _do_execute(self) -> bool:
        try:
            # Build HandleBars context
            self.logger.info("Building Handlebars context")
            hb = HandleBarsContextBuilder(str(self.context.source_dir))
            
            # Initialize step registry
            registry = WorkflowStepRegistry()
            
            # Process the input directory
            self.logger.info("Starting HTML to Markdown conversion using granular workflow steps")
            processor = PreProcessDirectory(
                src_dir=str(self.context.source_dir),
                dest_dir=str(self.context.interim_dir),
                static_path=str(self.context.static_dir),
                hb=hb,
                rules=self.context.rules,
                registry=registry
            )
            
            result = processor.execute()
            if not result:
                self.logger.error("Pre-processing failed")
            return result
            
        except Exception as e:
            self.logger.error(f"Pre-processing failed: {str(e)}")
            return False

class PostProcessStage(WorkflowStage):
    """Restructures and reformats the Markdown"""
    
    def _do_execute(self) -> bool:
        try:
            # Initialize step registry
            registry = WorkflowStepRegistry()
            
            self.logger.info("Starting Markdown restructuring using granular workflow steps")
            
            # Process each doc version
            success = True
            for version in self.context.rules.get('doc_dirs', []):
                self.logger.info(f"Processing documentation version: {version}")
                processor = ProcessDocVersion(
                    version=version,
                    input_path=str(self.context.interim_dir),
                    output_path=str(self.context.output_dir),
                    rules=self.context.rules,
                    registry=registry
                )
                
                if not processor.execute():
                    self.logger.error(f"Failed to process documentation version: {version}")
                    success = False
            
            return success
                
        except Exception as e:
            self.logger.error(f"Post-processing failed: {str(e)}")
            return False

class ProcessSpecialFilesStage(WorkflowStage):
    """Stage for processing special files with custom logic"""
    
    def __init__(self, name: str, context: 'WorkflowContext', special_files: List[Dict[str, str]]):
        super().__init__(name, context)
        self.special_files = special_files or []
        self.logger.debug(f"Initialized with {len(self.special_files)} special files: {self.special_files}")
    
    def _do_execute(self) -> bool:
        try:
            success = True
            
            self.logger.debug(f"Processing {len(self.special_files)} special files")
            
            for special_file in self.special_files:
                file_name = special_file.get('file')
                processor = special_file.get('processor')
                input_dir = special_file.get('input_dir', 'interim')
                
                self.logger.debug(f"Processing file: {file_name}, processor: {processor}, input_dir: {input_dir}")
                
                if not file_name or not processor:
                    self.logger.error(f"Invalid special file configuration: {special_file}")
                    success = False
                    continue
                
                # Determine input path
                if input_dir == 'interim':
                    input_path = str(self.context.interim_dir)
                elif input_dir == 'source':
                    input_path = str(self.context.source_dir)
                else:
                    input_path = str(Path(self.context.workspace_dir) / input_dir)
                
                self.logger.debug(f"Input path for {file_name}: {input_path}")
                
                processor_obj = ProcessSpecialFiles(
                    file_name=file_name,
                    input_path=input_path,
                    output_path=str(self.context.output_dir),
                    processor_name=processor,
                    registry=special_file_processors
                )
                
                if not processor_obj.execute():
                    self.logger.error(f"Failed to process special file: {file_name}")
                    success = False
            
            return success
        except Exception as e:
            self.logger.error(f"Error in special files processing stage: {str(e)}")
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
        doc_dirs = [d for d in self.context.output_dir.iterdir() if d.is_dir() and d.name != "static" and d.name != "data"]
        if not doc_dirs:
            self.logger.error("No documentation version directories found")
            return False
            
        self.logger.info(f"Found {len(doc_dirs)} documentation versions")
        
        # Check for key sections in each doc version
        for doc_dir in doc_dirs:
            section_dirs = [d for d in doc_dir.iterdir() if d.is_dir()]
            if not section_dirs:
                self.logger.error(f"No sections found in documentation version: {doc_dir.name}")
                return False
                
            self.logger.info(f"Found {len(section_dirs)} sections in version: {doc_dir.name}")
            
            # Check specific key sections that should exist
            key_sections = ['getting-started', 'apis', 'configuration']
            missing_sections = [s for s in key_sections if not any(d.name == s for d in section_dirs)]
            
            if missing_sections:
                self.logger.warning(f"Missing key sections in version {doc_dir.name}: {', '.join(missing_sections)}")
        
        # Check for data directory and files if special files were processed
        data_dir = self.context.output_dir / "data"
        if data_dir.exists():
            data_files = list(data_dir.glob("*.json"))
            self.logger.info(f"Found {len(data_files)} data files in data directory")
        
        return True 