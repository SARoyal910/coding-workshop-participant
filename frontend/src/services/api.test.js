import {
  afterEach, beforeEach, describe, expect, it, vi,
} from 'vitest';
import {
  ApiError, NETWORK_ERROR_MESSAGE, incidentsApi, request, setAuthToken, setUnauthorizedHandler,
} from './api';

/**
 * A fake fetch Response.
 * @param {number} status
 * @param {*} [body] JSON body; omit for an empty body.
 * @returns {object}
 */
function fakeResponse(status, body) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: body === undefined ? () => Promise.reject(new SyntaxError('no body')) : () => Promise.resolve(body),
  };
}

describe('api request()', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setAuthToken(null);
    setUnauthorizedHandler(null);
  });

  it('returns the parsed body on success and sends the token', async () => {
    fetchMock.mockResolvedValue(fakeResponse(200, { id: 42 }));
    setAuthToken('abc');

    await expect(request('GET', '/incidents/42')).resolves.toEqual({ id: 42 });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/incidents\/42$/);
    expect(options.headers.Authorization).toBe('Bearer abc');
  });

  it('builds the query string and skips empty values', async () => {
    fetchMock.mockResolvedValue(fakeResponse(200, { items: [] }));

    await incidentsApi.list({ status: 'open', q: '', page: 2, category: null });

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/incidents\?status=open&page=2$/);
  });

  it('returns null for 204 No Content', async () => {
    fetchMock.mockResolvedValue(fakeResponse(204));
    await expect(request('DELETE', '/incidents/1')).resolves.toBeNull();
  });

  it('calls the unauthorized handler on a 401 when logged in', async () => {
    const onUnauthorized = vi.fn();
    setAuthToken('expired-token');
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(fakeResponse(401, { error: 'Your session expired, please log in again', details: {} }));

    const error = await request('GET', '/auth/me').catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(401);
    expect(onUnauthorized).toHaveBeenCalledWith('Your session expired, please log in again');
  });

  it('does not log out on a 401 from the login form (no token yet)', async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(fakeResponse(401, { error: 'Invalid email or password', details: {} }));

    await expect(request('POST', '/auth/login')).rejects.toMatchObject({
      status: 401, message: 'Invalid email or password',
    });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('turns a network failure into a friendly message', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(request('GET', '/incidents')).rejects.toMatchObject({
      status: 0, message: NETWORK_ERROR_MESSAGE,
    });
  });

  it('keeps the message and details of a 409', async () => {
    fetchMock.mockResolvedValue(fakeResponse(409, {
      error: 'This ticket was updated by someone else. Refresh to see the latest.',
      details: { version: 'stale' },
    }));

    await expect(request('POST', '/incidents/1/status')).rejects.toMatchObject({
      status: 409,
      message: 'This ticket was updated by someone else. Refresh to see the latest.',
      details: { version: 'stale' },
    });
  });

  it('keeps field details of a 400 for the form', async () => {
    fetchMock.mockResolvedValue(fakeResponse(400, {
      error: 'Validation failed', details: { title: 'This field is required' },
    }));

    await expect(request('POST', '/incidents')).rejects.toMatchObject({
      status: 400, details: { title: 'This field is required' },
    });
  });

  it('uses a default permission message for a 403 without one', async () => {
    fetchMock.mockResolvedValue(fakeResponse(403, {}));

    await expect(request('POST', '/incidents/1/status')).rejects.toMatchObject({
      status: 403, message: "You don't have permission to do this.",
    });
  });

  it('falls back to a generic message when the error body is not JSON', async () => {
    fetchMock.mockResolvedValue(fakeResponse(502));

    await expect(request('GET', '/dashboard')).rejects.toMatchObject({
      status: 502, message: 'Request failed (502)',
    });
  });
});
