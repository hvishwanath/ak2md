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
                    output_path=str(self.context.output_dir / "content" / "en"),
                    rules=self.context.rules,
                    registry=registry
                )
                
                if not processor.execute():
                    self.logger.error(f"Failed to process documentation version: {version}")
                    success = False
            
            # Process kraft.md files if they exist
            if success:
                self.logger.info("Processing kraft.md files for heading level adjustments")
                success = self._process_kraft_files()
            
            return success
                
        except Exception as e:
            self.logger.error(f"Post-processing failed: {str(e)}")
            return False
    
    def _process_kraft_files(self) -> bool:
        """Process kraft.md files to adjust heading levels for migration section"""
        try:
            import re
            import os
            
            # Find all kraft.md files in the output directory
            kraft_files = list(self.context.output_dir.rglob("operations/kraft.md"))
            
            if not kraft_files:
                self.logger.info("No kraft.md files found to process")
                return True
            
            self.logger.info(f"Found {len(kraft_files)} kraft.md files to process")
            
            for kraft_file in kraft_files:
                self.logger.info(f"Processing kraft.md file: {kraft_file}")
                
                # Read the file content
                with open(kraft_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check if "ZooKeeper to KRaft Migration" section exists
                if "ZooKeeper to KRaft Migration" not in content:
                    self.logger.info(f"No 'ZooKeeper to KRaft Migration' section found in {kraft_file}")
                    continue
                
                # Split content into lines for processing
                lines = content.split('\n')
                processed_lines = []
                in_migration_section = False
                
                for line in lines:
                    # Check if this line starts a heading
                    heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
                    
                    if heading_match:
                        level = len(heading_match.group(1))
                        heading_text = heading_match.group(2)
                        
                        # Check if this is the "ZooKeeper to KRaft Migration" heading
                        if "ZooKeeper to KRaft Migration" in heading_text:
                            in_migration_section = True
                            # Bump up the heading level (remove one #)
                            new_level = max(1, level - 1)
                            processed_lines.append('#' * new_level + ' ' + heading_text)
                            continue
                        
                        # If we're in the migration section, bump up all subsection headings
                        if in_migration_section:
                            # Check if this is a subsection (higher level than the main migration heading)
                            if level >= 3:  # Assuming the main migration heading is level 2 or 3
                                new_level = max(1, level - 1)
                                processed_lines.append('#' * new_level + ' ' + heading_text)
                            else:
                                # This is a new main section, exit migration section
                                in_migration_section = False
                                processed_lines.append(line)
                            continue
                    
                    # If not a heading, just add the line as-is
                    processed_lines.append(line)
                
                # Write the processed content back to the file
                processed_content = '\n'.join(processed_lines)
                with open(kraft_file, 'w', encoding='utf-8') as f:
                    f.write(processed_content)
                
                self.logger.info(f"Successfully processed kraft.md file: {kraft_file}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing kraft.md files: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
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