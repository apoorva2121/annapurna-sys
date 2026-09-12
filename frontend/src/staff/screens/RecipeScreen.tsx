import { type ReactElement, useState } from 'react';
import { useParams } from 'react-router-dom';

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
import { type Draft, problemWith } from '@staff/screens/recipeLine';
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
  const [draft, setDraft] = useState<Draft[]>(() =>
    (current?.lines ?? []).map((line) => ({
      component_id: line.component_id,
      quantity: line.quantity,
    })),
  );
  const [notes, setNotes] = useState(current?.notes ?? '');
  const [problem, setProblem] = useState<string | null>(null);

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
          <div className="flex flex-wrap gap-2">
            <Button onClick={onSave} disabled={save.isPending}>
              {save.isPending ? strings.recipe.saving : strings.recipe.save}
            </Button>
            <ConfirmButton current={current} />
          </div>
        </>
      )}
    </div>
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

/** "A chef has weighed this." Absent before the first save, and absent once it is true. */
function ConfirmButton({ current }: { current: Recipe | null }): ReactElement {
  const confirm = useConfirmRecipe();
  if (current === null || current.confirmed_at !== null) {
    return <></>;
  }
  return (
    <>
      <Button
        variant="secondary"
        disabled={confirm.isPending}
        onClick={() => {
          confirm.mutate({ id: current.id });
        }}
      >
        {confirm.isPending ? strings.recipe.confirming : strings.recipe.confirm}
      </Button>
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
}: {
  draft: Draft[];
  catalogue: StockItem[];
  mayManage: boolean;
  onRemove: (componentId: string) => void;
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
        {draft.map((line) => {
          const item = byId.get(line.component_id);
          return (
            <TableRow key={line.component_id}>
              <TableCell>
                {item?.name ?? line.component_id}
                <span className="ml-2 rounded-sm bg-neutral-soft px-1.5 py-0.5 text-xs text-neutral">
                  {item?.kind === 'preparation'
                    ? strings.stock.preparations
                    : strings.stock.ingredients}
                </span>
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums">
                {line.quantity} {item?.base_unit ?? ''}
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
        })}
      </TableBody>
    </Table>
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
