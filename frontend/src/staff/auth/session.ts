// The shape of an authenticated session, and the four calls that create, restore and end one.
//
// Keys are the API's JSON keys verbatim (docs/engineering-standards.md section 4). No camelCase
// mapping layer until a real feature needs one — a mapper is a second place for the contract to be
// wrong.

import { apiGet, apiPost, setAccessToken } from '@shared/api';
import type { RestaurantTheme } from '@shared/theme/theme';

export type RestaurantSummary = {
  id: string;
  name: string;
  code: string;
  timezone: string;
  currency: string;
  /** `HH:MM:SS`. Travels with `timezone` because neither half of the business-day rule is any use
   *  alone — see `@shared/businessDay`. A restaurant's day starts here, not at midnight (ADR 0004). */
  business_day_start: string;
  /** `YYYY-MM-DD`, as the restaurant declared it (backlog-issues B8). Absent from an older API. */
  fssai_licence_expires_on?: string | null;
  /** The restaurant-wide look and its festive schedule. In the session rather than only on the
   *  settings endpoint, because that one is owner-and-admin-only and a theme has to render for the
   *  waiter too.
   *
   *  Optional because this is a *wire* type: during a deploy the app and the API are briefly
   *  different versions, and a field the server has not started sending must degrade to the default
   *  look rather than white-screen every signed-in user. */
  theme?: RestaurantTheme;
};

/** What a restaurant's theme is when the server sent none — an older API, or a seeded restaurant
 *  that predates the setting. Rendering the default look is a degradation; crashing is not. */
export const NO_RESTAURANT_THEME: RestaurantTheme = { default: null, schedule: [] };

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
  /** Every branch this person may switch to, including the current one (finding S12). The server
   *  decides; the client only renders what it is given. Optional for the same deploy-skew reason as
   *  `theme` above — the mapper below fills it in, so `Session.restaurants` is always present. */
  restaurants?: RestaurantSummary[];
  /** True when `restaurants` is the first twenty of more (backlog-issues B3); the rest page from
   *  `GET /auth/restaurants`. */
  has_more_restaurants?: boolean;
  roles: string[];
  permissions: string[];
  /** Serves tables. Optional for the same deploy-skew reason as `restaurants` above. */
  takes_tables?: boolean;
};

/** The session as the app holds it. `permissions` is a Set because `can()` runs on every render of
 *  every guarded element. */
export type Session = {
  employeeId: string;
  passwordChangeRequired: boolean;
  fullName: string;
  employeeCode: string;
  restaurant: RestaurantSummary;
  restaurants: RestaurantSummary[];
  hasMoreRestaurants: boolean;
  roles: string[];
  permissions: ReadonlySet<string>;
  /** Serves tables, and therefore sees the screens that are about working the floor.
   *
   *  Separate from `permissions` on purpose: an owner holds every permission there is, so no
   *  permission can ever be absent from them, and "this is not an owner's job" is not a statement
   *  about authority. See migration 0057. */
  takesTables: boolean;
};

function sessionFromMe(response: MeResponse): Session {
  return {
    employeeId: response.employee_id,
    passwordChangeRequired: false,
    fullName: response.full_name,
    employeeCode: response.employee_code,
    restaurant: response.restaurant,
    // Defaulted rather than trusted. During a deploy the app and the API are briefly different
    // versions, and a field the server has not started sending yet must not white-screen every
    // signed-in user — `session.restaurants.length` on undefined takes down the whole tree, not
    // just the switcher. One restaurant is the honest fallback: it is where they are.
    restaurants: response.restaurants ?? [response.restaurant],
    hasMoreRestaurants: response.has_more_restaurants ?? false,
    roles: response.roles,
    permissions: new Set(response.permissions),
    // Defaulted to false during a deploy skew: the conservative direction is to hide a floor
    // control from somebody rather than show one to an owner who does not want it.
    takesTables: response.takes_tables ?? false,
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

export type OrganizationOption = { id: string; name: string };

/** What POST /auth/login answers when the password opens accounts in more than one organization
 *  (backlog-issues B4): a single-use pass and where it can be used. No token is held yet. */
type OrganizationChoiceResponse = {
  choose_organization: true;
  ticket: string;
  expires_in_seconds: number;
  organizations: OrganizationOption[];
};

/** Thrown by `login` when the person has to say which organization. Not a failure: the screen asks,
 *  and `chooseOrganization` finishes signing in with the pass. */
export class OrganizationChoiceNeeded extends Error {
  readonly ticket: string;
  readonly organizations: OrganizationOption[];

  constructor(ticket: string, organizations: OrganizationOption[]) {
    super('Choose an organization');
    this.name = 'OrganizationChoiceNeeded';
    this.ticket = ticket;
    this.organizations = organizations;
  }
}

export async function login(identifier: string, password: string): Promise<Session> {
  const response = await apiPost<SessionResponse | OrganizationChoiceResponse>('/auth/login', {
    identifier,
    password,
  });
  if ('choose_organization' in response) {
    throw new OrganizationChoiceNeeded(response.ticket, response.organizations);
  }
  setAccessToken(response.access_token);
  // Carried from the login response: /auth/me describes the person, not the credential.
  return await profile(response.password_change_required);
}

/** The second step: sign in to the organization chosen, with the pass alone — the password is not
 *  sent again. A used or expired pass is refused and the screen starts over. */
export async function chooseOrganization(ticket: string, organizationId: string): Promise<Session> {
  const response = await apiPost<SessionResponse>('/auth/login/choose', {
    ticket,
    organization_id: organizationId,
  });
  setAccessToken(response.access_token);
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
