import os
import re
import json
import difflib
import logging

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
    
if __name__=="__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    builder = HandleBarsContextBuilder("../kafka-site/")
    print(builder)
    print(builder.get_context('/Users/hvishwanath/projects/kafka-site/39/design.html'))