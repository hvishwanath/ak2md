#!/usr/bin/env python3

import os
import json
import logging
import re
from typing import Dict, Callable, Any, Optional

logger = logging.getLogger('ak2md-workflow.steps.special-files')

# Registry for special file processors
special_file_processors = {}

def register_special_file_processor(name: str, processor_func: Callable):
    """Register a processor for special files"""
    special_file_processors[name] = processor_func
    logger.debug(f"Registered special file processor: {name}")

class ProcessSpecialFiles:
    """Process special files with custom logic and output to specified format"""
    
    def __init__(self, file_name: str, input_path: str, output_path: str, processor_name: str, 
                 registry: Optional[Dict[str, Callable]] = None):
        self.file_name = file_name
        self.input_path = input_path
        self.output_path = output_path
        self.processor_name = processor_name
        self.registry = registry or {}
        self.logger = logging.getLogger('ak2md-workflow.steps.process-special-files')
    
    def execute(self) -> bool:
        """Execute the special file processing"""
        try:
            input_file = os.path.join(self.input_path, self.file_name)
            if not os.path.exists(input_file):
                self.logger.warning(f"Special file not found: {input_file}")
                return True  # Not a failure, file might be optional
            
            processor = self.registry.get(self.processor_name)
            if not processor:
                self.logger.error(f"No processor found for: {self.processor_name}")
                return False
            
            self.logger.info(f"Processing special file {self.file_name} with {self.processor_name}")
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            result = processor(content, self.output_path)
            
            if not result:
                self.logger.error(f"Failed to process special file: {self.file_name}")
                return False
                
            self.logger.info(f"Successfully processed special file: {self.file_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error processing special file {self.file_name}: {str(e)}")
            return False

# Processor for committers.md
def process_committers(content: str, output_path: str) -> bool:
    """Process committers.md and create data/committers.json"""
    try:
        # Ensure data directory exists
        data_dir = os.path.join(output_path, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        # Parse the markdown content
        committers = []
        lines = content.split('\n')
        
        # Skip front matter and heading
        start_idx = 0
        for i, line in enumerate(lines):
            if line.strip() == '# The committers':
                start_idx = i + 1
                break
        
        # Process in pairs (image/info rows)
        i = start_idx
        while i < len(lines) - 1:
            line = lines[i].strip()
            if not line or line == '---|---|---|---':
                i += 1
                continue
                
            # Check if this is an image row
            if line.startswith('![]('):
                # Extract image path
                image_match = line.split('|')[0].strip()
                image_path = image_match.replace('![](', '').replace(')', '')
                
                # Extract name from next part
                name_part = line.split('|')[1].strip()
                name = name_part
                
                # Username and title are on the next lines
                username = lines[i+1].strip()
                title = lines[i+2].strip()
                
                # Check for social links
                linkedin = None
                twitter = None
                github = None
                website = None
                mastodon = None
                
                # Process next lines for links
                j = i + 3
                while j < len(lines) and not lines[j].strip().startswith('![]('):
                    link_line = lines[j].strip()
                    if '[/in/' in link_line:
                        linkedin = link_line.split('](')[1].split(')')[0]
                    elif '[@' in link_line and 'hachyderm.io' in link_line:
                        mastodon = link_line.split('](')[1].split(')')[0]
                    elif '[@' in link_line:
                        twitter = link_line.split('](')[1].split(')')[0]
                    elif '[github.com/' in link_line:
                        github = link_line.split('](')[1].split(')')[0]
                    elif '[' in link_line and '](' in link_line and not any(x in link_line for x in ['@', '/in/', 'github']):
                        website = link_line.split('](')[1].split(')')[0]
                    j += 1
                    
                    # If we hit a table separator or empty line, move to next row
                    if link_line == '---|---|---|---' or link_line == '':
                        break
                
                # Create committer object
                committer = {
                    "image": f"/{image_path}",
                    "name": name,
                    "title": title,
                    "linkedIn": linkedin,
                    "twitter": twitter
                }
                
                # Add optional fields if they exist
                if github:
                    committer["github"] = github
                if website:
                    committer["website"] = website
                if mastodon:
                    committer["mastodon"] = mastodon
                
                committers.append(committer)
                
                # Move to next row
                i = j
            else:
                i += 1
        
        # Write to JSON file
        output_file = os.path.join(data_dir, "committers.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(committers, f, indent=2)
            
        logger.info(f"Created committers.json with {len(committers)} committers")
        return True
    
    except Exception as e:
        logger.error(f"Error processing committers.md: {str(e)}")
        return False

# Processor for powered-by.html
def process_powered_by(content: str, output_path: str) -> bool:
    """Process powered-by.html and create data/testimonials.json"""
    try:
        # Ensure data directory exists
        data_dir = os.path.join(output_path, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        logger.info(f"Processing powered-by.html, content length: {len(content)} characters")
        
        # Extract JSON array from the script tag using a more robust pattern
        script_start = content.find('<script>')
        script_end = content.find('</script>', script_start)
        
        if script_start == -1 or script_end == -1:
            logger.error("Could not find script tags in powered-by.html")
            return False
            
        script_content = content[script_start:script_end]
        
        # Find the poweredByItems array
        array_start = script_content.find('var poweredByItems = [')
        if array_start == -1:
            logger.error("Could not find poweredByItems array declaration")
            return False
            
        # Find the closing bracket of the array
        array_start = script_content.find('[', array_start)
        bracket_count = 1
        array_end = array_start + 1
        
        while bracket_count > 0 and array_end < len(script_content):
            if script_content[array_end] == '[':
                bracket_count += 1
            elif script_content[array_end] == ']':
                bracket_count -= 1
            array_end += 1
            
        if bracket_count != 0:
            logger.error("Could not find matching closing bracket for the array")
            return False
            
        json_array_str = script_content[array_start:array_end]
        
        logger.info(f"Extracted JSON array with length: {len(json_array_str)} characters")
        
        # Attempt to parse and format the JSON to ensure it's valid
        try:
            # Parse the JSON array
            data = json.loads(json_array_str)
            
            # Write to JSON file with proper formatting
            output_file = os.path.join(data_dir, "testimonials.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Created testimonials.json with {len(data)} testimonials")
        except json.JSONDecodeError:
            logger.warning("Could not parse JSON, writing raw content")
            # If parsing fails, just write the raw string
            output_file = os.path.join(data_dir, "testimonials.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(json_array_str)
            logger.info(f"Created testimonials.json with raw data")
            
        return True
    
    except Exception as e:
        logger.error(f"Error processing powered-by.html: {str(e)}")
        return False

# Register processors
register_special_file_processor("committers", process_committers)
register_special_file_processor("powered-by", process_powered_by) 