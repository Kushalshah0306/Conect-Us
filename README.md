# Conect Us - Home Services Platform

A platform connecting users with home and commercial service providers, similar to UrbanCompany.

## Features
- User Authentication (Signup, Login, Google OAuth)
- Service Discovery (Home & Commercial Services)
- Service Booking System
- Admin Portal for managing services and bookings

## Technology Stack
- Backend: Python with Flask
- Database: SQLite
- Frontend: HTML, CSS, JavaScript
- Styling: Custom CSS with modern UI

## Project Structure
```
conect-us/
├── app.py                 # Main Flask application
├── requirements.txt      # Python dependencies
├── instance/             # SQLite database
├── static/
│   ├── css/
│   │   └── style.css     # Main stylesheet
│   ├── js/
│   │   └── main.js       # Frontend JavaScript
│   └── images/           # Service images
└── templates/
    ├── base.html         # Base template
    ├── index.html        # Home page
    ├── login.html        # Login page
    ├── signup.html       # Signup page
    ├── dashboard.html    # User dashboard
    ├── service_detail.html # Service details
    └── admin/
        ├── admin_login.html  # Admin login
        └── admin_dashboard.html # Admin dashboard
```

## Services to Include
1. Home Services
   - Plumber
   - Electrician
   - Carpenter
   - House Cleaning
   - AC Repair
   - Pest Control

2. Commercial Services
   - Office Cleaning
   - Security Services
   - Maintenance
   - Catering
