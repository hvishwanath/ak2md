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
    special_file_processors,
    TocCleaner
)
from workflow.processors.special_files import (
    _transform_youtube_to_carousel,
    _transform_use_cases_to_cards,
    _transform_code_to_tabs,
    _remove_redundant_links
)
from utils import HandleBarsContextBuilder

logger = logging.getLogger('ak2md-workflow.stages')

class CloneStage(WorkflowStage):
    """Clones or updates the Kafka site repository"""
    
    def _do_execute(self) -> bool:
        git_options = self.context.rules.get('git_options', {})
        target_branch = git_options.get('branch', 'asf-site')
        target_commit = git_options.get('commit')

        if not (self.context.source_dir / ".git").exists():
            # Fresh clone
            self.logger.info(f"Cloning {self.context.kafka_site_repo} (branch: {target_branch})")
            result = subprocess.run(
                ["git", "clone", "-b", target_branch, self.context.kafka_site_repo, str(self.context.source_dir)],
                capture_output=True,
                text=True
            )
        else:
            # Update existing repo
            self.logger.info("Fetching updates for existing repository")
            result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=str(self.context.source_dir),
                capture_output=True,
                text=True
            )
        
        if result.returncode != 0:
            self.logger.error(f"Git operation failed: {result.stderr}")
            return False
            
        # Checkout specific branch
        self.logger.info(f"Checking out branch {target_branch}")
        subprocess.run(
            ["git", "checkout", target_branch],
            cwd=str(self.context.source_dir),
            capture_output=True,
            text=True
        )
        
        if target_commit:
            # Hard reset to specific commit
            self.logger.info(f"Resetting to specific commit {target_commit}")
            result = subprocess.run(
                ["git", "reset", "--hard", target_commit],
                cwd=str(self.context.source_dir),
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                self.logger.error(f"Failed to reset to commit {target_commit}: {result.stderr}")
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
            
            # Clean TOC from all markdown files
            if success:
                self.logger.info("Cleaning manually created TOC sections from markdown files")
                toc_cleaner = TocCleaner(self.context.output_dir)
                if not toc_cleaner.execute():
                    self.logger.error("Failed to clean TOC sections")
                    success = False
            
            # Process kraft.md files if they exist
            if success:
                self.logger.info("Processing kraft.md files for heading level adjustments")
                success = self._process_kraft_files()

            # Create documentation redirects
            if success:
                self.logger.info("Creating documentation redirect files")
                success = self._create_doc_redirects()
            
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
    def _create_doc_redirects(self) -> bool:
        """Creates documentation/_index.md with redirect for each version and shadow files for streams"""
        try:
            import re
            
            content_dir = self.context.output_dir / "content" / "en"
            if not content_dir.exists():
                self.logger.warning(f"Content directory not found: {content_dir}")
                return True

            redirect_content = (
                "---\n"
                "title: \"Documentation Redirect\"\n"
                "robots: \"noindex\"\n"
                "_build:\n"
                "  list: false\n"
                "---\n\n"
                "{{< doc-redirect >}}\n"
            )
            
            version_pattern = re.compile(r'^\d+')
            processed_versions = []
            
            # Process each version directory
            for item in content_dir.iterdir():
                if item.is_dir() and version_pattern.match(item.name):
                    version = item.name
                    processed_versions.append(version)
                    
                    # 1. Create documentation/_index.md
                    doc_dir = item / "documentation"
                    doc_dir.mkdir(exist_ok=True)
                    
                    index_file = doc_dir / "_index.md"
                    if not index_file.exists():
                        self.logger.info(f"Creating redirect file: {index_file}")
                        with open(index_file, "w", encoding='utf-8') as f:
                            f.write(redirect_content)
                    
                    # 2. Generate shadow streams files
                    source_streams = item / "streams"
                    target_streams = doc_dir / "streams"
                    
                    if source_streams.exists():
                        self.logger.info(f"Generating shadow streams files for version {version}")
                        self._generate_shadow_files(source_streams, target_streams, redirect_content)

            # 3. Handle Global Documentation Directory (mirrors latest version)
            if processed_versions:
                def parse_version(v: str):
                    try:
                        if v.startswith('0'):
                            # 082 -> 0.8.2, 0110 -> 0.11.0
                            part = v[1:]
                            if len(part) == 2:
                                return (0, int(part[0]), int(part[1]))
                            elif len(part) == 3:
                                return (0, int(part[:2]), int(part[2]))
                        else:
                            # 32 -> 3.2, 41 -> 4.1
                            if len(v) == 2:
                                return (int(v[0]), int(v[1]), 0)
                    except:
                        pass
                    return (0, 0, 0)

                latest_version = max(processed_versions, key=parse_version)
                
                self.logger.info(f"Identified latest version for global mirror: {latest_version} (from {len(processed_versions)} versions)")
                
                latest_source_streams = content_dir / latest_version / "streams"
                global_target_streams = content_dir / "documentation" / "streams"
                
                if latest_source_streams.exists():
                    self.logger.info(f"Generating global shadow streams files from {latest_version}")
                    self._generate_shadow_files(latest_source_streams, global_target_streams, redirect_content)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating doc redirects: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    def _generate_shadow_files(self, source_dir: Path, target_base_dir: Path, content: str):
        """Recursively mirror directory structure and create shadow redirect files"""
        try:
            import os
            files_count = 0
            for root, dirs, files in os.walk(str(source_dir)):
                # relative path from source root
                rel_path = Path(root).relative_to(source_dir)
                
                # Determine target directory
                target_dir = target_base_dir / rel_path
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # For every file in source, create a corresponding file in target
                for file in files:
                    if file.endswith(".md") or file.endswith(".html"):
                        target_file = target_dir / file
                        if not target_file.exists():
                            # self.logger.debug(f"Creating shadow file: {target_file}")
                            with open(target_file, "w", encoding='utf-8') as f:
                                f.write(content)
                            files_count += 1
            
            self.logger.info(f"Generated {files_count} shadow files in {target_base_dir}")
            
        except Exception as e:
            self.logger.error(f"Error generating shadow files from {source_dir}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())


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

class StreamsEnhancementStage(WorkflowStage):
    """Enhances Kafka Streams documentation with carousel, cards, and tabbed code"""
    
    def _do_execute(self) -> bool:
        try:
            streams_config = self.context.rules.get('streams_enhancements', {})
            
            # Check if streams enhancements are enabled
            if not streams_config.get('enabled', True):
                self.logger.info("Streams enhancements are disabled, skipping")
                return True
            
            # Get list of versions to process
            target_versions = streams_config.get('versions', ['*'])
            if '*' in target_versions:
                # Process all versions
                target_versions = self.context.rules.get('doc_dirs', [])
            
            self.logger.info(f"Processing streams enhancements for versions: {target_versions}")
            
            success = True
            for version in target_versions:
                # Read from the post-processed introduction.md (has proper front matter)
                streams_intro_file = self.context.output_dir / "content" / "en" / version / "streams" / "introduction.md"
                
                if not streams_intro_file.exists():
                    self.logger.debug(f"No streams/introduction.md found for version {version}, skipping")
                    continue
                
                self.logger.info(f"Processing streams/introduction.md for version {version}")
                
                # Read the post-processed file (has proper front matter already)
                with open(streams_intro_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Load testimonials data
                testimonials_file = self.context.output_dir / "data" / "testimonials.json"
                testimonials_data = []
                if testimonials_file.exists():
                    import json
                    with open(testimonials_file, 'r', encoding='utf-8') as f:
                        testimonials_data = json.load(f)
                    self.logger.debug(f"Loaded {len(testimonials_data)} testimonials")
                else:
                    self.logger.warning(f"Testimonials file not found at {testimonials_file}")
                
                # Apply transformations in order
                try:
                    content = _transform_youtube_to_carousel(content)
                    content = _transform_use_cases_to_cards(content, testimonials_data)
                    content = _transform_code_to_tabs(content)
                    content = _remove_redundant_links(content)
                except Exception as e:
                    self.logger.error(f"Failed to process streams introduction for version {version}: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    success = False
                    continue
                
                # Write back the processed content
                with open(streams_intro_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                self.logger.info(f"Successfully enhanced streams/introduction.md for version {version}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Streams enhancement stage failed: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
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