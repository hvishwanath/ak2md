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
            
            # Sanitize HTML in descriptions to fix malformed attributes
            fixed_count = 0
            for item in data:
                if 'description' in item and item['description']:
                    original = item['description']
                    # Fix: <a href='...' , target='_blank'> → <a href='...' target='_blank'>
                    # Remove comma before target, _blank, or other common attributes
                    sanitized = re.sub(r'([\'"])\s*,\s*(target|rel|class|id|style)\s*=', r'\1 \2=', original)
                    if sanitized != original:
                        item['description'] = sanitized
                        fixed_count += 1
                        logger.debug(f"Fixed malformed HTML attribute in: {item.get('link', 'unknown')}")
            
            if fixed_count > 0:
                logger.info(f"Sanitized {fixed_count} testimonial descriptions with malformed HTML attributes")
            
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

# Processor for streams/introduction.md
def process_streams_introduction(content: str, output_path: str) -> bool:
    """Process streams/introduction.md to enhance with carousel, cards, and tabbed code
    
    This function:
    1. Converts YouTube video shortcodes to a carousel presentation
    2. Extracts Kafka Streams use cases and renders them as cards
    3. Converts Java/Scala code blocks to tabbed panes
    4. Removes redundant links
    """
    try:
        import re
        import json
        from pathlib import Path
        
        logger.info("Processing streams/introduction.md for enhancements")
        
        # Load testimonials data
        testimonials_file = Path(output_path) / "data" / "testimonials.json"
        testimonials_data = []
        if testimonials_file.exists():
            with open(testimonials_file, 'r', encoding='utf-8') as f:
                testimonials_data = json.load(f)
            logger.info(f"Loaded {len(testimonials_data)} testimonials from data file")
        else:
            logger.warning(f"Testimonials file not found at {testimonials_file}")
        
        # Step 1: Transform YouTube videos to carousel
        content = _transform_youtube_to_carousel(content)
        
        # Step 2: Transform Kafka Streams use cases to cards
        content = _transform_use_cases_to_cards(content, testimonials_data)
        
        # Step 3: Transform Java/Scala code to tabbed panes
        content = _transform_code_to_tabs(content)
        
        # Step 4: Remove redundant links
        content = _remove_redundant_links(content)
        
        # Write back the modified content
        # The file path is passed as file_name in the ProcessSpecialFiles call
        # We need to extract the actual file path from the input
        return content
        
    except Exception as e:
        logger.error(f"Error processing streams introduction: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def _transform_youtube_to_carousel(content: str) -> str:
    """Transform YouTube shortcodes into a carousel presentation with titles
    
    Uses custom carousel/carousel-item shortcodes for a slideshow experience.
    """
    import re
    
    logger.info("Transforming YouTube videos to carousel")
    
    # Pattern to match sections with YouTube videos and their headings
    # Looking for: ## Heading\n\n{{< youtube "ID" >}}
    video_pattern = re.compile(
        r'##\s+([^\n]+)\n\s*\n\s*\{\{<\s*youtube\s+"([^"]+)"\s*>\}\}',
        re.MULTILINE
    )
    
    videos = []
    for match in video_pattern.finditer(content):
        title = match.group(1).strip()
        video_id = match.group(2).strip()
        videos.append({
            'title': title,
            'video_id': video_id,
            'full_match': match.group(0)
        })
    
    if not videos:
        logger.warning("No YouTube videos found in expected format")
        return content
    
    logger.info(f"Found {len(videos)} YouTube videos to convert")
    
    # Find the position to insert the carousel (after the intro paragraph)
    # Look for the "## Intro to Streams" or first video section
    first_video_section = videos[0]['full_match'] if videos else None
    
    if first_video_section:
        # Build carousel HTML
        carousel_html = _build_video_carousel(videos)
        
        # Replace all video sections with the carousel
        # First, remove all individual video sections
        for video in videos:
            content = content.replace(video['full_match'], '', 1)
        
        # Insert carousel before the "* * *" separator or after intro text
        separator_pattern = r'\n\*\s+\*\s+\*\s*\n'
        separator_match = re.search(separator_pattern, content)
        
        if separator_match:
            # Insert before the separator
            insert_pos = separator_match.start()
            content = content[:insert_pos] + '\n\n' + carousel_html + '\n\n' + content[insert_pos:]
        else:
            # Insert after the intro paragraph (after first heading)
            intro_end = content.find('\n\n', content.find('# Kafka Streams'))
            if intro_end > 0:
                content = content[:intro_end] + '\n\n' + carousel_html + '\n\n' + content[intro_end:]
    
    return content

def _build_video_carousel(videos: list) -> str:
    """Build HTML for video carousel using custom carousel shortcode
    
    Uses carousel/carousel-item shortcodes for a slideshow experience.
    The first item is marked as active for Bootstrap carousel.
    """
    
    # Create carousel structure
    carousel_parts = ['## Tour of the Streams API\n\n']
    
    # Build carousel container
    carousel_parts.append('{{< carousel >}}\n')
    
    for i, video in enumerate(videos):
        # First item needs to be active for Bootstrap carousel
        active_attr = ' active="true"' if i == 0 else ''
        # Number the video titles (1. Intro to Streams, 2. Creating...)
        numbered_title = f"{i + 1}. {video['title']}"
        carousel_parts.append(f'{{{{< carousel-item title="{numbered_title}"{active_attr} >}}}}\n')
        # Use {{% %}} for nested shortcodes so Hugo processes them properly
        carousel_parts.append(f'{{{{% youtube "{video["video_id"]}" %}}}}\n')
        carousel_parts.append('{{< /carousel-item >}}\n')
    
    carousel_parts.append('{{< /carousel >}}\n')
    
    return ''.join(carousel_parts)

def _transform_use_cases_to_cards(content: str, testimonials_data: list) -> str:
    """Transform Kafka Streams use cases section to custom shortcode"""
    import re
    
    logger.info("Transforming Kafka Streams use cases to custom shortcode")
    
    # Find the "Kafka Streams use cases" section
    use_cases_pattern = re.compile(
        r'(##\s+Kafka\s+Streams\s+use\s+cases\s*\n)(.*?)(?=\n##|\Z)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    
    match = use_cases_pattern.search(content)
    if not match:
        logger.warning("Kafka Streams use cases section not found")
        return content
    
    # Replace the entire section content with the custom shortcode
    # Keep the heading, replace everything else with the shortcode
    replacement = match.group(1) + '\n{{< about/kstreams-users >}}\n\n'
    
    # Replace in content
    content = content[:match.start()] + replacement + content[match.end():]
    
    logger.info("Replaced use cases section with {{< about/kstreams-users >}} shortcode")
    
    return content

def _transform_code_to_tabs(content: str) -> str:
    """Transform Java and Scala code blocks to tabbed panes with proper dedenting"""
    import re
    
    logger.info("Transforming code blocks to tabbed panes")
    
    # Find the "Hello Kafka Streams" section
    hello_section_pattern = re.compile(
        r'##\s+Hello\s+Kafka\s+Streams\s*\n+(.*?)(?=\n##|\Z)',
        re.MULTILINE | re.DOTALL
    )
    
    match = hello_section_pattern.search(content)
    if not match:
        logger.warning("Hello Kafka Streams code section not found")
        return content
    
    section_content = match.group(1)
    
    # Check if code is already in tabpanes - if so, extract and reprocess
    if '{{< tabpane >}}' in section_content or '{{% tabpane %}}' in section_content:
        return _reprocess_existing_tabpanes(content, match, section_content)
    
    # Otherwise, process from "Java Scala" labeled code or markdown blocks
    return _process_raw_code_blocks(content, match, section_content)

def _reprocess_existing_tabpanes(content: str, hello_match, section_content: str) -> str:
    """Extract code from existing tabpanes, dedent properly, and rebuild"""
    import re
    
    logger.info("Reprocessing existing tabpanes with proper dedenting")
    
    # Extract tabs with their headers and code
    # Pattern: {{% tab header="Java" %}} or {{< tab header="Java" >}}
    tab_pattern = re.compile(
        r'\{{[%<]\s*tab\s+header="([^"]+)"\s*[%>]\}}\s*```(\w+)?\s*\n(.*?)```\s*\{{[%<]\s*/tab\s*[%>]\}}',
        re.DOTALL
    )
    
    tabs = []
    for match in tab_pattern.finditer(section_content):
        language_label = match.group(1)  # e.g., "Java", "Java 8+", "Scala"
        code_lang = match.group(2) if match.group(2) else "java"  # e.g., "java", "scala"
        code = match.group(3)
        
        # Dedent the code properly
        dedented_code = _dedent_code_simple(code)
        
        tabs.append({
            'label': language_label,
            'lang': code_lang.lower(),
            'code': dedented_code
        })
    
    if not tabs:
        logger.warning("No tabs found in existing tabpane")
        return content
    
    logger.info(f"Found {len(tabs)} tabs to reprocess: {[t['label'] for t in tabs]}")
    
    # Rebuild tabpanes with dedented code
    tabbed_code = _build_tabbed_code_from_tabs(tabs)
    
    # Find intro text before tabpane
    intro_match = re.search(r'(.*?)\{{[%<]\s*tabpane\s*[%>]\}}', section_content, re.DOTALL)
    intro_text = intro_match.group(1).strip() if intro_match else ""
    
    # Replace the section
    replacement = intro_text + '\n\n' + tabbed_code if intro_text else tabbed_code
    
    match_start = hello_match.start()
    match_end = hello_match.end()
    content = content[:match_start] + '## Hello Kafka Streams\n\n' + replacement + '\n' + content[match_end:]
    
    return content

def _process_raw_code_blocks(content: str, hello_match, section_content: str) -> str:
    """Process code from 'Java Scala' labeled blocks or markdown code fences"""
    import re
    
    # First try to find markdown code blocks
    code_block_pattern = re.compile(r'```(?:java|scala)?\n(.*?)```', re.DOTALL)
    code_blocks = code_block_pattern.findall(section_content)
    
    if len(code_blocks) >= 2:
        # Markdown code blocks found - extract language labels from preceding text
        # Look for "Java Scala" or "Java 8+ Scala" type labels
        label_match = re.search(r'(Java[^`\n]*?)\s+(Scala[^`\n]*?)\s*\n', section_content)
        java_label = label_match.group(1).strip() if label_match else "Java"
        scala_label = label_match.group(2).strip() if label_match else "Scala"
        
        java_code = code_blocks[0].strip()
        scala_code = code_blocks[1].strip()
        
        # Create tabs structure
        tabs = [
            {'label': java_label, 'lang': 'java', 'code': java_code},
            {'label': scala_label, 'lang': 'scala', 'code': scala_code}
        ]
        
        logger.info(f"Found markdown code blocks with labels: {java_label}, {scala_label}")
        
        # Build tabbed pane
        tabbed_code = _build_tabbed_code_from_tabs(tabs)
        
        # Find intro text
        intro_match = re.search(r'(.*?)(?:Java|```)', section_content, re.DOTALL)
        intro_text = intro_match.group(1).strip() if intro_match else ""
        
        # Replace the section
        replacement = intro_text + '\n\n' + tabbed_code if intro_text else tabbed_code
        match_start = hello_match.start()
        match_end = hello_match.end()
        return content[:match_start] + '## Hello Kafka Streams\n\n' + replacement + '\n' + content[match_end:]
    
    # Try "Java Scala" labeled indented code
    java_scala_match = re.search(r'(Java[^`\n]*?)\s+(Scala[^`\n]*?)\s*\n', section_content)
    
    if not java_scala_match:
        logger.warning("Expected code blocks not found in any recognized format")
        return content
    
    # Extract language labels
    java_label = java_scala_match.group(1).strip()
    scala_label = java_scala_match.group(2).strip()
    
    logger.info(f"Found labeled code blocks: {java_label}, {scala_label}")
    
    # Extract everything after "Java Scala" label
    code_start = java_scala_match.end()
    all_code = section_content[code_start:]
    
    # Stop at navigation links (Previous/Next) or other non-code content
    nav_match = re.search(r'\n\s*\[Previous\]|\n\s*\* \* \*|\n\s*\*\s+\[', all_code)
    if nav_match:
        all_code = all_code[:nav_match.start()]
    
    all_code = all_code.strip()
    
    # Split by looking for Scala imports
    scala_patterns = [
        r'\n\s*import java\.util\.Properties\n\s*import java\.util\.concurrent',
        r'\n\s*import org\.apache\.kafka\.streams\.scala',
        r'\n\s*object \w+.*extends App'
    ]
    
    scala_start_pos = None
    for pattern in scala_patterns:
        scala_match = re.search(pattern, all_code)
        if scala_match:
            scala_start_pos = scala_match.start() + 1
            break
    
    if not scala_start_pos:
        logger.warning("Could not identify Scala code start position")
        return content
    
    java_code = all_code[:scala_start_pos - 1].rstrip()
    scala_code = all_code[scala_start_pos:].rstrip()
    
    # Dedent the code
    java_code = _dedent_code_simple(java_code)
    scala_code = _dedent_code_simple(scala_code)
    
    # Create tabs structure
    tabs = [
        {'label': java_label, 'lang': 'java', 'code': java_code},
        {'label': scala_label, 'lang': 'scala', 'code': scala_code}
    ]
    
    # Build tabbed pane
    tabbed_code = _build_tabbed_code_from_tabs(tabs)
    
    # Find intro text
    intro_match = re.search(r'(.*?)Java', section_content, re.DOTALL)
    intro_text = intro_match.group(1).strip() if intro_match else ""
    
    # Replace the section
    replacement = intro_text + '\n\n' + tabbed_code if intro_text else tabbed_code
    match_start = hello_match.start()
    match_end = hello_match.end()
    return content[:match_start] + '## Hello Kafka Streams\n\n' + replacement + '\n' + content[match_end:]

def _dedent_code_simple(code_text: str) -> str:
    """Remove 4 spaces from the beginning of each line"""
    lines = code_text.split('\n')
    result = []
    for line in lines:
        if line.startswith('    '):  # 4 spaces
            result.append(line[4:])
        else:
            result.append(line)
    return '\n'.join(result).strip()  # strip() to remove leading/trailing empty lines

def _build_tabbed_code_from_tabs(tabs: list) -> str:
    """Build Hugo Docsy tabbed pane from tabs structure"""
    parts = []
    parts.append('{{< tabpane >}}\n')
    
    for tab in tabs:
        parts.append(f'{{{{% tab header="{tab["label"]}" %}}}}\n')
        parts.append(f'```{tab["lang"]}\n')
        parts.append(tab['code'])
        parts.append('\n```\n')
        parts.append('{{% /tab %}}\n')
    
    parts.append('{{< /tabpane >}}\n')
    return ''.join(parts)

def _build_tabbed_code(java_code: str, scala_code: str) -> str:
    """Build Hugo Docsy tabbed pane for code (deprecated - use _build_tabbed_code_from_tabs)"""
    tabs = [
        {'label': 'Java', 'lang': 'java', 'code': java_code},
        {'label': 'Scala', 'lang': 'scala', 'code': scala_code}
    ]
    return _build_tabbed_code_from_tabs(tabs)

def _remove_redundant_links(content: str) -> str:
    """Remove redundant navigation links (Previous/Next, Documentation, Kafka Streams)"""
    import re
    
    logger.info("Removing redundant links")
    
    # Pattern 1: Remove Previous/Next navigation links
    # Looking for: [Previous](/path) [Next](/path)
    prev_next_pattern = re.compile(
        r'\n\s*\[Previous\]\([^)]+\)\s*\[Next\]\([^)]+\)\s*\n?',
        re.MULTILINE
    )
    content = prev_next_pattern.sub('\n', content)
    
    # Pattern 2: Remove the redundant Documentation/Kafka Streams links at the end
    # Looking for: * [Documentation](/documentation)\n* [Kafka Streams](/streams)
    redundant_links_pattern = re.compile(
        r'\n\s*\*\s+\[Documentation\]\([^)]+\)\s*\n\s*\*\s+\[Kafka\s+Streams\]\([^)]+\)\s*\n?',
        re.MULTILINE | re.IGNORECASE
    )
    content = redundant_links_pattern.sub('\n', content)
    
    return content

# Register processors
register_special_file_processor("committers", process_committers) 
register_special_file_processor("powered-by", process_powered_by)
register_special_file_processor("blog", process_blog)
register_special_file_processor("cve-list", process_cve_list)
# Disabled: streams/introduction.md is now handled by StreamsEnhancementStage
# register_special_file_processor("streams-introduction", process_streams_introduction)

def _remove_redundant_links(content: str) -> str:
    """Remove redundant navigation links (Previous/Next, Documentation, Kafka Streams)"""
    import re
    
    logger.info("Removing redundant links")
    
    # Pattern 1: Remove Previous/Next navigation links
    # Looking for: [Previous](/path) [Next](/path)
    prev_next_pattern = re.compile(
        r'\n\s*\[Previous\]\([^)]+\)\s*\[Next\]\([^)]+\)\s*\n?',
        re.MULTILINE
    )
    content = prev_next_pattern.sub('\n', content)
    
    # Pattern 2: Remove the redundant Documentation/Kafka Streams links at the end
    # Looking for: * [Documentation](/documentation)\n* [Kafka Streams](/streams)
    redundant_links_pattern = re.compile(
        r'\n\s*\*\s+\[Documentation\]\([^)]+\)\s*\n\s*\*\s+\[Kafka\s+Streams\]\([^)]+\)\s*\n?',
        re.MULTILINE | re.IGNORECASE
    )
    content = redundant_links_pattern.sub('\n', content)
    
    return content

# Register processors
register_special_file_processor("committers", process_committers) 
register_special_file_processor("powered-by", process_powered_by)
register_special_file_processor("blog", process_blog)
register_special_file_processor("cve-list", process_cve_list)
# Disabled: streams/introduction.md is now handled by StreamsEnhancementStage
# register_special_file_processor("streams-introduction", process_streams_introduction) 