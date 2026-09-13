import { ApiClientError } from '@shared/api';

/**
 * Turn any thrown value into what a Notice shows, and what each Field shows under itself.
 *
 * Separate from QueryState.tsx because eslint's react-refresh rule requires a module to export
 * components or non-components, not both.
 *
 * An unknown throw still produces a title: a mutation that failed for a reason we did not model
 * must not render an empty red box.
 *
 * **A field problem is never dropped.** The server says which field broke which rule, in words
 * (`app/core/validation_messages.py`). A form wires the ones it shows into its `Field`s through
 * `fieldErrors`, and the Notice lists all of them, so a field the form does not show is still
 * explained. Found in the M03 manual pass: this helper used to keep only "The request was not
 * valid.", and nobody could tell what to fix.
 */

type FieldProblem = { field: string; message: string };

function isFieldProblem(entry: unknown): entry is FieldProblem {
  if (typeof entry !== 'object' || entry === null) {
    return false;
  }
  const candidate = entry as Record<string, unknown>;
  return typeof candidate['field'] === 'string' && typeof candidate['message'] === 'string';
}

function problems(error: unknown): FieldProblem[] {
  if (!(error instanceof ApiClientError)) {
    return [];
  }
  const fields: unknown = error.details?.['fields'];
  return Array.isArray(fields) ? (fields as unknown[]).filter(isFieldProblem) : [];
}

/** `payment_terms_days` → `Payment terms days`, for a field the screen gave no label. */
function humanise(field: string): string {
  const words = field.replaceAll(/[._]/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Each field's rule, keyed by the API field name, for `<Field error={…}>`. */
export function fieldErrors(error: unknown): Record<string, string> {
  return Object.fromEntries(problems(error).map((problem) => [problem.field, problem.message]));
}

export function errorProps(
  error: unknown,
  labels: Readonly<Record<string, string>> = {},
): { title: string; code: string | undefined; lines: string[] } {
  if (error instanceof ApiClientError) {
    return {
      title: error.message,
      code: error.code,
      lines: problems(error).map(
        (problem) => `${labels[problem.field] ?? humanise(problem.field)}: ${problem.message}`,
      ),
    };
  }
  return { title: 'Something went wrong.', code: undefined, lines: [] };
}
