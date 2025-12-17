# Employee Shift Scheduler

A Python application for generating employee shift schedules based on store hours, employee preferences, availability, and maximum work hours.

## Features

- **Store Hours Configuration**: Set operating hours for each day of the week
- **Employee Management**: Add employees with their preferences and constraints
  - Preferred work days and times
  - Unavailable days
  - Maximum hours per month
  - Preferred shift duration
- **Automatic Schedule Generation**: Generate monthly schedules that respect all constraints
- **Schedule Viewing**: View schedules by day or by employee
- **Export Functionality**: Download schedules as JSON

## Installation

The application uses Streamlit for the web interface. Make sure you have the required dependencies installed:

```bash
pip install streamlit
```

Or install from the main project's requirements.txt which already includes Streamlit.

## Usage

### Running the Application

Navigate to the scheduling directory and run:

```bash
streamlit run schedule_app.py
```

The application will open in your web browser at `http://localhost:8501`.

### Step-by-Step Guide

1. **Set Store Hours**
   - Navigate to "Store Hours" in the sidebar
   - For each day of the week, set the open and close times
   - Check/uncheck whether the store is open on that day

2. **Add Employees**
   - Navigate to "Employees" in the sidebar
   - Fill in the employee information:
     - Name (required)
     - Maximum hours per month
     - Preferred shift duration
     - Preferred work days
     - Unavailable days
     - Preferred work times
   - Click "Add Employee"

3. **Generate Schedule**
   - Navigate to "Generate Schedule" in the sidebar
   - Select the month and year for the schedule
   - Set the default shift duration
   - Click "Generate Schedule"
   - View the summary showing hours allocated per employee

4. **View Schedule**
   - Navigate to "View Schedule" in the sidebar
   - Choose to view by day or by employee
   - If viewing by employee, select the employee from the dropdown
   - Export the schedule as JSON if needed

## How It Works

The scheduler uses a constraint-based algorithm that:

1. **Respects Constraints**:
   - Store operating hours
   - Employee unavailable days
   - Maximum hours per month per employee
   - Minimum and maximum shift durations

2. **Optimizes for Preferences**:
   - Prioritizes employees who prefer working on specific days
   - Balances hours across employees
   - Attempts to match preferred work times when possible

3. **Generates Shifts**:
   - Creates shifts to cover all store operating hours
   - Distributes shifts evenly among available employees
   - Ensures no employee exceeds their maximum hours

## File Structure

```
scheduling/
├── schedule_app.py    # Main Streamlit application
├── scheduler.py       # Core scheduling algorithm
├── models.py         # Data models and classes
└── README.md         # This file
```

## Data Models

- **StoreHours**: Manages operating hours for each day of the week
- **Employee**: Stores employee information, preferences, and constraints
- **Shift**: Represents a single scheduled shift
- **Schedule**: Contains all shifts for a given month

## Future Enhancements

Potential improvements to the scheduler:

- More sophisticated optimization algorithms (genetic algorithms, constraint programming)
- Shift swapping and manual adjustments
- Conflict detection and resolution
- Integration with calendar systems
- Email notifications for employees
- Historical schedule tracking
- Analytics and reporting

## Notes

- The scheduler attempts to balance hours but may not always achieve perfect distribution
- Complex constraints may result in some days not being fully covered
- The algorithm prioritizes constraint satisfaction over perfect optimization
- For best results, ensure you have enough employees to cover all operating hours
