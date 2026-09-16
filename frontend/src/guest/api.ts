// The guest bundle's own API client. Small, and deliberately not `src/shared/api.ts`.
//
// ADR 0009: "Separate frontend bundles. The guest app is a small, fast, mostly-anonymous PWA. It
// ships none of the staff code." `shared/api.ts` is persona-neutral in name only — it carries the
// staff session: a refresh cookie, a cross-tab Web Lock, a single-flight refresh, a session-expiry
// handler and an idempotency-key allow-list. A guest has none of those. A guest token is minted
// from a QR code, lives a couple of hours, and when it dies the answer is to scan again.
//
// So this is forty lines instead of four hundred, and every one of them is something a diner's
// phone actually needs on a bad network.
//
// It is the second module eslint permits to call `fetch`, for that reason and no other.

import { CURRENT_NOTICE_VERSION, NOTICE_LANGUAGE } from './consentNotice';

const BASE = '/api/v1/guest';

/** The error envelope every route in this product answers with: `{code, message, details, issue}`. */
export type GuestError = {
  code: string;
  message: string;
  issue?: number | undefined;
};

export class GuestApiError extends Error {
  readonly code: string;
  readonly issue: number | undefined;
  readonly status: number;

  constructor(status: number, body: GuestError) {
    // `message` is what a person reads. The code is never shown (D11, D12).
    super(body.message);
    this.name = 'GuestApiError';
    this.code = body.code;
    this.issue = body.issue;
    this.status = status;
  }
}

let token: string | null = null;

export function setGuestToken(value: string | null): void {
  token = value;
}

export function guestToken(): string | null {
  return token;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = {
    method,
    headers: {
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(token === null ? {} : { Authorization: `Bearer ${token}` }),
    },
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }
  const response = await fetch(`${BASE}${path}`, init);

  if (response.status === 204) {
    return undefined as T;
  }

  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const envelope = payload as Partial<GuestError>;
    throw new GuestApiError(response.status, {
      code: envelope.code ?? 'guest.unreachable',
      // A fallback in words, because a guest on a train through a tunnel gets no envelope at all.
      message: envelope.message ?? 'We could not reach the restaurant. Check your connection.',
      issue: envelope.issue,
    });
  }
  return payload as T;
}

export type GuestSession = {
  token: string;
  expires_at: string;
  restaurant_name: string;
  scope: 'table' | 'order';
};

export function openSession(code: { table_slug?: string; order_token?: string }): Promise<GuestSession> {
  return request<GuestSession>('POST', '/session', code);
}

export type GuestVariant = { id: string; name: string; price: string };

export type GuestModifier = { id: string; name: string; price_delta: string };

export type GuestModifierGroup = {
  id: string;
  name: string;
  min_select: number;
  max_select: number;
  is_required: boolean;
  modifiers: GuestModifier[];
};

export type GuestItem = {
  id: string;
  name: string;
  description: string | null;
  food_type: 'veg' | 'non_veg' | 'egg';
  allergen_statement: string | null;
  calories_kcal: number | null;
  serving_size: string | null;
  image_url: string | null;
  variants: GuestVariant[];
  modifier_groups: GuestModifierGroup[];
};

export type GuestMenu = {
  version: number;
  categories: { id: string; name: string; items: GuestItem[] }[];
};

export function fetchMenu(): Promise<GuestMenu> {
  return request<GuestMenu>('GET', '/menu');
}

export type GuestBill = {
  lines: { name: string; quantity: number; amount: string }[];
  subtotal: string;
  discount_total: string;
  charge_total: string;
  tax_total: string;
  round_off: string;
  grand_total: string;
  is_settled: boolean;
};

export function fetchBill(): Promise<GuestBill> {
  return request<GuestBill>('GET', '/order');
}

export type FeedbackAnswers = {
  food_rating: number | null;
  service_rating: number | null;
  would_return: boolean | null;
  comment: string | null;
  phone: string | null;
  consents: string[];
};

export type FeedbackResult = { id: string; submitted_at: string; already_submitted: boolean };

export function submitFeedback(answers: FeedbackAnswers): Promise<FeedbackResult> {
  return request<FeedbackResult>('POST', '/feedback', {
    ...answers,
    // Sent with every submission that carries a consent, so the server records the words this
    // screen actually showed rather than whatever it believes is current.
    notice_version: CURRENT_NOTICE_VERSION,
    notice_language: NOTICE_LANGUAGE,
  });
}

export function withdrawConsent(purpose: string): Promise<unknown> {
  return request<unknown>('POST', '/consent', {
    purpose,
    notice_version: CURRENT_NOTICE_VERSION,
    notice_language: NOTICE_LANGUAGE,
  });
}
