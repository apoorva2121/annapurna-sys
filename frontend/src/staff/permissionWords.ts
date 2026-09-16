import type { Permission } from '@shared/permissions';

/**
 * What each permission lets a person do, in words (owner defect sheet row 19, backlog-issues B12).
 * The profile listed codes such as `cash.manage`. A `Record` over every permission, so adding one
 * without its sentence fails the type check.
 */
export const PERMISSION_WORDS: Record<Permission, string> = {
  'employee.view': "See the staff list and open anyone's record",
  'employee.create': 'Add a new employee, with or without a login',
  'employee.edit': "Change an employee's name, phone number or terms",
  'employee.deactivate': 'Deactivate or reactivate an employee',
  'employee.role.assign': "Give or take away an employee's roles",
  'employee.password.reset': 'Set a new password for someone who has forgotten theirs',
  'role.view': 'See what each role is allowed to do',
  'restaurant.configure': "Change the restaurant's settings, floor plan, kitchen stations and tax rates",
  'menu.view': 'See the menu',
  'menu.manage': 'Add and change dishes, sections and options',
  'menu.price': 'Change what a dish costs the guest',
  'recipe.view': 'See what each dish is made of',
  'recipe.manage': 'Write and change recipes',
  'cost.view': 'See what dishes and ingredients cost',
  'stock.view': 'See the stock on hand and its history',
  'stock.receive': 'Book in a delivery',
  'stock.produce': 'Make a batch of a preparation',
  'stock.adjust': 'Correct the stock, with a reason',
  'stock.count': 'Count the stock',
  'supplier.view': 'See suppliers and how their deliveries compare',
  'supplier.manage': 'Add and change suppliers',
  'purchase.manage': 'Raise and send purchase orders',
  'order.view': 'See orders, bills, invoices and credit notes',
  'order.create': 'Open an order for a table, a takeaway or a delivery',
  'order.modify': 'Add, change and send dishes, and cancel an unsettled order',
  'order.settle': 'Take payment and settle a bill',
  'order.void': 'Cancel an invoice, or issue a credit note and a refund',
  'order.discount': 'Give a discount or a comp, with a reason',
  'cash.manage': 'Open and close the till, count the cash, and record payouts',
  'floor.manage': 'Switch busy mode on or off for the floor',
  'order.assign': 'Choose or change who serves a table',
  'kot.view': 'See the kitchen display: what each station is cooking and what is late',
  'kot.update': 'Move a ticket through the kitchen and ask for a dish to be remade',
  'wastage.log': 'Record something thrown away — the system works out what it cost',
  'wastage.approve': 'Sign off waste that needs a second person to check it',
};

export function wordsFor(code: string): string | null {
  return (PERMISSION_WORDS as Record<string, string | undefined>)[code] ?? null;
}
