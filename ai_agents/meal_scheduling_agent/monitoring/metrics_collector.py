"""
Metrics Collection - Simple but professional metrics tracking

Provides visibility into:
- Intent classification accuracy
- Tool execution performance
- Cache hit rates
- Error rates
- Response times
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
from collections import defaultdict, deque


@dataclass
class MetricPoint:
    """Single metric measurement"""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class AgentMetrics:
    """Complete metrics snapshot for the agent"""
    timestamp: datetime
    
    # Performance metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    
    # Intent metrics
    intent_classifications: Dict[str, int] = field(default_factory=dict)
    intent_confidence_avg: float = 0.0
    clarification_rate: float = 0.0
    
    # Tool metrics
    tool_executions: Dict[str, int] = field(default_factory=dict)
    tool_success_rates: Dict[str, float] = field(default_factory=dict)
    tool_avg_execution_times: Dict[str, float] = field(default_factory=dict)
    cache_hit_rate: float = 0.0
    
    # Efficiency metrics
    llm_calls_saved: int = 0  # By using rules instead
    average_retry_count: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "performance": {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": (self.successful_requests / self.total_requests * 100) 
                               if self.total_requests > 0 else 0,
                "average_response_time_ms": self.average_response_time * 1000
            },
            "intents": {
                "classifications": self.intent_classifications,
                "average_confidence": self.intent_confidence_avg,
                "clarification_rate": self.clarification_rate
            },
            "tools": {
                "executions": self.tool_executions,
                "success_rates": self.tool_success_rates,
                "average_execution_times_ms": {
                    k: v * 1000 for k, v in self.tool_avg_execution_times.items()
                },
                "cache_hit_rate": self.cache_hit_rate
            },
            "efficiency": {
                "llm_calls_saved": self.llm_calls_saved,
                "average_retry_count": self.average_retry_count
            }
        }


class MetricsCollector:
    """
    Collects and aggregates metrics for the meal scheduling agent
    
    This is a simple in-memory implementation. In production,
    you would export to Prometheus, CloudWatch, etc.
    """
    
    def __init__(self, window_size: int = 100):
        """
        Initialize metrics collector
        
        Args:
            window_size: Number of recent requests to keep for averaging
        """
        self.window_size = window_size
        
        # Response time tracking (using deque for efficiency)
        self.response_times = deque(maxlen=window_size)
        
        # Intent tracking
        self.intent_counts = defaultdict(int)
        self.intent_confidences = deque(maxlen=window_size)
        self.clarification_requests = deque(maxlen=window_size)
        
        # Tool tracking
        self.tool_executions = defaultdict(int)
        self.tool_successes = defaultdict(int)
        self.tool_failures = defaultdict(int)
        self.tool_execution_times = defaultdict(lambda: deque(maxlen=window_size))
        self.tool_cache_hits = defaultdict(int)
        
        # Efficiency tracking
        self.llm_calls_saved = 0
        self.retry_counts = deque(maxlen=window_size)
        
        # Request tracking
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
    
    def record_request(self, success: bool, response_time: float, intent_type: str, confidence: float):
        """Record a complete request"""
        self.total_requests += 1
        self.response_times.append(response_time)
        
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        # Record intent info
        self.intent_counts[intent_type] += 1
        self.intent_confidences.append(confidence)
    
    def record_clarification_request(self, needed_clarification: bool):
        """Record whether clarification was needed"""
        self.clarification_requests.append(1 if needed_clarification else 0)
    
    def record_tool_execution(self, tool_name: str, success: bool, execution_time: float, 
                            cached: bool = False, retry_count: int = 0):
        """Record tool execution metrics"""
        self.tool_executions[tool_name] += 1
        
        if success:
            self.tool_successes[tool_name] += 1
        else:
            self.tool_failures[tool_name] += 1
        
        self.tool_execution_times[tool_name].append(execution_time)
        
        if cached:
            self.tool_cache_hits[tool_name] += 1
        
        if retry_count > 0:
            self.retry_counts.append(retry_count)
    
    def record_llm_call_saved(self):
        """Record when a rule-based approach saved an LLM call"""
        self.llm_calls_saved += 1
    
    def get_current_metrics(self) -> AgentMetrics:
        """Get current metrics snapshot"""
        metrics = AgentMetrics(timestamp=datetime.now())
        
        # Basic counts
        metrics.total_requests = self.total_requests
        metrics.successful_requests = self.successful_requests
        metrics.failed_requests = self.failed_requests
        
        # Response time
        if self.response_times:
            metrics.average_response_time = sum(self.response_times) / len(self.response_times)
        
        # Intent metrics
        metrics.intent_classifications = dict(self.intent_counts)
        if self.intent_confidences:
            metrics.intent_confidence_avg = sum(self.intent_confidences) / len(self.intent_confidences)
        if self.clarification_requests:
            metrics.clarification_rate = sum(self.clarification_requests) / len(self.clarification_requests)
        
        # Tool metrics
        metrics.tool_executions = dict(self.tool_executions)
        
        for tool_name in self.tool_executions:
            total = self.tool_executions[tool_name]
            successes = self.tool_successes[tool_name]
            
            if total > 0:
                metrics.tool_success_rates[tool_name] = (successes / total) * 100
                
                # Cache hit rate
                cache_hits = self.tool_cache_hits[tool_name]
                cache_hit_rate = (cache_hits / total) * 100 if total > 0 else 0
                
                # Average execution time
                exec_times = self.tool_execution_times[tool_name]
                if exec_times:
                    metrics.tool_avg_execution_times[tool_name] = sum(exec_times) / len(exec_times)
        
        # Overall cache hit rate
        total_cache_hits = sum(self.tool_cache_hits.values())
        total_tool_calls = sum(self.tool_executions.values())
        if total_tool_calls > 0:
            metrics.cache_hit_rate = (total_cache_hits / total_tool_calls) * 100
        
        # Efficiency metrics
        metrics.llm_calls_saved = self.llm_calls_saved
        if self.retry_counts:
            metrics.average_retry_count = sum(self.retry_counts) / len(self.retry_counts)
        
        return metrics
    
    def get_metrics_summary(self) -> str:
        """Get a human-readable metrics summary"""
        metrics = self.get_current_metrics()
        
        summary = [
            "=== Meal Scheduling Agent Metrics ===",
            f"Timestamp: {metrics.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "Performance:",
            f"  Total Requests: {metrics.total_requests}",
            f"  Success Rate: {(metrics.successful_requests / metrics.total_requests * 100):.1f}%" if metrics.total_requests > 0 else "  Success Rate: N/A",
            f"  Avg Response Time: {metrics.average_response_time * 1000:.1f}ms",
            "",
            "Intent Classification:",
            f"  Average Confidence: {metrics.intent_confidence_avg:.1%}",
            f"  Clarification Rate: {metrics.clarification_rate:.1%}",
            "  Intent Distribution:"
        ]
        
        for intent, count in sorted(metrics.intent_classifications.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / metrics.total_requests * 100) if metrics.total_requests > 0 else 0
            summary.append(f"    - {intent}: {count} ({percentage:.1f}%)")
        
        summary.extend([
            "",
            "Tool Performance:",
            f"  Cache Hit Rate: {metrics.cache_hit_rate:.1f}%",
            "  Tool Execution Stats:"
        ])
        
        for tool, count in sorted(metrics.tool_executions.items(), key=lambda x: x[1], reverse=True):
            success_rate = metrics.tool_success_rates.get(tool, 0)
            avg_time = metrics.tool_avg_execution_times.get(tool, 0)
            summary.append(f"    - {tool}: {count} calls, {success_rate:.1f}% success, {avg_time*1000:.1f}ms avg")
        
        summary.extend([
            "",
            "Efficiency:",
            f"  LLM Calls Saved: {metrics.llm_calls_saved}",
            f"  Average Retry Count: {metrics.average_retry_count:.2f}"
        ])
        
        return "\n".join(summary)


# Global metrics instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector"""
    global _metrics_collector
    
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    
    return _metrics_collector