import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';

import { strings } from '@staff/strings';
import { useCompliance } from '@staff/api/compliance';

/**
 * The owner's card, and the only thing it promises: **silence when there is nothing to say.**
 *
 * `docs/compliance-rules.md` exists because research returned stale-but-confident Indian law three
 * times in one session, and the practical consequence for a *screen* is this one. A compliance
 * widget that always shows something — a green tick, a score, "0 issues" — trains its reader to
 * skim past it, and the day it has something real to say they skim past that too. So when nothing
 * is outstanding this component renders nothing at all.
 *
 * **It never renders a severity.** The dashboard says how many things want looking at and links to
 * the list; deciding which of them is the frightening one is the list's job, with the citation
 * beside it. A red badge on a dashboard is an alarm with no way to check it.
 *
 * **It is silent while loading and silent on failure.** A card that says "could not check
 * compliance" beside the evening's revenue is noise on the one screen that must stay readable
 * during service, and the list itself reports its own errors properly.
 */
export function ComplianceCard(): ReactElement | null {
  const review = useCompliance();

  if (review.data === undefined || review.data.outstanding === 0) {
    return null;
  }

  return (
    <Link className="min-h-target rounded border border-border p-4 underline" to="/compliance">
      {strings.compliance.outstanding(review.data.outstanding)}
    </Link>
  );
}
