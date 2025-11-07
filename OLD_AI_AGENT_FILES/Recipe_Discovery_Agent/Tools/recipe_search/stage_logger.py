"""
Stage Logger for Recipe Search Pipeline

Provides structured logging for the 9-stage recipe discovery pipeline
with automatic timing, error tracking, and metrics collection.
"""

import logfire
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import time


@dataclass
class StageMetrics:
    """Metrics collected for each stage."""
    stage_number: int
    stage_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    status: str = "in_progress"
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, str]] = field(default_factory=list)
    
    def complete(self, status: str = "success", **metrics):
        """Mark stage as complete with metrics."""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.status = status
        self.metrics.update(metrics)
    
    def add_error(self, error_type: str, message: str):
        """Add an error to this stage."""
        self.errors.append({"type": error_type, "message": message[:200]})
        

class PipelineStageLogger:
    """
    Manages structured logging for the recipe search pipeline stages.
    
    Usage:
        logger = PipelineStageLogger(session_id, query)
        
        # Start a stage
        logger.start_stage(1, "web_search")
        # ... do work ...
        logger.complete_stage(1, urls_found=50, priority_count=10)
        
        # Log final summary
        logger.log_pipeline_summary()
    """
    
    def __init__(self, session_id: str, query: str):
        self.session_id = session_id
        self.query = query
        self.stages: Dict[int, StageMetrics] = {}
        self.pipeline_start = time.time()
        
    def start_stage(self, stage_number: int, stage_name: str) -> StageMetrics:
        """Start tracking a stage."""
        stage = StageMetrics(
            stage_number=stage_number,
            stage_name=stage_name,
            start_time=time.time()
        )
        self.stages[stage_number] = stage
        
        # Log stage start
        logfire.debug(f"stage_{stage_number}_started",
                      stage_name=stage_name,
                      session_id=self.session_id)
        
        return stage
    
    def complete_stage(self, stage_number: int, status: str = "success", **metrics):
        """Complete a stage with metrics."""
        if stage_number in self.stages:
            stage = self.stages[stage_number]
            stage.complete(status, **metrics)
            
            # Log stage completion
            logfire.info(f"stage_{stage_number}_completed",
                         stage_name=stage.stage_name,
                         duration=stage.duration,
                         status=status,
                         metrics=metrics,
                         errors=stage.errors,
                         session_id=self.session_id)
    
    def add_stage_error(self, stage_number: int, error_type: str, message: str):
        """Add an error to a stage."""
        if stage_number in self.stages:
            self.stages[stage_number].add_error(error_type, message)
    
    def log_pipeline_summary(self, total_recipes: int = 0, fallback_used: bool = False):
        """Log comprehensive pipeline summary."""
        total_duration = time.time() - self.pipeline_start
        
        # Collect all stage summaries
        stage_summaries = {}
        stage_timings = {}
        total_errors = []
        
        for num, stage in self.stages.items():
            stage_summaries[f"stage_{num}_{stage.stage_name}"] = {
                "duration": stage.duration or 0,
                "status": stage.status,
                "metrics": stage.metrics,
                "error_count": len(stage.errors)
            }
            stage_timings[stage.stage_name] = stage.duration or 0
            total_errors.extend(stage.errors)
        
        # Log comprehensive summary
        logfire.info("pipeline_summary",
                     query=self.query,
                     session_id=self.session_id,
                     total_duration=total_duration,
                     total_recipes=total_recipes,
                     fallback_used=fallback_used,
                     stage_count=len(self.stages),
                     stage_summaries=stage_summaries,
                     stage_timings=stage_timings,
                     total_errors=len(total_errors),
                     errors=total_errors[:5]  # First 5 errors
                     )
        
        return {
            "total_duration": total_duration,
            "stage_timings": stage_timings,
            "total_errors": len(total_errors)
        }


# Stage definitions for reference
PIPELINE_STAGES = {
    1: "web_search",
    2: "url_ranking", 
    3: "url_classification",
    4: "recipe_parsing",
    5: "nutrition_normalization",
    6: "requirements_verification",
    7: "relevance_ranking",
    8: "list_processing",
    9: "final_formatting"
}