#!/usr/bin/env python3

import logging
from enum import Enum, auto
from typing import Optional

class StageStatus(Enum):
    """Status values for workflow stages"""
    NOT_STARTED = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()

class WorkflowStage:
    """Base class for all workflow stages"""
    
    def __init__(self, name: str, context: 'WorkflowContext'):
        self.name = name
        self.context = context
        self.status = StageStatus.NOT_STARTED
        self.logger = logging.getLogger(f'ak2md-workflow.{name}')
    
    def execute(self) -> bool:
        """Execute the stage and return success status"""
        try:
            self.status = StageStatus.IN_PROGRESS
            self.logger.info(f"Starting stage: {self.name}")
            
            success = self._do_execute()
            
            self.status = StageStatus.COMPLETED if success else StageStatus.FAILED
            self.logger.info(f"Completed stage: {self.name} with status: {self.status}")
            
            return success
        except Exception as e:
            self.status = StageStatus.FAILED
            self.logger.error(f"Stage {self.name} failed with error: {str(e)}", exc_info=True)
            return False
    
    def _do_execute(self) -> bool:
        """Implementation specific to each stage"""
        raise NotImplementedError 