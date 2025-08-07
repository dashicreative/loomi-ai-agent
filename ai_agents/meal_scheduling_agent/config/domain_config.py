"""
Domain Configuration for Meal Scheduling Agent

Centralizes all configuration to make the agent efficient and maintainable.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import os


@dataclass
class RetryConfig:
    """Configuration for retry logic to reduce failed API calls"""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0
    retry_exceptions: List[type] = field(default_factory=lambda: [ConnectionError, TimeoutError])


@dataclass
class DomainConfig:
    """Base configuration for any domain agent"""
    
    # Domain identity
    domain_name: str
    version: str
    description: str
    
    # Performance settings (for efficiency)
    max_execution_time: int = 30  # seconds
    cache_ttl: int = 300  # seconds for caching responses
    max_concurrent_tools: int = 5
    
    # LLM settings (to reduce API calls)
    llm_temperature: float = 0.3  # Lower = more deterministic = less retries
    llm_max_retries: int = 2  # Limit LLM retries
    prefer_rule_based: bool = True  # Use rules before LLM when possible
    
    # Response settings
    response_style: str = "conversational"
    include_confidence: bool = False
    max_response_length: int = 500
    
    # Retry configuration
    default_retry_config: RetryConfig = field(default_factory=RetryConfig)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "domain_name": self.domain_name,
            "version": self.version,
            "description": self.description,
            "max_execution_time": self.max_execution_time,
            "cache_ttl": self.cache_ttl,
            "max_concurrent_tools": self.max_concurrent_tools,
            "llm_temperature": self.llm_temperature,
            "llm_max_retries": self.llm_max_retries,
            "prefer_rule_based": self.prefer_rule_based,
            "response_style": self.response_style,
            "include_confidence": self.include_confidence,
            "max_response_length": self.max_response_length
        }


@dataclass
class MealSchedulingConfig(DomainConfig):
    """Specific configuration for meal scheduling domain"""
    
    def __init__(self):
        super().__init__(
            domain_name="meal_scheduling",
            version="2.1.0",
            description="AI agent for intelligent meal planning and scheduling"
        )
        
        # Meal-specific settings
        self.max_meals_per_day: int = 4
        self.default_servings: int = 4
        self.default_meal_type: str = "dinner"
        self.allow_past_scheduling: bool = False
        self.allow_conflicts: bool = False
        
        # Scheduling limits (for efficiency)
        self.max_batch_size: int = 50  # Limit batch operations
        self.max_days_ahead: int = 365  # Limit how far ahead to schedule
        self.max_random_retries: int = 3  # For random meal selection
        
        # Intent thresholds
        self.confidence_thresholds = {
            "direct_schedule": 0.8,
            "batch_schedule": 0.7,
            "clear_schedule": 0.9,
            "ambiguous": 0.4
        }
        
        # Clarification triggers
        self.clarification_triggers = [
            "some", "a few", "random", "pick", "choose",
            "help", "what", "which", "suggest"
        ]
        
        # Tool categories for organization
        self.tool_categories = {
            "scheduling": ["ScheduleSingleMealTool", "ClearScheduleTool"],
            "data": ["LoadMealsTool", "FindMealByNameTool"],
            "selection": ["SelectRandomMealsTool", "SuggestAlternativeMealsTool"],
            "parsing": ["ParseDateTool", "GetDateRangeTool", "ExtractMealTypeTool"]
        }
    
    @classmethod
    def from_env(cls) -> 'MealSchedulingConfig':
        """Load configuration from environment variables"""
        config = cls()
        
        # Allow env overrides for key settings
        if os.getenv("MEAL_AGENT_MAX_BATCH_SIZE"):
            config.max_batch_size = int(os.getenv("MEAL_AGENT_MAX_BATCH_SIZE"))
        if os.getenv("MEAL_AGENT_LLM_TEMPERATURE"):
            config.llm_temperature = float(os.getenv("MEAL_AGENT_LLM_TEMPERATURE"))
        if os.getenv("MEAL_AGENT_PREFER_RULES"):
            config.prefer_rule_based = os.getenv("MEAL_AGENT_PREFER_RULES").lower() == "true"
            
        return config
    
    @classmethod
    def from_file(cls, filepath: str) -> 'MealSchedulingConfig':
        """Load configuration from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
                
        return config
    
    def validate(self) -> List[str]:
        """Validate configuration and return any errors"""
        errors = []
        
        if self.max_batch_size < 1:
            errors.append("max_batch_size must be at least 1")
        if self.max_days_ahead < 1:
            errors.append("max_days_ahead must be at least 1")
        if not 0 <= self.llm_temperature <= 1:
            errors.append("llm_temperature must be between 0 and 1")
        if self.max_execution_time < 1:
            errors.append("max_execution_time must be at least 1 second")
            
        return errors


# Singleton instance
_config_instance: Optional[MealSchedulingConfig] = None


def get_config() -> MealSchedulingConfig:
    """Get or create the configuration singleton"""
    global _config_instance
    
    if _config_instance is None:
        # Try loading from file first, then env, then defaults
        config_path = os.getenv("MEAL_AGENT_CONFIG_PATH")
        if config_path and os.path.exists(config_path):
            _config_instance = MealSchedulingConfig.from_file(config_path)
        else:
            _config_instance = MealSchedulingConfig.from_env()
        
        # Validate configuration
        errors = _config_instance.validate()
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
    
    return _config_instance