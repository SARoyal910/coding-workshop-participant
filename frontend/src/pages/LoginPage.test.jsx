import {
  beforeEach, describe, expect, it, vi,
} from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import LoginPage from './LoginPage';
import { AuthProvider } from '../context/AuthContext';
import { NotifyProvider } from '../context/NotifyContext';
import { ApiError, authApi } from '../services/api';

// Keep the real api module (ApiError etc.) but replace login so no request is sent.
vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, authApi: { ...actual.authApi, login: vi.fn() } };
});

/** Render the login page with the providers and router it needs. */
function renderLoginPage() {
  return render(
    <NotifyProvider>
      <AuthProvider>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<p>Home page</p>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </NotifyProvider>,
  );
}

/**
 * Fill in the form and press "Log in".
 * @param {string} email
 * @param {string} password
 */
async function submit(email, password) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/email/i), email);
  await user.type(screen.getByLabelText(/password/i), password);
  await user.click(screen.getByRole('button', { name: 'Log in' }));
}

describe('LoginPage', () => {
  beforeEach(() => {
    authApi.login.mockReset();
  });

  it('keeps the button disabled until both fields are filled', () => {
    renderLoginPage();
    expect(screen.getByRole('button', { name: 'Log in' })).toBeDisabled();
  });

  it('shows the server message when the credentials are wrong', async () => {
    authApi.login.mockRejectedValue(new ApiError(401, 'Invalid email or password'));
    renderLoginPage();

    await submit('dana@acme.inc', 'wrong-password');

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
    expect(authApi.login).toHaveBeenCalledWith('dana@acme.inc', 'wrong-password');
    // The form is usable again so the user can retry.
    expect(screen.getByRole('button', { name: 'Log in' })).toBeEnabled();
    expect(screen.queryByText('Home page')).not.toBeInTheDocument();
  });

  it('trims the email before sending it', async () => {
    authApi.login.mockRejectedValue(new ApiError(401, 'Invalid email or password'));
    renderLoginPage();

    await submit('  dana@acme.inc  ', 'pw');

    expect(authApi.login).toHaveBeenCalledWith('dana@acme.inc', 'pw');
  });

  it('goes to the home page after a successful login', async () => {
    // A token that expires in 8 hours, like the real ones (only the payload is read client-side).
    const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 8 * 3600 }));
    authApi.login.mockResolvedValue({
      token: `header.${payload}.signature`,
      user: { id: 5, name: 'Dana', role: 'employee' },
    });
    renderLoginPage();

    await submit('dana@acme.inc', 'right-password');

    expect(await screen.findByText('Home page')).toBeInTheDocument();
  });
});
