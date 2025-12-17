"""
Core scheduling algorithm for generating employee shift schedules.
"""
from typing import List, Dict
from datetime import datetime, time, timedelta
from models import (
    Employee, StoreHours, Shift, Schedule, DayOfWeek
)


class ShiftScheduler:
    """Generates shift schedules based on constraints and preferences."""
    
    def __init__(self, employees: List[Employee], store_hours: StoreHours):
        self.employees = employees
        self.store_hours = store_hours
    
    def generate_schedule(self, year: int, month: int) -> Schedule:
        """
        Generate a schedule for the given month.
        
        Args:
            year: Year for the schedule
            month: Month (1-12) for the schedule
            
        Returns:
            Schedule object with assigned shifts
        """
        schedule = Schedule(month=month, year=year)
        
        # Get all dates in the month
        dates = self._get_dates_in_month(year, month)
        
        # Track hours worked per employee
        employee_hours: Dict[str, float] = {emp.name: 0.0 for emp in self.employees}
        
        # Generate shifts for each day
        for date in dates:
            day_of_week = DayOfWeek(date.weekday())
            
            # Skip if store is closed (check date override first, then day of week)
            if not self.store_hours.is_open(day_of_week, date):
                continue
            
            hours = self.store_hours.get_hours(day_of_week, date)
            if hours is None:
                continue
            open_time, close_time = hours
            
            # Generate shifts for this day
            day_shifts = self._generate_shifts_for_day(
                day_of_week, date, open_time, close_time, employee_hours
            )
            
            # Add shifts to schedule (hours are already tracked in _generate_shifts_for_day)
            for shift in day_shifts:
                schedule.add_shift(shift)
        
        return schedule
    
    def _get_dates_in_month(self, year: int, month: int) -> List[datetime]:
        """Get all dates in a given month."""
        dates = []
        current_date = datetime(year, month, 1)
        
        while current_date.month == month:
            dates.append(current_date)
            current_date += timedelta(days=1)
        
        return dates
    
    def _generate_shifts_for_day(
        self,
        day: DayOfWeek,
        date: datetime,
        open_time: time,
        close_time: time,
        employee_hours: Dict[str, float]
    ) -> List[Shift]:
        """Generate shifts for a single day."""
        shifts = []
        
        # Get the date part (handle both date and datetime objects)
        if isinstance(date, datetime):
            date_only = date.date()
        else:
            date_only = date
        
        # Calculate total hours needed
        open_dt = datetime.combine(date_only, open_time)
        close_dt = datetime.combine(date_only, close_time)
        if close_dt < open_dt:
            close_dt += timedelta(days=1)
        
        total_hours = (close_dt - open_dt).total_seconds() / 3600.0
        
        # Get available employees for this day (basic check)
        # Store this outside the loop for fallback use
        initial_available_employees = [
            emp for emp in self.employees
            if emp.can_work(day) and 
            employee_hours[emp.name] < emp.max_hours_per_month
        ]
        
        if not initial_available_employees:
            return shifts
        
        available_employees = initial_available_employees
        
        # Sort employees by preference and hours worked (prioritize those who need hours)
        available_employees.sort(
            key=lambda e: (
                not e.prefers_day(day, date),
                employee_hours[e.name] / e.max_hours_per_month
            )
        )
        
        # Determine shift duration based on total hours
        # If <= 6 hours: 1 person, if > 6 hours: split among minimum people (at least 2)
        if total_hours <= 6.0:
            # Schedule 1 person for the entire duration
            shift_duration = total_hours
        else:
            # Calculate minimum number of people needed (at least 2)
            # Try to minimize people while keeping shifts reasonable (max 8 hours per person)
            max_shift_hours = 8.0
            num_people = max(2, int(total_hours / max_shift_hours) + (1 if total_hours % max_shift_hours > 0 else 0))
            shift_duration = total_hours / num_people
        
        # Generate shifts to cover the day
        # Use datetime for reliable time comparisons (handles midnight crossing)
        current_dt = open_dt
        
        max_iterations = 1000
        iteration = 0
        last_current_dt = None
        
        while current_dt < close_dt and iteration < max_iterations:
            iteration += 1
            
            # Re-filter available employees (in case they've hit max hours)
            available_employees = [
                emp for emp in self.employees
                if emp.can_work(day) and 
                employee_hours[emp.name] < emp.max_hours_per_month
            ]
            
            if not available_employees:
                # No employees available (all hit max hours), break
                break
            
            # Re-sort employees by preference and hours worked
            available_employees.sort(
                key=lambda e: (
                    not e.prefers_day(day, date),
                    employee_hours[e.name] / e.max_hours_per_month
                )
            )
            
            # Reset employee index when re-filtering (employee list may have changed)
            employee_index = 0
            
            # Calculate remaining time in the day
            remaining_time = (close_dt - current_dt).total_seconds() / 3600.0
            
            min_shift_duration = min(emp.min_hours_per_shift for emp in available_employees) if available_employees else 0
            if remaining_time < min_shift_duration:
                if len(shifts) > 0 or remaining_time < 0.25:
                    break
            
            # Find next available employee
            attempts = 0
            shift_created = False
            
            while attempts < len(available_employees) and not shift_created:
                emp = available_employees[employee_index % len(available_employees)]
                
                # Calculate potential shift duration for this employee
                remaining_hours = emp.max_hours_per_month - employee_hours[emp.name]
                
                # Try different shift durations, starting with ideal and working down
                potential_durations = sorted(set([
                    min(shift_duration, remaining_hours, remaining_time),
                    min(remaining_hours, remaining_time),
                    remaining_time
                ]), reverse=True)
                
                for actual_shift_duration in potential_durations:
                    allow_short_shift = (
                        len(shifts) == 0 and (
                            actual_shift_duration >= remaining_time * 0.8 or
                            remaining_time < emp.min_hours_per_shift
                        )
                    )
                    
                    if actual_shift_duration < emp.min_hours_per_shift and not allow_short_shift:
                        continue
                    if allow_short_shift and actual_shift_duration < 1.0:
                        continue
                    
                    end_dt = current_dt + timedelta(hours=actual_shift_duration)
                    if end_dt > close_dt:
                        end_dt = close_dt
                        actual_shift_duration = (end_dt - current_dt).total_seconds() / 3600.0
                        if actual_shift_duration < emp.min_hours_per_shift:
                            continue
                    
                    if emp.is_available_at_time(day, current_dt.time(), end_dt.time(), date):
                        shift = Shift(
                            employee_name=emp.name,
                            day=day,
                            start_time=current_dt.time(),
                            end_time=end_dt.time(),
                            date=date
                        )
                        
                        shifts.append(shift)
                        employee_hours[emp.name] += shift.duration_hours()
                        
                        current_dt = end_dt
                        employee_index += 1
                        shift_created = True
                        break  # Found a working shift, exit the duration loop
                
                if not shift_created:
                    employee_index += 1
                    attempts += 1
            
            if not shift_created:
                if len(shifts) == 0:
                    # Try minimal shift duration as last resort
                    for emp in available_employees:
                        min_duration = emp.min_hours_per_shift
                        if remaining_time >= min_duration:
                            end_dt = min(current_dt + timedelta(hours=min_duration), close_dt)
                            if emp.is_available_at_time(day, current_dt.time(), end_dt.time(), date):
                                shift = Shift(
                                    employee_name=emp.name,
                                    day=day,
                                    start_time=current_dt.time(),
                                    end_time=end_dt.time(),
                                    date=date
                                )
                                shifts.append(shift)
                                employee_hours[emp.name] += shift.duration_hours()
                                current_dt = end_dt
                                shift_created = True
                                break
                
                if not shift_created:
                    next_dt = current_dt + timedelta(minutes=15)
                    if last_current_dt == current_dt or next_dt >= close_dt:
                        break
                    last_current_dt = current_dt
                    current_dt = next_dt
                    employee_index = 0
        
        # Fallback: If no shifts were created, try simple approach
        if len(shifts) == 0:
            date_only = date.date() if isinstance(date, datetime) else date
            available_fallback = [
                emp for emp in self.employees
                if emp.can_work(day) and
                day not in emp.unavailable_days and
                not (hasattr(emp, 'unavailable_dates') and 
                     date_only in emp.unavailable_dates and
                     date_only not in getattr(emp, 'unavailable_times_by_date', {}))
            ]
            
            if available_fallback:
                total_hours_available = (close_dt - open_dt).total_seconds() / 3600.0
                if total_hours_available > 0:
                    emp = available_fallback[0]
                    remaining_hours = emp.max_hours_per_month - employee_hours.get(emp.name, 0)
                    shift_duration = min(total_hours_available, max(remaining_hours, 1.0), 8.0)
                    shift_duration = max(shift_duration, 1.0) if total_hours_available >= 1.0 else shift_duration
                    
                    if shift_duration > 0:
                        end_dt = min(open_dt + timedelta(hours=shift_duration), close_dt)
                        shift = Shift(
                            employee_name=emp.name,
                            day=day,
                            start_time=open_time,
                            end_time=end_dt.time(),
                            date=date
                        )
                        shifts.append(shift)
                        employee_hours[emp.name] = employee_hours.get(emp.name, 0) + shift.duration_hours()
        
        return shifts
    
