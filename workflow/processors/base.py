#!/usr/bin/env python3

import os
import logging
from typing import List, Dict, Any

from utils import get_title_from_filename, execute_step, write_file

logger = logging.getLogger('ak2md-workflow.steps.processor-base')

class PreProcessFile:
    """Process a single HTML file to Markdown"""
    
    def __init__(self, src_file: str, dest_file: str, static_path: str, hb_context: dict, rules: dict, 
                 steps: List):
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