"""
Tool Configuration - Settings for all tools
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ToolConfig:
    """Configuration for individual tools"""
    name: str
    description: str
    category: str
    max_retries: int = 3
    timeout: float = 10.0
    cache_results: bool = False
    cache_ttl: int = 300  # seconds
    
    # Performance settings
    requires_llm: bool = False
    parallel_capable: bool = True
    
    # Validation settings
    validate_inputs: bool = True
    validate_outputs: bool = True


class ToolConfigRegistry:
    """Registry of all tool configurations"""
    
    def __init__(self):
        self.configs: Dict[str, ToolConfig] = {
            # Data tools (can be cached)
            "LoadMealsTool": ToolConfig(
                name="LoadMealsTool",
                description="Load available meals from storage",
                category="data",
                cache_results=True,
                cache_ttl=600,  # Cache for 10 minutes
                requires_llm=False
            ),
            
            "FindMealByNameTool": ToolConfig(
                name="FindMealByNameTool",
                description="Find meal by name with fuzzy matching",
                category="data",
                cache_results=True,
                cache_ttl=300,
                requires_llm=False
            ),
            
            # Scheduling tools (no caching)
            "ScheduleSingleMealTool": ToolConfig(
                name="ScheduleSingleMealTool",
                description="Schedule a single meal",
                category="scheduling",
                cache_results=False,
                requires_llm=False,
                max_retries=2  # Reduce retries for write operations
            ),
            
            "ClearScheduleTool": ToolConfig(
                name="ClearScheduleTool",
                description="Clear scheduled meals",
                category="scheduling",
                cache_results=False,
                requires_llm=False,
                max_retries=2
            ),
            
            # Selection tools
            "SelectRandomMealsTool": ToolConfig(
                name="SelectRandomMealsTool",
                description="Select random meals from available options",
                category="selection",
                cache_results=False,  # Random should be fresh
                requires_llm=False
            ),
            
            "SuggestAlternativeMealsTool": ToolConfig(
                name="SuggestAlternativeMealsTool",
                description="Suggest meal alternatives",
                category="selection",
                cache_results=True,
                cache_ttl=300,
                requires_llm=False
            ),
            
            # Parsing tools (highly cacheable)
            "ParseDateTool": ToolConfig(
                name="ParseDateTool",
                description="Parse natural language dates",
                category="parsing",
                cache_results=True,
                cache_ttl=3600,  # Cache for 1 hour
                requires_llm=False
            ),
            
            "GetDateRangeTool": ToolConfig(
                name="GetDateRangeTool",
                description="Generate date ranges",
                category="parsing",
                cache_results=True,
                cache_ttl=3600,
                requires_llm=False
            ),
            
            "ExtractMealTypeTool": ToolConfig(
                name="ExtractMealTypeTool",
                description="Extract meal type from text",
                category="parsing",
                cache_results=True,
                cache_ttl=3600,
                requires_llm=False
            )
        }
    
    def get_config(self, tool_name: str) -> Optional[ToolConfig]:
        """Get configuration for a specific tool"""
        return self.configs.get(tool_name)
    
    def get_tools_by_category(self, category: str) -> List[ToolConfig]:
        """Get all tools in a category"""
        return [
            config for config in self.configs.values()
            if config.category == category
        ]
    
    def get_cacheable_tools(self) -> List[str]:
        """Get list of tools that support caching"""
        return [
            name for name, config in self.configs.items()
            if config.cache_results
        ]


# Singleton instance
_tool_config_registry: Optional[ToolConfigRegistry] = None


def get_tool_config_registry() -> ToolConfigRegistry:
    """Get or create the tool configuration registry"""
    global _tool_config_registry
    
    if _tool_config_registry is None:
        _tool_config_registry = ToolConfigRegistry()
    
    return _tool_config_registry