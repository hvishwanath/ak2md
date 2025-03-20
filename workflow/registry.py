#!/usr/bin/env python3

import logging
from typing import Optional, List, Callable, Dict, Any, Tuple

# Import the functions from utils
from utils import (
    sanitize_input_html,
    process_handlebars_templates,
    process_ssi_tags_with_hugo,
    convert_html_to_md,
    add_front_matter,
    process_markdown_headings,
    update_front_matter,
    process_markdown_links,
    split_markdown_by_heading
)

logger = logging.getLogger('ak2md-workflow.registry')

# Define step function type
StepFunction = Callable[[str, Dict[str, Any]], Tuple[str, Dict[str, Any]]]

class WorkflowStepRegistry:
    """Registry of workflow steps that can be composed into stages"""
    
    def __init__(self):
        self.pre_process_steps: Dict[str, StepFunction] = {}
        self.post_process_steps: Dict[str, StepFunction] = {}
        self._register_all_steps()
    
    def _register_all_steps(self):
        """Register all available steps"""
        # Register pre-process steps
        self.register_pre_process_step("sanitize_html", sanitize_input_html)
        self.register_pre_process_step("process_handlebars", process_handlebars_templates)
        self.register_pre_process_step("process_ssi", process_ssi_tags_with_hugo)
        self.register_pre_process_step("convert_to_md", convert_html_to_md)
        self.register_pre_process_step("add_front_matter", add_front_matter)
        self.register_pre_process_step("process_headings", process_markdown_headings)
        
        # Register post-process steps
        self.register_post_process_step("update_front_matter", update_front_matter)
        self.register_post_process_step("process_links", process_markdown_links)
        self.register_post_process_step("split_by_heading", split_markdown_by_heading)
    
    def register_pre_process_step(self, name: str, step_func: StepFunction):
        """Register a pre-process step"""
        self.pre_process_steps[name] = step_func
        logger.debug(f"Registered pre-process step: {name}")
    
    def register_post_process_step(self, name: str, step_func: StepFunction):
        """Register a post-process step"""
        self.post_process_steps[name] = step_func
        logger.debug(f"Registered post-process step: {name}")
    
    def get_pre_process_steps(self, step_names: Optional[List[str]] = None) -> List[StepFunction]:
        """Get pre-process steps by name or all if names not provided"""
        if step_names is None:
            # Default pre-process steps in the original order
            step_names = [
                "sanitize_html",
                "process_handlebars",
                "process_ssi",
                "convert_to_md",
                "add_front_matter",
                "process_headings"
            ]
        
        return [self.pre_process_steps[name] for name in step_names]
    
    def get_post_process_steps(self, step_names: Optional[List[str]] = None) -> List[StepFunction]:
        """Get post-process steps by name or all if names not provided"""
        if step_names is None:
            # Default post-process steps in a sensible order
            step_names = [
                "update_front_matter",
                "process_links",
                "split_by_heading"
            ]
        
        return [self.post_process_steps[name] for name in step_names] 