import { useQuery } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import { ApiClientError, apiGet } from '@shared/api';

// Keys are the API's JSON keys verbatim (docs/engineering-standards.md section 4). No camelCase
// mapping layer until a real feature needs one; M00 only proves the wire works.
type VersionResponse = {
  git_sha: string;
  built_at: string;
  env: string;
};

/**
 * M00 has no features. This screen exists to prove one thing: the web app loads and reaches the
 * API. Real screens arrive in M01, so it is deliberately plain.
 */
export default function App(): ReactElement {
  const versionQuery = useQuery({
    queryKey: ['version'],
    queryFn: () => apiGet<VersionResponse>('/version'),
  });

  // Pending, error and success are all rendered explicitly — no state may fail silently
  // (docs/engineering-standards.md section 5). Each is labelled in words as well as colour, because
  // colour never carries meaning alone (docs/ui/conventions.md).
  let body: ReactElement;

  if (versionQuery.isPending) {
    body = <p className="text-muted-foreground">Checking the API...</p>;
  } else if (versionQuery.isError) {
    const code =
      versionQuery.error instanceof ApiClientError ? versionQuery.error.code : 'client.unexpected';
    body = (
      <div className="rounded border border-critical p-4" role="alert">
        <p className="font-semibold text-critical">Cannot reach the API</p>
        <p className="font-mono text-sm text-muted-foreground">{code}</p>
        <p>{versionQuery.error.message}</p>
      </div>
    );
  } else {
    body = (
      <div className="rounded border border-border p-4">
        <p className="font-semibold text-success">API reachable</p>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 text-sm">
          <dt className="text-muted-foreground">Commit</dt>
          <dd className="font-mono">{versionQuery.data.git_sha}</dd>
          <dt className="text-muted-foreground">Built</dt>
          <dd className="font-mono">{versionQuery.data.built_at}</dd>
          <dt className="text-muted-foreground">Environment</dt>
          <dd className="font-mono">{versionQuery.data.env}</dd>
        </dl>
      </div>
    );
  }

  return (
    <main className="mx-auto max-w-md p-6">
      <h1 className="text-xl font-semibold">Restaurant OS</h1>
      <p className="mb-4 text-sm text-muted-foreground">M00 foundation - connectivity check</p>
      {body}
    </main>
  );
}
