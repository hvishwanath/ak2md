#!/usr/bin/env python3

import os
import logging
from typing import Dict, Any

from workflow.registry import WorkflowStepRegistry
from workflow.processors.doc_section import ProcessDocSection
from utils import update_front_matter

logger = logging.getLogger('ak2md-workflow.steps.processor-doc-version')

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