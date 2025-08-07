"""
Date Utilities - All date parsing and manipulation logic
"""

from datetime import date, timedelta
from typing import List, Optional


class DateUtils:
    """
    Date parsing and manipulation utilities
    """
    
    @staticmethod
    def get_tomorrow() -> str:
        """Get tomorrow's date in ISO format"""
        return (date.today() + timedelta(days=1)).isoformat()
    
    @staticmethod
    def get_next_weekday(weekday_name: str) -> str:
        """Get the next occurrence of a weekday (e.g., 'next monday')"""
        return DateUtils.get_next_weekday_date(weekday_name, date.today() + timedelta(days=7))
    
    @staticmethod  
    def get_upcoming_weekday(weekday_name: str) -> str:
        """Get the upcoming occurrence of a weekday (could be today if it matches)"""
        return DateUtils.get_next_weekday_date(weekday_name, date.today())
    
    @staticmethod
    def get_date_range(start_date: date, num_days: int) -> List[str]:
        """
        Generate a list of consecutive dates starting from start_date
        
        Args:
            start_date: Starting date
            num_days: Number of consecutive days
            
        Returns:
            List of ISO formatted date strings
        """
        dates = []
        for i in range(num_days):
            target_date = start_date + timedelta(days=i)
            dates.append(target_date.isoformat())
        return dates
    
    @staticmethod
    def get_next_weekday_date(weekday_name: str, from_date: Optional[date] = None) -> str:
        """
        Get the next occurrence of a weekday from a given date
        
        Args:
            weekday_name: Name of the weekday (e.g., "monday", "friday")
            from_date: Reference date (defaults to today)
            
        Returns:
            ISO formatted date string
        """
        if from_date is None:
            from_date = date.today()
            
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays.get(weekday_name.lower())
        if target_weekday is None:
            return from_date.isoformat()
        
        days_ahead = target_weekday - from_date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
            
        target_date = from_date + timedelta(days=days_ahead)
        return target_date.isoformat()
    
    @staticmethod
    def parse_relative_date(date_str: str, from_date: Optional[date] = None) -> Optional[str]:
        """
        Parse relative date strings to ISO format
        
        Args:
            date_str: Date string like "tomorrow", "next week", etc.
            from_date: Reference date (defaults to today)
            
        Returns:
            ISO formatted date string or None if not parseable
        """
        if from_date is None:
            from_date = date.today()
            
        date_lower = date_str.lower().strip()
        
        # Simple relative dates
        if date_lower == "today":
            return from_date.isoformat()
        elif date_lower == "tomorrow":
            return (from_date + timedelta(days=1)).isoformat()
        elif date_lower == "yesterday":
            return (from_date - timedelta(days=1)).isoformat()
        
        # Weekday names
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        if date_lower in weekdays:
            return DateUtils.get_next_weekday_date(date_lower, from_date)
        
        # "Next X days" patterns
        if "next" in date_lower and "days" in date_lower:
            try:
                # Extract number from string like "next 5 days"
                parts = date_lower.split()
                for part in parts:
                    if part.isdigit():
                        return DateUtils.get_date_range(from_date + timedelta(days=1), int(part))
            except:
                pass
        
        return None