// The shape of an authenticated session, and the four calls that create, restore and end one.
//
// Keys are the API's JSON keys verbatim (docs/engineering-standards.md section 4). No camelCase
// mapping layer until a real feature needs one — a mapper is a second place for the contract to be
// wrong.

import { apiGet, apiPost, setAccessToken } from '@shared/api';

export type RestaurantSummary = {
  id: string;
  name: string;
  code: string;
  timezone: string;
  currency: string;
  /** `HH:MM:SS`. Travels with `timezone` because neither half of the business-day rule is any use
   *  alone — see `@shared/businessDay`. A restaurant's day starts here, not at midnight (ADR 0004). */
  business_day_start: string;
};

/** What POST /auth/login and POST /auth/refresh answer. No refresh token: that is an httpOnly
 *  cookie the browser holds and script cannot read. */
export type SessionResponse = {
  access_token: string;
  expires_in_seconds: number;
  employee_id: string;
  full_name: string;
  restaurant: RestaurantSummary;
  roles: string[];
  permissions: string[];
  /** Somebody else set this password. The person is signed in — an account nobody can sign in to
   *  cannot have its password changed by its owner — but is asked to change it immediately. */
  password_change_required: boolean;
};

/** What GET /auth/me answers — the same picture, minus the credential. */
export type MeResponse = {
  employee_id: string;
  full_name: string;
  employee_code: string;
  restaurant: RestaurantSummary;
  roles: string[];
  permissions: string[];
};

/** The session as the app holds it. `permissions` is a Set because `can()` runs on every render of
 *  every guarded element. */
export type Session = {
  employeeId: string;
  passwordChangeRequired: boolean;
  fullName: string;
  employeeCode: string;
  restaurant: RestaurantSummary;
  roles: string[];
  permissions: ReadonlySet<string>;
};

function sessionFromMe(response: MeResponse): Session {
  return {
    employeeId: response.employee_id,
    passwordChangeRequired: false,
    fullName: response.full_name,
    employeeCode: response.employee_code,
    restaurant: response.restaurant,
    roles: response.roles,
    permissions: new Set(response.permissions),
  };
}

/**
 * Everything the app knows about the signed-in person, read once the token is in place.
 *
 * Both ways in end here, and that is the point. `/auth/login` and `/auth/refresh` answer with a
 * credential and a summary; `/auth/me` answers with the profile — including `employee_code`, which
 * the other two do not carry. Building the session from the login response alone left the code
 * blank until the next page reload quietly repaired it, which is a defect that survives
 * development precisely because developers reload constantly.
 */
async function profile(passwordChangeRequired = false): Promise<Session> {
  return {
    ...sessionFromMe(await apiGet<MeResponse>('/auth/me')),
    passwordChangeRequired,
  };
}

export async function login(identifier: string, password: string): Promise<Session> {
  const response = await apiPost<SessionResponse>('/auth/login', { identifier, password });
  setAccessToken(response.access_token);
  // Carried from the login response: /auth/me describes the person, not the credential.
  return await profile(response.password_change_required);
}

/**
 * Restore a session on a cold load, using the refresh cookie alone.
 *
 * This is what makes a page refresh survivable: the access token died with the previous tab, but
 * the httpOnly cookie did not. Called once at startup; a 401 here simply means "nobody is signed
 * in", which is the normal state of a login screen and not an error to report.
 */
export async function restore(): Promise<Session | null> {
  try {
    const response = await apiPost<SessionResponse>('/auth/refresh');
    setAccessToken(response.access_token);
    return await profile(response.password_change_required);
  } catch {
    setAccessToken(null);
    return null;
  }
}

export async function logout(): Promise<void> {
  try {
    await apiPost('/auth/logout');
  } finally {
    // Even if the call failed. What the user asked for is "no credential left in this browser",
    // and that has to hold however the request went.
    setAccessToken(null);
  }
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await apiPost('/auth/password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
}
