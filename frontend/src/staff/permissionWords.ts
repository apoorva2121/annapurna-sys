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
  'customer.view':
    'See a customer of this branch: their number, how often they have been and how they like things',
  'customer.manage':
    'Add and edit a customer, record what they agreed to, and erase their details at their request',
  'feedback.view': 'Read what diners said about a day’s service',
  'message.send':
    'Take part in the restaurant’s conversations, and attach a photo or a PDF to a message',
  'task.view': 'See the work assigned to you, and write down work for yourself',
  'task.complete': 'Accept, start and finish a task you were given',
  'task.assign':
    'Give a task to somebody else, change it, cancel it, and check that finished work was done',
  'shift.view': 'Read the roster, and clock yourself in and out',
  'shift.manage':
    'Create shifts, staff them, mark somebody absent, and correct a clock time with a reason',
  'report.operational.view':
    'Read the operational reports: dish performance, kitchen times and waste',
  'report.financial.view':
    'Read the money: revenue, the payment split, and the food-cost variance',
  'complaint.manage':
    'Log a complaint, give it an owner, and record what was actually done about it',
  'audit.view':
    'Read the audit trail: who changed a price, who voided a bill, who granted a role',
  'performance.view.own': 'See your own figures, and everything they are computed from',
  'performance.view.team': 'See how the work is shared out, and the team’s top contributors',
  'performance.publish': 'Freeze a period, after which its figures never move',
  'incentive.configure': 'Set what the restaurant rewards, and how much each part counts',
  'recognition.award': 'Give somebody an award, with a note saying what it is for',
};

export function wordsFor(code: string): string | null {
  return (PERMISSION_WORDS as Record<string, string | undefined>)[code] ?? null;
}
