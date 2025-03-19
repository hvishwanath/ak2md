#!/usr/bin/env python3

import os
import logging
import yaml
import shutil
from pathlib import Path
from typing import Optional, List, Callable, Dict, Any, Tuple

from utils import (
    HandleBarsContextBuilder,
    execute_step,
    get_title_from_filename,
    write_file,
    # From convert.py
    sanitize_input_html,
    process_handlebars_templates,
    process_ssi_tags_with_hugo,
    convert_html_to_md,
    add_front_matter,
    process_markdown_headings,
    # From post_process.py
    update_front_matter,
    process_markdown_links,
    split_markdown_by_heading
)

logger = logging.getLogger('ak2md-workflow.steps')

# Define step function type
StepFunction = Callable[[str, Dict[str, Any]], Tuple[str, Dict[str, Any]]]

class WorkflowStepRegistry:
    """Registry of workflow steps that can be composed into stages"""
    
    def __init__(self):
        self.pre_process_steps: Dict[str, StepFunction] = {}
        self.post_process_steps: Dict[str, StepFunction] = {}
        self._register_all_steps()
    
    def _register_all_steps(self):
        """Register all available steps"""
        # Register pre-process steps
        self.register_pre_process_step("sanitize_html", sanitize_input_html)
        self.register_pre_process_step("process_handlebars", process_handlebars_templates)
        self.register_pre_process_step("process_ssi", process_ssi_tags_with_hugo)
        self.register_pre_process_step("convert_to_md", convert_html_to_md)
        self.register_pre_process_step("add_front_matter", add_front_matter)
        self.register_pre_process_step("process_headings", process_markdown_headings)
        
        # Register post-process steps
        self.register_post_process_step("update_front_matter", update_front_matter)
        self.register_post_process_step("process_links", process_markdown_links)
        self.register_post_process_step("split_by_heading", split_markdown_by_heading)
    
    def register_pre_process_step(self, name: str, step_func: StepFunction):
        """Register a pre-process step"""
        self.pre_process_steps[name] = step_func
        logger.debug(f"Registered pre-process step: {name}")
    
    def register_post_process_step(self, name: str, step_func: StepFunction):
        """Register a post-process step"""
        self.post_process_steps[name] = step_func
        logger.debug(f"Registered post-process step: {name}")
    
    def get_pre_process_steps(self, step_names: Optional[List[str]] = None) -> List[StepFunction]:
        """Get pre-process steps by name or all if names not provided"""
        if step_names is None:
            # Default pre-process steps in the original order
            step_names = [
                "sanitize_html",
                "process_handlebars",
                "process_ssi",
                "convert_to_md",
                "add_front_matter",
                "process_headings"
            ]
        
        return [self.pre_process_steps[name] for name in step_names]
    
    def get_post_process_steps(self, step_names: Optional[List[str]] = None) -> List[StepFunction]:
        """Get post-process steps by name or all if names not provided"""
        if step_names is None:
            # Default post-process steps in a sensible order
            step_names = [
                "update_front_matter",
                "process_links",
                "split_by_heading"
            ]
        
        return [self.post_process_steps[name] for name in step_names]

class PreProcessFile:
    """Process a single HTML file to Markdown"""
    
    def __init__(self, src_file: str, dest_file: str, static_path: str, hb_context: dict, rules: dict, 
                 steps: List[StepFunction]):
        self.src_file = src_file
        self.dest_file = dest_file
        self.static_path = static_path
        self.hb_context = hb_context
        self.rules = rules
        self.steps = steps
    
    def execute(self) -> bool:
        """Process the file using the specified steps"""
        context = {
            "hb": self.hb_context
        }
        context['title'] = get_title_from_filename(self.dest_file)
        context['src_file_name'] = os.path.basename(self.src_file)
        context["dest_file_name"] = os.path.basename(self.dest_file)
        context['base_dir'] = os.path.dirname(self.src_file)
        context['up_level'] = True
        context['remove_numeric'] = True
        context['rules'] = self.rules
        
        logger.info(f'Processing file: {self.src_file}, Destination file: {self.dest_file}')
        try:
            with open(self.src_file, 'r', encoding='utf-8') as html_file:
                html_content = html_file.read()
            
            content, context = html_content, context
            for step in self.steps:
                content, context = execute_step(step, content, context)
            
            write_file(self.dest_file, content, context)
            return True
        except Exception as e:
            logger.error(f'Error processing file: {self.src_file}, Error: {e}')
            return False

class PreProcessDirectory:
    """Process a directory of HTML files to Markdown"""
    
    def __init__(self, src_dir: str, dest_dir: str, static_path: str, hb: HandleBarsContextBuilder, 
                 rules: dict, registry: WorkflowStepRegistry):
        self.src_dir = src_dir
        self.dest_dir = dest_dir
        self.static_path = static_path
        self.hb = hb
        self.rules = rules
        self.registry = registry
    
    def execute(self) -> bool:
        """Process the directory and its contents"""
        if os.path.basename(self.src_dir) in self.rules.get('exclude_dirs', []):
            logger.info(f'Skipping excluded directory: {self.src_dir}')
            return True
        
        if os.path.basename(self.src_dir) in self.rules.get('static_dirs', []):
            logger.info(f'Copying static directory: {self.src_dir}')
            parent_dir = os.path.dirname(os.path.abspath(self.src_dir))
            # If parent directory is not one of the docs_dirs, then copy directly into static path
            if os.path.basename(parent_dir) in self.rules.get('doc_dirs', []):
                dest_dir = os.path.join(os.path.join(self.static_path, os.path.basename(parent_dir)), 
                                       os.path.basename(self.src_dir))
            else:
                dest_dir = os.path.join(self.static_path, os.path.basename(self.src_dir))
            try:
                shutil.copytree(self.src_dir, dest_dir, dirs_exist_ok=True)
                return True
            except Exception as e:
                logger.error(f'Error copying static directory: {self.src_dir}, Error: {e}')
                return False
        
        try:
            if not os.path.exists(self.dest_dir):
                os.makedirs(self.dest_dir)
                with open(os.path.join(self.dest_dir, '_index.md'), 'w', encoding='utf-8') as index_file:
                    index_file.write('')
                logger.info(f'Created directory and _index.md: {self.dest_dir}')
            
            # Process files and subdirectories
            for item in os.listdir(self.src_dir):
                src_path = os.path.join(self.src_dir, item)
                dest_path = os.path.join(self.dest_dir, item)
                
                if os.path.isdir(src_path):
                    logger.info(f'Processing directory: {src_path}')
                    processor = PreProcessDirectory(
                        src_path, dest_path, self.static_path, self.hb, self.rules, self.registry
                    )
                    if not processor.execute():
                        return False
                elif src_path.endswith('.html'):
                    logger.info(f'Processing HTML file: {src_path}')
                    processor = PreProcessFile(
                        src_path, dest_path, self.static_path, 
                        self.hb.get_context(src_path), self.rules,
                        self.registry.get_pre_process_steps()
                    )
                    if not processor.execute():
                        return False
                else:
                    try:
                        shutil.copy2(src_path, dest_path)
                        logger.info(f'Copied file: {src_path} to {dest_path}')
                    except Exception as e:
                        logger.error(f'Error copying file: {src_path}, Error: {e}')
                        return False
            
            return True
        except Exception as e:
            logger.error(f'Error processing directory: {self.src_dir}, Error: {e}')
            return False

class ProcessDocSection:
    """Process a section in a documentation version"""
    
    def __init__(self, section: dict, context: dict, registry: WorkflowStepRegistry):
        self.section = section
        self.context = context
        self.registry = registry
    
    def execute(self) -> bool:
        """Process the section using the specified strategy"""
        try:
            self.context["section_dir"] = os.path.join(self.context['output_path'], self.section['name'])
            
            # Create the section directory
            if os.path.exists(self.context["section_dir"]):
                shutil.rmtree(self.context["section_dir"])
            os.makedirs(self.context["section_dir"])
            
            # Create the _index.md file
            index_file = os.path.join(self.context["section_dir"], '_index.md')
            template_values = {
                "title": self.section["title"],
                "description": self.section.get("description", ""),
                "tags": self.context["front_matter"]["tags"] + self.section.get("tags", []),
                "aliases": "",
                "weight": self.context["section_weight"],
                "type": self.section.get("type", "docs"),
                "keywords": self.section.get("keywords", "")
            }
            self.context["template_values"] = template_values
            
            # Write index file
            front_matter, _ = update_front_matter("", self.context)
            with open(index_file, 'w') as file:
                file.write(front_matter)
            
            strategy = self.section["strategy"]
            if strategy == "arrange":
                return self._execute_arrange_strategy()
            elif strategy == "split_markdown_by_heading":
                return self._execute_split_strategy()
            else:
                logger.error(f"Unknown strategy: {strategy}")
                return False
        except Exception as e:
            logger.error(f"Error processing section {self.section.get('name')}: {str(e)}")
            return False
    
    def _execute_arrange_strategy(self) -> bool:
        """Execute the 'arrange' strategy"""
        steps = [
            update_front_matter,
            process_markdown_headings,
            process_markdown_links,
        ]
        
        for w, n in enumerate(self.section["files"], start=1):
            template_values = {
                "title": n["title"],
                "description": n.get("description", ""),
                "tags": self.context["front_matter"]["tags"] + n.get("tags", []),
                "aliases": "",
                "weight": w,
                "type": self.section.get("type", "docs"),
                "keywords": n.get("keywords", "")
            }
            
            self.context["template_values"] = template_values
            src_file = os.path.join(self.context['src_dir'], n['src_file'])
            if not os.path.exists(src_file):
                logger.info(f'File not found: {src_file}, continuing processing...')
                continue
                
            if "dst_file" in n:
                dest_file = os.path.join(self.context["section_dir"], n['dst_file'])
            else:
                dest_file = os.path.join(self.context["section_dir"], n['src_file'])
                
            logger.info(f'Processing file: {src_file}, Destination file: {dest_file}')
            try:
                with open(src_file, 'r', encoding='utf-8') as html_file:
                    content = html_file.read()
                    
                for step in steps:
                    content, self.context = execute_step(step, content, self.context)
                
                write_file(dest_file, content, self.context)
            except Exception as e:
                logger.error(f'Error processing file: {src_file}, Error: {e}')
                return False
        
        return True
    
    def _execute_split_strategy(self) -> bool:
        """Execute the 'split_markdown_by_heading' strategy"""
        src_file = os.path.join(self.context['src_dir'], self.section['src_file'])
        if not os.path.exists(src_file):
            logger.info(f'File not found: {src_file}, continuing processing...')
            return True
            
        try:
            with open(src_file, 'r', encoding='utf-8') as md_file:
                content = md_file.read()
                
            _, self.context = execute_step(split_markdown_by_heading, content, self.context)
            return True
        except Exception as e:
            logger.error(f'Error processing file: {src_file}, Error: {e}')
            return False

class ProcessDocVersion:
    """Process a specific documentation version"""
    
    def __init__(self, version: str, input_path: str, output_path: str, 
                 rules: dict, registry: WorkflowStepRegistry):
        self.version = version
        self.input_path = input_path
        self.output_path = output_path
        self.rules = rules
        self.registry = registry
    
    def execute(self) -> bool:
        """Process all sections for this documentation version"""
        try:
            version_output_path = os.path.join(self.output_path, self.version)
            if not os.path.exists(version_output_path):
                os.makedirs(version_output_path)
                
            # Create version index file
            index_file = os.path.join(version_output_path, '_index.md')
            
            # Determine version string based on version ID format
            if len(self.version) == 4:
                doc_version = f"{self.version[0]}.{self.version[1]}{self.version[2]}.{self.version[3]}.X"
            elif len(self.version) == 3:
                doc_version = f"{self.version[0]}.{self.version[1]}.{self.version[2]}.X"
            elif len(self.version) == 2:
                doc_version = f"{self.version[0]}.{self.version[1]}.X"
            else:
                doc_version = f"{self.version[0]}.X"
                
            template_values = {
                "title": f"AK {doc_version}",
                "description": f"Documentation for AK {doc_version}",
                "tags": self.rules["front_matter"]["tags"],
                "aliases": "",
                "weight": "",
                "type": "docs",
                "keywords": ""
            }
            
            context = {
                "template_values": template_values,
                "front_matter": self.rules["front_matter"]
            }
            
            front_matter, _ = update_front_matter("", context)
            with open(index_file, 'w') as file:
                file.write(front_matter)
            
            # Process all sections for this version
            src_path = os.path.join(self.input_path, self.version)
            success = True
            
            for weight, section in enumerate(self.rules.get('sections'), start=1):
                context = dict()
                context['output_path'] = version_output_path
                context['front_matter'] = self.rules.get('front_matter')
                context['src_dir'] = src_path
                context['static_dir'] = os.path.join(self.output_path, 'static')
                context['doc_dir'] = self.version
                context['up_level'] = True
                context['remove_numeric'] = True
                context["section"] = section
                context["section_weight"] = weight
                context["link_updates"] = self.rules.get('link_updates')
                
                logger.info(f'Processing section: {section["name"]} in doc directory: {self.version}')
                processor = ProcessDocSection(section, context, self.registry)
                if not processor.execute():
                    success = False
                    logger.error(f"Failed to process section {section['name']} for version {self.version}")
            
            return success
        except Exception as e:
            logger.error(f"Error processing documentation version {self.version}: {str(e)}")
            return False 