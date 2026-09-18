import { type ReactElement, useState } from 'react';

import { Button } from '@shared/ui/button';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { exportCsv } from '@staff/api/reports';

/**
 * Download this report as a spreadsheet.
 *
 * **Fetched, not linked.** A plain `<a href>` would reach the API without this session's token —
 * it lives in memory, not in a cookie — and putting the token in a query string would write a live
 * credential into every proxy log between here and the server. `exportCsv` sends the header and
 * hands the browser a blob to save.
 *
 * **A failed download says so.** It is the one action on a report screen that can fail while the
 * screen around it stays perfectly healthy, and a button that silently does nothing is how
 * somebody concludes the export is broken and starts re-typing figures by hand — which is the
 * habit this whole module exists to end.
 */
export function ExportButton({ report }: { report: string }): ReactElement {
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="secondary"
        disabled={busy}
        onClick={() => {
          setFailure(null);
          setBusy(true);
          void exportCsv(report)
            .catch((error: unknown) => {
              setFailure(error);
            })
            .finally(() => {
              setBusy(false);
            });
        }}
      >
        {strings.reports.exportCsv}
      </Button>
      {failure === null ? null : <Notice tone="critical" {...errorProps(failure)} />}
    </div>
  );
}
