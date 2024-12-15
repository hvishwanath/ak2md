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

def post_process(context):
    
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
        exception_ledger.append((src_file, dest_file, e))
