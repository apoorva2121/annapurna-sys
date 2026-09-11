import { ApiClientError } from '@shared/api';

/**
 * Turn any thrown value into the two things a Notice shows.
 *
 * Separate from QueryState.tsx because eslint's react-refresh rule requires a module to export
 * components or non-components, not both.
 *
 * An unknown throw still produces a title: a mutation that failed for a reason we did not model
 * must not render an empty red box.
 */
export function errorProps(error: unknown): { title: string; code: string | undefined } {
  if (error instanceof ApiClientError) {
    return { title: error.message, code: error.code };
  }
  return { title: 'Something went wrong.', code: undefined };
}
