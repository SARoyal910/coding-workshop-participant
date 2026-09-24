/**
 * API client. Every request goes through `request()`, so errors are handled
 * in one place (DESIGN.md 13.8):
 * - 401 -> logs the user out (via the handler AuthContext registers)
 * - 400 -> ApiError.details maps field names to messages for the form
 * - network failure -> a friendly "can't reach the server" message
 */

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export const NETWORK_ERROR_MESSAGE = "Can't reach the server. Check your connection and try again.";

/** An error returned by the API, with the HTTP status and field-level details. */
export class ApiError extends Error {
  /**
   * @param {number} status HTTP status (0 when the server could not be reached).
   * @param {string} message Message safe to show to the user.
   * @param {Object<string, string>} [details] Field name -> error message.
   */
  constructor(status, message, details = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

let authToken = null;
let unauthorizedHandler = null;

/**
 * Set the token sent as "Authorization: Bearer <token>" on every request.
 * @param {string|null} token
 */
export function setAuthToken(token) {
  authToken = token;
}

/**
 * Register a callback for 401 responses on authenticated requests (expired or invalid session).
 * @param {function(string): void} handler Receives the server's message.
 */
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

/**
 * Build "?a=1&b=2", skipping empty values.
 * @param {Object<string, *>} [query]
 * @returns {string}
 */
function toQueryString(query = {}) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  const text = params.toString();
  return text ? `?${text}` : '';
}

/**
 * Send one request to the API.
 * @param {string} method HTTP method.
 * @param {string} path Path after /api, e.g. "/incidents/42".
 * @param {{body?: Object, query?: Object}} [options]
 * @returns {Promise<*>} Parsed JSON body, or null for 204.
 * @throws {ApiError}
 */
export async function request(method, path, { body, query } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  let response;
  try {
    response = await fetch(`${API_URL}/api${path}${toQueryString(query)}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, NETWORK_ERROR_MESSAGE);
  }

  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (response.ok) return data;

  const message = data.error || `Request failed (${response.status})`;
  if (response.status === 401 && authToken && unauthorizedHandler) {
    unauthorizedHandler(message);
  }
  if (response.status === 403) {
    throw new ApiError(403, data.error || "You don't have permission to do this.", data.details);
  }
  throw new ApiError(response.status, message, data.details);
}

export const authApi = {
  login: (email, password) => request('POST', '/auth/login', { body: { email, password } }),
  register: (name, email, password) => request('POST', '/auth/register', { body: { name, email, password } }),
  me: () => request('GET', '/auth/me'),
  refresh: () => request('POST', '/auth/refresh'),
};

export const dashboardApi = {
  get: () => request('GET', '/dashboard'),
};

export const incidentsApi = {
  list: (query) => request('GET', '/incidents', { query }),
  get: (id) => request('GET', `/incidents/${id}`),
  options: () => request('GET', '/incidents/options'),
  similar: (query) => request('GET', '/incidents/similar', { query }),
  pendingRequests: (query) => request('GET', '/incidents/requests', { query }),
  alerts: () => request('GET', '/incidents/alerts'),
  create: (fields) => request('POST', '/incidents', { body: fields }),
  update: (id, fields) => request('PUT', `/incidents/${id}`, { body: fields }),
  changeStatus: (id, fields) => request('POST', `/incidents/${id}/status`, { body: fields }),
  addNote: (id, body) => request('POST', `/incidents/${id}/notes`, { body: { body } }),
  editNote: (id, noteId, body) => request('PUT', `/incidents/${id}/notes/${noteId}`, { body: { body } }),
  join: (id) => request('POST', `/incidents/${id}/join`),
  assign: (id, engineerId) => request('POST', `/incidents/${id}/assign`, { body: { engineer_id: engineerId } }),
  acknowledge: (id) => request('POST', `/incidents/${id}/acknowledge`),
  changePriority: (id, fields) => request('POST', `/incidents/${id}/priority`, { body: fields }),
  requestReopen: (id, reason) => request('POST', `/incidents/${id}/requests`, { body: { reason } }),
  decideRequest: (id, requestId, fields) => request('POST', `/incidents/${id}/requests/${requestId}/decision`, { body: fields }),
  void: (id, fields) => request('DELETE', `/incidents/${id}`, { body: fields }),
  addWorkLog: (id, fields) => request('POST', `/incidents/${id}/work-logs`, { body: fields }),
  editWorkLog: (id, logId, fields) => request('PUT', `/incidents/${id}/work-logs/${logId}`, { body: fields }),
};

export const facilitiesApi = {
  list: (query) => request('GET', '/facilities/buildings', { query }),
  createBuilding: (fields) => request('POST', '/facilities/buildings', { body: fields }),
  updateBuilding: (id, fields) => request('PUT', `/facilities/buildings/${id}`, { body: fields }),
  deleteBuilding: (id) => request('DELETE', `/facilities/buildings/${id}`),
  createFloor: (buildingId, fields) => request('POST', `/facilities/buildings/${buildingId}/floors`, { body: fields }),
  updateFloor: (id, fields) => request('PUT', `/facilities/floors/${id}`, { body: fields }),
  deleteFloor: (id) => request('DELETE', `/facilities/floors/${id}`),
  createSeat: (floorId, fields) => request('POST', `/facilities/floors/${floorId}/seats`, { body: fields }),
  updateSeat: (id, fields) => request('PUT', `/facilities/seats/${id}`, { body: fields }),
  deleteSeat: (id) => request('DELETE', `/facilities/seats/${id}`),
};

export const engineersApi = {
  list: (query) => request('GET', '/engineers', { query }),
  create: (fields) => request('POST', '/engineers', { body: fields }),
  update: (id, fields) => request('PUT', `/engineers/${id}`, { body: fields }),
  setAvailability: (id, isAvailable) => request('PUT', `/engineers/${id}/availability`, { body: { is_available: isAvailable } }),
};
