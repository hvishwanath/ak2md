"""
Workflow package for the AK2MD project.

This package contains the components for converting Apache Kafka HTML documentation to Markdown.
"""

from workflow.registry import WorkflowStepRegistry
from workflow.stages import (
    CloneStage,
    PreProcessStage,
    PostProcessStage,
    ValidationStage,
    ProcessSpecialFilesStage
)
from workflow.processors import (
    PreProcessDirectory,
    ProcessDocVersion,
    ProcessDocSection,
    ProcessSpecialFiles,
    special_file_processors,
    register_special_file_processor
)

__all__ = [
    'WorkflowStepRegistry',
    'CloneStage',
    'PreProcessStage',
    'PostProcessStage',
    'ValidationStage',
    'ProcessSpecialFilesStage',
    'PreProcessDirectory',
    'ProcessDocVersion',
    'ProcessDocSection',
    'ProcessSpecialFiles',
    'special_file_processors',
    'register_special_file_processor'
] 