import os
import re
import logging
import shutil
import yaml
from utils import *

    
def process_section(context):
    context["section_dir"] = os.path.join(context['output_path'], context['section']['name'])
    
    # create the section directory
    if os.path.exists(context["section_dir"]):
        shutil.rmtree(context["section_dir"])
    os.makedirs(context["section_dir"])
    
    # create the _index.md file
    index_file = os.path.join(context["section_dir"], '_index.md')
    template_values = {
        "title": context["section"]["title"],
        "description": context["section"].get("description", ""),
        "tags": context["front_matter"]["tags"] + context["section"].get("tags", []),
        "aliases": "",
        "weight": context["section_weight"],
        "type": context["section"].get("type", "docs"),
        "keywords": context["section"].get("keywords", "")
    }
    context["template_values"] = template_values
    front_matter, _ = update_front_matter("", context)
    with open(index_file, 'w') as file:
        file.write(front_matter)
    
    strategy = context["section"]["strategy"]
    if strategy == "arrange":
        steps = [
            update_front_matter,
            process_markdown_headings,
            process_markdown_links,
        ]

        for w, n in enumerate(context["section"]["files"], start=1):
            template_values = {
                "title": n["title"],
                "description": n.get("description", ""),
                "tags": context["front_matter"]["tags"] + n.get("tags", []),
                "aliases": "",
                "weight": w,
                "type": context["section"].get("type", "docs"),
                "keywords": n.get("keywords", "")
            }
            
            context["template_values"] = template_values
            src_file = os.path.join(context['src_dir'], n['file'])
            if not os.path.exists(src_file):
                logging.info(f'File not found: {src_file}, continuing processing...')
                continue
            dest_file = os.path.join(context["section_dir"], n['file'])
            logging.info(f'Processing file: {src_file}, Destination file: {dest_file}')
            try:
                with open(src_file, 'r', encoding='utf-8') as html_file:
                    content = html_file.read()
                for step in steps:
                    content, context = execute_step(step, content, context)
                
                write_file(dest_file, content, context)
            except Exception as e:
                logging.error(f'Error processing file: {src_file}, Error: {e}')
                raise e

    elif strategy == "split_markdown_by_heading":
        steps = [
            split_markdown_by_heading,
        ]
        src_file = os.path.join(context['src_dir'], context['section']['file'])                 
        if not os.path.exists(src_file):
            logging.info(f'File not found: {src_file}, continuing processing...')
            return
        try:
            with open(src_file, 'r', encoding='utf-8') as html_file:
                content = html_file.read()
            for step in steps:
                content, context = execute_step(step, content, context)
         
        except Exception as e:
            logging.error(f'Error processing file: {src_file}, Error: {e}')
            raise e


def post_process(input_path, output_path, static_path, rules):    
    for dir in rules.get('doc_dirs'):
        index_file = os.path.join(output_path, dir, '_index.md')
        if len(dir) == 4:
            doc_version = f"{dir[0]}.{dir[1]}{dir[2]}.{dir[3]}.X"
        elif len(dir) == 3:
            doc_version = f"{dir[0]}.{dir[1]}.{dir[2]}.X"
        elif len(dir) == 2:
            doc_version = f"{dir[0]}.{dir[1]}.X"
        else:
            doc_version = f"{dir[0]}.X"
            
        template_values = {
            "title": f"AK {doc_version}",
            "description": f"Documentation for AK {doc_version}",
            "tags": rules["front_matter"]["tags"],
            "aliases": "",
            "weight": "",
            "type": "docs",
            "keywords": ""
        }
        d = {
            "template_values": template_values,
            "front_matter": rules["front_matter"]
        }
        front_matter, _ = update_front_matter("", d)
        with open(index_file, 'w') as file:
            file.write(front_matter)

        src_path = os.path.join(input_path, dir)
        for weight, section in enumerate(rules.get('sections'), start=1):
            context = dict()
            context['output_path'] = os.path.join(output_path, dir)
            context['front_matter'] = rules.get('front_matter')
            context['src_dir'] = src_path
            context['static_dir'] = static_path
            context['doc_dir'] = dir
            context['up_level'] = True
            context['remove_numeric'] = True
            context["section"] = section
            context["section_weight"] = weight
            context["link_updates"] = rules.get('link_updates')
            logging.info(f'Processing section: {section["name"]} in doc directory: {dir}')
            process_section(context)
            

if __name__=="__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    rules = yaml.safe_load(open('process.yaml'))
    
    # Define source and destination paths
    input_path = '/Users/hvishwanath/projects/staging/'  # Change this to your input path
    output_path = '/Users/hvishwanath/projects/staging-hugo/'  # Change this to your output path 
    static_path = os.path.join(output_path, 'static')

    # Process the input
    post_process(input_path, output_path, static_path, rules)
    logging.info('Processing completed')