#!/usr/bin/env python3

import os
import shutil
import logging
from typing import Dict, Any

from workflow.registry import WorkflowStepRegistry
from utils import execute_step, write_file, update_front_matter, process_markdown_headings, process_markdown_links, split_markdown_by_heading

logger = logging.getLogger('ak2md-workflow.steps.processor-doc-section')

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