#!/usr/bin/env python3
"""
Processor to remove manually created Table of Contents from markdown files.
Hugo Docsy will auto-generate TOC, so we don't need manual ones.
"""

import re
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger('ak2md-workflow.processors.toc-cleaner')

class TocCleaner:
    """Remove manually created TOC sections from markdown files"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.modified_count = 0
        self.total_count = 0
    
    def execute(self) -> bool:
        """Process all markdown files to remove TOC sections"""
        try:
            logger.info("Starting TOC cleanup process")
            
            # Find all markdown files in the content directory
            content_dir = self.output_dir / "content"
            if not content_dir.exists():
                logger.warning(f"Content directory not found: {content_dir}")
                return True  # Not an error, just nothing to do
            
            md_files = list(content_dir.rglob('*.md'))
            self.total_count = len(md_files)
            logger.info(f"Found {self.total_count} markdown files to process")
            
            for md_file in md_files:
                if self._process_file(md_file):
                    self.modified_count += 1
            
            logger.info(f"TOC cleanup complete: modified {self.modified_count} of {self.total_count} files")
            return True
            
        except Exception as e:
            logger.error(f"Error during TOC cleanup: {str(e)}")
            return False
    
    def _process_file(self, file_path: Path) -> bool:
        """Process a single markdown file to remove TOC sections"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Apply all TOC removal patterns
            content = self._remove_table_of_contents(content)
            content = self._remove_config_param_reference_toc(content)
            content = self._remove_table_of_contents(content)
            content = self._remove_config_param_reference_toc(content)
            content = self._remove_navigation_breadcrumbs(content)
            
            # Specific cleaner for protocol.md manual TOC
            if "protocol.md" in file_path.name:
                content = self._remove_protocol_toc(content)
            
            # Only write if content changed
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.debug(f"Modified: {file_path.relative_to(self.output_dir)}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return False
    
    def _remove_table_of_contents(self, content: str) -> str:
        """Remove **Table of Contents** section with bullet list."""
        # Pattern: **Table of Contents** followed by bullet lists
        pattern = r'\*\*Table of Contents\*\*\n\n(?:  \* .*\n(?:    \* .*\n)*)*'
        return re.sub(pattern, '', content)
    
    def _remove_config_param_reference_toc(self, content: str) -> str:
        """Remove Configuration parameter reference TOC section."""
        # Pattern: # Configuration parameter reference followed by bullet lists
        # Match from the heading to the next "##" heading
        pattern = r'(# Configuration parameter reference\n\n)(?:  \* .*\n(?:    \* .*\n)*)+(\n##)'
        # Keep the heading and the next section marker, remove the list
        return re.sub(pattern, r'\1\2', content)
    
    def _remove_navigation_breadcrumbs(self, content: str) -> str:
        """Remove navigation breadcrumb lines like [Introduction](...) [Run Demo](...) ..."""
        # Pattern: Line starting with [SomeText](url) repeated multiple times
        # This matches lines with 2 or more consecutive markdown links
        pattern = r'^(\[[\w\s:]+\]\([^\)]+\)\s*){2,}\n\n'
        return re.sub(pattern, '', content, flags=re.MULTILINE)

    def _remove_protocol_toc(self, content: str) -> str:
        """Remove manual TOC from protocol.md files."""
        # The TOC in protocol.md usually looks like a list starting with specific sections
        # We'll use a regex that matches the structure described by the user
        
        # Pattern to match the specific TOC structure in protocol.md
        # It typically starts with * Preliminaries and ends before the first real heading
        pattern = r'^\s*\*\s+Preliminaries\n(?:^\s+\* .*\n)*'
        
        # Check if we find the start of the TOC
        if re.search(pattern, content, re.MULTILINE):
            logger.info("Found protocol.md manual TOC pattern, removing it")
            return re.sub(pattern, '', content, flags=re.MULTILINE)
            
        return content


def clean_toc_from_markdown(output_dir: Path) -> bool:
    """
    Convenience function to clean TOC from all markdown files.
    
    Args:
        output_dir: The output directory containing the content folder
        
    Returns:
        True if successful, False otherwise
    """
    cleaner = TocCleaner(output_dir)
    return cleaner.execute()

