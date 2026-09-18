// The rules that decide whether M18 is trusted or ignored, checked by a machine.
//
// `docs/compliance-rules.md` opens by recording that research returned stale-but-confident Indian
// law three times in one session. A product that warns a restaurant about the law is a product
// that can be confidently wrong about the law, and a confidently wrong warning is worse than no
// warning: an owner who acts on a false alarm once will ignore the true one after it.
//
// The backend holds most of the guarantees, because they are properties of the data — a rule that
// is not `in_force` cannot be constructed as `critical`, a suppression cannot be a delete, a
// finding's words are frozen onto its row. Five are properties of the *screen*, and a screen can
// be rewritten by somebody who has not read any of this:
//
// 1. **The screen never decides whether something is wrong.** No date arithmetic, no threshold, no
//    regex against a licence number. A browser evaluating an Indian rule would be a second
//    implementation of the law, free to disagree with the one that wrote the record — and the
//    record is what an owner hands an inspector.
// 2. **A rule that is not in force says so in words.** The status sentences must reach the screen.
//    Folding `notified_not_in_force` into a severity, or into a colour, is the one failure this
//    module cannot commit.
// 3. **No colour carries the finding.** `docs/ui/conventions.md` rule 5, and here more than
//    usual: a red border on an advisory about law commencing in 2027 is the product asserting an
//    urgency it has no right to.
// 4. **Nothing is filtered out of the list.** Suppression is a decision recorded on the server, not
//    a filter the browser applies. A finding somebody set aside stays visible, marked.
// 5. **Every finding shows where its rule comes from.** The citation is not conditional on
//    severity, on state, or on anything else the screen might decide.
import { describe, expect, it } from 'vitest';

const screens = import.meta.glob<string>('./screens/ComplianceScreen.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const card = import.meta.glob<string>('./components/ComplianceCard.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const api = import.meta.glob<string>('./api/compliance.ts', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function withoutComments(source: string): string {
  return source
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}

const screen = withoutComments(Object.values(screens)[0] ?? '');
const client = withoutComments(Object.values(api)[0] ?? '');
const dashboard = withoutComments(Object.values(card)[0] ?? '');

describe('the compliance screen keeps its five promises', () => {
  it('reads the files it checks, so an empty parse cannot pass', () => {
    expect(screen.length).toBeGreaterThan(1000);
    expect(client.length).toBeGreaterThan(500);
  });

  // Rule 1. Named concretely: these are the shapes a re-implementation would take.
  it('decides nothing about whether a rule is broken', () => {
    expect(screen, 'compares a date').not.toMatch(/new Date\(|Date\.now\(/);
    expect(screen, 'tests a licence number').not.toMatch(/\\d\{|RegExp|\.match\(/);
    expect(screen, 'compares against a threshold').not.toMatch(/[<>]=?\s*\d{3,}/);
    expect(client, 'the client decides something').not.toMatch(/new Date\(|Date\.now\(/);
  });

  // Rule 2. The four statuses are not interchangeable and the screen must be able to say which.
  it('says in words when a rule is not law today', () => {
    expect(screen).toContain('strings.compliance.status');
    expect(screen).toContain("'in_force'");
  });

  // Rule 3. The severity reaches the reader as a word from `strings`, never as a class name.
  it('never carries a finding in colour alone', () => {
    expect(screen).toContain('strings.compliance.severity');
    expect(screen, 'paints a finding').not.toMatch(
      /(text|border|bg)-(critical|serious|caution|warning|success)\b/,
    );
  });

  // Rule 4. The list is rendered whole. A `.filter(` here would be the browser deciding what an
  // inspector gets to see.
  it('filters nothing out of the list', () => {
    expect(screen).not.toContain('.filter(');
    expect(client).not.toContain('.filter(');
  });

  // Rule 5. Rendered unconditionally from the row, so no branch can drop it.
  it('shows where every rule comes from', () => {
    expect(screen).toContain('<Source finding={finding} />');
    expect(screen).toContain('strings.compliance.checkedOn');
  });

  // And the shape that makes rule 1 hard to undo: the client type carries the finished sentences,
  // so there is nothing for a screen to compute from.
  it('receives finished sentences rather than parts to assemble', () => {
    for (const field of ['title:', 'risk:', 'action:']) {
      expect(client).toContain(field);
    }
  });
});

// The sixth promise, and the only one the dashboard makes.
//
// A compliance widget that always shows something — a green tick, a score, "0 issues" — trains
// its reader to skim past it, and the day it has something real to say they skim past that too.
describe('the owner’s card is silent when there is nothing to say', () => {
  it('reads the card it checks', () => {
    expect(dashboard.length).toBeGreaterThan(300);
  });

  it('returns null when nothing is outstanding', () => {
    expect(dashboard).toContain('outstanding === 0');
    expect(dashboard).toContain('return null;');
  });

  it('renders no severity and no colour of its own', () => {
    expect(dashboard).not.toContain('severity');
    expect(dashboard).not.toMatch(/(text|border|bg)-(critical|serious|caution|warning)/);
  });

  it('says nothing while loading and nothing when the check fails', () => {
    expect(dashboard, 'shows a spinner on the dashboard').not.toContain('isPending');
    expect(dashboard, 'shows an error beside the evening’s revenue').not.toContain('error');
  });
});
