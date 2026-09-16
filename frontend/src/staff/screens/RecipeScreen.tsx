import { type ReactElement, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { Button } from '@shared/ui/button';
import { Label } from '@shared/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { useAuth } from '@staff/auth/AuthContext';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { type Draft, isQuantity, problemWith, serialise } from '@staff/screens/recipeLine';
import {
  type Recipe,
  type StockItem,
  useConfirmRecipe,
  useCurrentRecipe,
  useSaveRecipeVersion,
  useStockItems,
} from '@staff/api/stock';

/**
 * What a dish is made of — the chef's screen, and the one M04 shipped without.
 *
 * **Grams, never rupees.** `seed/organization.yaml` gives the chef `recipe.manage` and withholds
 * `cost.view` by name: "a chef sees grams, not rupees". So nothing on this screen shows a price,
 * and that is not an omission to fix later — the API does not send one to a chef, and a screen that
 * wanted one would be asking for the boundary to be removed.
 *
 * **Saving writes a new version and never edits one.** `order_line` (M07) cites the version that
 * was current when the line was added, so a recipe whose lines moved would restate what every past
 * order cost. The API has one write for this reason and the screen has one button.
 *
 * **A recipe nobody has checked says so.** `library/PROVENANCE.md` is explicit that most of the
 * starter library is estimated, so a matched recipe must be visibly different from one a chef
 * wrote — otherwise the dish-cost screen states a number with confidence nobody has earned.
 */
export default function RecipeScreen(): ReactElement {
  const { variantId } = useParams<{ variantId: string }>();
  const { can } = useAuth();
  const recipe = useCurrentRecipe(variantId);
  const items = useStockItems();

  return (
    <div className="max-w-3xl space-y-page">
      <h1 className="text-2xl font-semibold">{strings.recipe.title}</h1>
      <p className="text-sm text-muted-foreground">{strings.recipe.intro}</p>

      <QueryState
        isPending={recipe.isPending}
        error={recipe.error}
        pendingLabel={strings.recipe.title}
      >
        <Editor
          // Keyed on the variant so navigating between dishes rebuilds the draft rather than
          // carrying one dish's lines into another dish's save.
          key={variantId}
          variantId={variantId ?? ''}
          current={recipe.data ?? null}
          catalogue={items.data?.items ?? []}
          mayManage={can(Permission.RECIPE_MANAGE)}
        />
      </QueryState>
    </div>
  );
}

/** A recipe's lines as an editable draft. `null` — no recipe at all — starts from nothing. */
function savedLines(current: Recipe | null): Draft[] {
  return (current?.lines ?? []).map((line) => ({
    component_id: line.component_id,
    quantity: line.quantity,
  }));
}

function Editor({
  variantId,
  current,
  catalogue,
  mayManage,
}: {
  variantId: string;
  current: Recipe | null;
  catalogue: StockItem[];
  mayManage: boolean;
}): ReactElement {
  const save = useSaveRecipeVersion();
  const [draft, setDraft] = useState<Draft[]>(() => savedLines(current));
  const [notes, setNotes] = useState(current?.notes ?? '');
  const [problem, setProblem] = useState<string | null>(null);
  const [leaving, setLeaving] = useState(false);
  const navigate = useNavigate();

  // What the server holds, compared with what is on screen. It is the whole reason Confirm can be
  // trusted: without it a chef could edit three lines and certify the version underneath them.
  const dirty = serialise(draft) !== serialise(savedLines(current));

  function add(componentId: string, quantity: string): void {
    const found = problemWith(componentId, quantity, draft);
    setProblem(found);
    if (found === null) {
      setDraft((lines) => [...lines, { component_id: componentId, quantity: quantity.trim() }]);
    }
  }

  function onSave(): void {
    if (draft.length === 0) {
      setProblem(strings.recipe.needsLines);
      return;
    }
    // Every line, not only the one just added: quantities are editable in place, so a line that
    // was valid when it was added can be blank or zero by the time Save is pressed. The server's
    // CHECK would refuse it, but after a round trip and with the whole version rejected.
    if (draft.some((line) => !isQuantity(line.quantity))) {
      setProblem(strings.recipe.noQuantity);
      return;
    }
    setProblem(null);
    save.mutate({ menu_item_variant_id: variantId, lines: draft, notes: notes.trim() || null });
  }

  return (
    <div className="space-y-page">
      <Status current={current} mayManage={mayManage} />

      {draft.length === 0 ? (
        <p className="text-muted-foreground">{strings.recipe.empty}</p>
      ) : (
        <Lines
          draft={draft}
          catalogue={catalogue}
          mayManage={mayManage}
          onRemove={(componentId) => {
            setDraft((lines) => lines.filter((row) => row.component_id !== componentId));
          }}
          onQuantity={(componentId, quantity) => {
            setDraft((lines) =>
              lines.map((row) => (row.component_id === componentId ? { ...row, quantity } : row)),
            );
          }}
        />
      )}
      {mayManage && <AddLine catalogue={catalogue} onAdd={add} />}
      {problem !== null && <Notice tone="critical" title={problem} />}

      {mayManage && (
        <>
          <Field
            label={strings.recipe.notes}
            value={notes}
            onChange={(event) => {
              setNotes(event.target.value);
            }}
          />
          {save.isError && <Notice tone="critical" {...errorProps(save.error)} />}
          <LeaveWarning
            show={leaving}
            onLeave={() => {
              void navigate(-1);
            }}
            onStay={() => {
              setLeaving(false);
            }}
          />
          <div className="flex flex-wrap gap-2">
            {/* Disabled until something changes: saving an identical recipe made a new unconfirmed
                version of the same thing, and the server refuses it now as well. */}
            <Button onClick={onSave} disabled={save.isPending || !dirty}>
              {save.isPending ? strings.recipe.saving : strings.recipe.save}
            </Button>
            <ConfirmButton current={current} dirty={dirty} />
            <BackButton
              dirty={dirty}
              onWarn={() => {
                setLeaving(true);
              }}
              onLeave={() => {
                void navigate(-1);
              }}
            />
          </div>
        </>
      )}
    </div>
  );
}

/** A way off this page that is not Save (owner defect sheet, row 24).
 *
 * Back goes where the person came from - usually Dish costs, which is where the owner's steps
 * start. Whether a change is worth a question is this button's decision, not the editor's. */
function BackButton({
  dirty,
  onWarn,
  onLeave,
}: {
  dirty: boolean;
  onWarn: () => void;
  onLeave: () => void;
}): ReactElement {
  return (
    <Button
      variant="ghost"
      onClick={() => {
        if (dirty) {
          onWarn();
          return;
        }
        onLeave();
      }}
    >
      {strings.recipe.back}
    </Button>
  );
}

/** One question before a change is thrown away (owner defect sheet, row 24).
 *
 * Its own component rather than a block inside the editor, which is already at the complexity the
 * lint rule allows - and a prompt rendered in the page rather than `window.confirm`, which blocks
 * the tab and cannot be tested. */
function LeaveWarning({
  show,
  onLeave,
  onStay,
}: {
  show: boolean;
  onLeave: () => void;
  onStay: () => void;
}): ReactElement | null {
  if (!show) {
    return null;
  }
  return (
    <Notice tone="info" title={strings.recipe.unsaved}>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button variant="secondary" onClick={onLeave}>
          {strings.recipe.leaveAnyway}
        </Button>
        <Button variant="ghost" onClick={onStay}>
          {strings.recipe.keepEditing}
        </Button>
      </div>
    </Notice>
  );
}

/**
 * Which version this is, and whether anybody has checked it.
 *
 * `library/PROVENANCE.md` says most of the starter library is estimated, so an unconfirmed recipe
 * has to be visibly different from one a chef wrote — otherwise a cost computed from it is stated
 * with a confidence nobody earned. Its own component so the editor reads as an editor.
 */
function Status({
  current,
  mayManage,
}: {
  current: Recipe | null;
  mayManage: boolean;
}): ReactElement {
  const confirmed = current !== null && current.confirmed_at !== null;
  return (
    <div className="space-y-3">
      {!mayManage && <Notice tone="info" title={strings.recipe.readOnly} />}
      {current !== null && (
        <p className="text-sm text-muted-foreground">{strings.recipe.version(current.version)}</p>
      )}
      {current !== null && !confirmed && (
        <Notice tone="info" title={strings.recipe.unconfirmed}>
          {strings.recipe.unconfirmedWhy}
        </Notice>
      )}
      {confirmed && <Notice tone="success" title={strings.recipe.confirmed} />}
    </div>
  );
}

/**
 * "A chef has weighed this." Absent before the first save, and absent once it is true.
 *
 * **Disabled while the draft has unsaved edits.** Confirmation applies to the saved version, so a
 * chef who changed three quantities and then pressed this would mark the *old* numbers as checked —
 * and `confirmed_at` is what the dish-cost screen reads to decide whether a cost is a proposal or a
 * fact. Certifying the wrong version is worse than certifying nothing.
 */
function ConfirmButton({
  current,
  dirty,
}: {
  current: Recipe | null;
  dirty: boolean;
}): ReactElement {
  const confirm = useConfirmRecipe();
  if (current === null || current.confirmed_at !== null) {
    return <></>;
  }
  return (
    <>
      <Button
        variant="secondary"
        disabled={confirm.isPending || dirty}
        onClick={() => {
          confirm.mutate({ id: current.id });
        }}
      >
        {confirm.isPending ? strings.recipe.confirming : strings.recipe.confirm}
      </Button>
      {dirty && (
        <p className="self-center text-sm text-muted-foreground">{strings.recipe.confirmBlocked}</p>
      )}
      {confirm.isError && <Notice tone="critical" {...errorProps(confirm.error)} />}
    </>
  );
}

/** The lines as they stand, with the unit spelled out beside every number.
 *
 * Its own component so `Editor` stays readable, and because a number with no unit beside it is the
 * single easiest way to put 200 kg of paneer into a dish.
 */
function Lines({
  draft,
  catalogue,
  mayManage,
  onRemove,
  onQuantity,
}: {
  draft: Draft[];
  catalogue: StockItem[];
  mayManage: boolean;
  onRemove: (componentId: string) => void;
  onQuantity: (componentId: string, quantity: string) => void;
}): ReactElement {
  const byId = new Map(catalogue.map((item) => [item.id, item]));
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{strings.recipe.component}</TableHead>
          <TableHead className="text-right">{strings.recipe.quantity}</TableHead>
          {mayManage && <TableHead />}
        </TableRow>
      </TableHeader>
      <TableBody>
        {draft.map((line) => (
          <LineRow
            key={line.component_id}
            line={line}
            item={byId.get(line.component_id)}
            mayManage={mayManage}
            onRemove={onRemove}
            onQuantity={onQuantity}
          />
        ))}
      </TableBody>
    </Table>
  );
}

/** One line: what it is, how much of it, and the two controls that change those. */
function LineRow({
  line,
  item,
  mayManage,
  onRemove,
  onQuantity,
}: {
  line: Draft;
  item: StockItem | undefined;
  mayManage: boolean;
  onRemove: (componentId: string) => void;
  onQuantity: (componentId: string, quantity: string) => void;
}): ReactElement {
  // Falls back to the id rather than rendering blank: a line pointing at something the catalogue
  // did not return is a real state (a deactivated item, a slow second query), and a nameless row
  // with a quantity beside it is worse than an ugly one.
  const name = item?.name ?? line.component_id;
  return (
    <TableRow>
      <TableCell>
        {name}
        {/* ADR 0006 asks the editor to make it obvious when a line nests. A word, not a colour. */}
        <span className="ml-2 rounded-sm bg-neutral-soft px-1.5 py-0.5 text-xs text-neutral">
          {item?.kind === 'preparation' ? strings.stock.preparations : strings.stock.ingredients}
        </span>
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">
        {/* **Editable in place.** The first version of this screen offered only Add and Remove, so
            correcting 200 g to 180 g meant deleting the line and retyping it — on the screen whose
            whole job is a chef correcting library quantities during onboarding. The unit stays
            beside the number: a figure with no unit next to it is the easiest way there is to put
            200 kg of paneer into a dish. */}
        {mayManage ? (
          <input
            className="min-h-target w-24 rounded-md border border-input bg-card px-2 text-right font-mono tabular-nums focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            aria-label={strings.recipe.quantityFor(name)}
            value={line.quantity}
            onChange={(event) => {
              onQuantity(line.component_id, event.target.value);
            }}
          />
        ) : (
          line.quantity
        )}{' '}
        {item?.base_unit ?? ''}
      </TableCell>
      {mayManage && (
        <TableCell>
          <Button
            variant="ghost"
            onClick={() => {
              onRemove(line.component_id);
            }}
          >
            {strings.recipe.removeLine}
          </Button>
        </TableCell>
      )}
    </TableRow>
  );
}

function AddLine({
  catalogue,
  onAdd,
}: {
  catalogue: StockItem[];
  onAdd: (componentId: string, quantity: string) => void;
}): ReactElement {
  const [component, setComponent] = useState('');
  const [quantity, setQuantity] = useState('');
  const unit = catalogue.find((item) => item.id === component)?.base_unit ?? '';

  return (
    <div className="flex flex-wrap items-end gap-2 rounded-md border p-page">
      <div className="min-w-56 space-y-1">
        <Label htmlFor="recipe-component">{strings.recipe.component}</Label>
        <Select value={component} onValueChange={setComponent}>
          <SelectTrigger id="recipe-component">
            <SelectValue placeholder={strings.recipe.chooseComponent} />
          </SelectTrigger>
          <SelectContent>
            {catalogue.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.name} ({item.base_unit})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Field
        label={strings.recipe.quantity}
        // The unit is the hint, so it is impossible to type a number without seeing what it means.
        hint={unit}
        value={quantity}
        onChange={(event) => {
          setQuantity(event.target.value);
        }}
      />
      <Button
        variant="secondary"
        onClick={() => {
          onAdd(component, quantity);
          setComponent('');
          setQuantity('');
        }}
      >
        {strings.recipe.addLine}
      </Button>
    </div>
  );
}
