"""
Streamlit application for employee shift scheduling.
"""
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, time, timedelta
from typing import Dict, Optional
import json
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO

from models import (
    Employee, StoreHours, DayOfWeek, Schedule
)
from scheduler import ShiftScheduler


# Shared utility functions
EMPLOYEE_COLOR_PALETTE = [
    '#2196F3',  # Blue
    '#9C27B0',  # Purple
    '#4CAF50',  # Green
    '#FF9800',  # Orange
    '#E91E63',  # Pink
    '#00BCD4',  # Cyan
    '#FFEB3B',  # Yellow
    '#795548',  # Brown
    '#3F51B5',  # Indigo
    '#009688',  # Teal
    '#FF5722',  # Deep Orange
    '#9E9E9E',  # Grey
    '#607D8B',  # Blue Grey
    '#8BC34A',  # Light Green
    '#FFC107',  # Amber
]


def get_employee_colors(employee_list):
    """Generate distinct colors for each employee."""
    color_map = {}
    for i, emp in enumerate(employee_list):
        color_map[emp] = EMPLOYEE_COLOR_PALETTE[i % len(EMPLOYEE_COLOR_PALETTE)]
    return color_map


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def is_dark_color(hex_color):
    """Check if a color is dark enough to need white text."""
    r, g, b = hex_to_rgb(hex_color)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance < 0.5


# Page configuration
st.set_page_config(
    page_title="Employee Shift Scheduler",
    page_icon="📅",
    layout="wide"
)

# Serialization functions for export/import
def serialize_store_hours(store_hours: StoreHours) -> Dict:
    """Serialize StoreHours to a dictionary."""
    # Use getattr for backward compatibility
    hours = getattr(store_hours, 'hours', {})
    date_overrides = getattr(store_hours, 'date_overrides', {})
    
    hours_dict = {}
    for day, times in hours.items():
        if times and len(times) == 2:
            hours_dict[day.name] = {
                "open": times[0].isoformat(),
                "close": times[1].isoformat()
            }
    
    date_overrides_dict = {}
    for date_obj, override in date_overrides.items():
        date_key = date_obj.strftime("%Y-%m-%d")
        if override is None:
            date_overrides_dict[date_key] = None
        else:
            if override and len(override) == 2:
                date_overrides_dict[date_key] = {
                    "open": override[0].isoformat(),
                    "close": override[1].isoformat()
                }
    
    return {
        "hours": hours_dict,
        "date_overrides": date_overrides_dict
    }


def deserialize_store_hours(data: Dict) -> StoreHours:
    """Deserialize dictionary to StoreHours."""
    store_hours = StoreHours()
    
    # Restore regular hours
    for day_name, times_dict in data.get("hours", {}).items():
        try:
            day = DayOfWeek[day_name]
            if times_dict and "open" in times_dict and "close" in times_dict:
                open_time = time.fromisoformat(times_dict["open"])
                close_time = time.fromisoformat(times_dict["close"])
                store_hours.set_hours(day, open_time, close_time)
        except (KeyError, ValueError) as e:
            # Skip invalid day names or time formats
            continue
    
    # Restore date overrides
    for date_key, override in data.get("date_overrides", {}).items():
        try:
            date_obj = datetime.strptime(date_key, "%Y-%m-%d")
            if override is None:
                store_hours.set_closed_for_date(date_obj)
            elif isinstance(override, dict) and "open" in override and "close" in override:
                open_time = time.fromisoformat(override["open"])
                close_time = time.fromisoformat(override["close"])
                store_hours.set_hours_for_date(date_obj, open_time, close_time)
        except (ValueError, KeyError) as e:
            # Skip invalid date formats or time formats
            continue
    
    return store_hours


def serialize_employee(employee: Employee) -> Dict:
    """Serialize Employee to a dictionary."""
    def serialize_time(t: time) -> str:
        return t.isoformat() if t else None
    
    def serialize_datetime(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d") if dt else None
    
    def serialize_times_dict(times_dict, key_func):
        """Serialize a times dictionary (by day or by date)."""
        return {
            key_func(k): {
                "start": serialize_time(times[0]),
                "end": serialize_time(times[1])
            }
            for k, times in times_dict.items()
            if times and len(times) == 2
        }
    
    return {
        "name": employee.name,
        "preferred_days": [day.name for day in getattr(employee, 'preferred_days', [])],
        "preferred_start_time": serialize_time(getattr(employee, 'preferred_start_time', None)),
        "preferred_end_time": serialize_time(getattr(employee, 'preferred_end_time', None)),
        "preferred_times_by_day": serialize_times_dict(
            getattr(employee, 'preferred_times_by_day', {}),
            lambda day: day.name
        ),
        "available_times_by_day": serialize_times_dict(
            getattr(employee, 'available_times_by_day', {}),
            lambda day: day.name
        ),
        "unavailable_days": [day.name for day in getattr(employee, 'unavailable_days', []) if day],
        "unavailable_times_by_day": serialize_times_dict(
            getattr(employee, 'unavailable_times_by_day', {}),
            lambda day: day.name
        ),
        "preferred_dates": [serialize_datetime(dt) for dt in getattr(employee, 'preferred_dates', []) if dt],
        "preferred_times_by_date": serialize_times_dict(
            getattr(employee, 'preferred_times_by_date', {}),
            serialize_datetime
        ),
        "unavailable_dates": [serialize_datetime(dt) for dt in getattr(employee, 'unavailable_dates', []) if dt],
        "unavailable_times_by_date": serialize_times_dict(
            getattr(employee, 'unavailable_times_by_date', {}),
            serialize_datetime
        ),
        "available_times_by_date": serialize_times_dict(
            getattr(employee, 'available_times_by_date', {}),
            serialize_datetime
        ),
        "max_hours_per_month": getattr(employee, 'max_hours_per_month', 160.0),
        "min_hours_per_shift": getattr(employee, 'min_hours_per_shift', 4.0),
        "max_hours_per_shift": getattr(employee, 'max_hours_per_shift', 8.0)
    }


def deserialize_employee(data: Dict) -> Employee:
    """Deserialize dictionary to Employee."""
    def deserialize_time(t_str: str) -> Optional[time]:
        try:
            return time.fromisoformat(t_str) if t_str else None
        except (ValueError, AttributeError):
            return None
    
    def deserialize_datetime(dt_str: str) -> Optional[datetime]:
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d") if dt_str else None
        except (ValueError, AttributeError):
            return None
    
    def deserialize_times_dict(times_dict, key_func):
        """Deserialize a times dictionary (by day or by date)."""
        result = {}
        if not isinstance(times_dict, dict):
            return result
        for key, times_data in times_dict.items():
            try:
                if not isinstance(times_data, dict):
                    continue
                start = deserialize_time(times_data.get("start"))
                end = deserialize_time(times_data.get("end"))
                if start and end:
                    result[key_func(key)] = (start, end)
            except (KeyError, ValueError, TypeError):
                # Skip invalid entries
                continue
        return result
    
    employee = Employee(
        name=data["name"],
        max_hours_per_month=data.get("max_hours_per_month", 160.0),
        min_hours_per_shift=data.get("min_hours_per_shift", 4.0),
        max_hours_per_shift=data.get("max_hours_per_shift", 8.0)
    )
    
    # Restore preferred days
    try:
        employee.preferred_days = [
            DayOfWeek[day_name] for day_name in data.get("preferred_days", [])
            if isinstance(day_name, str) and day_name.upper() in [d.name for d in DayOfWeek]
        ]
    except (KeyError, AttributeError):
        employee.preferred_days = []
    
    # Restore legacy preferred times
    if data.get("preferred_start_time"):
        employee.preferred_start_time = deserialize_time(data["preferred_start_time"])
    if data.get("preferred_end_time"):
        employee.preferred_end_time = deserialize_time(data["preferred_end_time"])
    
    # Restore times by day
    employee.preferred_times_by_day = deserialize_times_dict(
        data.get("preferred_times_by_day", {}),
        lambda name: DayOfWeek[name]
    )
    employee.available_times_by_day = deserialize_times_dict(
        data.get("available_times_by_day", {}),
        lambda name: DayOfWeek[name]
    )
    employee.unavailable_times_by_day = deserialize_times_dict(
        data.get("unavailable_times_by_day", {}),
        lambda name: DayOfWeek[name]
    )
    
    # Restore unavailable days
    try:
        employee.unavailable_days = [
            DayOfWeek[day_name] for day_name in data.get("unavailable_days", [])
            if isinstance(day_name, str) and day_name.upper() in [d.name for d in DayOfWeek]
        ]
    except (KeyError, AttributeError):
        employee.unavailable_days = []
    
    # Restore preferred dates
    employee.preferred_dates = [
        dt for dt_str in data.get("preferred_dates", [])
        if (dt := deserialize_datetime(dt_str))
    ]
    
    # Restore times by date
    employee.preferred_times_by_date = deserialize_times_dict(
        data.get("preferred_times_by_date", {}),
        deserialize_datetime
    )
    employee.unavailable_dates = [
        dt for dt_str in data.get("unavailable_dates", [])
        if (dt := deserialize_datetime(dt_str))
    ]
    employee.unavailable_times_by_date = deserialize_times_dict(
        data.get("unavailable_times_by_date", {}),
        deserialize_datetime
    )
    employee.available_times_by_date = deserialize_times_dict(
        data.get("available_times_by_date", {}),
        deserialize_datetime
    )
    
    return employee


# Initialize session state
def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        'employees': [],
        'store_hours': StoreHours(),
        'schedule': None,
        'current_page': "Store Hours"
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value
    
    # Ensure date_overrides exists (for backward compatibility)
    if not hasattr(st.session_state.store_hours, 'date_overrides'):
        st.session_state.store_hours.date_overrides = {}
    
    # Set default store hours if none are set
    if not st.session_state.store_hours.hours:
        # Weekdays (Monday-Friday): 6:00 PM - 11:00 PM
        for day in [DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, 
                     DayOfWeek.THURSDAY, DayOfWeek.FRIDAY]:
            st.session_state.store_hours.set_hours(day, time(18, 0), time(23, 0))
        
        # Saturday: 11:00 AM - 11:00 PM
        st.session_state.store_hours.set_hours(DayOfWeek.SATURDAY, time(11, 0), time(23, 0))
        
        # Sunday: 11:00 AM - 8:00 PM
        st.session_state.store_hours.set_hours(DayOfWeek.SUNDAY, time(11, 0), time(20, 0))

init_session_state()


def day_name(day: DayOfWeek) -> str:
    """Get day name from enum."""
    return day.name.capitalize()


def day_from_name(name: str) -> DayOfWeek:
    """Get day enum from name."""
    return DayOfWeek[name.upper()]


def normalize_date(date_obj: datetime) -> datetime:
    """Normalize datetime to date-only (no time component)."""
    return datetime(date_obj.year, date_obj.month, date_obj.day)


def get_month_info(year: int, month: int):
    """Get month information: first day, last day, number of days, start weekday."""
    first_day = datetime(year, month, 1)
    next_month = month % 12 + 1
    next_year = year + (1 if month == 12 else 0)
    last_day = datetime(next_year, next_month, 1) - timedelta(days=1)
    return first_day, last_day, last_day.day, first_day.weekday()


def format_time_range(start: time, end: time) -> str:
    """Format time range as string."""
    return f"{start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}"


def ensure_date_attributes(emp):
    """Ensure employee has all date-specific attributes initialized."""
    list_attrs = ['preferred_dates', 'unavailable_dates']
    dict_attrs = ['preferred_times_by_date', 'unavailable_times_by_date', 'available_times_by_date']
    for attr in list_attrs:
        if not hasattr(emp, attr):
            setattr(emp, attr, [])
    for attr in dict_attrs:
        if not hasattr(emp, attr):
            setattr(emp, attr, {})


def remove_preference_from_all_lists(emp, date_only):
    """Remove a date preference from all possible lists/dicts."""
    list_attrs = ['preferred_dates', 'unavailable_dates']
    dict_attrs = ['preferred_times_by_date', 'unavailable_times_by_date', 'available_times_by_date']
    
    for attr in list_attrs:
        attr_list = getattr(emp, attr, [])
        if date_only in attr_list:
            attr_list.remove(date_only)
    for attr in dict_attrs:
        attr_dict = getattr(emp, attr, {})
        if date_only in attr_dict:
            del attr_dict[date_only]


def clear_editing_state(i):
    """Clear all editing state variables for employee i."""
    for key in ['editing_pref_date', 'editing_pref_type', 'editing_pref_start', 'editing_pref_end']:
        if f"{key}_{i}" in st.session_state:
            del st.session_state[f"{key}_{i}"]


def has_date_preference(emp, date_only):
    """Check if employee has any preference for the given date."""
    list_attrs = ['preferred_dates', 'unavailable_dates']
    dict_attrs = ['preferred_times_by_date', 'unavailable_times_by_date', 'available_times_by_date']
    return (any(date_only in getattr(emp, attr, []) for attr in list_attrs) or 
            any(date_only in getattr(emp, attr, {}) for attr in dict_attrs))


def show_times_by_day(times_dict, title, suffix=""):
    """Display times by day in a formatted way."""
    if times_dict:
        st.markdown(f"**{title}:**")
        for day, times in sorted(times_dict.items(), key=lambda x: x[0].value):
            st.markdown(f"  {day_name(day)}: {format_time_range(times[0], times[1])}{suffix}")


def get_default_store_hours(day: DayOfWeek) -> tuple:
    """Get default store hours for a given day of week."""
    if day.value < 5:  # Monday through Friday
        return (time(18, 0), time(23, 0))  # 6:00 PM - 11:00 PM
    elif day.value == 5:  # Saturday
        return (time(11, 0), time(23, 0))  # 11:00 AM - 11:00 PM
    else:  # Sunday
        return (time(11, 0), time(20, 0))  # 11:00 AM - 8:00 PM


def show_employee_calendar_view(employee, year: int, month: int):
    """Display a calendar view showing employee date-specific preferences for each day of the month."""
    first_day, last_day, num_days, start_weekday = get_month_info(year, month)
    
    # Get employee date preferences
    preferred_dates = getattr(employee, 'preferred_dates', [])
    preferred_times_by_date = getattr(employee, 'preferred_times_by_date', {})
    unavailable_dates = getattr(employee, 'unavailable_dates', [])
    unavailable_times_by_date = getattr(employee, 'unavailable_times_by_date', {})
    available_times_by_date = getattr(employee, 'available_times_by_date', {})
    
    # Build calendar HTML table with controlled spacing
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    # Calculate number of weeks needed
    total_cells = start_weekday + num_days
    num_weeks = (total_cells + 6) // 7
    
    # Calculate dynamic height: header (~40px) + (num_weeks * ~112px per week with spacing)
    calendar_height = 40 + (num_weeks * 112) + 20  # Extra padding at bottom
    
    # Start building HTML
    html = '<style>.calendar-table { width: 100%; border-collapse: separate; border-spacing: 2px; } .calendar-cell { background-color: #f5f5f5; padding: 12px; border-radius: 5px; border: 1px solid #ddd; min-height: 110px; vertical-align: top; width: 14.28%; } .calendar-header { font-weight: bold; text-align: center; padding: 8px; background-color: #4472C4; color: #ffffff; }</style><table class="calendar-table"><tr>'
    
    # Header row
    for day_name_short in day_names:
        html += f'<th class="calendar-header">{day_name_short}</th>'
    html += '</tr>'
    
    # Calendar rows
    current_date = 1
    for week in range(num_weeks):
        html += '<tr>'
        for day_idx in range(7):
            if week == 0 and day_idx < start_weekday:
                # Empty cell before month starts
                html += '<td class="calendar-cell"></td>'
            elif current_date <= num_days:
                # Day cell
                date_obj = datetime(year, month, current_date)
                date_only = normalize_date(date_obj)
                
                # Check for date-specific preferences
                pref_text = ""
                bg_color = "#f5f5f5"  # Default light gray
                
                # Check preferred dates (all day)
                if date_only in preferred_dates:
                    pref_text = "<strong>Preferred</strong> (all day)"
                    bg_color = "#e3f2fd"  # Light blue
                # Check preferred times by date
                elif date_only in preferred_times_by_date:
                    times = preferred_times_by_date[date_only]
                    pref_text = f"<strong>Preferred</strong><br>{format_time_range(times[0], times[1])}"
                    bg_color = "#e3f2fd"  # Light blue
                # Check unavailable dates (all day)
                elif date_only in unavailable_dates:
                    pref_text = "<strong>Unavailable</strong> (all day)"
                    bg_color = "#ffebee"  # Light red
                # Check unavailable times by date
                elif date_only in unavailable_times_by_date:
                    times = unavailable_times_by_date[date_only]
                    pref_text = f"<strong>Unavailable</strong><br>{format_time_range(times[0], times[1])}"
                    bg_color = "#fff3e0"  # Light orange
                # Check available times by date
                elif date_only in available_times_by_date:
                    times = available_times_by_date[date_only]
                    pref_text = f"<strong>Available Only</strong><br>{format_time_range(times[0], times[1])}"
                    bg_color = "#f1f8e9"  # Light green
                else:
                    # No date-specific preference, show day of week info
                    day_of_week = DayOfWeek(date_obj.weekday())
                    if day_of_week in getattr(employee, 'preferred_days', []):
                        pref_text = "Preferred (weekly)"
                        bg_color = "#e8eaf6"  # Very light purple
                    elif day_of_week in getattr(employee, 'unavailable_days', []):
                        pref_text = "Unavailable (weekly)"
                        bg_color = "#fce4ec"  # Very light pink
                    else:
                        pref_text = "Regular"
                        bg_color = "#f5f5f5"  # Light gray
                
                html += f'<td class="calendar-cell" style="background-color: {bg_color};"><div style="font-size: 18px; font-weight: bold; margin-bottom: 8px; color: #333333;">{current_date}</div><div style="font-size: 12px; line-height: 1.4; word-wrap: break-word; color: #333333;">{pref_text}</div></td>'
                current_date += 1
            else:
                # Empty cell after month ends
                html += '<td class="calendar-cell"></td>'
        html += '</tr>'
    
    html += '</table>'
    components.html(html, height=calendar_height)


def show_calendar_view(year: int, month: int):
    """Display a calendar view showing store hours for each day of the month."""
    first_day, last_day, num_days, start_weekday = get_month_info(year, month)
    
    # Build calendar HTML table with controlled spacing
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    date_overrides = getattr(st.session_state.store_hours, 'date_overrides', {})
    
    # Calculate number of weeks needed
    total_cells = start_weekday + num_days
    num_weeks = (total_cells + 6) // 7
    
    # Calculate dynamic height: header (~40px) + (num_weeks * ~112px per week with spacing)
    calendar_height = 40 + (num_weeks * 112) + 20  # Extra padding at bottom
    
    # Start building HTML
    html = '<style>.calendar-table { width: 100%; border-collapse: separate; border-spacing: 2px; } .calendar-cell { background-color: #f5f5f5; padding: 12px; border-radius: 5px; border: 1px solid #ddd; min-height: 110px; vertical-align: top; width: 14.28%; } .calendar-header { font-weight: bold; text-align: center; padding: 8px; background-color: #4472C4; color: #ffffff; }</style><table class="calendar-table"><tr>'
    
    # Header row
    for day_name_short in day_names:
        html += f'<th class="calendar-header">{day_name_short}</th>'
    html += '</tr>'
    
    # Calendar rows
    current_date = 1
    for week in range(num_weeks):
        html += '<tr>'
        for day_idx in range(7):
            if week == 0 and day_idx < start_weekday:
                # Empty cell before month starts
                html += '<td class="calendar-cell"></td>'
            elif current_date <= num_days:
                # Day cell
                date_obj = datetime(year, month, current_date)
                date_only = normalize_date(date_obj)
                
                # Check for date override first
                has_override = date_only in date_overrides
                if has_override:
                    override = date_overrides[date_only]
                    if override is None:
                        # Explicitly closed
                        hours_text = "<strong>CLOSED</strong>"
                        bg_color = "#ffebee"  # Light red
                    else:
                        # Has specific hours
                        hours_text = format_time_range(override[0], override[1])
                        bg_color = "#e8f5e9"  # Light green
                else:
                    # Use day of week hours
                    day_of_week = DayOfWeek(date_obj.weekday())
                    day_hours = st.session_state.store_hours.get_hours(day_of_week)
                    if day_hours:
                        hours_text = format_time_range(day_hours[0], day_hours[1])
                        bg_color = "#f5f5f5"  # Light gray
                    else:
                        hours_text = "<strong>CLOSED</strong>"
                        bg_color = "#ffebee"  # Light red
                
                html += f'<td class="calendar-cell" style="background-color: {bg_color};"><div style="font-size: 18px; font-weight: bold; margin-bottom: 8px; color: #333333;">{current_date}</div><div style="font-size: 12px; line-height: 1.4; word-wrap: break-word; color: #333333;">{hours_text}</div></td>'
                current_date += 1
            else:
                # Empty cell after month ends
                html += '<td class="calendar-cell"></td>'
        html += '</tr>'
    
    html += '</table>'
    components.html(html, height=calendar_height)


def show_schedule_calendar_view(schedule: Schedule, year: int, month: int):
    """Display a calendar view showing shifts for each day of the month."""
    first_day, last_day, num_days, start_weekday = get_month_info(year, month)
    
    # Build calendar HTML table with controlled spacing
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    # Group shifts by date
    shifts_by_date = {}
    for shift in schedule.shifts:
        if shift.date:
            date_only = normalize_date(shift.date)
            if date_only not in shifts_by_date:
                shifts_by_date[date_only] = []
            shifts_by_date[date_only].append(shift)
    
    # Get unique employees and assign colors
    unique_employees = sorted(set(s.employee_name for s in schedule.shifts))
    
    # Generate color mapping for employees
    employee_colors = get_employee_colors(unique_employees)
    
    # Calculate number of weeks needed
    total_cells = start_weekday + num_days
    num_weeks = (total_cells + 6) // 7
    
    # Calculate dynamic height: header (~40px) + (num_weeks * ~130px per week with spacing)
    # Increased height to account for cells with multiple shifts
    calendar_height = 40 + (num_weeks * 130) + 30  # Extra padding at bottom
    
    # Start building HTML
    html = '<style>.calendar-table { width: 100%; border-collapse: separate; border-spacing: 2px; } .calendar-cell { background-color: #f5f5f5; padding: 12px; border-radius: 5px; border: 1px solid #ddd; min-height: 120px; vertical-align: top; width: 14.28%; } .calendar-header { font-weight: bold; text-align: center; padding: 8px; background-color: #4472C4; color: #ffffff; } .shift-entry { font-size: 11px; line-height: 1.3; margin-bottom: 4px; padding: 2px 4px; border-radius: 3px; }</style><table class="calendar-table"><tr>'
    
    # Header row
    for day_name_short in day_names:
        html += f'<th class="calendar-header">{day_name_short}</th>'
    html += '</tr>'
    
    # Calendar rows
    current_date = 1
    for week in range(num_weeks):
        html += '<tr>'
        for day_idx in range(7):
            if week == 0 and day_idx < start_weekday:
                # Empty cell before month starts
                html += '<td class="calendar-cell"></td>'
            elif current_date <= num_days:
                # Day cell
                date_obj = datetime(year, month, current_date)
                date_only = normalize_date(date_obj)
                
                # Get shifts for this date
                day_shifts = shifts_by_date.get(date_only, [])
                day_shifts.sort(key=lambda x: x.start_time)
                
                # Build cell content
                cell_content = f'<div style="font-size: 18px; font-weight: bold; margin-bottom: 8px; color: #333333;">{current_date}</div>'
                
                if day_shifts:
                    for shift in day_shifts:
                        duration = shift.duration_hours()
                        employee_color = employee_colors.get(shift.employee_name, "#2196F3")
                        # Determine text color based on background brightness
                        text_color = "#ffffff" if is_dark_color(employee_color) else "#000000"
                        shift_text = f"<strong style=\"color: {text_color};\">{shift.employee_name}</strong><br><span style=\"color: {text_color};\">{shift.start_time.strftime('%I:%M %p')} - {shift.end_time.strftime('%I:%M %p')}<br>({duration:.1f}h)</span>"
                        cell_content += f'<div class="shift-entry" style="background-color: {employee_color};">{shift_text}</div>'
                    bg_color = "#e8f5e9"  # Light green background for cells with shifts
                else:
                    cell_content += '<div style="font-size: 12px; color: #999;">No shifts</div>'
                    bg_color = "#f5f5f5"  # Light gray
                
                html += f'<td class="calendar-cell" style="background-color: {bg_color};">{cell_content}</td>'
                current_date += 1
            else:
                # Empty cell after month ends
                html += '<td class="calendar-cell"></td>'
        html += '</tr>'
    
    html += '</table>'
    components.html(html, height=calendar_height)


def main():
    # Add CSS to remove top spacing
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 0.5rem !important;
    }
    header[data-testid="stHeader"] {
        padding-top: 0rem !important;
    }
    #MainMenu {
        visibility: hidden;
    }
    footer {
        visibility: hidden;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Sidebar for navigation with buttons
    st.sidebar.header("Navigation")
    
    # Navigation buttons
    if st.sidebar.button("🏪 Store Hours", use_container_width=True, type="primary" if st.session_state.current_page == "Store Hours" else "secondary"):
        st.session_state.current_page = "Store Hours"
        st.rerun()
    
    if st.sidebar.button("👥 Employees", use_container_width=True, type="primary" if st.session_state.current_page == "Employees" else "secondary"):
        st.session_state.current_page = "Employees"
        st.rerun()
    
    if st.sidebar.button("⚙️ Generate Schedule", use_container_width=True, type="primary" if st.session_state.current_page == "Generate Schedule" else "secondary"):
        st.session_state.current_page = "Generate Schedule"
        st.rerun()
    
    if st.sidebar.button("📋 View Schedule", use_container_width=True, type="primary" if st.session_state.current_page == "View Schedule" else "secondary"):
        st.session_state.current_page = "View Schedule"
        st.rerun()
    
    # Data Management Section
    st.sidebar.divider()
    st.sidebar.header("💾 Data Management")
    
    # Export data
    export_data = {
        "store_hours": serialize_store_hours(st.session_state.store_hours),
        "employees": [serialize_employee(emp) for emp in st.session_state.employees]
    }
    json_data = json.dumps(export_data, indent=2)
    st.sidebar.download_button(
        label="📤 Export Data",
        data=json_data,
        file_name=f"scheduling_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        use_container_width=True
    )
    
    # Import data
    uploaded_file = st.sidebar.file_uploader(
        "📥 Import Data",
        type=['json'],
        help="Upload a previously exported JSON file to restore store hours and employees",
        key="import_data_file"
    )
    
    # Track last processed file to avoid reprocessing
    if 'last_imported_file_name' not in st.session_state:
        st.session_state.last_imported_file_name = None
    
    if uploaded_file is not None:
        # Check if this is a new file (different from last processed)
        current_file_name = uploaded_file.name if hasattr(uploaded_file, 'name') else str(uploaded_file)
        
        if current_file_name != st.session_state.last_imported_file_name:
            try:
                # Streamlit file uploader returns bytes, need to decode to string
                file_content = uploaded_file.read().decode('utf-8')
                data = json.loads(file_content)
                
                # Restore store hours
                if "store_hours" in data:
                    st.session_state.store_hours = deserialize_store_hours(data["store_hours"])
                    # Ensure date_overrides attribute exists
                    if not hasattr(st.session_state.store_hours, 'date_overrides'):
                        st.session_state.store_hours.date_overrides = {}
                
                # Restore employees
                if "employees" in data:
                    employees_list = []
                    for emp_data in data["employees"]:
                        emp = deserialize_employee(emp_data)
                        # Ensure all date-specific attributes are initialized
                        ensure_date_attributes(emp)
                        employees_list.append(emp)
                    st.session_state.employees = employees_list
                
                # Mark this file as processed
                st.session_state.last_imported_file_name = current_file_name
                
                # Show success messages and force UI refresh
                if "store_hours" in data:
                    st.sidebar.success("Store hours imported successfully!")
                if "employees" in data:
                    st.sidebar.success(f"{len(data['employees'])} employees imported successfully!")
                
                # Clear any existing schedule since data has changed
                st.session_state.schedule = None
                
                # Force UI refresh
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Error importing data: {str(e)}")
                import traceback
                st.sidebar.exception(e)
    
    # Display the current page
    page = st.session_state.current_page
    
    if page == "Store Hours":
        show_store_hours_page()
    elif page == "Employees":
        show_employees_page()
    elif page == "Generate Schedule":
        show_generate_schedule_page()
    elif page == "View Schedule":
        show_view_schedule_page()


def show_store_hours_page():
    """Display page for setting store hours."""
    st.header("Store Hours of Operation")
    
    # Monthly Calendar View at the top
    st.markdown("**📆 Monthly Calendar View**")
    st.caption("View store hours for an entire month in calendar format.")
    
    # Month/year selector
    col_cal1, col_cal2 = st.columns(2)
    with col_cal1:
        calendar_month = st.selectbox(
            "Month",
            options=list(range(1, 13)),
            format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
            index=datetime.now().month - 1,
            key="calendar_month"
        )
    with col_cal2:
        calendar_year = st.number_input(
            "Year",
            min_value=2020,
            max_value=2100,
            value=datetime.now().year,
            key="calendar_year"
        )
    
    # Add CSS to reduce spacing between calendar and tabs
    st.markdown("""
    <style>
    iframe[title*="streamlit"] {
        margin-bottom: -2rem !important;
    }
    .stTabs {
        margin-top: -2rem !important;
        padding-top: 0 !important;
    }
    div[data-testid="stTabs"] {
        margin-top: -2rem !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Display calendar
    show_calendar_view(calendar_year, calendar_month)
    
    st.markdown("**📅 Weekly Hours**")
    st.markdown("Set the operating hours for each day of the week.")
    
    days = list(DayOfWeek)
    
    # Create 7 columns for the 7 days of the week
    cols = st.columns(7)
    
    # Store the time inputs in a dictionary to collect them before saving
    weekly_hours_inputs = {}
    
    for i, day in enumerate(days):
        with cols[i]:
            st.markdown(f"**{day_name(day)}**")
            
            # Get current hours if set, otherwise use defaults
            current_hours = st.session_state.store_hours.get_hours(day)
            if current_hours:
                default_open, default_close = current_hours
            else:
                default_open, default_close = get_default_store_hours(day)
            
            open_time = st.time_input(
                "Open",
                value=default_open,
                key=f"open_{day.name}"
            )
            
            close_time = st.time_input(
                "Close",
                value=default_close,
                key=f"close_{day.name}"
            )
            
            # Store the inputs for later saving
            weekly_hours_inputs[day] = (open_time, close_time)
            
            # Add a clear button to close the store on this day
            if st.session_state.store_hours.is_open(day):
                if st.button("Clear", key=f"clear_{day.name}", use_container_width=True):
                    if day in st.session_state.store_hours.hours:
                        del st.session_state.store_hours.hours[day]
                    st.rerun()
            else:
                st.caption("Closed")
    
    # Save button for weekly hours
    if st.button("💾 Save Weekly Hours", type="primary", use_container_width=True, key="save_weekly_hours"):
        for day, (open_time, close_time) in weekly_hours_inputs.items():
            if open_time and close_time:
                st.session_state.store_hours.set_hours(day, open_time, close_time)
            elif day in st.session_state.store_hours.hours:
                del st.session_state.store_hours.hours[day]
        st.success("Weekly hours saved!")
        st.rerun()
    
    st.divider()
    st.markdown("**📆 Date-Specific Hours**")
    st.markdown("Override store hours for specific dates (e.g., holidays, special events).")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("**Set Date-Specific Hours**")
        
        # Check if we're editing a selected override
        editing_override_date = st.session_state.get("editing_override_date")
        
        # Use a dynamic key that changes when we start editing to force widget recreation
        if editing_override_date:
            editing_date = editing_override_date.date() if hasattr(editing_override_date, 'date') else editing_override_date
            # Use a key that includes the editing date to force widget update
            date_key = f"override_date_editing_{editing_date}"
            date_value = editing_date
            st.caption(f"✏️ Editing: {editing_override_date.strftime('%B %d, %Y')}")
        else:
            # Not editing - use standard key
            date_key = "override_date"
            date_value = st.session_state.get("override_date", datetime.now().date())
        
        selected_date = st.date_input(
            "Select Date",
            value=date_value,
            key=date_key
        )
        
        # Check if there's an existing override for this date
        date_dt = datetime.combine(selected_date, time.min)
        date_only = normalize_date(date_dt)
        # Use hasattr check for backward compatibility
        date_overrides = getattr(st.session_state.store_hours, 'date_overrides', {})
        has_override = date_only in date_overrides
        
        # If editing, use the editing date's override, otherwise check selected date
        if editing_override_date:
            edit_date_only = normalize_date(editing_override_date)
            if edit_date_only in date_overrides:
                existing_override = date_overrides[edit_date_only]
                if existing_override is None:
                    is_closed = True
                    day_of_week = DayOfWeek(editing_override_date.weekday())
                    day_hours = st.session_state.store_hours.get_hours(day_of_week)
                    if day_hours:
                        default_open, default_close = day_hours
                    else:
                        default_open, default_close = get_default_store_hours(day_of_week)
                else:
                    default_open = existing_override[0]
                    default_close = existing_override[1]
                    is_closed = False
            else:
                day_of_week = DayOfWeek(editing_override_date.weekday())
                day_hours = st.session_state.store_hours.get_hours(day_of_week)
                if day_hours:
                    default_open, default_close = day_hours
                    is_closed = False
                else:
                    default_open, default_close = get_default_store_hours(day_of_week)
                    is_closed = True
        elif has_override:
            # Get existing override (backward compatible)
            existing_override = date_overrides.get(date_only)
            if existing_override is None:
                # Explicitly closed
                is_closed = True
                day_of_week = DayOfWeek(selected_date.weekday())
                day_hours = st.session_state.store_hours.get_hours(day_of_week)
                if day_hours:
                    default_open = day_hours[0]
                    default_close = day_hours[1]
                else:
                    # Use default hours for this day of week
                    default_open, default_close = get_default_store_hours(day_of_week)
            else:
                # Has specific hours
                default_open = existing_override[0]
                default_close = existing_override[1]
                is_closed = False
        else:
            # Use the day of week hours as default
            day_of_week = DayOfWeek(selected_date.weekday())
            day_hours = st.session_state.store_hours.get_hours(day_of_week)
            if day_hours:
                default_open = day_hours[0]
                default_close = day_hours[1]
                is_closed = False
            else:
                # Use default hours for this day of week
                default_open, default_close = get_default_store_hours(day_of_week)
                is_closed = True
        
        # Use dynamic keys for time inputs when editing to force update
        if editing_override_date:
            open_time_key = f"override_open_time_editing_{editing_date}"
            close_time_key = f"override_close_time_editing_{editing_date}"
            checkbox_key = f"close_override_date_editing_{editing_date}"
        else:
            open_time_key = "override_open_time"
            close_time_key = "override_close_time"
            checkbox_key = "close_override_date"
        
        override_open = st.time_input(
            "Open Time",
            value=default_open,
            key=open_time_key,
            disabled=is_closed
        )
        
        override_close = st.time_input(
            "Close Time",
            value=default_close,
            key=close_time_key,
            disabled=is_closed
        )
        
        close_store = st.checkbox(
            "Close store on this date",
            value=is_closed,
            key=checkbox_key
        )
        
        # Change button text based on whether we're editing
        button_text = "Save" if editing_override_date else "Set Override"
        if st.button(button_text, type="primary", use_container_width=True):
            # If editing, remove old override first
            if editing_override_date:
                old_date_only = normalize_date(editing_override_date)
                if old_date_only in st.session_state.store_hours.date_overrides:
                    del st.session_state.store_hours.date_overrides[old_date_only]
                # Clear editing state
                if "editing_override_date" in st.session_state:
                    del st.session_state["editing_override_date"]
            
            if close_store:
                # Mark date as explicitly closed
                if hasattr(st.session_state.store_hours, 'set_closed_for_date'):
                    st.session_state.store_hours.set_closed_for_date(date_dt)
                else:
                    # Fallback: store None in date_overrides
                    date_only = normalize_date(date_dt)
                    st.session_state.store_hours.date_overrides[date_only] = None
                st.success(f"Store marked as closed on {selected_date.strftime('%B %d, %Y')}")
            else:
                if hasattr(st.session_state.store_hours, 'set_hours_for_date'):
                    st.session_state.store_hours.set_hours_for_date(
                        date_dt, override_open, override_close
                    )
                else:
                    # Fallback: store directly in date_overrides
                    date_only = normalize_date(date_dt)
                    st.session_state.store_hours.date_overrides[date_only] = (override_open, override_close)
                st.success(f"Hours set for {selected_date.strftime('%B %d, %Y')}")
            st.rerun()
        
        # Cancel editing button if in edit mode
        if editing_override_date:
            if st.button("Cancel Editing", use_container_width=True):
                if "editing_override_date" in st.session_state:
                    editing_date = st.session_state["editing_override_date"]
                    editing_date_only = editing_date.date() if hasattr(editing_date, 'date') else editing_date
                    # Clear the editing-specific keys
                    old_date_key = f"override_date_editing_{editing_date_only}"
                    old_checkbox_key = f"close_override_date_editing_{editing_date_only}"
                    old_open_key = f"override_open_time_editing_{editing_date_only}"
                    old_close_key = f"override_close_time_editing_{editing_date_only}"
                    for old_key in [old_date_key, old_checkbox_key, old_open_key, old_close_key]:
                        if old_key in st.session_state:
                            del st.session_state[old_key]
                    del st.session_state["editing_override_date"]
                st.rerun()
        
        # Check if there's an existing override for the selected date
        date_dt_check = datetime.combine(selected_date, time.min)
        date_only_check = normalize_date(date_dt_check)
        has_override_for_selected = date_only_check in date_overrides
        
        if has_override_for_selected and st.button("Remove Override", use_container_width=True):
            if hasattr(st.session_state.store_hours, 'remove_date_override'):
                st.session_state.store_hours.remove_date_override(date_dt_check)
            else:
                # Fallback: remove directly from date_overrides
                if date_only_check in st.session_state.store_hours.date_overrides:
                    del st.session_state.store_hours.date_overrides[date_only_check]
            # Clear editing state if this was the override being edited
            if editing_override_date and date_only_check == normalize_date(editing_override_date):
                if "editing_override_date" in st.session_state:
                    del st.session_state["editing_override_date"]
            st.success(f"Override removed for {selected_date.strftime('%B %d, %Y')}")
            st.rerun()
    
    with col2:
        st.markdown("**Active Date Overrides:**")
        st.caption("Click an override to edit it:")
        
        date_overrides = getattr(st.session_state.store_hours, 'date_overrides', {})
        if date_overrides:
            # Sort dates
            sorted_dates = sorted(date_overrides.keys())
            
            # Display clickable overrides
            for date in sorted_dates:
                hours = date_overrides[date]
                if hours is None:
                    hours_str = "CLOSED"
                else:
                    hours_str = f"{hours[0].strftime('%I:%M %p')} - {hours[1].strftime('%I:%M %p')}"
                
                override_text = f"{date.strftime('%B %d, %Y')} - {day_name(DayOfWeek(date.weekday()))} - {hours_str}"
                
                if st.button(override_text, key=f"click_override_{date}", use_container_width=True):
                    # Store selected override info in session state to populate form
                    st.session_state["editing_override_date"] = date
                    # Clear any old editing date keys to force widget recreation
                    editing_date = date.date() if hasattr(date, 'date') else date
                    old_date_key = f"override_date_editing_{editing_date}"
                    old_checkbox_key = f"close_override_date_editing_{editing_date}"
                    old_open_key = f"override_open_time_editing_{editing_date}"
                    old_close_key = f"override_close_time_editing_{editing_date}"
                    for old_key in [old_date_key, old_checkbox_key, old_open_key, old_close_key]:
                        if old_key in st.session_state:
                            del st.session_state[old_key]
                    st.rerun()
        else:
            st.caption("No date-specific overrides set. Use the form to add overrides.")


def show_employees_page():
    """Display page for managing employees."""
    st.header("Employee Management")
    
    # Create tabs: "Add New Employee" first, then employee tabs
    tab_labels = ["➕ Add New Employee"]
    if st.session_state.employees:
        tab_labels.extend([f"👤 {emp.name}" for emp in st.session_state.employees])
    
    all_tabs = st.tabs(tab_labels)
    
    # Add New Employee tab
    with all_tabs[0]:
        st.markdown("Add and manage employee information, preferences, and availability.")
        
        # Add new employee form
        emp_name = st.text_input("Employee Name", key="new_emp_name")
        
        max_hours = st.number_input(
            "Maximum Hours per Month",
            min_value=0.0,
            max_value=300.0,
            value=160.0,
            step=1.0,
            key="new_emp_max_hours"
        )
        
        st.markdown("**Preferred Work Days & Times**")
        st.markdown("Select preferred days and set preferred work times for each day (hourly increments only).")
        st.info("💡 **Tip:** \n"
                "- **Preferred + times**: Preferred work times for that day\n"
                "- **Preferred (no times)**: Available all day, prefers this day\n"
                "- **Unavailable + times**: Unavailable during those hours (available at other times)\n"
                "- **Unavailable (no times)**: Entire day unavailable\n"
                "- **Neither checked + times**: Available only during those hours\n"
                "- **Neither checked (no times)**: Available all day (just not preferred)")
        
        preferred_days = []
        preferred_times_by_day = {}
        available_times_by_day = {}
        unavailable_days = []
        unavailable_times_by_day = {}
        
        # Hour options (0-23)
        hour_options = list(range(24))
        hour_labels = [f"{h:02d}:00" for h in hour_options]
        
        # Create a table-like layout with day name, preferred checkbox, unavailable checkbox, and times
        for day in DayOfWeek:
            day_cols = st.columns([1, 1, 1, 1.5, 1.5])
            
            with day_cols[0]:
                st.markdown(f"**{day_name(day)}**")
            
            with day_cols[1]:
                is_preferred = st.checkbox(
                    "Preferred",
                    key=f"pref_{day.name}",
                    help="Mark this as a preferred work day"
                )
            
            with day_cols[2]:
                is_unavailable = st.checkbox(
                    "Unavailable",
                    key=f"unavail_{day.name}",
                    help="Mark this day as unavailable. If times are set, only those hours are unavailable."
                )
            
            with day_cols[3]:
                start_hour_idx = st.selectbox(
                    "Start",
                    options=hour_options,
                    format_func=lambda x: hour_labels[x],
                    index=None,
                    key=f"pref_start_{day.name}",
                    label_visibility="visible"
                )
                day_start = time(start_hour_idx, 0) if start_hour_idx is not None else None
            
            with day_cols[4]:
                end_hour_idx = st.selectbox(
                    "End",
                    options=hour_options,
                    format_func=lambda x: hour_labels[x],
                    index=None,
                    key=f"pref_end_{day.name}",
                    label_visibility="visible"
                )
                day_end = time(end_hour_idx, 0) if end_hour_idx is not None else None
            
            # Handle day availability based on checkboxes and times
            if day_start and day_end:
                times = (day_start, day_end)
                if is_unavailable:
                    unavailable_times_by_day[day] = times
                elif is_preferred:
                    preferred_times_by_day[day] = times
                else:
                    available_times_by_day[day] = times
            elif is_unavailable:
                unavailable_days.append(day_name(day))
            elif is_preferred:
                preferred_days.append(day_name(day))
        
        if st.button("Add Employee", type="primary"):
            if emp_name:
                # Check if employee already exists
                if any(emp.name == emp_name for emp in st.session_state.employees):
                    st.error(f"Employee '{emp_name}' already exists!")
                else:
                    employee = Employee(
                        name=emp_name,
                        preferred_days=[day_from_name(d) for d in preferred_days if d],
                        preferred_times_by_day=preferred_times_by_day,
                        available_times_by_day=available_times_by_day,
                        unavailable_days=[day_from_name(d) for d in unavailable_days if d],
                        unavailable_times_by_day=unavailable_times_by_day,
                        max_hours_per_month=max_hours
                    )
                    st.session_state.employees.append(employee)
                    st.success(f"Employee '{emp_name}' added successfully!")
                    st.rerun()
            else:
                st.error("Please enter an employee name.")
    
    # Employee tabs (if any employees exist)
    if st.session_state.employees:
        for i, (emp, emp_tab) in enumerate(zip(st.session_state.employees, all_tabs[1:])):
            with emp_tab:
                # Employee info and actions at the top
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**Max Hours/Month:** {emp.max_hours_per_month}")
                    st.markdown(f"**Preferred Days:** {', '.join([day_name(d) for d in emp.preferred_days]) if emp.preferred_days else 'None'}")
                    
                    # Show unavailable days (completely unavailable)
                    unavailable_days_list = [d for d in emp.unavailable_days if d not in getattr(emp, 'unavailable_times_by_day', {})]
                    if unavailable_days_list:
                        st.markdown(f"**Unavailable Days (all day):** {', '.join([day_name(d) for d in unavailable_days_list])}")
                    
                    # Show unavailable times by day (partial unavailability)
                    show_times_by_day(getattr(emp, 'unavailable_times_by_day', {}), 
                                     "Unavailable Times by Day", " (unavailable during these hours)")
                    
                    # Show preferred times by day
                    preferred_times = getattr(emp, 'preferred_times_by_day', {})
                    if preferred_times:
                        show_times_by_day(preferred_times, "Preferred Times by Day")
                    elif emp.preferred_start_time and emp.preferred_end_time:
                        # Fall back to general preferred times
                        st.markdown(f"**Preferred Time:** {format_time_range(emp.preferred_start_time, emp.preferred_end_time)}")
                    
                    # Show available times by day (when not preferred/unavailable)
                    show_times_by_day(getattr(emp, 'available_times_by_day', {}), 
                                     "Available Times by Day", " (available during these hours)")
                
                with col2:
                    col_edit, col_delete = st.columns(2)
                    with col_edit:
                        if st.button("Edit", key=f"edit_{i}", use_container_width=True):
                            if f"editing_employee_{i}" not in st.session_state:
                                st.session_state[f"editing_employee_{i}"] = True
                            else:
                                st.session_state[f"editing_employee_{i}"] = not st.session_state[f"editing_employee_{i}"]
                            st.rerun()
                    with col_delete:
                        if st.button("Delete", key=f"delete_{i}", use_container_width=True):
                            st.session_state.employees.pop(i)
                            # Clean up edit state if it exists
                            if f"editing_employee_{i}" in st.session_state:
                                del st.session_state[f"editing_employee_{i}"]
                            # Clean up all related session state for this employee
                            for key in list(st.session_state.keys()):
                                if key.endswith(f"_{i}") and ("editing" in key or "pref" in key):
                                    del st.session_state[key]
                            st.rerun()
                
                # Edit employee preferences (only show if edit button was pressed)
                if st.session_state.get(f"editing_employee_{i}", False):
                    st.markdown("---")
                    st.markdown("**✏️ Edit Preferred Work Days & Times**")
                    
                    # Max hours editor
                    new_max_hours = st.number_input(
                        "Maximum Hours per Month",
                        min_value=0.0,
                        max_value=300.0,
                        value=emp.max_hours_per_month,
                        step=1.0,
                        key=f"edit_max_hours_{i}"
                    )
                    
                    st.markdown("**Preferred Work Days & Times**")
                    st.info("💡 **Tip:** \n"
                            "- **Preferred + times**: Preferred work times for that day\n"
                            "- **Preferred (no times)**: Available all day, prefers this day\n"
                            "- **Unavailable + times**: Unavailable during those hours (available at other times)\n"
                            "- **Unavailable (no times)**: Entire day unavailable\n"
                            "- **Neither checked + times**: Available only during those hours\n"
                            "- **Neither checked (no times)**: Available all day (just not preferred)")
                    
                    edit_preferred_days = []
                    edit_preferred_times_by_day = {}
                    edit_available_times_by_day = {}
                    edit_unavailable_days = []
                    edit_unavailable_times_by_day = {}
                    
                    # Hour options (0-23)
                    hour_options = list(range(24))
                    hour_labels = [f"{h:02d}:00" for h in hour_options]
                    
                    # Get current values
                    current_preferred_days = getattr(emp, 'preferred_days', [])
                    current_preferred_times = getattr(emp, 'preferred_times_by_day', {})
                    current_available_times = getattr(emp, 'available_times_by_day', {})
                    current_unavailable_days = getattr(emp, 'unavailable_days', [])
                    current_unavailable_times = getattr(emp, 'unavailable_times_by_day', {})
                    
                    # Create a table-like layout with day name, preferred checkbox, unavailable checkbox, and times
                    for day in DayOfWeek:
                        day_cols = st.columns([1, 1, 1, 1.5, 1.5])
                        
                        with day_cols[0]:
                            st.markdown(f"**{day_name(day)}**")
                        
                        # Determine current state
                        is_currently_preferred = day in current_preferred_days
                        is_currently_unavailable = day in current_unavailable_days
                        has_preferred_times = day in current_preferred_times
                        has_available_times = day in current_available_times
                        has_unavailable_times = day in current_unavailable_times
                        
                        # Get current times if they exist
                        current_start_idx = None
                        current_end_idx = None
                        if has_preferred_times:
                            start_time, end_time = current_preferred_times[day]
                            current_start_idx = start_time.hour
                            current_end_idx = end_time.hour
                        elif has_available_times:
                            start_time, end_time = current_available_times[day]
                            current_start_idx = start_time.hour
                            current_end_idx = end_time.hour
                        elif has_unavailable_times:
                            start_time, end_time = current_unavailable_times[day]
                            current_start_idx = start_time.hour
                            current_end_idx = end_time.hour
                        
                        with day_cols[1]:
                            # Check if preferred: either in preferred_days list OR has preferred_times
                            is_preferred = st.checkbox(
                                "Preferred",
                                value=is_currently_preferred or has_preferred_times,
                                key=f"edit_pref_{day.name}_{i}",
                                help="Mark this as a preferred work day"
                            )
                        
                        with day_cols[2]:
                            # Check if unavailable: either in unavailable_days list OR has unavailable_times
                            is_unavailable = st.checkbox(
                                "Unavailable",
                                value=is_currently_unavailable or has_unavailable_times,
                                key=f"edit_unavail_{day.name}_{i}",
                                help="Mark this day as unavailable. If times are set, only those hours are unavailable."
                            )
                        
                        with day_cols[3]:
                            start_hour_idx = st.selectbox(
                                "Start",
                                options=hour_options,
                                format_func=lambda x: hour_labels[x],
                                index=current_start_idx if current_start_idx is not None else None,
                                key=f"edit_pref_start_{day.name}_{i}",
                                label_visibility="visible"
                            )
                            day_start = time(start_hour_idx, 0) if start_hour_idx is not None else None
                        
                        with day_cols[4]:
                            end_hour_idx = st.selectbox(
                                "End",
                                options=hour_options,
                                format_func=lambda x: hour_labels[x],
                                index=current_end_idx if current_end_idx is not None else None,
                                key=f"edit_pref_end_{day.name}_{i}",
                                label_visibility="visible"
                            )
                            day_end = time(end_hour_idx, 0) if end_hour_idx is not None else None
                        
                        # Handle day availability based on checkboxes and times
                        if day_start and day_end:
                            if is_unavailable:
                                # Partial unavailability - store the unavailable time range
                                edit_unavailable_times_by_day[day] = (day_start, day_end)
                            elif is_preferred:
                                # Preferred day - times are preferred times
                                edit_preferred_times_by_day[day] = (day_start, day_end)
                            else:
                                # Neither preferred nor unavailable - times are available times
                                edit_available_times_by_day[day] = (day_start, day_end)
                        elif is_unavailable and not day_start and not day_end:
                            # Complete unavailability - add to unavailable_days list
                            edit_unavailable_days.append(day_name(day))
                        elif is_preferred and not day_start and not day_end:
                            # Preferred all day
                            edit_preferred_days.append(day_name(day))
                    
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.button("Save Changes", type="primary", key=f"save_edit_{i}", use_container_width=True):
                            # Update employee preferences
                            emp.max_hours_per_month = new_max_hours
                            emp.preferred_days = [day_from_name(d) for d in edit_preferred_days]
                            emp.preferred_times_by_day = edit_preferred_times_by_day
                            emp.available_times_by_day = edit_available_times_by_day
                            emp.unavailable_days = [day_from_name(d) for d in edit_unavailable_days]
                            emp.unavailable_times_by_day = edit_unavailable_times_by_day
                            # Close edit form
                            st.session_state[f"editing_employee_{i}"] = False
                            st.success(f"Employee '{emp.name}' updated successfully!")
                            st.rerun()
                    with col_cancel:
                        if st.button("Cancel", key=f"cancel_edit_{i}", use_container_width=True):
                            # Close edit form
                            st.session_state[f"editing_employee_{i}"] = False
                            st.rerun()
                
                # Date-specific preferences section
                st.markdown("---")
                st.markdown("**📅 Date-Specific Preferences**")
                st.caption("Set preferences for specific dates in the month (overrides day-of-week preferences).")
                # Add CSS to reduce spacing in date preferences section
                st.markdown("""
                <style>
                div[data-testid="column"] {
                    padding-top: 0.5rem !important;
                    padding-bottom: 0.5rem !important;
                }
                .stSelectbox, .stDateInput, .stRadio {
                    margin-bottom: 0.5rem !important;
                }
                </style>
                """, unsafe_allow_html=True)
                
                # Month/year selector
                col_cal1, col_cal2 = st.columns(2)
                with col_cal1:
                    pref_month = st.selectbox(
                        "Month",
                        options=list(range(1, 13)),
                        format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
                        index=datetime.now().month - 1,
                        key=f"pref_calendar_month_{i}"
                    )
                with col_cal2:
                    pref_year = st.number_input(
                        "Year",
                        min_value=2020,
                        max_value=2100,
                        value=datetime.now().year,
                        key=f"pref_calendar_year_{i}"
                    )
                
                # Display calendar, preferences table, and form side by side
                col_cal, col_prefs, col_form = st.columns([3, 2, 2])
                
                with col_cal:
                    st.markdown("**📆 Monthly Calendar View**")
                    st.caption(f"View {emp.name}'s date-specific preferences for the selected month.")
                    show_employee_calendar_view(emp, pref_year, pref_month)
                
                with col_prefs:
                    st.markdown("**Active Date-Specific Preferences:**")
                    # Collect all date preferences with mapping to actual date objects
                    date_prefs = []
                    date_pref_map = {}  # Maps display string to (date_obj, pref_type, times)
                    
                    # Helper function to add preferences
                    def add_pref(date_obj, pref_type, times=None, is_all_day=False):
                        date_str = date_obj.strftime("%B %d, %Y")
                        if times:
                            times_str = format_time_range(times[0], times[1])
                            display_str = f"{date_str} - {pref_type} ({times_str})"
                            type_str = pref_type
                        else:
                            display_str = f"{date_str} - {pref_type} (all day)"
                            type_str = f"{pref_type} (all day)"
                            times_str = "All day"
                        date_prefs.append({
                            "Preference": display_str,
                            "Date": date_str,
                            "Type": type_str,
                            "Times": times_str
                        })
                        date_pref_map[display_str] = (date_obj, pref_type, times)
                    
                    # Collect all preferences
                    for date_obj in getattr(emp, 'preferred_dates', []):
                        add_pref(date_obj, "Preferred")
                    for date_obj, times in getattr(emp, 'preferred_times_by_date', {}).items():
                        add_pref(date_obj, "Preferred", times)
                    for date_obj in getattr(emp, 'unavailable_dates', []):
                        add_pref(date_obj, "Unavailable")
                    for date_obj, times in getattr(emp, 'unavailable_times_by_date', {}).items():
                        add_pref(date_obj, "Unavailable", times)
                    for date_obj, times in getattr(emp, 'available_times_by_date', {}).items():
                        add_pref(date_obj, "Available Only", times)
                    
                    if date_prefs:
                        # Sort by date
                        date_prefs.sort(key=lambda x: datetime.strptime(x["Date"], "%B %d, %Y"))
                        
                        st.caption("Click a preference to edit it:")
                        # Display clickable preferences
                        for pref in date_prefs:
                            pref_display = pref["Preference"]
                            date_obj, pref_type, pref_times = date_pref_map[pref_display]
                            
                            # Make the preference itself clickable
                            pref_text = f"{pref['Date']} - {pref['Type']} - {pref['Times']}"
                            if st.button(pref_text, key=f"click_pref_{pref_display}_{i}", use_container_width=True):
                                # Store selected preference info in session state to populate form
                                st.session_state[f"editing_pref_date_{i}"] = date_obj
                                st.session_state[f"editing_pref_type_{i}"] = pref_type
                                if pref_times:
                                    st.session_state[f"editing_pref_start_{i}"] = pref_times[0].hour
                                    st.session_state[f"editing_pref_end_{i}"] = pref_times[1].hour
                                else:
                                    st.session_state[f"editing_pref_start_{i}"] = None
                                    st.session_state[f"editing_pref_end_{i}"] = None
                                # Clear any old editing date keys to force widget recreation
                                editing_date = date_obj.date() if hasattr(date_obj, 'date') else date_obj
                                old_date_key = f"pref_date_input_{i}_editing_{editing_date}"
                                old_radio_key = f"pref_type_radio_{i}_editing_{editing_date}"
                                old_start_key = f"pref_date_start_{i}_editing_{editing_date}"
                                old_end_key = f"pref_date_end_{i}_editing_{editing_date}"
                                for old_key in [old_date_key, old_radio_key, old_start_key, old_end_key]:
                                    if old_key in st.session_state:
                                        del st.session_state[old_key]
                                st.rerun()
                    else:
                        st.caption("No date-specific preferences set. Use the form to add preferences.")
                
                with col_form:
                    st.markdown("**Set Date-Specific Preference**")
                    # Check if we're editing a selected preference
                    editing_pref_date = st.session_state.get(f"editing_pref_date_{i}")
                    
                    # Use a dynamic key that changes when we start editing to force widget recreation
                    if editing_pref_date:
                        editing_date = editing_pref_date.date() if hasattr(editing_pref_date, 'date') else editing_pref_date
                        # Use a key that includes the editing date to force widget update
                        date_key = f"pref_date_input_{i}_editing_{editing_date}"
                        date_value = editing_date
                        default_type = st.session_state.get(f"editing_pref_type_{i}", "Preferred")
                        default_start = st.session_state.get(f"editing_pref_start_{i}")
                        default_end = st.session_state.get(f"editing_pref_end_{i}")
                        st.caption(f"✏️ Editing: {editing_pref_date.strftime('%B %d, %Y')}")
                    else:
                        # Not editing - use standard key
                        date_key = f"pref_date_input_{i}"
                        date_value = st.session_state.get(date_key, datetime.now().date())
                        default_type = "Preferred"
                        default_start = None
                        default_end = None
                    
                    selected_pref_date = st.date_input(
                        "Select Date",
                        value=date_value,
                        key=date_key
                    )
                    
                    # Hour options (0-23)
                    hour_options = list(range(24))
                    hour_labels = [f"{h:02d}:00" for h in hour_options]
                    
                    # Map default_type to radio index
                    type_options = ["Preferred", "Unavailable", "Available Only"]
                    default_type_idx = type_options.index(default_type) if default_type in type_options else 0
                    
                    # Use dynamic keys for widgets when editing to force update
                    if editing_pref_date:
                        radio_key = f"pref_type_radio_{i}_editing_{editing_date}"
                        start_key = f"pref_date_start_{i}_editing_{editing_date}"
                        end_key = f"pref_date_end_{i}_editing_{editing_date}"
                    else:
                        radio_key = f"pref_type_radio_{i}"
                        start_key = f"pref_date_start_{i}"
                        end_key = f"pref_date_end_{i}"
                    
                    pref_type = st.radio(
                        "Preference Type",
                        options=type_options,
                        index=default_type_idx,
                        key=radio_key,
                        help="Preferred: prefers this day/time\nUnavailable: cannot work during these hours\nAvailable Only: can only work during these hours"
                    )
                    
                    start_hour_idx = st.selectbox(
                        "Start Hour",
                        options=hour_options,
                        format_func=lambda x: hour_labels[x],
                        index=default_start if default_start is not None else None,
                        key=start_key
                    )
                    pref_start = time(start_hour_idx, 0) if start_hour_idx is not None else None
                    
                    end_hour_idx = st.selectbox(
                        "End Hour",
                        options=hour_options,
                        format_func=lambda x: hour_labels[x],
                        index=default_end if default_end is not None else None,
                        key=end_key
                    )
                    pref_end = time(end_hour_idx, 0) if end_hour_idx is not None else None
                    
                    # Change button text based on whether we're editing
                    button_text = "Save" if editing_pref_date else "Set Preference"
                    if st.button(button_text, type="primary", use_container_width=True, key=f"set_pref_{i}"):
                        date_dt = datetime.combine(selected_pref_date, time.min)
                        date_only = normalize_date(date_dt)
                        
                        # Initialize date-specific attributes if they don't exist
                        ensure_date_attributes(emp)
                        
                        # If editing, remove old preference first (from the original date if different)
                        if editing_pref_date:
                            old_date_only = datetime(editing_pref_date.year, editing_pref_date.month, editing_pref_date.day)
                            remove_preference_from_all_lists(emp, old_date_only)
                            # Clear editing state
                            clear_editing_state(i)
                        
                        # Remove from other lists for the new date
                        remove_preference_from_all_lists(emp, date_only)
                        
                        # Set based on preference type
                        pref_config = {
                            "Preferred": ("preferred_times_by_date", "preferred_dates", "Preference set"),
                            "Unavailable": ("unavailable_times_by_date", "unavailable_dates", "Unavailability set"),
                            "Available Only": ("available_times_by_date", None, "Available times set")
                        }
                        
                        times_attr, dates_attr, success_msg = pref_config[pref_type]
                        
                        if pref_start and pref_end:
                            getattr(emp, times_attr)[date_only] = (pref_start, pref_end)
                            st.success(f"{success_msg} for {selected_pref_date.strftime('%B %d, %Y')}")
                        elif dates_attr:
                            getattr(emp, dates_attr).append(date_only)
                            st.success(f"{success_msg} for {selected_pref_date.strftime('%B %d, %Y')}")
                        else:
                            st.warning("Please set start and end times for 'Available Only' preference.")
                        
                        st.rerun()
                    
                    # Cancel editing button if in edit mode
                    if editing_pref_date:
                        if st.button("Cancel Editing", key=f"cancel_editing_pref_{i}", use_container_width=True):
                            # Clear the editing-specific keys before clearing state
                            editing_date = editing_pref_date.date() if hasattr(editing_pref_date, 'date') else editing_pref_date
                            old_date_key = f"pref_date_input_{i}_editing_{editing_date}"
                            old_radio_key = f"pref_type_radio_{i}_editing_{editing_date}"
                            old_start_key = f"pref_date_start_{i}_editing_{editing_date}"
                            old_end_key = f"pref_date_end_{i}_editing_{editing_date}"
                            for old_key in [old_date_key, old_radio_key, old_start_key, old_end_key]:
                                if old_key in st.session_state:
                                    del st.session_state[old_key]
                            clear_editing_state(i)
                            st.rerun()
                    
                    date_dt = datetime.combine(selected_pref_date, time.min)
                    date_only = normalize_date(date_dt)
                    
                    # Check if there's an existing preference for this date
                    has_pref = has_date_preference(emp, date_only)
                    
                    if has_pref and st.button("Remove Preference", use_container_width=True, key=f"remove_pref_{i}"):
                        remove_preference_from_all_lists(emp, date_only)
                        
                        # Clear editing state if this was the preference being edited
                        if editing_pref_date and date_only == normalize_date(editing_pref_date):
                            # Clear the editing-specific keys before clearing state
                            editing_date = editing_pref_date.date() if hasattr(editing_pref_date, 'date') else editing_pref_date
                            old_date_key = f"pref_date_input_{i}_editing_{editing_date}"
                            old_radio_key = f"pref_type_radio_{i}_editing_{editing_date}"
                            old_start_key = f"pref_date_start_{i}_editing_{editing_date}"
                            old_end_key = f"pref_date_end_{i}_editing_{editing_date}"
                            for old_key in [old_date_key, old_radio_key, old_start_key, old_end_key]:
                                if old_key in st.session_state:
                                    del st.session_state[old_key]
                            clear_editing_state(i)
                        
                        st.success(f"Preference removed for {selected_pref_date.strftime('%B %d, %Y')}")
                        st.rerun()


def show_generate_schedule_page():
    """Display page for generating schedules."""
    st.header("Generate Schedule")
    
    # Check prerequisites
    if not st.session_state.store_hours.hours:
        st.warning("⚠️ Please set store hours first!")
        return
    
    if not st.session_state.employees:
        st.warning("⚠️ Please add employees first!")
        return
    
    # Date selection
    selected_date = st.date_input(
        "Select Month",
        value=datetime.now(),
        key="schedule_date"
    )
    
    if st.button("Generate Schedule", type="primary"):
        with st.spinner("Generating schedule..."):
            scheduler = ShiftScheduler(
                st.session_state.employees,
                st.session_state.store_hours
            )
            
            schedule = scheduler.generate_schedule(
                selected_date.year,
                selected_date.month
            )
            
            st.session_state.schedule = schedule
            st.success(f"Schedule generated for {selected_date.strftime('%B %Y')}!")
            st.rerun()
    
    st.divider()
    
    # Show summary if schedule exists
    st.markdown("**📊 Summary**")
    if st.session_state.schedule:
        schedule = st.session_state.schedule
        
        # Hours per employee
        st.write("**Hours per Employee:**")
        for emp in st.session_state.employees:
            hours = schedule.get_total_hours_for_employee(emp.name)
            percentage = (hours / emp.max_hours_per_month * 100) if emp.max_hours_per_month > 0 else 0
            st.progress(min(percentage / 100, 1.0), text=f"{emp.name}: {hours:.1f} / {emp.max_hours_per_month:.1f} hours ({percentage:.1f}%)")
    else:
        st.info("No schedule generated yet. Use the form above to create one.")


def show_view_schedule_page():
    """Display page for viewing the generated schedule."""
    st.header("View Schedule")
    
    if not st.session_state.schedule:
        st.info("No schedule generated yet. Go to 'Generate Schedule' to create one.")
        return
    
    schedule = st.session_state.schedule
    
    tab1, tab2, tab3, tab4 = st.tabs(["📅 Calendar", "📋 By Day", "👤 By Employee", "💾 Export"])
    
    with tab1:
        # Calendar view
        col1, col2 = st.columns(2)
        with col1:
            calendar_month = st.selectbox(
                "Month",
                options=list(range(1, 13)),
                format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
                index=schedule.month - 1,
                key="schedule_calendar_month"
            )
        with col2:
            calendar_year = st.number_input(
                "Year",
                min_value=2020,
                max_value=2100,
                value=schedule.year,
                key="schedule_calendar_year"
            )
        
        # Display calendar
        show_schedule_calendar_view(schedule, calendar_year, calendar_month)
        
        # Display color legend
        unique_employees = sorted(set(s.employee_name for s in schedule.shifts))
        if unique_employees:
            st.markdown("**Employee Color Legend:**")
            
            # Generate color mapping (same as in calendar view)
            employee_colors = get_employee_colors(unique_employees)
            
            # Calculate total hours for each employee
            employee_hours = {}
            for emp in unique_employees:
                employee_hours[emp] = schedule.get_total_hours_for_employee(emp)
            
            # Display legend in columns
            num_cols = min(4, len(unique_employees))
            cols = st.columns(num_cols)
            for i, emp in enumerate(unique_employees):
                with cols[i % num_cols]:
                    color = employee_colors[emp]
                    total_hours = employee_hours[emp]
                    st.markdown(
                        f'<div style="display: flex; align-items: center; margin-bottom: 8px;">'
                        f'<div style="width: 20px; height: 20px; background-color: {color}; border-radius: 3px; margin-right: 8px; border: 1px solid #ddd;"></div>'
                        f'<span><strong>{emp}</strong> - {total_hours:.1f} hrs</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
    
    with tab2:
        # Display schedule by day
        # Group shifts by date
        dates = sorted(set(s.date for s in schedule.shifts if s.date))
        
        for date in dates:
            st.subheader(date.strftime("%A, %B %d, %Y"))
            
            # Get shifts for this date
            day_shifts = [s for s in schedule.shifts if s.date == date]
            day_shifts.sort(key=lambda x: x.start_time)
            
            if day_shifts:
                for shift in day_shifts:
                    duration = shift.duration_hours()
                    st.write(
                        f"**{shift.employee_name}** - "
                        f"{shift.start_time.strftime('%I:%M %p')} to "
                        f"{shift.end_time.strftime('%I:%M %p')} "
                        f"({duration:.1f} hours)"
                    )
            else:
                st.info("No shifts scheduled for this day.")
            
            st.divider()
    
    with tab3:
        # Display schedule by employee
        employee_names = [emp.name for emp in st.session_state.employees]
        selected_employee = st.selectbox(
            "Select Employee",
            options=employee_names,
            key="employee_filter"
        )
        
        if selected_employee:
            employee_shifts = schedule.get_shifts_for_employee(selected_employee)
            employee_shifts.sort(key=lambda x: (x.date, x.start_time) if x.date else (datetime.min, x.start_time))
            
            total_hours = schedule.get_total_hours_for_employee(selected_employee)
            st.metric("Total Hours", f"{total_hours:.1f}")
            
            if employee_shifts:
                # Group by date
                shifts_by_date = {}
                for shift in employee_shifts:
                    if shift.date:
                        date_key = shift.date.strftime("%Y-%m-%d")
                        if date_key not in shifts_by_date:
                            shifts_by_date[date_key] = []
                        shifts_by_date[date_key].append(shift)
                
                for date_key in sorted(shifts_by_date.keys()):
                    date = datetime.strptime(date_key, "%Y-%m-%d")
                    st.subheader(date.strftime("%A, %B %d, %Y"))
                    
                    for shift in shifts_by_date[date_key]:
                        duration = shift.duration_hours()
                        st.write(
                            f"{shift.start_time.strftime('%I:%M %p')} to "
                            f"{shift.end_time.strftime('%I:%M %p')} "
                            f"({duration:.1f} hours)"
                        )
                    st.divider()
            else:
                st.info(f"No shifts scheduled for {selected_employee}.")
    
    with tab4:
        # Export option with employee filter
        employee_names = [emp.name for emp in st.session_state.employees]
        employee_names.insert(0, "All Employees")  # Add "All" option at the beginning
        
        selected_employee_export = st.selectbox(
            "Filter by Employee (optional)",
            options=employee_names,
            key="export_employee_filter",
            help="Select an employee to filter the schedule, or 'All Employees' to include everyone"
        )
        
        # Generate color mapping for employees
        
        # Prepare PDF data
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1f4e79'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        # Filter shifts by selected employee
        shifts_to_export = schedule.shifts
        if selected_employee_export and selected_employee_export != "All Employees":
            shifts_to_export = [s for s in schedule.shifts if s.employee_name == selected_employee_export]
        
        # Title
        month_name = datetime(schedule.year, schedule.month, 1).strftime("%B %Y")
        if selected_employee_export and selected_employee_export != "All Employees":
            title_text = f"Employee Schedule - {selected_employee_export} - {month_name}"
        else:
            title_text = f"Employee Schedule - {month_name}"
        title = Paragraph(title_text, title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.3*inch))
        
        # Get unique employees from shifts and assign colors
        unique_employees = sorted(set(s.employee_name for s in shifts_to_export))
        employee_colors = get_employee_colors(unique_employees)
        
        # Add legend at the top if showing all employees
        if selected_employee_export == "All Employees" and unique_employees:
            legend_style = ParagraphStyle(
                'LegendStyle',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#1f4e79'),
                spaceAfter=10,
                alignment=TA_LEFT
            )
            legend_title = Paragraph("<b>Employee Color Legend:</b>", legend_style)
            elements.append(legend_title)
            
            # Create legend table
            legend_data = [["Employee", "Color"]]
            for emp in unique_employees:
                legend_data.append([emp, ""])  # Color will be shown via background
            
            legend_table = Table(legend_data, colWidths=[2*inch, 0.5*inch])
            legend_style_list = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ]
            
            # Add background colors to legend rows
            for i, emp in enumerate(unique_employees, start=1):
                legend_style_list.append(('BACKGROUND', (1, i), (1, i), colors.HexColor(employee_colors[emp])))
            
            legend_table.setStyle(TableStyle(legend_style_list))
            elements.append(legend_table)
            elements.append(Spacer(1, 0.3*inch))
        
        # Group shifts by date
        shifts_by_date = {}
        for shift in sorted(shifts_to_export, key=lambda x: (x.date or datetime.min, x.start_time)):
            if shift.date:
                date_key = shift.date.strftime("%Y-%m-%d")
                if date_key not in shifts_by_date:
                    shifts_by_date[date_key] = []
                shifts_by_date[date_key].append(shift)
        
        # Create table data
        table_data = [["Date", "Day", "Employee", "Start Time", "End Time", "Duration (hrs)"]]
        row_colors = []  # Track which employee color to use for each row
        
        for date_key in sorted(shifts_by_date.keys()):
            date_obj = datetime.strptime(date_key, "%Y-%m-%d")
            for shift in shifts_by_date[date_key]:
                table_data.append([
                    date_obj.strftime("%Y-%m-%d"),
                    shift.day.name if shift.day else "",
                    shift.employee_name,
                    shift.start_time.strftime("%I:%M %p"),
                    shift.end_time.strftime("%I:%M %p"),
                    f"{shift.duration_hours():.2f}"
                ])
                row_colors.append(employee_colors.get(shift.employee_name, colors.white))
        
        # Create table
        table = Table(table_data, colWidths=[1.2*inch, 0.8*inch, 1.5*inch, 1*inch, 1*inch, 1*inch])
        
        # Build table style with color coding
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]
        
        # Add background colors and text colors for each row based on employee
        for i, row_color in enumerate(row_colors, start=1):
            table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor(row_color)))
            # Use white text for dark backgrounds, black for light backgrounds
            text_color = colors.white if is_dark_color(row_color) else colors.black
            table_style.append(('TEXTCOLOR', (0, i), (-1, i), text_color))
        
        table.setStyle(TableStyle(table_style))
        
        elements.append(table)
        
        # Build PDF
        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()
        
        # Generate filename
        if selected_employee_export and selected_employee_export != "All Employees":
            filename = f"schedule_{selected_employee_export.replace(' ', '_')}_{schedule.year}_{schedule.month:02d}.pdf"
        else:
            filename = f"schedule_{schedule.year}_{schedule.month:02d}.pdf"
        
        st.download_button(
            label="Download PDF",
            data=pdf_data,
            file_name=filename,
            mime="application/pdf"
        )


if __name__ == "__main__":
    main()
