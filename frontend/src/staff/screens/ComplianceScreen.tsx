import { type ReactElement, useState } from 'react';

import { Button } from '@shared/ui/button';
import { Permission } from '@shared/permissions';
import { useAuth } from '@staff/auth/AuthContext';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type Finding,
  exportCompliance,
  useAcknowledge,
  useCompliance,
  useSuppress,
} from '@staff/api/compliance';

/**
 * What puts this restaurant's licences at risk.
 *
 * **Opening this screen is the check.** There is no background job (ADR 0005), so the request
 * behind this list evaluates the ten rules, writes what it newly found and resolves what has been
 * put right. That is why `raised_at` reads *"first detected by this system"* — a licence that
 * expired in March and is first opened in June is dated June, and the screen says so rather than
 * leaving somebody to work it out during an inspection.
 *
 * **Every finding shows where the rule comes from, and when that was last checked.**
 * `docs/compliance-rules.md` opens by recording that research returned stale-but-confident Indian
 * law three times in one session. A product that warns a restaurant about the law can be
 * confidently wrong about it, and the mitigation is not to try harder — it is to put the
 * instrument and the `checked_on` date on the screen so a person can verify rather than trust.
 *
 * **A rule that is not in force says so in words.** Never in a colour, never by being smaller.
 * *"Notified, but not in force yet — this is not law today."* Conflating that with a current
 * obligation is the single failure this module must not commit, because an owner who acts on a
 * false alarm once will ignore the true one after it.
 *
 * **Setting something aside is a decision, not a delete.** The finding stays, marked, with the
 * reason attached — and the hint on the box says so before somebody types. The export is what an
 * owner hands an inspector, and advice ignored is still advice given.
 */
export default function ComplianceScreen(): ReactElement {
  const review = useCompliance();
  const { can } = useAuth();

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.compliance.title}</h1>
      <p className="text-sm text-muted-foreground">{strings.compliance.intro}</p>

      <QueryState
        isPending={review.isPending}
        error={review.error}
        pendingLabel={strings.compliance.loading}
      >
        {review.data === undefined ? null : (
          <>
            <p className="text-sm font-medium">
              {review.data.outstanding === 0
                ? strings.compliance.clear
                : strings.compliance.outstanding(review.data.outstanding)}
            </p>
            <ol className="flex flex-col gap-4">
              {review.data.findings.map((finding) => (
                <Row key={finding.id} finding={finding} mayAct={can(Permission.COMPLIANCE_ACT)} />
              ))}
            </ol>
            <ExportRecord />
          </>
        )}
      </QueryState>
    </div>
  );
}

/**
 * One finding, in the order a person needs it: what it is, why it matters, what to do, and only
 * then where the rule comes from.
 *
 * **No colour carries the severity.** `docs/ui/conventions.md` rule 5, and here it matters more
 * than usual — a red border on an advisory about law that commences in 2027 would be the product
 * asserting urgency it has no right to. The severity is a word.
 */
function Row({ finding, mayAct }: { finding: Finding; mayAct: boolean }): ReactElement {
  const state = strings.compliance.state[finding.state] ?? '';
  return (
    <li className="flex flex-col gap-2 rounded border border-border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium">{finding.title}</span>
        <span className="text-sm text-muted-foreground">
          {strings.compliance.severity[finding.severity] ?? finding.severity}
        </span>
      </div>

      <p className="text-sm">
        <span className="text-muted-foreground">{strings.compliance.risk}: </span>
        {finding.risk}
      </p>
      <p className="text-sm">
        <span className="text-muted-foreground">{strings.compliance.action}: </span>
        {finding.action}
      </p>

      <Source finding={finding} />

      {state !== '' && <p className="text-sm font-medium">{state}</p>}
      {mayAct && finding.state === 'open' && <Actions finding={finding} />}
    </li>
  );
}

/**
 * The instrument, when it commenced, when the citation was last checked — and, when the rule is
 * anything other than in force, the sentence saying so.
 */
function Source({ finding }: { finding: Finding }): ReactElement {
  const citation = finding.citation;
  const caveat =
    citation === null || citation.status === 'in_force'
      ? null
      : (strings.compliance.status[citation.status] ?? null);

  return (
    <div className="flex flex-col gap-1 border-t border-border pt-2 text-sm text-muted-foreground">
      {/* Said before the citation, not after it: somebody who stops reading here must not stop
          having read that this is not a current obligation. */}
      {caveat !== null && <p className="font-medium text-foreground">{caveat}</p>}
      {citation !== null && (
        <>
          <p>
            {strings.compliance.source}: {citation.instrument}
          </p>
          <p className="tabular-nums">
            {strings.compliance.commenced(citation.commencement)}{' '}
            {strings.compliance.checkedOn(citation.checked_on)}
          </p>
        </>
      )}
      <p className="tabular-nums">
        {strings.compliance.detected(finding.raised_at.slice(0, 10))}{' '}
        {strings.compliance.detectedNote}
      </p>
    </div>
  );
}

/** Mark as seen, or set aside with a reason. Only for somebody who holds `compliance.act`. */
function Actions({ finding }: { finding: Finding }): ReactElement {
  const [reason, setReason] = useState<string | null>(null);
  const acknowledge = useAcknowledge();
  const suppress = useSuppress();

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          disabled={acknowledge.isPending}
          onClick={() => {
            acknowledge.mutate({ id: finding.id });
          }}
        >
          {strings.compliance.acknowledge}
        </Button>
        <Button
          variant="ghost"
          onClick={() => {
            setReason(reason === null ? '' : null);
          }}
        >
          {strings.compliance.suppress}
        </Button>
      </div>

      {reason !== null && (
        <div className="flex flex-col gap-2">
          <Field
            label={strings.compliance.suppressLabel}
            hint={strings.compliance.suppressHint}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
          <Button
            variant="secondary"
            disabled={reason.trim() === '' || suppress.isPending}
            onClick={() => {
              suppress.mutate({ id: finding.id, reason });
            }}
          >
            {strings.compliance.suppressSubmit}
          </Button>
        </div>
      )}

      {acknowledge.error !== null && <Notice tone="critical" {...errorProps(acknowledge.error)} />}
      {suppress.error !== null && <Notice tone="critical" {...errorProps(suppress.error)} />}
    </div>
  );
}

/**
 * The document an owner hands an inspector.
 *
 * Fetched rather than linked, for the reason `ExportButton` gives: this session's token lives in
 * memory, and putting it in a query string would write a live credential into every proxy log
 * between here and the server.
 */
function ExportRecord(): ReactElement {
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
          void exportCompliance()
            .catch((error: unknown) => {
              setFailure(error);
            })
            .finally(() => {
              setBusy(false);
            });
        }}
      >
        {strings.compliance.exportCsv}
      </Button>
      {failure === null ? null : <Notice tone="critical" {...errorProps(failure)} />}
    </div>
  );
}
