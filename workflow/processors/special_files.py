#!/usr/bin/env python3

import os
import json
import logging
import re
from typing import Dict, Callable, Any, Optional
from datetime import datetime
from workflow.context import WorkflowContext

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

# Processor for blog.md
def process_blog(content: str, output_path: str) -> bool:
    """Process blog.md to extract individual blog posts.
    
    Creates:
    - blog/_index.md
    - blog/releases/_index.md
    - blog/releases/ak-{version}.md for each release announcement
    """
    try:
        # Create necessary directories
        blog_dir = os.path.join(output_path, "blog")
        releases_dir = os.path.join(blog_dir, "releases")
        os.makedirs(blog_dir, exist_ok=True)
        os.makedirs(releases_dir, exist_ok=True)
        
        # Write blog/_index.md
        blog_index_content = """---
title: "Blog"
linkTitle: "Blog"
weight: 40
menu:
  main:
    weight: 40
---
"""
        with open(os.path.join(blog_dir, "_index.md"), 'w', encoding='utf-8') as f:
            f.write(blog_index_content)
        
        # Write blog/releases/_index.md
        releases_index_content = """---
title: "Release Announcements"
linkTitle: "Release Announcements"
weight: 10
menu:
  main:
    weight: 10
---
"""
        with open(os.path.join(releases_dir, "_index.md"), 'w', encoding='utf-8') as f:
            f.write(releases_index_content)
        
        # Split content into individual posts (split at level 1 headings)
        posts = re.split(r'(?m)^# ', content)[1:]  # Skip the first empty split
        
        for post in posts:
            # Extract version from title
            title_match = re.match(r'^([^\n]+)', post)
            if not title_match:
                continue
                
            title = title_match.group(1)
            version_match = re.search(r'(\d+\.\d+\.\d+)', title)
            if not version_match:
                continue
                
            version = version_match.group(1)
            
            # Extract author and date from first line of content
            content_lines = post.split('\n')
            if len(content_lines) < 2:
                continue
                
            # Remove the duplicate title line (first line after the heading)
            content_lines = [line for line in content_lines[1:] if line.strip() != title]
            
            # Find the first non-empty line that contains date and author
            date_line = None
            for line in content_lines:  # No need to skip title line anymore
                if line.strip():  # Non-empty line
                    date_line = line.strip()
                    break
            
            if not date_line:
                formatted_date = '2025-03-18'  # Fallback date
                author = 'Apache Kafka Team'  # Fallback author
                logger.warning(f"Could not find date line for version {version}")
            else:
                # Extract date and author using regex
                date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', date_line)
                
                # Try different author formats:
                # 1. Name (@handle) with Twitter
                # 2. Name ([@handle](https://twitter.com/handle))
                # 3. Name ([@handle](https://www.linkedin.com/in/handle/))
                # 4. Just Name
                author_match = (
                    re.search(r'-\s*([^(]+?)\s*\(@([^)]+)\)', date_line) or  # Format 1
                    re.search(r'-\s*([^(]+?)\s*\(\[@([^]]+)\]', date_line) or  # Format 2
                    re.search(r'-\s*([^(]+)', date_line)  # Format 4 (fallback)
                )
                
                if date_match and author_match:
                    date_str = date_match.group(1)
                    
                    # Format author name based on what we found
                    if len(author_match.groups()) > 1:  # We have a handle
                        author = f"{author_match.group(1).strip()} (@{author_match.group(2)})"
                    else:  # Just the name
                        author = author_match.group(1).strip()
                    
                    # Convert date to YYYY-MM-DD format
                    try:
                        date = datetime.strptime(date_str, '%d %B %Y')
                        formatted_date = date.strftime('%Y-%m-%d')
                    except ValueError:
                        try:
                            # Try alternate format (e.g., "10 Oct 2023")
                            date = datetime.strptime(date_str, '%d %b %Y')
                            formatted_date = date.strftime('%Y-%m-%d')
                        except ValueError:
                            formatted_date = '2025-03-18'  # Fallback date if parsing fails
                            logger.warning(f"Could not parse date '{date_str}' for version {version}, using fallback date")
                    
                    # Remove the date line from content
                    content_lines = [line for line in content_lines if line.strip() != date_line]
                else:
                    formatted_date = '2025-03-18'  # Fallback date
                    author = 'Apache Kafka Team'  # Fallback author
                    logger.warning(f"Could not extract date and author from line for version {version}, line: '{date_line}'")
            
            # Create front matter
            front_matter = {
                'date': formatted_date,
                'title': title,
                'linkTitle': f'AK {version}',
                'author': author
            }
            
            # Convert level 1 headings to level 2
            content = '\n'.join(content_lines)
            content = re.sub(r'^# ', '## ', content, flags=re.MULTILINE)
            
            # Write the blog post
            post_file = os.path.join(releases_dir, f'ak-{version}.md')
            with open(post_file, 'w', encoding='utf-8') as f:
                f.write(f"""---
date: {front_matter['date']}
title: {front_matter['title']}
linkTitle: {front_matter['linkTitle']}
author: {front_matter['author']}
---

{content}
""")
            logger.info(f"Created blog post: ak-{version}.md")
            
        return True
        
    except Exception as e:
        logger.error(f"Error processing blog.md: {str(e)}")
        return False

# Register processors
register_special_file_processor("committers", process_committers) 
register_special_file_processor("powered-by", process_powered_by)
register_special_file_processor("blog", process_blog) 