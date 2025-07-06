#!/usr/bin/env python3

import os
import json
import logging
import re
from typing import Dict, Callable, Any, Optional
from datetime import datetime
from workflow.context import WorkflowContext
from bs4 import BeautifulSoup

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

# Processor for committers.html
def process_committers(content: str, output_path: str) -> bool:
    """Process committers.html and create data/committers.json
    
    This function parses the HTML content of committers.html and extracts
    information about each committer, including their image, name, title,
    and social links, and writes it to a JSON file.
    """
    try:
        # Ensure data directory exists
        data_dir = os.path.join(output_path, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        # Use BeautifulSoup to parse the HTML content
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find the table containing committer information
        table = soup.find('table')
        if not table:
            logger.error("Could not find committers table in HTML content")
            return False
        
        # Parse each row (tr) in the table
        committers = []
        for row in table.find_all('tr'):
            # Each row has two committers, with alternating td elements for image and info
            tds = row.find_all('td')
            
            # Process in pairs (image td, info td)
            for i in range(0, len(tds), 2):
                if i + 1 >= len(tds):
                    continue  # Skip if no paired td for info
                
                img_td = tds[i]
                info_td = tds[i + 1]
                
                # Extract image path
                img_tag = img_td.find('img')
                if not img_tag:
                    continue  # Skip if no image found
                
                image_path = img_tag.get('src', '')
                
                # Get all text content and split into lines
                info_text = info_td.get_text().strip()
                lines = [line.strip() for line in info_text.split('\n') if line.strip()]
                
                # The first line is the name
                name = lines[0] if lines else ""
                
                # Find the title, which is usually after the github login
                title = ""
                for j, line in enumerate(lines):
                    # Skip github_login which is in a hidden div
                    if "github_login" in str(info_td):
                        # The title is usually 2 positions after the name
                        if j >= 2 and not any(word in line.lower() for word in ["@", "/in/", "github.com", "hachyderm.io"]):
                            title = line
                            break
                    else:
                        # If no github_login, title is usually right after the name
                        if j >= 1 and not any(word in line.lower() for word in ["@", "/in/", "github.com", "hachyderm.io"]):
                            title = line
                            break
                
                # Initialize social links
                linkedin = None
                twitter = None
                github = None
                website = None
                
                # Extract social links
                for link in info_td.find_all('a'):
                    href = link.get('href', '')
                    link_text = link.get_text().strip()
                    
                    if 'linkedin.com' in href:
                        linkedin = href
                    elif 'twitter.com' in href or link_text.startswith('@'):
                        twitter = href
                    elif 'github.com' in href:
                        github = href
                    elif not any(x in href for x in ['linkedin.com', 'twitter.com', 'github.com']):
                        website = href
                
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
                
                # Add to committers list
                committers.append(committer)
        
        # Write to JSON file
        output_file = os.path.join(data_dir, "committers.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(committers, f, indent=2)
            
        logger.info(f"Created committers.json with {len(committers)} committers")
        return True
    
    except Exception as e:
        logger.error(f"Error processing committers.html: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
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
        blog_dir = os.path.join(output_path, "content", "en", "blog")
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

# Processor for cve-list.md
def process_cve_list(content: str, output_path: str) -> bool:
    """Process cve-list.md with special formatting requirements
    
    This function processes the cve-list.md file with the following changes:
    1. Changes the title to "CVE List"
    2. Bumps down all headings (h1 -> h2, h2 -> h3, etc.)
    3. Outputs to the content/en/community/ directory
    """
    try:
        # Ensure community directory exists
        community_dir = os.path.join(output_path, "content", "en", "community")
        os.makedirs(community_dir, exist_ok=True)
        
        logger.info(f"Processing cve-list.md, content length: {len(content)} characters")
        
        # Update the front matter title
        content = re.sub(
            r'title: Cve List',
            'title: CVE List',
            content
        )
        
        # Bump down all headings (h1 -> h2, h2 -> h3, etc.) and add anchor IDs for CVEs
        # Use regex to find all heading patterns and add one more #
        def bump_heading_level(match):
            level = len(match.group(1))
            new_level = min(6, level + 1)  # Ensure the level doesn't exceed 6
            heading_text = match.group(2)
            
            # Check if this is a CVE heading (contains CVE-XXXX-XXXXX pattern)
            cve_match = re.search(r'CVE-\d{4}-\d+', heading_text)
            if cve_match:
                cve_id = cve_match.group(0)
                # Add anchor ID to the heading
                return '#' * new_level + ' ' + heading_text + ' {#' + cve_id + '}'
            else:
                return '#' * new_level + ' ' + heading_text
        
        # Find all headings and bump them down
        heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        content = heading_pattern.sub(bump_heading_level, content)
        
        # Write to community directory
        output_file = os.path.join(community_dir, "cve-list.md")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
            
        logger.info(f"Successfully processed cve-list.md and saved to {output_file}")
        return True
    
    except Exception as e:
        logger.error(f"Error processing cve-list.md: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# Register processors
register_special_file_processor("committers", process_committers) 
register_special_file_processor("powered-by", process_powered_by)
register_special_file_processor("blog", process_blog)
register_special_file_processor("cve-list", process_cve_list) 