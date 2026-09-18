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

// The writes whose effect is money or stock (ADR 0010). A request to one of these without an
// Idempotency-Key is refused here, before it leaves the browser. The key has to be made when the
// person tapped (`useIdempotencyKey`): a wrapper that invented one per request would give every
// retry a new key, which is exactly the double booking the key exists to stop.
const IDEMPOTENT_ENDPOINTS: readonly RegExp[] = [
  /^\/staff\/goods-receipts$/,
  /^\/staff\/purchase-orders\/[^/]+\/receive$/,
  /^\/staff\/orders\/[^/]+\/settle$/,
  /^\/staff\/invoices\/[^/]+\/cancel$/,
  /^\/staff\/invoices\/[^/]+\/credit-notes$/,
  /^\/staff\/cash\/sessions\/[^/]+\/payouts$/,
  /^\/staff\/cash\/sessions\/[^/]+\/adjustments$/,
  // M09. Logging waste writes the stock ledger, and a double-tapped Log on a phone in a kitchen is
  // exactly what the key exists for — double-booked waste is not a duplicate row, it is a second
  // consumption and a food-cost figure that is wrong all month.
  /^\/staff\/wastage$/,
];

export type RequestOptions = { idempotencyKey?: string };

export function requiresIdempotencyKey(method: string, path: string): boolean {
  return method === 'POST' && IDEMPOTENT_ENDPOINTS.some((pattern) => pattern.test(path));
}

/** The failure envelope every backend error uses (docs/engineering-standards.md section 4). */
export type ApiError = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  requestId?: string;
  /** The number a person quotes (backlog-issues B12, D12). The code is never shown. */
  issue?: number;
};

/**
 * Issue numbers for the errors the browser makes itself, from `backend/app/core/issues.json`.
 * `api.issue.test.ts` fails if they drift from the catalogue.
 */
export const FRONTEND_ISSUES = {
  'network.unreachable': 1084,
  'idempotency.key_missing': 1055,
  'http.status': 1052,
} as const;

export class ApiClientError extends Error {
  readonly code: string;

  // Declared `| undefined` instead of optional: exactOptionalPropertyTypes rejects assigning
  // undefined to an optional property, and the constructor assigns both unconditionally.
  readonly details: Record<string, unknown> | undefined;

  readonly requestId: string | undefined;

  readonly issue: number | undefined;

  constructor(error: ApiError) {
    super(error.message);
    this.name = 'ApiClientError';
    this.code = error.code;
    this.details = error.details;
    this.requestId = error.requestId;
    this.issue = error.issue;
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
  issue?: unknown;
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
      issue: FRONTEND_ISSUES['http.status'],
      ...identity,
    };
  }

  return {
    code: body.code,
    message: body.message,
    ...(body.details === undefined ? {} : { details: body.details }),
    ...(typeof body.issue === 'number' ? { issue: body.issue } : {}),
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

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

async function send(
  method: Method,
  path: string,
  body?: unknown,
  idempotencyKey?: string,
): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (idempotencyKey !== undefined) {
    headers['Idempotency-Key'] = idempotencyKey;
  }
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
    // than a bare TypeError, since every error state carries `code` and nothing may fail silently
    // (docs/ui/conventions.md).
    throw new ApiClientError({
      code: 'network.unreachable',
      message: 'Could not reach the server. Check the connection and try again.',
      issue: FRONTEND_ISSUES['network.unreachable'],
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
  refreshInFlight ??= acrossTabs(negotiate).finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

// The lock every tab of this browser takes before refreshing (backlog-issues B4, owner decision D6).
// The server has no grace window: a rotated refresh token presented twice revokes the whole family.
// The single-flight above only covers one tab, so two tabs waking together would each present the
// same cookie. Under this lock the second tab refreshes after the first, with the cookie the first
// rotated. A browser without Web Locks keeps the single-flight alone.
const REFRESH_LOCK = 'restaurant-os-refresh';

function acrossTabs(run: () => Promise<string | null>): Promise<string | null> {
  const locks = (globalThis.navigator as { locks?: LockManager } | undefined)?.locks;
  return locks === undefined ? run() : locks.request(REFRESH_LOCK, run);
}

async function negotiate(): Promise<string | null> {
  const response = await send('POST', REFRESH_PATH);
  const body = response.ok
    ? ((await readJson(response)) as { access_token?: unknown } | null)
    : null;
  const token = typeof body?.access_token === 'string' ? body.access_token : null;

  if (token !== null) {
    accessToken = token;
    return token;
  }

  // No usable credential came back, but *why* decides what to do about it.
  //
  // 401 is the server saying this session is over: forget the token so nothing replays it, and
  // tell the app, which redirects to login.
  //
  // Anything else — a 502 from a proxy mid-deploy, an HTML error page, a 200 whose body carries no
  // token — is a fault, not an expiry. Ending the session for it would sign people out of a
  // working session because of our own deployment, during service. A dropped connection already
  // behaves this way (`send` throws before reaching here), and these should not differ.
  if (response.status === 401) {
    accessToken = null;
    sessionExpired?.();
  }
  return null;
}

/**
 * One request, with at most one refresh-and-replay behind it.
 *
 * "At most one" is the whole contract. There is no retry counter and no loop here on purpose: the
 * only path that re-sends is the single `if` below, so a dead session costs two requests and then
 * an error, however many components are mounted.
 */
async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const { idempotencyKey } = options;
  if (idempotencyKey === undefined && requiresIdempotencyKey(method, path)) {
    throw new ApiClientError({
      code: 'idempotency.key_missing',
      issue: FRONTEND_ISSUES['idempotency.key_missing'],
      message: 'This action was sent without its idempotency key, which is a bug in this screen.',
    });
  }
  let response = await send(method, path, body, idempotencyKey);

  if (response.status === 401 && !NEVER_REFRESH.has(path)) {
    const token = await refreshOnce();
    if (token !== null) {
      response = await send(method, path, body, idempotencyKey);
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

/**
 * POST. For an endpoint in `IDEMPOTENT_ENDPOINTS`, `options.idempotencyKey` is required and the
 * request is refused without it rather than sent. The replay after a refresh carries the same key.
 */
export function apiPost<T = void>(
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return request<T>('POST', path, body, options);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>('PATCH', path, body);
}

/**
 * PUT, for a resource whose whole value is being replaced rather than patched.
 *
 * M03's modifier attachment is the first: a dish's list of modifier groups is a set, not a log, so
 * "these are the groups now" is the honest request and PATCH would imply a merge nobody wants.
 */
export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>('PUT', path, body);
}

/**
 * DELETE, for the few rows this product genuinely removes.
 *
 * ADR 0008 reserves deletion for rows nothing else points at — M10's customer preferences are the
 * first: a preference is a statement about somebody's body and their beliefs, and a person asking
 * for it to be taken off should have it taken off rather than flagged.
 */
export function apiDelete<T = void>(path: string): Promise<T> {
  return request<T>('DELETE', path);
}

/**
 * PUT raw bytes at one of *our own* paths, with this session's token.
 *
 * M11's upload path for a deployment whose storage cannot presign (the filesystem driver). It is
 * separate from `apiPut` because the body is a `File` rather than JSON, and separate from a bare
 * `fetch` because the token must be attached — while an upload URL that points at a *bucket* must
 * never carry it. The caller decides which by looking at the URL the server handed back; this
 * function is only ever given ours.
 */
export async function apiPutBytes(path: string, file: Blob, contentType: string): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': contentType };
  if (accessToken !== null) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  let response = await putBytes(path, file, headers);
  if (response.status === 401) {
    const token = await refreshOnce();
    if (token !== null) {
      headers.Authorization = `Bearer ${token}`;
      response = await putBytes(path, file, headers);
    }
  }
  if (!response.ok) {
    throw await errorFrom(response);
  }
}

async function putBytes(
  path: string,
  file: Blob,
  headers: Record<string, string>,
): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${path}`, { method: 'PUT', headers, body: file });
  } catch {
    throw unreachable();
  }
}

/**
 * PUT bytes at a URL somebody else signed — a storage bucket's, never ours.
 *
 * **This deliberately sends no `Authorization` header.** The URL already carries its own
 * signature, and attaching this session's token would hand a live credential for our API to
 * another host. It lives here rather than in a screen for the same reason every other request
 * does, and because this is the one file allowed to call `fetch` at all.
 *
 * The headers are the server's, sent back exactly: with S3 the content type is part of what was
 * signed, and a different one is a signature mismatch nothing above could explain.
 */
/**
 * Fetch a report's CSV and hand the browser a file to save.
 *
 * **It cannot be a plain `<a href>`.** This application's access token lives in memory rather than
 * in a cookie (see `setAccessToken`), so a link would arrive at the API unauthenticated — and
 * putting the token in the query string would write a live credential into every proxy log it
 * passes. So the bytes are fetched with the header, turned into a blob, and saved.
 *
 * Buffering the whole file is fine here and only here: every report this serves is an *aggregate*
 * — a row per day, per ingredient or per dish — so the largest of them is a few hundred lines. A
 * route that streamed raw order lines would need a different answer.
 */
export async function downloadCsv(path: string, filename: string): Promise<void> {
  const headers: Record<string, string> = { Accept: 'text/csv' };
  if (accessToken !== null) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { method: 'GET', headers });
  } catch {
    throw unreachable();
  }
  if (!response.ok) {
    throw await errorFrom(response);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
  } finally {
    // Revoked immediately: an object URL holds the blob in memory until it is, and a manager
    // exporting a report a dozen times in an afternoon should not accumulate a dozen copies.
    URL.revokeObjectURL(url);
  }
}

export async function putToSignedUrl(
  url: string,
  method: string,
  headers: Record<string, string>,
  file: Blob,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(url, { method, headers, body: file });
  } catch {
    throw unreachable();
  }
  if (!response.ok) {
    throw unreachable();
  }
}

// ---------------------------------------------------------------- server-sent events (M08)

/** One parsed event off a `text/event-stream` body. */
export type StreamEvent = { id: string | null; event: string; data: string };

export type StreamOptions = {
  signal: AbortSignal;
  /** The highest id this client has already applied. Replayed from, inclusively, by the server. */
  lastEventId?: string | null;
  onEvent: (event: StreamEvent) => void;
  /** The server's own `retry:` value, in milliseconds. The caller backs off by it. */
  onRetryInterval?: (milliseconds: number) => void;
};

/**
 * Read a Server-Sent Events stream, with this client's access token on it.
 *
 * **Why not `EventSource`.** The browser's own implementation cannot set a request header, and this
 * application's access token lives in memory rather than in a cookie (see `setAccessToken` above).
 * The usual workaround — putting the token in the query string — writes a live credential into
 * every proxy log, load balancer log and browser history entry it passes. So the stream is read
 * from a `fetch` body instead, which costs this parser and buys the same `Authorization` header,
 * the same single-flight refresh, and control over the backoff.
 *
 * Resolves when the server closes the stream or the caller aborts. Reconnection is the caller's:
 * this function does one connection, so the retry policy lives with the screen that knows what a
 * gap means.
 */
export async function openEventStream(path: string, options: StreamOptions): Promise<void> {
  const body = await connectStream(path, options);
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      // `stream: true` matters: a multi-byte character can straddle two chunks, and decoding each
      // chunk independently would corrupt a dish name at the boundary.
      buffer += decoder.decode(value, { stream: true });
      // An event ends at a blank line. Anything after the last one is a partial event and stays in
      // the buffer until the rest of it arrives.
      const blocks = buffer.split(/\r\n\r\n|\n\n|\r\r/);
      buffer = blocks.pop() ?? '';
      blocks.forEach((block) => { dispatchBlock(block, options); });
    }
  } finally {
    reader.releaseLock();
  }
}

/** The handshake: one attempt, one refresh-and-retry, and a readable body or an error. */
async function connectStream(
  path: string,
  { signal, lastEventId }: StreamOptions,
): Promise<ReadableStream<Uint8Array>> {
  let response = await sendStream(path, lastEventId, signal);
  if (response.status === 401) {
    const token = await refreshOnce();
    if (token !== null) {
      response = await sendStream(path, lastEventId, signal);
    }
  }
  if (!response.ok) {
    throw await errorFrom(response);
  }
  if (response.body === null) {
    throw unreachable();
  }
  return response.body;
}

function dispatchBlock(block: string, { onEvent, onRetryInterval }: StreamOptions): void {
  const { event, retry } = parseEventBlock(block);
  if (retry !== null) {
    onRetryInterval?.(retry);
  }
  if (event !== null) {
    onEvent(event);
  }
}

function unreachable(): ApiClientError {
  return new ApiClientError({
    code: 'network.unreachable',
    message: 'Could not reach the server. Check the connection and try again.',
    issue: FRONTEND_ISSUES['network.unreachable'],
  });
}

function sendStream(
  path: string,
  lastEventId: string | null | undefined,
  signal: AbortSignal,
): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'text/event-stream' };
  if (accessToken !== null) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  if (lastEventId !== null && lastEventId !== undefined) {
    headers['Last-Event-ID'] = lastEventId;
  }
  try {
    return fetch(`${API_BASE}${path}`, { method: 'GET', headers, signal });
  } catch {
    throw unreachable();
  }
}

/**
 * One event block, per the HTML spec's event-stream parser.
 *
 * A block carrying only a comment (`: heartbeat`) yields no event, which is the point of a
 * heartbeat: it proves the connection is alive without pretending anything happened.
 */
function parseEventBlock(block: string): { event: StreamEvent | null; retry: number | null } {
  const fields = { id: null as string | null, event: 'message', data: [] as string[], retry: null as number | null };

  for (const rawLine of block.split(/\r\n|\n|\r/)) {
    // A blank line is framing and a line beginning with a colon is a comment — the heartbeat.
    if (rawLine !== '' && !rawLine.startsWith(':')) {
      applyField(fields, rawLine);
    }
  }

  const event =
    fields.data.length === 0
      ? null
      : { id: fields.id, event: fields.event, data: fields.data.join('\n') };
  return { event, retry: fields.retry };
}

type EventFields = { id: string | null; event: string; data: string[]; retry: number | null };

function applyField(fields: EventFields, rawLine: string): void {
  const colon = rawLine.indexOf(':');
  const field = colon === -1 ? rawLine : rawLine.slice(0, colon);
  // One leading space after the colon is part of the framing, not of the value.
  const value = colon === -1 ? '' : rawLine.slice(colon + 1).replace(/^ /, '');

  if (field === 'id') {
    fields.id = value;
  } else if (field === 'event') {
    fields.event = value;
  } else if (field === 'data') {
    fields.data.push(value);
  } else if (field === 'retry' && /^\d+$/.test(value)) {
    fields.retry = Number(value);
  }
  // Any other field name is ignored, which the wire format requires: it is how a server adds one
  // without breaking every client that predates it.
}
