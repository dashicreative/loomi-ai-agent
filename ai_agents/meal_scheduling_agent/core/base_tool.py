"""
Base Tool Interface - Enterprise-grade tool abstraction

Provides:
- Standardized execution interface
- Input/output validation  
- Retry logic with exponential backoff
- Metrics and performance tracking
- Error handling
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, List
from dataclasses import dataclass
import time
import asyncio
import json
from datetime import datetime
import hashlib

from pydantic import BaseModel, ValidationError
from ..config import get_config, get_tool_config_registry, RetryConfig
from ..exceptions import ToolExecutionError


@dataclass
class ToolResult:
    """Standardized result from tool execution"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    tool_name: str = ""
    cached: bool = False
    retry_count: int = 0


class ToolMetrics:
    """Simple metrics tracking for tools"""
    
    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.execution_count = 0
        self.success_count = 0
        self.error_count = 0
        self.cache_hits = 0
        self.total_execution_time = 0.0
        
    def record_execution(self, success: bool, execution_time: float, cached: bool = False):
        """Record metrics for a tool execution"""
        self.execution_count += 1
        self.total_execution_time += execution_time
        
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
            
        if cached:
            self.cache_hits += 1
    
    def get_average_execution_time(self) -> float:
        """Get average execution time"""
        if self.execution_count == 0:
            return 0.0
        return self.total_execution_time / self.execution_count
    
    def get_success_rate(self) -> float:
        """Get success rate percentage"""
        if self.execution_count == 0:
            return 0.0
        return (self.success_count / self.execution_count) * 100


class ToolCache:
    """Simple in-memory cache for tool results"""
    
    def __init__(self):
        self._cache: Dict[str, tuple[Any, float]] = {}
    
    def get(self, key: str, ttl: int) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < ttl:
                return value
            else:
                # Remove expired entry
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Set cache value with current timestamp"""
        self._cache[key] = (value, time.time())
    
    def clear(self):
        """Clear all cache entries"""
        self._cache.clear()


# Global cache instance
_tool_cache = ToolCache()


class BaseTool(ABC):
    """
    Universal tool interface - all tools inherit from this
    
    Provides enterprise-grade features while maintaining efficiency
    """
    
    def __init__(self, 
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 input_model: Optional[Type[BaseModel]] = None,
                 output_model: Optional[Type[BaseModel]] = None):
        """
        Initialize base tool
        
        Args:
            name: Tool name (defaults to class name)
            description: Tool description (defaults to docstring)
            input_model: Pydantic model for input validation
            output_model: Pydantic model for output validation
        """
        self.name = name or self.__class__.__name__
        self.description = description or self.__doc__ or "No description"
        self.input_model = input_model
        self.output_model = output_model
        
        # Get configuration
        self.config = get_config()
        self.tool_config = get_tool_config_registry().get_config(self.name)
        
        # Initialize metrics
        self.metrics = ToolMetrics(self.name)
        
        # Retry configuration
        self.retry_config = self.config.default_retry_config
        
    async def execute(self, **kwargs) -> ToolResult:
        """
        Universal execution wrapper with all enterprise features
        
        This method should NOT be overridden. Override _execute instead.
        """
        start_time = time.time()
        
        try:
            # Check cache first (if enabled)
            if self.tool_config and self.tool_config.cache_results:
                cache_key = self._generate_cache_key(kwargs)
                cached_result = _tool_cache.get(cache_key, self.tool_config.cache_ttl)
                if cached_result is not None:
                    execution_time = time.time() - start_time
                    self.metrics.record_execution(True, execution_time, cached=True)
                    return ToolResult(
                        success=True,
                        data=cached_result,
                        execution_time=execution_time,
                        tool_name=self.name,
                        cached=True
                    )
            
            # Validate inputs
            validated_input = await self._validate_input(kwargs)
            
            # Execute with retry logic
            result, retry_count = await self._execute_with_retry(validated_input)
            
            # Validate output
            if self.output_model and self.tool_config and self.tool_config.validate_outputs:
                result = await self._validate_output(result)
            
            # Cache result if enabled
            if self.tool_config and self.tool_config.cache_results:
                _tool_cache.set(cache_key, result)
            
            # Record metrics
            execution_time = time.time() - start_time
            self.metrics.record_execution(True, execution_time)
            
            return ToolResult(
                success=True,
                data=result,
                execution_time=execution_time,
                tool_name=self.name,
                retry_count=retry_count
            )
            
        except Exception as e:
            # Record failure metrics
            execution_time = time.time() - start_time
            self.metrics.record_execution(False, execution_time)
            
            return ToolResult(
                success=False,
                error=str(e),
                execution_time=execution_time,
                tool_name=self.name
            )
    
    @abstractmethod
    async def _execute(self, **kwargs) -> Dict[str, Any]:
        """
        Domain-specific implementation
        
        This is the only method that needs to be implemented by subclasses.
        
        Args:
            **kwargs: Validated input parameters
            
        Returns:
            Dictionary with execution results
        """
        pass
    
    async def _validate_input(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate input parameters"""
        if self.input_model and self.tool_config and self.tool_config.validate_inputs:
            try:
                validated = self.input_model(**kwargs)
                return validated.dict()
            except ValidationError as e:
                raise ToolExecutionError(f"Input validation failed: {e}")
        return kwargs
    
    async def _validate_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate output data"""
        if self.output_model:
            try:
                validated = self.output_model(**result)
                return validated.dict()
            except ValidationError as e:
                raise ToolExecutionError(f"Output validation failed: {e}")
        return result
    
    async def _execute_with_retry(self, validated_input: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
        """Execute with exponential backoff retry logic"""
        last_exception = None
        retry_count = 0
        
        max_attempts = self.retry_config.max_attempts
        if self.tool_config:
            max_attempts = min(max_attempts, self.tool_config.max_retries)
        
        for attempt in range(max_attempts):
            try:
                result = await self._execute(**validated_input)
                return result, retry_count
                
            except tuple(self.retry_config.retry_exceptions) as e:
                last_exception = e
                retry_count += 1
                
                if attempt < max_attempts - 1:
                    # Calculate exponential backoff delay
                    delay = min(
                        self.retry_config.initial_delay * (self.retry_config.exponential_base ** attempt),
                        self.retry_config.max_delay
                    )
                    await asyncio.sleep(delay)
                    continue
                    
            except Exception as e:
                # Don't retry non-retryable exceptions
                raise e
        
        raise ToolExecutionError(f"Failed after {max_attempts} attempts: {last_exception}")
    
    def _generate_cache_key(self, kwargs: Dict[str, Any]) -> str:
        """Generate cache key from input parameters"""
        # Create deterministic string representation
        key_data = json.dumps(kwargs, sort_keys=True, default=str)
        key_with_tool = f"{self.name}:{key_data}"
        
        # Return hash for efficient storage
        return hashlib.md5(key_with_tool.encode()).hexdigest()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get tool performance metrics"""
        return {
            "tool_name": self.name,
            "execution_count": self.metrics.execution_count,
            "success_count": self.metrics.success_count,
            "error_count": self.metrics.error_count,
            "success_rate": self.metrics.get_success_rate(),
            "average_execution_time": self.metrics.get_average_execution_time(),
            "cache_hits": self.metrics.cache_hits,
            "cache_hit_rate": (self.metrics.cache_hits / self.metrics.execution_count * 100) 
                             if self.metrics.execution_count > 0 else 0
        }
    
    def __repr__(self) -> str:
        """Professional string representation"""
        return f"{self.name}(category={self.tool_config.category if self.tool_config else 'unknown'})"