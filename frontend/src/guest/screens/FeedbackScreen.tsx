import { type ReactElement, useState } from 'react';

import { type FeedbackResult, GuestApiError, submitFeedback, withdrawConsent } from '../api';
import { CONSENT_CHOICES, NOTICE_TEXT } from '../consentNotice';
import { strings } from '../strings';

/**
 * Three questions, and never a fourth.
 *
 * `docs/customer-experience.md`: "Three questions maximum. Food, service, would-you-return. Free
 * text optional. **Every extra question halves completion.**" So this screen asks three things and
 * the request schema has no room for more.
 *
 * **Anonymous is the normal path, not a degraded one.** A guest can rate a meal without typing
 * anything about themselves, and the feedback is still fully linked to the dish, the waiter, the
 * station and the prep time — through the order, which the bill token already names.
 *
 * **No consent box is ever pre-ticked**, on any layer (`docs/compliance-rules.md` §B2). Each one is
 * separate, each says what it is for, and each can be turned off from this same screen — which is
 * the only honest reading of "withdrawal as easy as granting".
 *
 * **Nothing here calls any of that a legal requirement.** Those obligations are notified and
 * commence 13 May 2027; this product builds to the standard now because consent architecture cannot
 * be retrofitted, and `test_consent_notice.py` asserts the screen does not overstate it.
 */
export function FeedbackScreen(): ReactElement {
  const [food, setFood] = useState<number | null>(null);
  const [service, setService] = useState<number | null>(null);
  const [wouldReturn, setWouldReturn] = useState<boolean | null>(null);
  const [comment, setComment] = useState('');
  const [phone, setPhone] = useState('');
  const [consents, setConsents] = useState<string[]>([]);
  const [result, setResult] = useState<FeedbackResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const nothingChosen = food === null && service === null && wouldReturn === null;

  if (result !== null) {
    return <Thanks result={result} consents={consents} />;
  }

  return (
    <section className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold">{strings.feedback.title}</h2>
        <p className="text-base text-muted-foreground">{strings.feedback.intro}</p>
      </header>

      <Rating label={strings.feedback.food} value={food} onChange={setFood} />
      <Rating label={strings.feedback.service} value={service} onChange={setService} />

      <fieldset className="flex flex-col gap-2">
        <legend className="text-base font-medium">{strings.feedback.wouldReturn}</legend>
        <div className="flex gap-2">
          <Choice
            selected={wouldReturn === true}
            onSelect={() => {
              setWouldReturn(true);
            }}
          >
            {strings.feedback.yes}
          </Choice>
          <Choice
            selected={wouldReturn === false}
            onSelect={() => {
              setWouldReturn(false);
            }}
          >
            {strings.feedback.no}
          </Choice>
        </div>
      </fieldset>

      <label className="flex flex-col gap-1 text-base font-medium">
        {strings.feedback.commentLabel}
        <input
          className="min-h-target rounded-md border border-border bg-background px-3 text-base font-normal"
          value={comment}
          onChange={(event) => {
            setComment(event.target.value);
          }}
          placeholder={strings.feedback.commentPlaceholder}
        />
      </label>

      {/* The phone number sits **below** the ratings, never above them: a guest who came to say the
          paneer was good must be able to finish without meeting a form about themselves. */}
      <div className="flex flex-col gap-3 border-t border-border pt-4">
        <p className="text-base font-medium">{NOTICE_TEXT.heading}</p>
        <p className="text-sm text-muted-foreground">{NOTICE_TEXT.body}</p>

        <label className="flex flex-col gap-1 text-base">
          {strings.feedback.phoneLabel}
          <input
            className="min-h-target rounded-md border border-border bg-background px-3 text-base"
            inputMode="tel"
            value={phone}
            onChange={(event) => {
              setPhone(event.target.value);
            }}
            placeholder={strings.feedback.phonePlaceholder}
          />
        </label>

        <ul className="flex flex-col gap-2">
          {CONSENT_CHOICES.map((choice) => (
            <li key={choice.purpose}>
              <label className="flex min-h-target items-start gap-3 text-base">
                <input
                  type="checkbox"
                  className="mt-1 size-5"
                  onChange={(event) => {
                    setConsents((current) =>
                      event.target.checked
                        ? [...current, choice.purpose]
                        : current.filter((purpose) => purpose !== choice.purpose),
                    );
                  }}
                />
                <span className="flex flex-col">
                  <span>{choice.label}</span>
                  <span className="text-sm text-muted-foreground">{choice.detail}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>

        <p className="text-sm text-muted-foreground">{NOTICE_TEXT.footer}</p>
      </div>

      {error === null ? null : <p className="text-base text-critical">{error}</p>}

      <button
        type="button"
        className="min-h-target rounded-md bg-primary px-4 text-base font-medium text-primary-foreground disabled:opacity-50"
        disabled={nothingChosen || sending}
        onClick={() => {
          setSending(true);
          setError(null);
          submitFeedback({
            food_rating: food,
            service_rating: service,
            would_return: wouldReturn,
            comment: comment === '' ? null : comment,
            phone: phone === '' ? null : phone,
            // Only what was actually ticked. A number with nothing ticked is not stored at all.
            consents: phone === '' ? [] : consents,
          })
            .then(setResult)
            .catch((reason: unknown) => {
              setError(
                reason instanceof GuestApiError ? reason.message : strings.scan.offlineBody,
              );
            })
            .finally(() => {
              setSending(false);
            });
        }}
      >
        {sending ? strings.feedback.sending : strings.feedback.send}
      </button>
      {nothingChosen ? (
        <p className="text-sm text-muted-foreground">{strings.feedback.nothingChosen}</p>
      ) : null}
    </section>
  );
}

/**
 * What a guest sees after tapping Send — and the only place a consent can be taken back.
 *
 * §B2 asks that withdrawing be as easy as granting. One tap, on the screen they are already
 * looking at, with no email and no waiter in between, is the only honest reading of that.
 */
function Thanks({
  result,
  consents,
}: {
  result: FeedbackResult;
  consents: string[];
}): ReactElement {
  const [withdrawn, setWithdrawn] = useState<string[]>([]);

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold">
        {result.already_submitted ? strings.feedback.alreadyTitle : strings.feedback.thanksTitle}
      </h2>
      <p className="text-base text-muted-foreground">
        {result.already_submitted ? strings.feedback.alreadyBody : strings.feedback.thanksBody}
      </p>
      {consents.length === 0 ? null : (
        <ul className="flex flex-col gap-2">
          {consents.map((purpose) => (
            <li key={purpose} className="flex items-center justify-between gap-2">
              <span className="text-sm">
                {CONSENT_CHOICES.find((choice) => choice.purpose === purpose)?.label ?? purpose}
              </span>
              {withdrawn.includes(purpose) ? (
                <span className="text-sm text-muted-foreground">{strings.feedback.withdrawn}</span>
              ) : (
                <button
                  type="button"
                  className="min-h-target rounded-md bg-muted px-3 text-base"
                  onClick={() => {
                    void withdrawConsent(purpose).then(() => {
                      setWithdrawn((current) => [...current, purpose]);
                    });
                  }}
                >
                  {strings.feedback.withdraw}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}


function Rating({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (value: number) => void;
}): ReactElement {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-base font-medium">{label}</legend>
      <div className="flex gap-2">
        {strings.ratings.scale.map((option) => (
          <Choice
            key={option}
            selected={value === option}
            onSelect={() => {
              onChange(option);
            }}
            label={strings.ratings.label(option)}
          >
            {String(option)}
          </Choice>
        ))}
      </div>
    </fieldset>
  );
}

function Choice({
  selected,
  onSelect,
  children,
  label,
}: {
  selected: boolean;
  onSelect: () => void;
  children: string;
  label?: string;
}): ReactElement {
  return (
    <button
      type="button"
      // Selection is a ring, not a border: a control that grows under a thumb moves the one beside
      // it, and the next tap lands on the wrong number.
      className={`min-h-target flex-1 rounded-md px-3 text-base ${
        selected ? 'bg-brand-soft text-brand ring-2 ring-brand' : 'bg-muted text-foreground'
      }`}
      aria-pressed={selected}
      aria-label={label}
      onClick={onSelect}
    >
      {children}
    </button>
  );
}
