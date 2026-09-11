// The one module in the codebase allowed to call fetch; eslint.config.js exempts this file and no
// other (docs/engineering-standards.md section 5). Everything else reaches the API through
// TanStack Query calling in here.

// Same-origin in production, and the Vite dev proxy keeps it same-origin in development too, so no
// CORS-only code path exists that production never exercises.
const API_BASE = '/api/v1';

const REFRESH_PATH = '/auth/refresh';

// The auth handshake itself must never trigger a refresh. A wrong password is a 401 the user has
// to see, not a session to repair — and refreshing on /auth/refresh's own 401 is a loop by
// construction.
const NEVER_REFRESH: ReadonlySet<string> = new Set(['/auth/login', REFRESH_PATH, '/auth/logout']);

/** The failure envelope every backend error uses (docs/engineering-standards.md section 4). */
export type ApiError = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  requestId?: string;
};

export class ApiClientError extends Error {
  readonly code: string;

  // Declared `| undefined` instead of optional: exactOptionalPropertyTypes rejects assigning
  // undefined to an optional property, and the constructor assigns both unconditionally.
  readonly details: Record<string, unknown> | undefined;

  readonly requestId: string | undefined;

  constructor(error: ApiError) {
    super(error.message);
    this.name = 'ApiClientError';
    this.code = error.code;
    this.details = error.details;
    this.requestId = error.requestId;
  }
}

// ---------------------------------------------------------------- session state
//
// The access token lives in a module variable and nowhere else — never localStorage, never a
// non-httpOnly cookie (M01 spec). Script injected into the page can read both of those; it cannot
// read this any more easily than it can read anything else in the heap, and crucially the token
// dies with the tab. The refresh token is never here at all: it is an httpOnly cookie the browser
// attaches to /auth requests and JavaScript cannot see.

let accessToken: string | null = null;
let sessionExpired: (() => void) | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

/** Registered by the auth provider, so the client can say "this session is over" without importing
 *  the router. Passing null unregisters, which is what a test teardown wants. */
export function onSessionExpired(handler: (() => void) | null): void {
  sessionExpired = handler;
}

// ---------------------------------------------------------------- error mapping

type ErrorEnvelope = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};

function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== 'object' || body === null) {
    return false;
  }
  const candidate = body as Record<string, unknown>;
  if (typeof candidate.code !== 'string' || typeof candidate.message !== 'string') {
    return false;
  }
  return (
    candidate.details === undefined ||
    (typeof candidate.details === 'object' && candidate.details !== null)
  );
}

async function readJson(response: Response): Promise<unknown> {
  try {
    const parsed: unknown = await response.json();
    return parsed;
  } catch {
    // A proxy 502 or an HTML error page is not our envelope; the caller synthesises a code.
    return null;
  }
}

function toApiError(status: number, body: unknown, requestId: string | null): ApiError {
  // Spread-or-nothing rather than `requestId: requestId ?? undefined`: exactOptionalPropertyTypes
  // forbids an explicit undefined on an optional property.
  const identity = requestId === null ? {} : { requestId };

  if (!isErrorEnvelope(body)) {
    // Anything that never reached the application still has to carry a stable `code`, because the
    // UI switches on code and never on HTTP status.
    return {
      code: `http.${String(status)}`,
      message: `The server returned an unexpected response (HTTP ${String(status)}).`,
      ...identity,
    };
  }

  return {
    code: body.code,
    message: body.message,
    ...(body.details === undefined ? {} : { details: body.details }),
    ...identity,
  };
}

async function errorFrom(response: Response): Promise<ApiClientError> {
  const body = await readJson(response);
  return new ApiClientError(
    toApiError(response.status, body, response.headers.get('X-Request-Id')),
  );
}

// ---------------------------------------------------------------- transport

type Method = 'GET' | 'POST' | 'PATCH';

async function send(method: Method, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (accessToken !== null) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const init: RequestInit = { method, headers };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  try {
    return await fetch(`${API_BASE}${path}`, init);
  } catch {
    // Restaurant networks drop constantly. A dead network has to surface as a coded error rather
    // than a bare TypeError, since every error state renders `code` and nothing may fail silently
    // (docs/ui/conventions.md).
    throw new ApiClientError({
      code: 'network.unreachable',
      message: 'Could not reach the server. Check the connection and try again.',
    });
  }
}

/**
 * Exchange the refresh cookie for a new access token. At most one of these runs at a time.
 *
 * The single-flight matters more than it looks. Several widgets mount together, all 401, and all
 * want a refresh — but refresh *rotates* the token, so the second and third calls are replays of a
 * token already spent. The backend treats a replayed refresh token as theft and revokes the entire
 * session family (`AuthService._handle_replay`), which would log the user out for the crime of
 * loading a page with three panels on it.
 */
function refreshOnce(): Promise<string | null> {
  refreshInFlight ??= negotiate().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function negotiate(): Promise<string | null> {
  const response = await send('POST', REFRESH_PATH);
  if (!response.ok) {
    // The session is genuinely over. Forget the token so nothing replays it, and tell the app,
    // which redirects to login.
    accessToken = null;
    sessionExpired?.();
    return null;
  }
  const body = (await readJson(response)) as { access_token?: unknown } | null;
  const token = typeof body?.access_token === 'string' ? body.access_token : null;
  accessToken = token;
  return token;
}

/**
 * One request, with at most one refresh-and-replay behind it.
 *
 * "At most one" is the whole contract. There is no retry counter and no loop here on purpose: the
 * only path that re-sends is the single `if` below, so a dead session costs two requests and then
 * an error, however many components are mounted.
 */
async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  let response = await send(method, path, body);

  if (response.status === 401 && !NEVER_REFRESH.has(path)) {
    const token = await refreshOnce();
    if (token !== null) {
      response = await send(method, path, body);
    }
    // If the refresh failed we deliberately fall through holding the ORIGINAL 401, so the caller
    // sees why the request failed rather than a second-hand message about the refresh.
  }

  if (!response.ok) {
    throw await errorFrom(response);
  }

  // 204 is what logout, password change, deactivate and reactivate answer. `.json()` on an empty
  // body throws, and that throw would be reported as a failed mutation of something that worked.
  if (response.status === 204) {
    return undefined as T;
  }

  const data: unknown = await response.json();
  return data as T;
}

/**
 * GET a JSON resource from the API.
 *
 * Money arrives as a STRING (`"1240.00"`) and stays one all the way to the formatter. Nothing here
 * coerces response values, because parsing a rupee amount into a JavaScript number puts a float in
 * front of money (docs/engineering-standards.md section 4, CLAUDE.md invariant 3).
 */
export function apiGet<T>(path: string): Promise<T> {
  return request<T>('GET', path);
}

export function apiPost<T = void>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, body);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>('PATCH', path, body);
}
