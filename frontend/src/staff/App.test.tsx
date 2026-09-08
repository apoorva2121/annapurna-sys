import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClientError, apiGet } from '@shared/api';

import App from './App';

// Only apiGet is faked. ApiClientError stays real so the component's instanceof check - the thing
// that turns a failure into a stable `code` the UI can switch on - is what is actually exercised.
vi.mock('@shared/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@shared/api')>();
  return { ...actual, apiGet: vi.fn() };
});

const apiGetMock = vi.mocked(apiGet);

function renderApp(): void {
  // Retries off: a retrying query would make the error state take seconds to appear.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiGetMock.mockReset();
});

describe('App', () => {
  it('renders the pending state while the version request is in flight', () => {
    apiGetMock.mockReturnValue(
      new Promise(() => {
        // Never settles, so the query stays pending for the length of the assertion.
      }),
    );

    renderApp();

    expect(screen.getByText('Checking the API...')).toBeInTheDocument();
  });

  it('renders the code and message when the API returns an error envelope', async () => {
    apiGetMock.mockRejectedValue(
      new ApiClientError({
        code: 'version.unavailable',
        message: 'The version endpoint is not available.',
      }),
    );

    renderApp();

    expect(await screen.findByText('version.unavailable')).toBeInTheDocument();
    expect(screen.getByText('The version endpoint is not available.')).toBeInTheDocument();
  });

  it('renders the git sha and build time on success', async () => {
    apiGetMock.mockResolvedValue({
      git_sha: 'abc1234',
      built_at: '2026-09-08T10:00:00+00:00',
      env: 'local',
    });

    renderApp();

    expect(await screen.findByText('abc1234')).toBeInTheDocument();
    expect(screen.getByText('2026-09-08T10:00:00+00:00')).toBeInTheDocument();
  });
});
