/**
 * Display labels and colors for values that come from the API.
 * The values themselves (status names etc.) are defined by the backend.
 */

export const STATUS_LABELS = {
  open: 'Open',
  in_progress: 'In progress',
  blocked: 'Blocked',
  resolved: 'Resolved',
  closed: 'Closed',
};

/** MUI Chip color for each status. */
export const STATUS_COLORS = {
  open: 'info',
  in_progress: 'primary',
  blocked: 'error',
  resolved: 'success',
  closed: 'default',
};

export const PRIORITY_LABELS = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
};

export const PRIORITY_COLORS = {
  low: 'default',
  medium: 'info',
  high: 'warning',
  critical: 'error',
};

export const CATEGORY_LABELS = {
  IT: 'IT',
  facilities: 'Facilities',
  AV: 'AV',
  security: 'Security',
};

/** Engineer shifts, in office time (see backend constants). */
export const SHIFT_LABELS = {
  day: 'Day (7:00–15:00)',
  swing: 'Swing (15:00–23:00)',
  night: 'Night (23:00–7:00)',
};

export const ROLE_LABELS = {
  employee: 'Employee',
  engineer: 'Engineer',
  admin: 'Admin',
};

/** Button text for each workflow transition, keyed by target status. */
export const TRANSITION_LABELS = {
  in_progress: 'Start work',
  blocked: 'Mark blocked',
  resolved: 'Resolve',
  closed: 'Close ticket',
};

export const REQUEST_LABELS = {
  reopen: 'Reopen',
  close_approval: 'Close approval',
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
};

/** Human-readable text for audit events. */
export const EVENT_LABELS = {
  created: 'Reported the incident',
  title_changed: 'Changed the title',
  description_changed: 'Changed the description',
  status_changed: 'Changed the status',
  priority_changed: 'Changed the priority',
  engineer_joined: 'Joined the ticket',
  acknowledged: 'Acknowledged for this shift',
  note_added: 'Added a note',
  note_edited: 'Edited a note',
  work_logged: 'Logged work',
  work_log_edited: 'Edited a work log',
  request_created: 'Made a request',
  request_decided: 'Decided a request',
  archived: 'Archived the ticket',
  voided: 'Voided the ticket',
};

/**
 * Format an ISO timestamp for display, e.g. "Sep 23, 2:05 PM".
 * @param {string|null} value
 * @returns {string}
 */
export function formatDateTime(value) {
  if (!value) return '';
  return new Date(value).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

/**
 * Format a duration in hours: "45 min", "6.1 h" or "2.3 days".
 * @param {number|string|null} hours
 * @returns {string|null}
 */
export function formatHours(hours) {
  if (hours === null || hours === undefined) return null;
  const value = Number(hours);
  if (value < 1) return `${Math.round(value * 60)} min`;
  if (value < 48) return `${value.toFixed(1)} h`;
  return `${(value / 24).toFixed(1)} days`;
}

/**
 * How long a ticket has been in its current status: "20 min", "5 hours", "1 day", "3 days".
 * @param {string|null} since ISO timestamp of the last status change.
 * @param {Date} [now]
 * @returns {string|null}
 */
export function formatStatusAge(since, now = new Date()) {
  if (!since) return null;
  const minutes = Math.max(0, Math.floor((now - new Date(since)) / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? 'hour' : 'hours'}`;
  const days = Math.floor(hours / 24);
  return `${days} ${days === 1 ? 'day' : 'days'}`;
}

/**
 * Format a location as "Building · Floor 2 · Seat 2-R-004".
 * @param {{building_name: string, floor_number: number, seat_code?: string}} incident
 * @returns {string}
 */
export function formatLocation(incident) {
  const parts = [incident.building_name, `Floor ${incident.floor_number}`];
  if (incident.seat_code) parts.push(`Seat ${incident.seat_code}`);
  return parts.join(' · ');
}
