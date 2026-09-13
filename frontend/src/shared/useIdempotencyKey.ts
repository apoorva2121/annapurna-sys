import { useCallback, useState } from 'react';

/**
 * One idempotency key per submission (ADR 0010; M07 spec decision 8).
 *
 * **Not one per tap.** A store manager who taps "Book it in" twice on a stalled connection is making
 * one submission, and two keys would book the delivery twice — the exact failure the key exists to
 * prevent. **Not one per request either.** TanStack Query's retry re-sends the same variables, and a
 * key minted inside the request would differ on every attempt, so a retry would be a second effect.
 *
 * So the key is made when the screen first needs one and kept until the submission succeeds; the
 * screen calls `renew` on success, and the next delivery on the same screen is a new submission.
 */
export function useIdempotencyKey(): { key: string; renew: () => void } {
  const [key, setKey] = useState(newKey);
  const renew = useCallback(() => {
    setKey(newKey());
  }, []);
  return { key, renew };
}

/**
 * A random UUID. `crypto.randomUUID` exists only in a secure context, and a tablet reaching a
 * development server by its LAN address is not one, so the fallback builds the same shape from
 * `getRandomValues`, which is available everywhere.
 */
export function newKey(): string {
  if (typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
