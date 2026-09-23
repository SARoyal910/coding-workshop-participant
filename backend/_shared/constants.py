"""
Fixed lists used across services.

Keeping them in one place means the database CHECK constraints, the seed data
and the request validation can never drift apart.
"""

ROLES = ("employee", "engineer", "admin")

STATUSES = ("open", "in_progress", "blocked", "resolved", "closed")
PRIORITIES = ("low", "medium", "high", "critical")

SPECIALTIES = ("facilities", "IT", "AV", "security")
SHIFTS = ("day", "swing", "night")

# Shift hours are local office time. Timestamps are stored in UTC.
ACME_TIMEZONE = "America/New_York"

# Shift start hour (24h clock, ACME_TIMEZONE) for each shift. Every shift is 8 hours long.
# The night shift (23-07) crosses midnight.
SHIFT_START_HOURS = {"day": 7, "swing": 15, "night": 23}
SHIFT_LENGTH_HOURS = 8

ENGINEER_ROLES = ("primary", "helper")
REQUEST_TYPES = ("reopen", "close_approval")
REQUEST_STATUSES = ("pending", "approved", "rejected")

# Category -> allowed issue types. Categories use the same names as specialties.
ISSUE_TYPES = {
    "IT": ("Wi-Fi", "Monitor", "Docking station", "Printer", "Badge reader"),
    "facilities": ("HVAC", "Lighting", "Plumbing", "Furniture", "Cleaning"),
    "AV": ("Projector", "Video conferencing", "Speakers"),
    "security": ("Door access", "Camera", "Lock"),
}

# Only company addresses may self-register.
EMAIL_DOMAIN = "acme.inc"
