import os
import html2text
import shutil
import re
import logging
import subprocess

from pybars import Compiler
from utils import HandleBarsContextBuilder, execute_step


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s -  %(funcName)s - %(lineno)d - %(levelname)s - %(message)s')

exclude_dirs = ['markdown', '.git', 'node_modules', '.history', 'javadoc', 'generated', 'images']

# Function to capitalize the filename and use it as the title
def get_title_from_filename(filename):
    return os.path.splitext(os.path.basename(filename))[0].replace('-', ' ').title()

# Function to update the front matter of a Markdown file
def update_front_matter(filepath):
    title = get_title_from_filename(filepath)
    front_matter = Constants.Front_Matter_Template.format(title=title)
    
    with open(filepath, 'r') as file:
        content = file.read()
    
    # Remove existing comment and front matter if they exist
    content = re.sub(r'<!--.*?-->\n*', '', content, flags=re.DOTALL)
    content = re.sub(r'^---\n.*?\n---\n*', '', content, flags=re.DOTALL | re.MULTILINE)
    
    # Write the new comment and front matter
    with open(filepath, 'w') as file:
        file.write(f"{front_matter}\n{content}")

def render_handlebars_template(html_content, context):
    logging.debug(f'Rendering Handlebars template with context: {context}')
    compiler = Compiler()
    template = compiler.compile(html_content)
    return template(context), context

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
        md_file = match.replace('.html', '.md')
        shortcode = f'{{{{< include file="{md_file}" >}}}}'
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

    logging.debug(f'Processing with Context: {context}')
    handlebars_pattern = re.compile(r'<script[^>]*type="text/x-handlebars-template"[^>]*>(.*?)</script>', re.DOTALL)
    matches = handlebars_pattern.findall(html_content)            
    for match in matches:
        logging.debug(f'Found Handlebars template: {match}')
        try:
            rendered_content, context = render_handlebars_template(match, context)
        except Exception as e:
            if 'bad escape' in str(e):
                logging.debug(f"trying to find template keys")
                # try to manually handle potential template strings
                # construct a regex to match {{x}} kind of strings and collect all the keys
                template_keys = re.findall(r'\{\{([a-zA-Z0-9_]+)\}\}', match)
                # for each key, replace {{key}} with context[key]
                # if key is not found in context, replace with ''
                for key in template_keys:
                    value = context.get(key, '')
                    match = re.sub(r'\{\{' + key + r'\}\}', value, match)
                rendered_content = match
            else:
                raise e
        # logging.info(f'Rendered Handlebars template: {rendered_content}')
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

def write_file(dest_file, markdown_content, context):
    try:
        dest_file = dest_file.replace('.html', '.md')
        with open(dest_file, 'w', encoding='utf-8') as md_file:
            md_file.write(markdown_content)
        logging.info(f'Converted and saved Markdown file: {dest_file}')
    except Exception as e:
        logging.error(f'Error writing file {dest_file}: {e}')
        raise e
    
    
def sanitize_input_html(content, context):
    # TODO: For some reason, the python re.sub() function is not working as expected, shelling out works
    # Replace \w with \\w and \c with \\c, but not \\w or \\c
    # content = re.sub(r'(?<!\\)\\w', r'\\w', content)
    # content = re.sub(r'(?<!\\)\\c', r'\\c', content)
   
    sanitize_list = ["ops.html", "index.html", "upgrade-guide.html", 
                     "tutorial.html", "connect.html", "quickstart.html"]
    
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

def process_markdown_headings(markdown_content, context):
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
    

def process_file(src_file, dest_file, hb_context):
    
    context = {
        "hb": hb_context
    }
    context['title'] = get_title_from_filename(dest_file)
    context['src_file_name'] = os.path.basename(src_file)
    context["dest_file_name"] = os.path.basename(dest_file)
    context['base_dir'] = os.path.dirname(src_file)
    context['up_level'] = True
    context['remove_numeric'] = True
    steps = [
        sanitize_input_html,
        process_handlebars_templates,
        process_ssi_tags_with_hugo,
        convert_html_to_md,
        add_front_matter,
        process_markdown_headings
    ]
    
    logging.info(f'Processing file: {src_file}, Destination file: {dest_file}, Context: {context}')
    try:
        with open(src_file, 'r', encoding='utf-8') as html_file:
            html_content = html_file.read()
        
        content, context = html_content, context
        for step in steps:
            content, context = execute_step(step, content, context)
        
        write_file(dest_file, content, context)
    except Exception as e:
        logging.error(f'Error processing file: {src_file}, Error: {e}')
        
def process_directory(src_dir, dest_dir, hb):
    if os.path.basename(src_dir) in exclude_dirs:
        logging.info(f'Skipping excluded directory: {src_dir}')
        return

    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
        # Create an empty _index.md file in the new directory
        with open(os.path.join(dest_dir, '_index.md'), 'w', encoding='utf-8') as index_file:
            index_file.write('')
        logging.info(f'Created directory and _index.md: {dest_dir}')

    for item in os.listdir(src_dir):
        src_path = os.path.join(src_dir, item)
        dest_path = os.path.join(dest_dir, item)

        if os.path.isdir(src_path):
            logging.info(f'Processing directory: {src_path}')
            process_directory(src_path, dest_path, hb)
        elif src_path.endswith('.html'):
            logging.info(f'Processing HTML file: {src_path}')
            process_file(src_path, dest_path, hb.get_context(src_path))
        else:
            shutil.copy2(src_path, dest_path)
            logging.info(f'Copied file: {src_path} to {dest_path}')


def main(input_path, output_path, hb):
    if os.path.isdir(input_path):
        logging.info(f'Starting processing directory: {input_path}')
        process_directory(input_path, output_path, hb)
    elif os.path.isfile(input_path) and input_path.endswith('.html'):
        output_path = os.path.join(output_path, os.path.basename(input_path))
        logging.info(f'Starting processing file: {input_path}')
        process_file(input_path, output_path, hb.get_context(input_path))
    else:
        logging.error(f'Invalid input path: {input_path}')

# Define source and destination paths
input_path = '../kafka-site/'
# /Users/hvishwanath/projects/kafka-site/39/connect.html
# input_path = '../kafka-site/39/connect.html'  # Change this to your input path
# input_path = '../kafka-site/39/ops.html'  # Change this to your input path
# input_path = '../kafka-site/39/documentation.html'  # Change this to your input path
# input_path = '../kafka-site/39/streams/upgrade-guide.html'  # Change this to your input path
# input_path = '../kafka-site/test.html'  # Change this to your input path

# input_path = '../kafka-site/39/design.html'  # Change this to your input path
output_path = '/Users/hvishwanath/projects/kmd/'  # Change this to your output path
output_path = '/Users/hvishwanath/projects/content_kafka/'  # Change this to your output path

# Build HB context
logging.debug('Building Handlebars context')
hb = HandleBarsContextBuilder("../kafka-site/")
logging.debug(f'Handlebars context: {hb}')

# Process the input
main(input_path, output_path, hb)
logging.info('Processing completed')