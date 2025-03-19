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
    # if content is not string, convert it to string
    if not isinstance(content, str):
        markdown_content = '\n'.join(content)
    else:
        markdown_content = content

    up_level = context.get('up_level', False)
    remove_numeric = context.get('remove_numeric', False)
    
    def bump_heading_level(match):
        level = len(match.group(1))
        new_level = max(1, level - 1)  # Ensure the level doesn't go below 1
        return '#' * new_level + ' ' + match.group(2)

    def remove_numeric_heading(match):
        heading_text = match.group(2)
        # Remove numeric headings of the form a., a.b, or a.b.c
        heading_text = re.sub(r'^\d+(\.\d+)*\.*\s*', '', heading_text)
        return match.group(1) + ' ' + heading_text

    # Find all headings
    heading_pattern = re.compile(r'^(#{1,6})\s*(.*)', re.MULTILINE)
    processed_content = markdown_content

    if up_level:
        # Bump up heading levels
        processed_content = heading_pattern.sub(bump_heading_level, processed_content)

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

def split_markdown_by_heading(content, context):
    heading_level = context["section"]["strategy_params"][0]
    heading_pattern = re.compile(rf'^({"#" * heading_level} )(.+)$') 
    lines = content.split('\n')
    out = []
    current_title = None
    counter = 1
    
    def write_to_file(title, content):
        fn = title.strip().lower().replace(' ', '-')
        output_file_name = os.path.join(context["section_dir"], f"{fn}.md")
        out, _= process_markdown_headings(content, context)
        out, _= process_markdown_links(out, context)

        template_values = {
            "title": title,
            "description": title,
            "tags": context["front_matter"]["tags"], 
            "aliases": "",
            "weight": counter,
            "type": context["section"].get("type", "docs"),
            "keywords": ""
        }
        context["template_values"] = template_values
        out, _ = update_front_matter(out, context)
        with open(output_file_name, 'w') as file:
            file.writelines(out)

    for line in lines:
        match = heading_pattern.match(line)
        if match:
            if current_title:
                write_to_file(current_title, out)
                counter += 1
            current_title = match.group(2)
            out = [line]
        else:
            out.append(line)
    
    if current_title:
        write_to_file(current_title, out) 
    
    return "", context

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