#!/usr/bin/env python3

import os
import shutil
import logging

from workflow.registry import WorkflowStepRegistry
from workflow.processors.base import PreProcessFile
from utils import HandleBarsContextBuilder

logger = logging.getLogger('ak2md-workflow.steps.processor-directory')

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