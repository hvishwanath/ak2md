import os
import html2text
import shutil
import re
import logging
from pybars import Compiler
from constants import Constants
from utils import HandleBarsContextBuilder


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

exclude_dirs = ['markdown']
exception_ledger = []

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
    return template(context)

def process_ssi_tags(html_content, base_dir):
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
    return html_content

def process_ssi_tags_with_hugo(html_content):
    ssi_pattern = re.compile(r'<!--#include virtual="([^"]+\.html)" -->')
    matches = ssi_pattern.findall(html_content)
    for match in matches:
        shortcode = f'{{{{< include file="{match}" >}}}}'
        html_content = html_content.replace(f'<!--#include virtual="{match}" -->', shortcode)
        logging.debug(f'Replaced SSI with Hugo shortcode: {match}')
    return html_content

def convert_html_to_md(html_content):
    h = html2text.HTML2Text()
    h.ignore_links = False  # Set to True to ignore links
    h.ignore_images = False  # Set to True to ignore images
    h.ignore_emphasis = False  # Set to True to ignore emphasis (bold, italic)
    h.bypass_tables = False  # Set to True to ignore tables
    h.body_width = 0  # Set to 0 to prevent wrapping
    return h.handle(html_content)

def process_handlebars_templates(html_content, context):

    logging.debug(f'Processing with Context: {context}')
    handlebars_pattern = re.compile(r'<script[^>]*type="text/x-handlebars-template"[^>]*>(.*?)</script>', re.DOTALL)
    matches = handlebars_pattern.findall(html_content)            
    for match in matches:
        logging.debug(f'Found Handlebars template: {match}')
        rendered_content = render_handlebars_template(match, context)
        html_content = handlebars_pattern.sub(rendered_content, html_content, count=1)
    logging.debug(f'Processed Handlebars template: {html_content}')
    return html_content

def process_file(src_file, dest_file, context):
    logging.info(f'Processing file: {src_file}, Destination file: {dest_file}, Context: {context}')
    try:
        title = get_title_from_filename(dest_file)
        with open(src_file, 'r', encoding='utf-8') as html_file:
            html_content = html_file.read()

        # Process Handlebars templates
        html_content = process_handlebars_templates(html_content, context)

        # Process SSI tags
        if Constants.SSI_Processor == "hugo":
            html_content = process_ssi_tags_with_hugo(html_content)
        else:
            html_content = process_ssi_tags(html_content, os.path.dirname(src_file))

        # Convert rendered HTML to Markdown
        logging.debug("After handlebars processing: " + html_content)
        markdown_content = convert_html_to_md(html_content)
        # Add license and front matter
        markdown_content = f"{Constants.Front_Matter_Template.format(title=title)}\n{markdown_content}"
        dest_file = dest_file.replace('.html', '.md')
        with open(dest_file, 'w', encoding='utf-8') as md_file:
            md_file.write(markdown_content)
        logging.info(f'Converted and saved Markdown file: {dest_file}')
    except Exception as e:
        logging.error(f'Error processing file: {src_file}, Error: {e}')
        exception_ledger.append((src_file, dest_file, e))
        
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
# input_path = '../kafka-site/32/streams/upgrade-guide.html'  # Change this to your input path

# input_path = '../kafka-site/39/design.html'  # Change this to your input path
output_path = '/Users/hvishwanath/projects/kafka-site-md/content/'  # Change this to your output path

# Build HB context
logging.debug('Building Handlebars context')
hb = HandleBarsContextBuilder("../kafka-site/")
logging.debug(f'Handlebars context: {hb}')

# Process the input
main(input_path, output_path, hb)
logging.info("Collected Exceptions: " + str(exception_ledger))
logging.info('Processing completed')