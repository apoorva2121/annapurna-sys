// The one module in the codebase allowed to call fetch; eslint.config.js exempts this file and no
// other (docs/engineering-standards.md section 5). Everything else reaches the API through
// TanStack Query calling in here.

// Same-origin in production, and the Vite dev proxy keeps it same-origin in development too, so no
// CORS-only code path exists that production never exercises.
const API_BASE = '/api/v1';

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

/**
 * GET a JSON resource from the API.
 *
 * Money arrives as a STRING (`"1240.00"`) and stays one all the way to the formatter. Nothing here
 * coerces response values, because parsing a rupee amount into a JavaScript number puts a float in
 * front of money (docs/engineering-standards.md section 4, CLAUDE.md invariant 3).
 */
export async function apiGet<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { headers: { Accept: 'application/json' } });
  } catch {
    // Restaurant networks drop constantly. A dead network has to surface as a coded error rather
    // than a bare TypeError, since every error state renders `code` and nothing may fail silently
    // (docs/ui/conventions.md).
    throw new ApiClientError({
      code: 'network.unreachable',
      message: 'Could not reach the server. Check the connection and try again.',
    });
  }

  if (!response.ok) {
    const body = await readJson(response);
    const requestId = response.headers.get('X-Request-Id');
    throw new ApiClientError(toApiError(response.status, body, requestId));
  }

  const data: unknown = await response.json();
  return data as T;
}
