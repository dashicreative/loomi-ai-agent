"""
Temporal Reasoner - Universal date and time understanding for the agent

This module provides centralized temporal reasoning capabilities that can interpret
natural language time expressions consistently across all agent functions.
"""

from typing import Tuple, Optional, Dict, Any, List
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import re


class TemporalReference(Enum):
    """Types of temporal references"""
    SPECIFIC_DATE = "specific_date"  # "August 15", "2025-08-15"
    RELATIVE_DAY = "relative_day"    # "today", "tomorrow", "yesterday"
    RELATIVE_WEEK = "relative_week"  # "this week", "next week", "last week"
    RELATIVE_MONTH = "relative_month"  # "this month", "next month"
    WEEKDAY = "weekday"              # "Monday", "next Tuesday"
    DATE_RANGE = "date_range"        # "next 5 days", "this weekend"
    ALL_TIME = "all_time"            # "all", "everything"
    AMBIGUOUS = "ambiguous"          # unclear references


@dataclass
class TemporalContext:
    """Resolved temporal context from natural language"""
    reference_type: TemporalReference
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    confidence: float = 1.0
    original_phrase: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def is_single_day(self) -> bool:
        """Check if this represents a single day"""
        return self.start_date == self.end_date and self.start_date is not None
    
    def get_date_range(self) -> Tuple[Optional[str], Optional[str]]:
        """Get ISO formatted date range"""
        start = self.start_date.isoformat() if self.start_date else None
        end = self.end_date.isoformat() if self.end_date else None
        return start, end


class TemporalReasoner:
    """
    Universal temporal reasoning for natural language date/time expressions
    
    This class provides consistent interpretation of temporal expressions
    across all agent functions (scheduling, clearing, querying, etc.)
    """
    
    def __init__(self, reference_date: Optional[date] = None):
        """
        Initialize temporal reasoner
        
        Args:
            reference_date: The date to use as "today" (for testing)
        """
        self.reference_date = reference_date or date.today()
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for efficient matching"""
        # Relative day patterns
        self.today_pattern = re.compile(r'\b(today|tonight|this evening)\b', re.I)
        self.tomorrow_pattern = re.compile(r'\b(tomorrow)\b', re.I)
        self.yesterday_pattern = re.compile(r'\b(yesterday)\b', re.I)
        
        # Week patterns
        self.this_week_pattern = re.compile(r'\b(this week|current week)\b', re.I)
        self.next_week_pattern = re.compile(r'\b(next week)\b', re.I)
        self.last_week_pattern = re.compile(r'\b(last week|previous week)\b', re.I)
        
        # Month patterns
        self.this_month_pattern = re.compile(r'\b(this month|current month)\b', re.I)
        self.next_month_pattern = re.compile(r'\b(next month)\b', re.I)
        
        # Weekday patterns
        self.weekday_pattern = re.compile(
            r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.I
        )
        self.next_weekday_pattern = re.compile(
            r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.I
        )
        
        # Range patterns
        self.next_n_days_pattern = re.compile(r'\b(next|coming)\s+(\d+)\s+days?\b', re.I)
        self.weekend_pattern = re.compile(r'\b(this weekend|next weekend|weekend)\b', re.I)
        
        # All/everything patterns
        self.all_pattern = re.compile(r'\b(all|everything|entire schedule)\b', re.I)
    
    def interpret(self, phrase: str) -> TemporalContext:
        """
        Interpret a natural language temporal phrase
        
        Args:
            phrase: Natural language phrase containing temporal reference
            
        Returns:
            TemporalContext with resolved dates and metadata
        """
        phrase_lower = phrase.lower().strip()
        
        # Check for specific patterns in order of specificity
        
        # 1. Check for "all" or "everything"
        if self.all_pattern.search(phrase_lower):
            return TemporalContext(
                reference_type=TemporalReference.ALL_TIME,
                original_phrase=phrase,
                metadata={"scope": "all"}
            )
        
        # 2. Check for relative days
        if self.today_pattern.search(phrase_lower):
            return self._create_single_day_context(
                self.reference_date,
                TemporalReference.RELATIVE_DAY,
                phrase
            )
        
        if self.tomorrow_pattern.search(phrase_lower):
            tomorrow = self.reference_date + timedelta(days=1)
            return self._create_single_day_context(
                tomorrow,
                TemporalReference.RELATIVE_DAY,
                phrase
            )
        
        if self.yesterday_pattern.search(phrase_lower):
            yesterday = self.reference_date - timedelta(days=1)
            return self._create_single_day_context(
                yesterday,
                TemporalReference.RELATIVE_DAY,
                phrase
            )
        
        # 3. Check for week references
        if self.next_week_pattern.search(phrase_lower):
            return self._get_next_week_context(phrase)
        
        if self.this_week_pattern.search(phrase_lower):
            return self._get_this_week_context(phrase)
        
        if self.last_week_pattern.search(phrase_lower):
            return self._get_last_week_context(phrase)
        
        # 4. Check for month references
        if self.next_month_pattern.search(phrase_lower):
            return self._get_next_month_context(phrase)
        
        if self.this_month_pattern.search(phrase_lower):
            return self._get_this_month_context(phrase)
        
        # 5. Check for specific weekdays
        next_weekday_match = self.next_weekday_pattern.search(phrase_lower)
        if next_weekday_match:
            weekday_name = next_weekday_match.group(1)
            target_date = self._get_next_occurrence_of_weekday(weekday_name, skip_today=True)
            return self._create_single_day_context(
                target_date,
                TemporalReference.WEEKDAY,
                phrase,
                {"weekday": weekday_name, "next": True}
            )
        
        weekday_match = self.weekday_pattern.search(phrase_lower)
        if weekday_match:
            weekday_name = weekday_match.group(1)
            target_date = self._get_next_occurrence_of_weekday(weekday_name, skip_today=False)
            return self._create_single_day_context(
                target_date,
                TemporalReference.WEEKDAY,
                phrase,
                {"weekday": weekday_name}
            )
        
        # 6. Check for ranges
        next_n_days_match = self.next_n_days_pattern.search(phrase_lower)
        if next_n_days_match:
            num_days = int(next_n_days_match.group(2))
            start_date = self.reference_date + timedelta(days=1)
            end_date = self.reference_date + timedelta(days=num_days)
            return TemporalContext(
                reference_type=TemporalReference.DATE_RANGE,
                start_date=start_date,
                end_date=end_date,
                original_phrase=phrase,
                metadata={"days": num_days}
            )
        
        # 7. Check for weekend
        weekend_match = self.weekend_pattern.search(phrase_lower)
        if weekend_match:
            return self._get_weekend_context(phrase_lower, phrase)
        
        # 8. If no pattern matches, return ambiguous
        return TemporalContext(
            reference_type=TemporalReference.AMBIGUOUS,
            confidence=0.3,
            original_phrase=phrase
        )
    
    def _create_single_day_context(
        self,
        target_date: date,
        ref_type: TemporalReference,
        phrase: str,
        metadata: Optional[Dict] = None
    ) -> TemporalContext:
        """Create context for a single day"""
        return TemporalContext(
            reference_type=ref_type,
            start_date=target_date,
            end_date=target_date,
            original_phrase=phrase,
            metadata=metadata or {}
        )
    
    def _get_week_boundaries(self, week_offset: int = 0) -> Tuple[date, date]:
        """
        Get Sunday-Saturday boundaries for a week
        
        Args:
            week_offset: 0 for this week, 1 for next week, -1 for last week
        """
        # Find this week's Sunday
        days_since_sunday = self.reference_date.weekday() + 1
        if self.reference_date.weekday() == 6:  # Sunday
            days_since_sunday = 0
        
        this_sunday = self.reference_date - timedelta(days=days_since_sunday)
        
        # Apply week offset
        target_sunday = this_sunday + timedelta(weeks=week_offset)
        target_saturday = target_sunday + timedelta(days=6)
        
        return target_sunday, target_saturday
    
    def _get_this_week_context(self, phrase: str) -> TemporalContext:
        """Get context for 'this week'"""
        start_date, end_date = self._get_week_boundaries(0)
        return TemporalContext(
            reference_type=TemporalReference.RELATIVE_WEEK,
            start_date=start_date,
            end_date=end_date,
            original_phrase=phrase,
            metadata={"week": "this"}
        )
    
    def _get_next_week_context(self, phrase: str) -> TemporalContext:
        """Get context for 'next week'"""
        start_date, end_date = self._get_week_boundaries(1)
        return TemporalContext(
            reference_type=TemporalReference.RELATIVE_WEEK,
            start_date=start_date,
            end_date=end_date,
            original_phrase=phrase,
            metadata={"week": "next"}
        )
    
    def _get_last_week_context(self, phrase: str) -> TemporalContext:
        """Get context for 'last week'"""
        start_date, end_date = self._get_week_boundaries(-1)
        return TemporalContext(
            reference_type=TemporalReference.RELATIVE_WEEK,
            start_date=start_date,
            end_date=end_date,
            original_phrase=phrase,
            metadata={"week": "last"}
        )
    
    def _get_this_month_context(self, phrase: str) -> TemporalContext:
        """Get context for 'this month'"""
        start_date = self.reference_date.replace(day=1)
        # Get last day of month
        if self.reference_date.month == 12:
            end_date = self.reference_date.replace(year=self.reference_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = self.reference_date.replace(month=self.reference_date.month + 1, day=1) - timedelta(days=1)
        
        return TemporalContext(
            reference_type=TemporalReference.RELATIVE_MONTH,
            start_date=start_date,
            end_date=end_date,
            original_phrase=phrase,
            metadata={"month": "this"}
        )
    
    def _get_next_month_context(self, phrase: str) -> TemporalContext:
        """Get context for 'next month'"""
        # Get first day of next month
        if self.reference_date.month == 12:
            start_date = self.reference_date.replace(year=self.reference_date.year + 1, month=1, day=1)
        else:
            start_date = self.reference_date.replace(month=self.reference_date.month + 1, day=1)
        
        # Get last day of next month
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
        
        return TemporalContext(
            reference_type=TemporalReference.RELATIVE_MONTH,
            start_date=start_date,
            end_date=end_date,
            original_phrase=phrase,
            metadata={"month": "next"}
        )
    
    def _get_next_occurrence_of_weekday(self, weekday_name: str, skip_today: bool = False) -> date:
        """Get the next occurrence of a specific weekday"""
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays.get(weekday_name.lower())
        if target_weekday is None:
            return self.reference_date
        
        days_ahead = target_weekday - self.reference_date.weekday()
        
        if days_ahead < 0 or (days_ahead == 0 and skip_today):
            days_ahead += 7
        
        return self.reference_date + timedelta(days=days_ahead)
    
    def _get_weekend_context(self, phrase_lower: str, phrase: str) -> TemporalContext:
        """Get context for weekend references"""
        # Determine which weekend
        if "next" in phrase_lower:
            # Next weekend
            days_until_saturday = (5 - self.reference_date.weekday()) % 7
            if days_until_saturday == 0:  # Today is Saturday
                days_until_saturday = 7
            next_saturday = self.reference_date + timedelta(days=days_until_saturday + 7)
            next_sunday = next_saturday + timedelta(days=1)
        else:
            # This weekend
            days_until_saturday = (5 - self.reference_date.weekday()) % 7
            if days_until_saturday == 0 and self.reference_date.weekday() == 5:
                # Today is Saturday, include it
                next_saturday = self.reference_date
            else:
                next_saturday = self.reference_date + timedelta(days=days_until_saturday)
            next_sunday = next_saturday + timedelta(days=1)
        
        return TemporalContext(
            reference_type=TemporalReference.DATE_RANGE,
            start_date=next_saturday,
            end_date=next_sunday,
            original_phrase=phrase,
            metadata={"weekend": "next" if "next" in phrase_lower else "this"}
        )
    
    def describe_context(self, context: TemporalContext) -> str:
        """Generate a human-readable description of a temporal context"""
        if context.reference_type == TemporalReference.ALL_TIME:
            return "all time"
        
        if context.is_single_day() and context.start_date:
            if context.start_date == self.reference_date:
                return "today"
            elif context.start_date == self.reference_date + timedelta(days=1):
                return "tomorrow"
            else:
                return context.start_date.strftime("%A, %B %d")
        
        if context.start_date and context.end_date:
            return f"from {context.start_date.strftime('%B %d')} to {context.end_date.strftime('%B %d')}"
        
        return context.original_phrase