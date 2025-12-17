"""
Data models for the shift scheduling system.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime, time, timedelta
from enum import Enum


class DayOfWeek(Enum):
    """Days of the week."""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


@dataclass
class TimeSlot:
    """Represents a time slot for a shift."""
    day: DayOfWeek
    start_time: time
    end_time: time
    
    def duration_hours(self) -> float:
        """Calculate duration in hours."""
        start = datetime.combine(datetime.today(), self.start_time)
        end = datetime.combine(datetime.today(), self.end_time)
        if end < start:
            end += timedelta(days=1)
        return (end - start).total_seconds() / 3600.0


@dataclass
class StoreHours:
    """Store operating hours for each day of the week."""
    hours: Dict[DayOfWeek, tuple] = field(default_factory=dict)
    date_overrides: Dict[datetime, Optional[tuple]] = field(default_factory=dict)
    
    def _normalize_date(self, date: datetime) -> datetime:
        """Normalize date to date-only (no time component)."""
        return datetime(date.year, date.month, date.day)
    
    def set_hours(self, day: DayOfWeek, open_time: time, close_time: time):
        """Set hours for a specific day of the week."""
        self.hours[day] = (open_time, close_time)
    
    def set_hours_for_date(self, date: datetime, open_time: time, close_time: time):
        """Set hours for a specific date (overrides day of week)."""
        self.date_overrides[self._normalize_date(date)] = (open_time, close_time)
    
    def set_closed_for_date(self, date: datetime):
        """Mark a specific date as closed (overrides day of week)."""
        self.date_overrides[self._normalize_date(date)] = None
    
    def remove_date_override(self, date: datetime):
        """Remove date-specific override."""
        date_only = self._normalize_date(date)
        if date_only in self.date_overrides:
            del self.date_overrides[date_only]
    
    def get_hours(self, day: DayOfWeek, date: Optional[datetime] = None) -> Optional[tuple]:
        """Get hours for a specific day, checking date overrides first."""
        if date:
            date_only = self._normalize_date(date)
            if date_only in self.date_overrides:
                return self.date_overrides[date_only]
        return self.hours.get(day)
    
    def is_open(self, day: DayOfWeek, date: Optional[datetime] = None) -> bool:
        """Check if store is open on a given day, checking date overrides first."""
        if date:
            date_only = self._normalize_date(date)
            if date_only in self.date_overrides:
                return self.date_overrides[date_only] is not None
        return day in self.hours
    
    def get_date_override(self, date: datetime):
        """Get hours override for a specific date."""
        date_only = self._normalize_date(date)
        if date_only in self.date_overrides:
            return self.date_overrides[date_only]
        raise KeyError("No override for this date")
    
    def has_date_override(self, date: datetime) -> bool:
        """Check if there's an override (open or closed) for a specific date."""
        return self._normalize_date(date) in self.date_overrides


@dataclass
class Employee:
    """Employee information and preferences."""
    name: str
    preferred_days: List[DayOfWeek] = field(default_factory=list)
    preferred_start_time: Optional[time] = None  # Legacy: general preferred start time
    preferred_end_time: Optional[time] = None  # Legacy: general preferred end time
    preferred_times_by_day: Dict[DayOfWeek, tuple] = field(default_factory=dict)  # Day-specific preferred times
    available_times_by_day: Dict[DayOfWeek, tuple] = field(default_factory=dict)  # Day-specific available times (when not preferred/unavailable)
    unavailable_days: List[DayOfWeek] = field(default_factory=list)  # Days completely unavailable
    unavailable_times_by_day: Dict[DayOfWeek, tuple] = field(default_factory=dict)  # Time ranges when unavailable on specific days
    # Date-specific preferences (overrides day-of-week preferences)
    preferred_dates: List[datetime] = field(default_factory=list)  # Specific dates that are preferred
    preferred_times_by_date: Dict[datetime, tuple] = field(default_factory=dict)  # Preferred times for specific dates
    unavailable_dates: List[datetime] = field(default_factory=list)  # Specific dates that are completely unavailable
    unavailable_times_by_date: Dict[datetime, tuple] = field(default_factory=dict)  # Unavailable time ranges for specific dates
    available_times_by_date: Dict[datetime, tuple] = field(default_factory=dict)  # Available time ranges for specific dates
    max_hours_per_month: float = 160.0
    min_hours_per_shift: float = 4.0
    max_hours_per_shift: float = 8.0
    
    def can_work(self, day: DayOfWeek) -> bool:
        """Check if employee can work on a given day (not completely unavailable)."""
        return day not in self.unavailable_days
    
    def _normalize_date(self, date: datetime) -> datetime:
        """Normalize date to date-only (no time component)."""
        return datetime(date.year, date.month, date.day)
    
    def _time_to_datetime(self, date_or_today: datetime, time_obj: time) -> datetime:
        """Convert time to datetime for comparison."""
        dt = datetime.combine(date_or_today, time_obj)
        return dt
    
    def _times_overlap(self, start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
        """Check if two time ranges overlap."""
        if end1 < start1:
            end1 += timedelta(days=1)
        if end2 < start2:
            end2 += timedelta(days=1)
        return start1 < end2 and end1 > start2
    
    def _is_within_range(self, start: datetime, end: datetime, range_start: datetime, range_end: datetime) -> bool:
        """Check if a time range is within another time range."""
        if end < start:
            end += timedelta(days=1)
        if range_end < range_start:
            range_end += timedelta(days=1)
        return start >= range_start and end <= range_end
    
    def is_available_at_time(self, day: DayOfWeek, start_time: time, end_time: time, date: Optional[datetime] = None) -> bool:
        """Check if employee is available during a specific time range on a given day."""
        if date:
            date_only = self._normalize_date(date)
            base_date = date
            
            # Check date-specific unavailability
            if date_only in self.unavailable_dates:
                if date_only in self.unavailable_times_by_date:
                    unavail_start, unavail_end = self.unavailable_times_by_date[date_only]
                    shift_start = self._time_to_datetime(base_date, start_time)
                    shift_end = self._time_to_datetime(base_date, end_time)
                    unavail_start_dt = self._time_to_datetime(base_date, unavail_start)
                    unavail_end_dt = self._time_to_datetime(base_date, unavail_end)
                    return not self._times_overlap(shift_start, shift_end, unavail_start_dt, unavail_end_dt)
                return False
            
            # Check date-specific available times
            if date_only in self.available_times_by_date:
                avail_start, avail_end = self.available_times_by_date[date_only]
                shift_start = self._time_to_datetime(base_date, start_time)
                shift_end = self._time_to_datetime(base_date, end_time)
                avail_start_dt = self._time_to_datetime(base_date, avail_start)
                avail_end_dt = self._time_to_datetime(base_date, avail_end)
                return self._is_within_range(shift_start, shift_end, avail_start_dt, avail_end_dt)
        
        # Day-of-week preferences
        if day in self.unavailable_days and day not in self.unavailable_times_by_day:
            return False
        
        base_date = datetime.today()
        shift_start = self._time_to_datetime(base_date, start_time)
        shift_end = self._time_to_datetime(base_date, end_time)
        
        # Check day-specific unavailable times
        if day in self.unavailable_times_by_day:
            unavail_start, unavail_end = self.unavailable_times_by_day[day]
            unavail_start_dt = self._time_to_datetime(base_date, unavail_start)
            unavail_end_dt = self._time_to_datetime(base_date, unavail_end)
            if self._times_overlap(shift_start, shift_end, unavail_start_dt, unavail_end_dt):
                return False
        
        # Check day-specific available times
        if day in self.available_times_by_day:
            avail_start, avail_end = self.available_times_by_day[day]
            avail_start_dt = self._time_to_datetime(base_date, avail_start)
            avail_end_dt = self._time_to_datetime(base_date, avail_end)
            return self._is_within_range(shift_start, shift_end, avail_start_dt, avail_end_dt)
        
        return True
    
    def prefers_day(self, day: DayOfWeek, date: Optional[datetime] = None) -> bool:
        """Check if employee prefers a given day (checks date-specific preferences first)."""
        if date:
            date_only = self._normalize_date(date)
            if date_only in getattr(self, 'preferred_dates', []):
                return True
            if date_only in getattr(self, 'preferred_times_by_date', {}):
                return True
        return day in self.preferred_days
    
    def get_preferred_times(self, day: DayOfWeek) -> Optional[tuple]:
        """Get preferred times for a specific day."""
        if day in self.preferred_times_by_day:
            return self.preferred_times_by_day[day]
        if self.preferred_start_time and self.preferred_end_time:
            return (self.preferred_start_time, self.preferred_end_time)
        return None


@dataclass
class Shift:
    """A scheduled shift for an employee."""
    employee_name: str
    day: DayOfWeek
    start_time: time
    end_time: time
    date: Optional[datetime] = None
    
    def duration_hours(self) -> float:
        """Calculate shift duration in hours."""
        start = datetime.combine(datetime.today(), self.start_time)
        end = datetime.combine(datetime.today(), self.end_time)
        if end < start:
            end += timedelta(days=1)
        return (end - start).total_seconds() / 3600.0


@dataclass
class Schedule:
    """A monthly schedule containing all shifts."""
    month: int
    year: int
    shifts: List[Shift] = field(default_factory=list)
    
    def add_shift(self, shift: Shift):
        """Add a shift to the schedule."""
        self.shifts.append(shift)
    
    def get_shifts_for_employee(self, employee_name: str) -> List[Shift]:
        """Get all shifts for a specific employee."""
        return [s for s in self.shifts if s.employee_name == employee_name]
    
    def get_total_hours_for_employee(self, employee_name: str) -> float:
        """Calculate total hours worked by an employee."""
        return sum(s.duration_hours() for s in self.get_shifts_for_employee(employee_name))
    
    def get_shifts_for_day(self, day: DayOfWeek, date: Optional[datetime] = None) -> List[Shift]:
        """Get all shifts for a specific day."""
        if date:
            return [s for s in self.shifts if s.day == day and s.date == date]
        return [s for s in self.shifts if s.day == day]
