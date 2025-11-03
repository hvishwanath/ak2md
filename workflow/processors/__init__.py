"""
The processors package contains the main processing functionality for the workflow.
"""

from workflow.processors.base import PreProcessFile
from workflow.processors.directory import PreProcessDirectory
from workflow.processors.doc_version import ProcessDocVersion
from workflow.processors.doc_section import ProcessDocSection
from workflow.processors.special_files import (
    ProcessSpecialFiles,
    special_file_processors,
    register_special_file_processor,
    process_committers
)
from workflow.processors.toc_cleaner import TocCleaner, clean_toc_from_markdown

__all__ = [
    'PreProcessFile',
    'PreProcessDirectory',
    'ProcessDocVersion',
    'ProcessDocSection',
    'ProcessSpecialFiles',
    'special_file_processors',
    'register_special_file_processor',
    'process_committers',
    'TocCleaner',
    'clean_toc_from_markdown'
] 