import os
import re
import json
import difflib
import logging
import subprocess
import shutil
import yaml
import html2text

def execute_step(step, *args):
    try:
        return step(*args)
    except Exception as e:
        logging.error(f'Error executing step {step.__name__}: {e}')
        raise e

class HandleBarsContextBuilder:
    TemplateJS_File = 'templateData.js'
    def _extract_context_from_js(self, file_path):
        context_pattern = re.compile(r'var\s+context\s*=\s*({.*?});', re.DOTALL)
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            match = context_pattern.search(content)
            if match:
                context_str = match.group(1)
                try:
                    context_dict = json.loads(context_str)
                    return context_dict
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON in file {file_path}: {e}")
                    return None
        return None
    
    def _find_templatedata_js_files(self, root_dir):
        logging.debug(f"Searching for {self.TemplateJS_File} files in {root_dir}")
        context_data = {}
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                if filename == self.TemplateJS_File:
                    file_path = os.path.join(dirpath, filename)
                    logging.debug(f"Found {self.TemplateJS_File} file: {file_path}")
                    context_dict = self._extract_context_from_js(file_path)
                    if context_dict:
                        context_data[file_path] = context_dict
        logging.debug(f"Found {len(context_data)} {self.TemplateJS_File} files")
        return context_data

    def __init__(self, root_dir="."):
        self.context_data = self._find_templatedata_js_files(root_dir)
        self.context_dict = {}
        for file_path, context in self.context_data.items():
            self.context_dict[file_path] = context
    
    def __repr__(self):
        return str(self.context_dict)
        
    def get_context(self, file_path):
        close_matches = difflib.get_close_matches(file_path, self.context_dict.keys(), n=1, cutoff=0.4)
        if close_matches:
            return self.context_dict.get(close_matches[0], {})
        return {}

#
# Markdown Processing Functions
#

def process_markdown_headings(content, context):
    """
    Process markdown headings with optional transformations.
    
    Args:
        content: Markdown content (string or list of strings)
        context: Dictionary containing preprocessing options:
            - up_level (bool): If True, bump heading levels up (reduce # count by 1)
            - remove_numeric (bool): If True, remove numeric prefixes from headings
              Removes patterns like: 1., 1:, 1.2., 1.2:, 1.2.3., 1.2.3:, etc.
    
    Returns:
        Tuple of (processed_content, context)
    """
    # if content is not string, convert it to string
    if not isinstance(content, str):
        markdown_content = '\n'.join(content)
    else:
        markdown_content = content

    up_level = context.get('up_level', False)
    remove_numeric = context.get('remove_numeric', False)
    
    logging.debug(f'Processing markdown headings: up_level={up_level}, remove_numeric={remove_numeric}')
    
    def bump_heading_level(match):
        level = len(match.group(1))
        new_level = max(1, level - 1)  # Ensure the level doesn't go below 1
        return '#' * new_level + ' ' + match.group(2)

    def remove_numeric_heading(match):
        heading_text = match.group(2)
        # Remove numeric headings of the form: 1., 1:, 1.2., 1.2:, 1.2.3., 1.2.3:, etc.
        heading_text = re.sub(r'^\d+(\.\d+)*[.:]*\s*', '', heading_text)
        return '#' * len(match.group(1)) + ' ' + heading_text

    # Find all headings
    heading_pattern = re.compile(r'^(#{1,6})\s*(.*)', re.MULTILINE)
    processed_content = markdown_content
    
    if up_level:
        lines = markdown_content.split('\n')
        processed_lines = []
        in_migration_section = False
        
        for line in lines:
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                heading_text = heading_match.group(2).strip()
                heading_level = len(heading_match.group(1))
                
                # Check if we're entering the migration section
                if heading_text == "ZooKeeper to KRaft Migration":
                    in_migration_section = True
                    # Set this heading to h3 level
                    processed_lines.append('### ' + heading_text)
                    continue
                
                # Check if we're exiting the migration section
                # Exit when we encounter Tiered Storage (regardless of heading level or numeric prefix)
                # or when we encounter a true h2 heading (not Tiered Storage)
                if in_migration_section and ("Tiered Storage" in heading_text or (heading_level == 2 and "Tiered Storage" not in heading_text)):
                    in_migration_section = False
                    # Apply normal upleveling for the heading that caused us to exit
                    processed_lines.append(bump_heading_level(heading_match))
                    continue
                
                # If we're in the migration section, don't uplevel subsections - keep them at h4
                if in_migration_section:
                    # Keep subsections at h4 level (don't uplevel them)
                    if heading_level >= 2:  # If it's h2 or higher, set it to h4
                        processed_lines.append('#### ' + heading_text)
                    else:
                        processed_lines.append(line)  # Keep original level if it's already h3 or lower
                else:
                    # Apply normal upleveling for headings outside the migration section
                    processed_lines.append(bump_heading_level(heading_match))
            else:
                processed_lines.append(line)
        
        processed_content = '\n'.join(processed_lines)

    if remove_numeric:
        # Remove numeric headings
        processed_content = heading_pattern.sub(remove_numeric_heading, processed_content)

    return processed_content, context

def _get_front_matter(context, values):
    template = context['front_matter']["template"]
    return template.format(**values)

def update_front_matter(content, context):
    # Remove existing comment and front matter if they exist
    content = re.sub(r'<!--.*?-->\n*', '', content, flags=re.DOTALL)
    content = re.sub(r'^---\n.*?\n---\n*', '', content, flags=re.DOTALL | re.MULTILINE)
    front_matter = _get_front_matter(context, context["template_values"])
    
    return f"{front_matter}\n{content}", context

def sanitize_filename(text):
    """
    Sanitize text to create a valid filename.
    Removes or replaces characters that are problematic for filenames.
    """
    # Remove or replace special characters
    text = text.strip()
    # Remove colons, question marks, quotes, asterisks, pipe, less/greater than
    text = re.sub(r'[:\?\*\|<>\"\']+', '', text)
    # Replace slashes and backslashes with hyphens
    text = re.sub(r'[/\\]+', '-', text)
    # Replace multiple spaces or special chars with single hyphen
    text = re.sub(r'[\s\._,;]+', '-', text)
    # Remove leading/trailing hyphens
    text = text.strip('-')
    # Convert to lowercase
    text = text.lower()
    # Limit length to avoid filesystem issues
    if len(text) > 200:
        text = text[:200].rsplit('-', 1)[0]  # Cut at word boundary
    return text

def sanitize_yaml_title(text):
    """
    Sanitize text to be safe in YAML front matter.
    Removes trailing colons and other problematic characters.
    """
    text = text.strip()
    # Remove trailing punctuation (colons, commas, semicolons) in any combination
    text = re.sub(r'[:;,\s]+$', '', text)
    # Strip again after removing trailing chars
    text = text.strip()
    return text

def split_markdown_by_heading(content, context):
    heading_level = context["section"]["strategy_params"][0]
    heading_pattern = re.compile(rf'^({"#" * heading_level} )(.+)$') 
    lines = content.split('\n')
    out = []
    current_title = None
    counter = 1
    
    def write_to_file(title, content):
        # Sanitize title for YAML front matter
        sanitized_title = sanitize_yaml_title(title)
        # Sanitize for filename
        fn = sanitize_filename(title)
        output_file_name = os.path.join(context["section_dir"], f"{fn}.md")
        out, _= process_markdown_headings(content, context)
        out, _= process_markdown_links(out, context)

        template_values = {
            "title": sanitized_title,
            "description": sanitized_title,
            "tags": context["front_matter"]["tags"], 
            "aliases": "",
            "weight": counter,
            "type": context["section"].get("type", "docs"),
            "keywords": ""
        }
        context["template_values"] = template_values
        out, _ = update_front_matter(out, context)
        # Remove duplicate H1 if it matches the title
        out, _ = remove_duplicate_title_heading(out, context)
        with open(output_file_name, 'w') as file:
            file.writelines(out)

    for line in lines:
        match = heading_pattern.match(line)
        if match:
            heading_text = match.group(2).strip()
            if current_title:
                write_to_file(current_title, out)
                counter += 1
            current_title = heading_text
            out = [line]
        else:
            out.append(line)
    
    if current_title:
        write_to_file(current_title, out) 
    
    return "", context

def remove_duplicate_title_heading(content, context):
    """
    Remove the first H1 or H2 heading if it exactly matches the title in front matter.
    
    This prevents duplicate headings when the Hugo title and first markdown heading are the same.
    Checks both H1 and H2 levels since content may have been upleveled or split.
    
    Args:
        content: Markdown content (string)
        context: Dictionary containing template_values with title
    
    Returns:
        Tuple of (processed_content, context)
    """
    if not isinstance(content, str):
        return content, context
    
    # Get the title from template values
    template_values = context.get('template_values', {})
    title = template_values.get('title', '').strip()
    
    if not title:
        return content, context
    
    # Find the first H1 or H2 heading
    lines = content.split('\n')
    first_heading_index = None
    first_heading_text = None
    heading_level = None
    
    for i, line in enumerate(lines):
        # Check for H1 (single #)
        if line.startswith('# ') and not line.startswith('## '):
            first_heading_text = line[2:].strip()  # Remove '# ' prefix
            first_heading_index = i
            heading_level = 1
            break
        # Check for H2 (double ##)
        elif line.startswith('## ') and not line.startswith('### '):
            first_heading_text = line[3:].strip()  # Remove '## ' prefix
            first_heading_index = i
            heading_level = 2
            break
    
    # If we found a heading and it matches the title, remove it
    if first_heading_index is not None and first_heading_text == title:
        logging.info(f'Removing duplicate H{heading_level} heading: "{title}"')
        # Remove the heading line and any immediately following empty lines
        del lines[first_heading_index]
        # Remove following empty lines (but keep first non-empty)
        while first_heading_index < len(lines) and lines[first_heading_index].strip() == '':
            del lines[first_heading_index]
        content = '\n'.join(lines)
    
    return content, context

def process_markdown_links(content, context):
    link_updates = context.get('link_updates', [])
    # logging.info(f'Processing markdown links: {link_updates}')
    for update in link_updates:
        search_string = update.get('search_str', '')
        action = update.get('action', '')
        value = update.get('value', '')
        content = _update_links_in_markdown(content, search_string, value, action)
    return content, context
        
def _update_links_in_markdown(content, search_string, value, action):
    # Regex to find markdown links
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    def replace_link(match):
        text, url = match.groups()
        if action == 'prefix' and search_string in url and not url.startswith(value):
            url = value + url
        elif action == 'replace' and search_string in url:
            url = value
        elif action == 'substitute':
            url = re.sub(search_string, value, url)
        
        logging.info(f'Updating links in markdown content: {action} {search_string} -> {value}') 
        logging.info(f'[BEFORE] {match.group(0)}')
        logging.info(f'[AFTER] [{text}]({url})')

        return f'[{text}]({url})'

    updated_content = link_pattern.sub(replace_link, content)
    return updated_content

def get_title_from_filename(filename):
    return os.path.splitext(os.path.basename(filename))[0].replace('-', ' ').title()

def write_file(dest_file, markdown_content, context):
    try:
        dest_file = dest_file.replace('.html', '.md')
        with open(dest_file, 'w', encoding='utf-8') as md_file:
            md_file.write(markdown_content)
        logging.info(f'Converted and saved Markdown file: {dest_file}')
    except Exception as e:
        logging.error(f'Error writing file {dest_file}: {e}')
        raise e


def render_handlebars_template(html_content, context):
    logging.debug(f'Rendering Handlebars template with context: {context}')
    from pybars import Compiler
    compiler = Compiler()
    template = compiler.compile(html_content)
    return template(context)

def process_ssi_tags(html_content, context):
    base_dir = context.get('base_dir', '.')
    ssi_pattern = re.compile(r'<!--#include virtual="([^"]+\.html)" -->')
    matches = ssi_pattern.findall(html_content)
    for match in matches:
        include_path = os.path.join(base_dir, match)
        if os.path.exists(include_path):
            with open(include_path, 'r', encoding='utf-8') as include_file:
                include_content = include_file.read()
            html_content = html_content.replace(f'<!--#include virtual="{match}" -->', include_content)
            logging.debug(f'Processed SSI include: {match}')
        else:
            logging.warning(f'Include file not found: {include_path}')
    return html_content, context

def process_ssi_tags_with_hugo(html_content, context):
    ssi_pattern = re.compile(r'<!--#include virtual="([^"]+\.html)" -->')
    matches = ssi_pattern.findall(html_content)
    for match in matches:
        if "generated" in match:
            # {{< include-html file="static/39/generated/kafka_config.html" >}}
            hb_context = context.get('hb', {})
            version = hb_context.get('version', '{}')
            prefix = f"/static/{version}/"
            md_file = f"{prefix}{match}"
        else:
            md_file = match.replace('.html', '.md')
        shortcode = f'{{{{< include-html file="{md_file}" >}}}}'
        html_content = html_content.replace(f'<!--#include virtual="{match}" -->', shortcode)
        logging.debug(f'Replaced SSI with Hugo shortcode: {shortcode}')
    return html_content, context

def convert_youtube_embeds_to_shortcode(html_content, context):
    """
    Convert YouTube video embeds (with onclick loadVideo) to Hugo youtube shortcodes.
    
    Handles two patterns:
    1. Simple onclick="loadVideo()" with separate JavaScript function
    2. onclick="loadVideo('id', 'VIDEO_ID?params', 'class')" inline
    3. Video series with titles in a separate navigation block
    """
    logging.info('Converting YouTube embeds to Hugo shortcodes')
    
    # Pattern 1: Extract video IDs from JavaScript loadVideo functions
    # Matches: iframe.src="https://www.youtube.com/embed/VIDEO_ID?params"
    js_pattern = re.compile(r'iframe\.src\s*=\s*["\']https://www\.youtube\.com/embed/([a-zA-Z0-9_-]+)(\?[^"\']*)?["\']', re.IGNORECASE)
    js_matches = js_pattern.findall(html_content)
    
    # Pattern 2: Extract video IDs from onclick attributes with parameters
    # Matches: onclick="loadVideo('placeholder-id', 'VIDEO_ID?params', 'class')"
    onclick_pattern = re.compile(r'onclick\s*=\s*["\']loadVideo\([^,]*,\s*[\'"]([a-zA-Z0-9_-]+)(\?[^\'"]*)?\s*[\'"]', re.IGNORECASE)
    onclick_matches = onclick_pattern.findall(html_content)
    
    # Collect all video IDs and their class associations
    video_ids = []
    video_classes = {}  # Map class (video_1, video_2) to video ID
    
    for match in js_matches:
        video_ids.append(match[0])
    
    # Extract video IDs with their associated classes
    # Pattern: onclick="loadVideo('placeholder', 'VIDEO_ID?params', 'class')"
    onclick_class_pattern = re.compile(
        r'onclick\s*=\s*["\']loadVideo\([^,]*,\s*[\'"]([a-zA-Z0-9_-]+)(\?[^\'"]*)?[\'"],?\s*[\'"]([^\'"]*)[\'"]\)',
        re.IGNORECASE
    )
    for match in onclick_class_pattern.finditer(html_content):
        video_id = match.group(1)
        class_name = match.group(3)  # Changed from group(2) to group(3) because we added query param group
        video_ids.append(video_id)
        video_classes[class_name] = video_id
        logging.debug(f'Found video ID {video_id} with class {class_name}')
    
    logging.info(f'Found {len(video_ids)} YouTube video(s): {video_ids}')
    
    if not video_ids:
        return html_content, context
    
    # Pattern 3: Extract video titles from navigation list (if exists)
    # Matches: <p class="video__item video_list_1">...<span class="video__text">Title</span>...
    video_titles = {}  # Map video number to title
    title_pattern = re.compile(
        r'<p[^>]*class="[^"]*video__item[^"]*video_list_(\d+)[^"]*"[^>]*>.*?'
        r'<span[^>]*class="video__text"[^>]*>([^<]+)</span>',
        re.IGNORECASE | re.DOTALL
    )
    
    for match in title_pattern.finditer(html_content):
        video_num = match.group(1)
        title = match.group(2).strip()
        video_titles[video_num] = title
        logging.debug(f'Found video title #{video_num}: {title}')
    
    # Check if we have a video series with titles
    has_video_series = len(video_titles) > 0 and len(video_titles) == len(video_ids)
    
    if has_video_series:
        logging.info('Detected video series with navigation - creating structured output')
        
        # Find and replace the entire video grid section
        # Pattern matches from the start of video grid to the end of video list
        grid_pattern = re.compile(
            r'<div[^>]*class="[^"]*video__series__grid[^"]*"[^>]*>.*?</div>\s*</div>\s*</div>',
            re.IGNORECASE | re.DOTALL
        )
        
        # Build the replacement with titles and videos
        replacement_parts = []
        for i, (video_num, title) in enumerate(sorted(video_titles.items()), 1):
            class_key = f'video_{video_num}'
            video_id = video_classes.get(class_key, video_ids[i-1] if i-1 < len(video_ids) else None)
            
            if video_id:
                # Use ":" instead of "." to avoid html2text escaping it as a list marker
                replacement_parts.append(f'\n<h3>{i}: {title}</h3>\n')
                replacement_parts.append(f'<div class="youtube-video">\n{{{{< youtube "{video_id}" >}}}}\n</div>\n')
        
        replacement = '\n'.join(replacement_parts)
        html_content = grid_pattern.sub(replacement, html_content)
        logging.info(f'Replaced video series grid with {len(video_titles)} titled videos')
        
    else:
        # Original behavior: Replace individual img tags
        for video_id in video_ids:
            # First, try to find img with onclick containing this video_id
            img_onclick_pattern = re.compile(
                r'<img[^>]*onclick\s*=\s*["\']loadVideo\([^)]*' + re.escape(video_id) + r'[^)]*\)["\'][^>]*>\s*'
                r'(?:<span[^>]*>\([^)]*YouTube[^)]*\)</span>\s*)?',
                re.IGNORECASE | re.DOTALL
            )
            
            if img_onclick_pattern.search(html_content):
                replacement = f'\n\n<div class="youtube-video">\n{{{{< youtube "{video_id}" >}}}}\n</div>\n\n'
                html_content = img_onclick_pattern.sub(replacement, html_content, count=1)
                logging.debug(f'Replaced YouTube embed with video ID: {video_id}')
                continue
        
        # Handle simple onclick="loadVideo()" without parameters
        simple_onclick_pattern = re.compile(
            r'<img[^>]*id\s*=\s*["\']([^"\']+)["\'][^>]*onclick\s*=\s*["\']loadVideo\(\)["\'][^>]*>\s*'
            r'(?:<span[^>]*>\([^)]*YouTube[^)]*\)</span>\s*)?',
            re.IGNORECASE | re.DOTALL
        )
        
        simple_matches = simple_onclick_pattern.finditer(html_content)
        for i, match in enumerate(simple_matches):
            if i < len(video_ids):
                video_id = video_ids[i]
                replacement = f'\n\n<div class="youtube-video">\n{{{{< youtube "{video_id}" >}}}}\n</div>\n\n'
                html_content = html_content.replace(match.group(0), replacement, 1)
                logging.debug(f'Replaced simple YouTube embed with video ID: {video_id}')
    
    # Clean up any remaining notification spans about YouTube
    notification_pattern = re.compile(
        r'<span[^>]*id\s*=\s*["\']notification["\'][^>]*>.*?YouTube.*?</span>',
        re.IGNORECASE | re.DOTALL
    )
    html_content = notification_pattern.sub('', html_content)
    
    return html_content, context

def convert_html_to_md(html_content, context):
    h = html2text.HTML2Text()
    h.ignore_links = False  # Set to True to ignore links
    h.ignore_images = False  # Set to True to ignore images
    h.ignore_emphasis = False  # Set to True to ignore emphasis (bold, italic)
    h.bypass_tables = False  # Set to True to ignore tables
    h.body_width = 0  # Set to 0 to prevent wrapping
    markdown_content = h.handle(html_content)
    return markdown_content, context

def process_handlebars_templates(html_content, context):
    hb_context = context.get('hb', {})
    logging.debug(f'Processing with Handlebars Context: {hb_context}')
    handlebars_pattern = re.compile(r'<script[^>]*type="text/x-handlebars-template"[^>]*>(.*?)</script>', re.DOTALL)
    matches = handlebars_pattern.findall(html_content)            
    for match in matches:
        logging.debug(f'Found Handlebars template: {match}')
        try:
            rendered_content = render_handlebars_template(match, hb_context)
        except Exception as e:
            if 'bad escape' in str(e):
                logging.debug(f"trying to find template keys")
                # try to manually handle potential template strings
                # construct a regex to match {{x}} kind of strings and collect all the keys
                template_keys = re.findall(r'\{\{([a-zA-Z0-9_]+)\}\}', match)
                # for each key, replace {{key}} with context[key]
                # if key is not found in context, replace with ''
                for key in template_keys:
                    value = hb_context.get(key, '')
                    match = re.sub(r'\{\{' + key + r'\}\}', value, match)
                rendered_content = match
            else:
                raise e
        try:
            html_content = handlebars_pattern.sub(rendered_content, html_content, count=1)
        except Exception as e:
            logging.error(f'Error replacing Handlebars template: {e}')
            logging.error(f'Rendered content: {rendered_content[49280:49300]}')
            logging.error(f'Original HTML : {html_content[49280:49300]}')
            raise e
        
    logging.debug(f'Processed Handlebars template: {html_content}')
    return html_content, context

def add_front_matter(markdown_content, context):
    title = context.get('title', 'Untitled')
    fm_template = """---\ntitle: {title}\ntype: docs\n---\n"""
    markdown_content = f"{fm_template.format(title=title)}\n{markdown_content}"
    return markdown_content, context

def sanitize_input_html(content, context):
    sanitize_list = context.get('rules', {}).get('sanitize_list', [])
    if context.get('src_file_name') not in sanitize_list:
        return content, context
    
    sed_command = r"sed -E 's/([^\\])\\w/\1\\\\w/g; s/([^\\])\\c/\1\\\\c/g; s/([^\\])\\l/\1\\\\l/g; s/([^\\])\\k/\1\\\\k/g; s/([^\\])\\s/\1\\\\s/g'"
    try:
        # Execute the command and capture the output
        result = subprocess.run(sed_command, input=content, text=True, capture_output=True, shell=True, check=True)
        logging.info(f'Sanitized HTML content in file: {context.get("src_file_name")}')
        sanitized_content = result.stdout
        return sanitized_content, context
    except subprocess.CalledProcessError as e:
        logging.error(f"Error occurred: {e}")
        raise e

if __name__=="__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    builder = HandleBarsContextBuilder("../kafka-site/")
    print(builder)
    print(builder.get_context('/Users/hvishwanath/projects/kafka-site/39/design.html'))