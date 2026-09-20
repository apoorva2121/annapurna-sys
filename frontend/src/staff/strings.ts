// Every user-facing string in the staff app, in one place.
//
// docs/ui/conventions.md: "English only in month 1; keep all user-facing strings in one place so
// Hindi and regional languages are a later data change, not a refactor." A restaurant in Pune will
// have waiters who read Devanagari far more comfortably than Latin script, and the cost of that
// translation should be a second object here rather than a sweep through every component.
//
// Server messages are NOT here. The backend already writes them in plain English and owns the
// wording for anything it refuses; duplicating them would mean two sources of truth for the same
// sentence and a UI that contradicts the API.

export const strings = {
  appName: 'Restaurant OS',

  login: {
    title: 'Sign in',
    identifierLabel: 'Phone number or email',
    // Phone first, because that is what most waiters and kitchen staff actually have (M01 spec,
    // open decision 2).
    identifierHint: 'Use the phone number or email your manager set up for you.',
    passwordLabel: 'Password',
    submit: 'Sign in',
    submitting: 'Signing in…',
    offline: 'You appear to be offline. Check the connection and try again.',
    // Decision D20.
    forgot: 'Forgot password?',
    forgotAnswer:
      'Ask your manager or the owner. They set a new one from Staff, and you choose your own the next time you sign in.',
    // Backlog-issues B4: one login at more than one hotel. Asked only after the password.
    chooseTitle: 'Which hotel?',
    chooseHint: 'Your login works at more than one hotel. Choose where to sign in.',
    continue: 'Continue',
    startOver: 'Use a different login',
  },

  nav: {
    staff: 'Staff',
    branch: 'Restaurant',
    profile: 'Your profile',
    // Backlog-issues B11b: the component gallery, shown only in a development build.
    design: 'Design gallery',
    compliance: 'Compliance',
    signOut: 'Sign out',
    signingOut: 'Signing out…',
    // M03 and M04 shipped their screens behind routes with nothing linking to them, so each was
    // reachable only by typing a URL. Found by the M03/M04 review. (M02's four screens were always
    // in the header — an earlier version of this comment said otherwise and was wrong.)
    settings: 'Restaurant settings',
    menu: 'Menu',
    menuOptions: 'Options and add-ons',
    menuCodes: 'Names and codes',
    shiftSetup: 'Shifts',
    // Group headings. The grouping already existed in `AppShell`'s code — three times, each forced
    // by eslint's complexity budget rather than designed — and was never shown on the screen.
    groups: {
      service: 'Service',
      menu: 'Menu and recipes',
      buying: 'Buying',
      insight: 'Insight',
      people: 'People',
      setup: 'Set up',
      yours: 'Yours',
      kitchen: 'Kitchen and waste',
      store: 'The store',
      diners: 'Diners',
    },
    // The drawer. Not an icon alone: the design system allows an icon-only button only for an
    // action done fifty times a shift, and opening a menu is not one.
    more: 'Menu',
    closeMenu: 'Close',
    stock: 'Ingredients and recipes',
    costs: 'Dish costs',
    suppliers: 'Suppliers',
    purchaseOrders: 'Purchase orders',
    myShifts: 'My shifts',
    reports: 'Reports',
    analytics: 'Trends',
    workload: 'Workload',
    myPerformance: 'My performance',
    audit: 'Audit trail',
    notifications: 'Alerts',
    roster: 'Roster',
    messages: 'Messages',
    tasks: 'Tasks',
    onHand: 'Stock on hand',
    receive: 'Record a delivery',
    produce: 'Make a batch',
    kitchen: 'Kitchen',
    logWaste: 'Log waste',
    wasteSummary: 'Waste',
    customers: 'Customers',
    feedback: 'What diners said',
    complaints: 'Complaints',
    count: 'Stock count',
  },

  home: {
    greeting: (name: string) => `Signed in as ${name}`,
    noPermissions:
      'You are signed in, but nothing has been assigned to you yet. Ask your manager to give you a role.',
    m01Note: 'Ordering, the kitchen display and reports arrive in later modules.',
  },

  staff: {
    title: 'Staff',
    add: 'Add employee',
    empty: 'No employees yet. Add the first one with “Add employee”.',
    emptyInactive: 'Nobody has been deactivated.',
    showInactive: 'Include deactivated',
    active: 'Active',
    inactive: 'Inactive',
    noLogin: 'No login',
    // The owner's decision, 2026-09-19. Worded as the job rather than as a permission, because
    // that is what it is: an owner holds every permission there is, so this could never have been
    // one. See migration 0057.
    takesTables: 'Serves tables',
    takesTablesHint:
      'Only people who serve tables can be recorded as a table’s waiter, and only they appear in performance figures for service.',
    takesTablesSaved: 'Saved.',
    noRoles: 'No role yet',
    loading: 'Loading the staff list…',
    showMore: 'Show more',
    showingMore: 'Loading…',
  },

  employee: {
    newTitle: 'Add employee',
    editTitle: 'Employee',
    fullName: 'Full name',
    employeeCode: 'Employee code',
    phone: 'Phone number',
    joinedOn: 'Joined on',
    loginIdentifier: 'Login (phone or email)',
    // Help text rewritten for decision D21.
    fullNameHint: 'As it should appear on rotas and reports. At least two letters.',
    employeeCodeHint:
      'Filled in with the next free code. Change it if you number staff your own way.',
    loginHint: 'Only for someone who will sign in. Leave it blank for staff who never use the app.',
    initialPasswordHint:
      'At least 10 characters. Tell them in person; they choose their own the first time they sign in.',
    // Decision D14.
    nowGiveRole: (name: string) => `Now give ${name} a role`,
    finish: 'Finish',
    addedAs: (name: string, roles: string[]) =>
      roles.length === 0
        ? `${name} added, with no role yet`
        : `${name} added as ${roles.join(', ')}`,
    backToStaff: 'Back to staff',
    initialPassword: 'Initial password',
    passwordHint: 'At least 10 characters.',
    save: 'Save',
    saving: 'Saving…',
    create: 'Add employee',
    creating: 'Adding…',
    saved: 'Saved.',
    deactivate: 'Deactivate',
    deactivating: 'Deactivating…',
    reactivate: 'Reactivate',
    reactivating: 'Reactivating…',
    // Destructive actions name the thing (docs/ui/conventions.md).
    confirmDeactivate: (name: string) =>
      `Deactivate ${name}? They are signed out immediately and keep their history. They are not deleted.`,
    rolesTitle: 'Roles',
    rolesHint: 'Roles apply at this restaurant. Changing them signs the person out.',
    rolesSave: 'Save roles',
    rolesSaving: 'Saving roles…',
    rolesSaved: 'Roles updated.',
    // Backlog-issues B6: a new password set by someone else.
    resetTitle: 'Set a new password',
    resetHint: (name: string) =>
      `For when ${name} has forgotten theirs. They are signed out everywhere and choose their own the next time they sign in.`,
    newPassword: 'New password',
    reset: 'Set new password',
    resetting: 'Setting…',
    resetDone: (name: string) => `New password set. Tell ${name} in person, not by message.`,
  },

  profile: {
    title: 'Your profile',
    name: 'Name',
    code: 'Employee code',
    restaurant: 'Restaurant',
    roles: 'Roles',
    permissions: 'What you can do',
    changePassword: 'Change password',
    currentPassword: 'Current password',
    newPassword: 'New password',
    submit: 'Change password',
    submitting: 'Changing…',
    changed: 'Password changed. Your other devices have been signed out.',
    // Decision D23: this device only; the restaurant's default is in Settings.
    appearance: 'Appearance on this device',
    appearanceHint:
      "Only this device, and only for you. The restaurant's default look is set in Settings.",
    appearanceSelected: 'in use',
    mustChange: 'Change your password now',
    mustChangeWhy:
      'Someone else set this password for you, so they know it. Until you change it, anything done with your account will look like you did it.',
  },

  setup: {
    navSettings: 'Settings',
    navFloor: 'Floor plan',
    navStations: 'Kitchen stations',
    navTax: 'Tax rates',

    theme: {
      title: 'Restaurant default appearance',
      hint: 'The look everyone here sees, unless they chose one on their own device in their profile.',
      defaultLabel: 'Default theme',
      none: 'Follow the device',
      scheduleTitle: 'Festive themes',
      scheduleHint:
        'A theme for a stretch of days — Deepavali, a local festival. Dates rather than a rule, because these move every year.',
      scheduleEmpty: 'No festive themes scheduled.',
      addWindow: 'Add a festive theme',
      windowTheme: 'Theme',
      from: 'From',
      to: 'To',
      remove: 'Remove',
      overlaps: 'Two festive themes cannot cover the same day.',
      // Its own verb, not a second 'Save settings'. Two identical buttons on one screen are
      // ambiguous to a reader and indistinguishable to a screen reader.
      save: 'Save appearance',
      saved: 'Appearance saved.',
    },

    // Backlog-issues B2.
    tables: {
      title: 'Tables after the bill',
      hint: 'How long a table is cleared for once its bill is paid, and when the floor is too busy to clear tables at all.',
      cleaningMinutes: 'Cleaning time (minutes)',
      cleaningMinutesHint:
        'A table counts as free this long after its bill. Leave it blank if only a person should clear a table, with Mark ready.',
      busyTitle: 'Busy hours',
      busyHint:
        'During these hours a paid table is free at once, with no cleaning step. A window can run past midnight, such as 22:00 to 01:00.',
      busyEmpty: 'No busy hours set.',
      addWindow: 'Add busy hours',
      from: 'From',
      to: 'To',
      remove: 'Remove',
      save: 'Save table settings',
      saved: 'Table settings saved.',
    },

    restaurant: {
      title: 'Restaurant settings',
      loading: 'Loading settings…',
      timezone: 'Timezone',
      timezoneHint:
        'An IANA name, such as Asia/Kolkata. Every date in the product is worked out from this.',
      currency: 'Currency',
      businessDayStart: 'The business day starts at',
      // Not a tooltip. ADR 0004 calls this the setting owners misunderstand most, and the sentence
      // below is computed from the value on screen rather than written out — see businessDayExample.
      businessDayExample: (time: string, day: string, counts: string): string =>
        `An order at ${time} on ${day} counts towards ${counts}'s sales.`,
      businessDayMidnight:
        'At midnight the business day is the calendar day. A restaurant that serves past midnight will see last night’s late orders counted against today.',
      businessDayWhy:
        'Most restaurants serve past midnight. Setting this after closing time keeps a night’s takings on one report instead of splitting them across two days.',
      gstin: 'GSTIN',
      fssai: 'FSSAI licence number',
      fssaiHint: 'Prints on every bill. Required for a food business in India.',
      fssaiExpires: 'FSSAI licence valid until',
      fssaiExpiresHint: 'The date on the licence. The app warns 30 days before it runs out.',
      address: 'Address',
      addressHint: 'Line 1 and the city are needed. The address prints on every bill.',
      addressLine1: 'Address line 1',
      addressLine2: 'Address line 2',
      city: 'City',
      state: 'State',
      pincode: 'PIN code',
      pincodeHint: 'Six digits.',
      save: 'Save settings',
      saving: 'Saving…',
      saved: 'Settings saved.',
    },

    floor: {
      title: 'Floor plan',
      tableAction: (verb: string, code: string) => `${verb} table ${code}`,
      areasTitle: 'Dining areas',
      areasEmpty: 'No dining areas yet. Add one before adding tables.',
      addArea: 'Add a dining area',
      areaName: 'Area name',
      areaNamePlaceholder: 'AC Hall',
      creating: 'Adding…',
      moveUp: 'Move up',
      moveDown: 'Move down',
      deactivate: 'Deactivate',
      reactivate: 'Reactivate',
      showInactive: 'Show deactivated',
      inactive: 'Deactivated',
      tablesTitle: 'Tables',
      tablesEmpty: 'No tables in this area yet.',
      addTable: 'Add a table',
      tableCode: 'Table',
      tableCodePlaceholder: 'T4',
      seats: 'Seats',
      status: 'Status',
      inArea: 'Area',
      // ADR 0008, and the reason deactivation is offered instead of deletion.
      neverDeleted:
        'Nothing here is deleted. A table that took an order last year still has to resolve when that order is read.',
    },

    stations: {
      title: 'Kitchen stations',
      empty: 'No stations yet. Add the sections a ticket can be sent to.',
      add: 'Add a station',
      code: 'Code',
      codeHint:
        'Permanent. The menu routes dishes by this, so it cannot change once dishes point at it. Lower case, no spaces.',
      name: 'Name',
      nameHint: 'Shown on the kitchen display. Safe to change at any time.',
    },

    tax: {
      title: 'Tax rates',
      empty: 'No tax groups yet.',
      add: 'Add a tax group',
      addGroupHint:
        'A tax group is a class of item — restaurant food, packaged goods. Menu items point at the group, so changing what it charges later never means re-tagging the menu.',
      code: 'Code',
      codeHint:
        'Permanent, e.g. GST5. Menu items and recipes join on it, so it cannot change later.',
      name: 'Name',
      rate: 'Rate',
      ratePercent: 'Percent',
      rateHint: 'As a percentage, e.g. 5 for GST 5%.',
      inclusive: 'Menu prices already include this tax',
      effectiveFrom: 'Starts on',
      effectiveTo: 'Ends on',
      current: 'Current',
      superseded: 'Superseded',
      supersede: 'Change the rate',
      supersedeHint:
        'A rate is never edited. Charging a new one closes the current one the day before the new one starts, so an invoice from last month still cites the rate that was charged. Menu items keep pointing at this group.',
      cancel: 'Cancel',
      history: 'Rate history',
      noRates: 'No rate yet.',
      renameOnly: 'Rename',
      renameHint:
        'Only the name can change. The rate and the dates are fixed once the rate exists.',
      immutable:
        'Rates are never edited in place. Every order line copies the rate it was charged, and an invoice cites it.',
    },
  },

  menu: {
    title: 'Menu',
    // brand.md §8.7: a dish page is reached by its id, so it carries the way back.
    backToMenu: 'Menu',
    showInactive: 'Show deactivated',
    inactive: 'Deactivated',
    neverDeleted:
      'Nothing on the menu is ever deleted. A dish is deactivated, so an order from last year still resolves to what it sold.',
    categoriesTitle: 'Sections',
    categoriesEmpty: 'No sections yet. Add one — every dish belongs to a section.',
    categoryCode: 'Code',
    categoryName: 'Section name',
    codeHint: 'Permanent, e.g. MAIN_VEG. Recipes and the starter library join on it.',
    addCategory: 'Add section',
    creating: 'Saving…',
    save: 'Save',
    saveOptions: 'Save options',
    edit: 'Change',
    cancel: 'Cancel',
    moveUp: 'Move up',
    moveDown: 'Move down',
    dishesTitle: 'Dishes',
    dishesEmpty: 'No dishes in this section yet.',
    noVariants: 'No sellable variant',
    dishCode: 'Dish code',
    dishCodeHint: 'Permanent, e.g. BUTTER_CHICKEN. This is how a recipe finds the dish.',
    dishName: 'Dish name',
    description: 'Description',
    foodType: 'Food type',
    veg: 'Vegetarian',
    nonVeg: 'Non-vegetarian',
    egg: 'Contains egg',
    // Backlog-issues B8 (compliance-rules §A2, §B1).
    allergens: 'Allergens',
    allergensHint:
      'What a guest with an allergy needs to know, like “milk, cashew”. Write “None” if it has none. Left blank, the menu says nobody has checked.',
    calories: 'Calories (kcal)',
    caloriesHint: 'Per serving. Required only for a Central Licence or ten or more outlets.',
    caloriesProblem: 'Enter calories as a whole number, like 480.',
    servingSize: 'Serving size',
    station: 'Kitchen station',
    stationHint: 'Where the ticket prints when this dish is ordered.',
    variantsTitle: 'Sold as',
    variantCode: 'Variant code',
    variantName: 'Variant name',
    price: 'Price',
    priceHint: 'What a guest pays, before tax.',
    taxGroup: 'Tax group',
    prepMinutes: 'Prep minutes',
    prepHint: 'The standard. The kitchen display measures the actual.',
    addVariant: 'Add a variant',
    priceLocked:
      'Changing a price needs the menu.price permission, which is the owner’s. You can change everything else about this dish.',
    // A waiter holds menu.view and nothing more. The form used to render for them and 403 on
    // submit, which reads as a broken product rather than as a boundary in it.
    readOnly: 'You can read the menu but not change it. Ask a manager to make an edit.',
    deactivate: 'Deactivate',
    reactivate: 'Reactivate',
    modifiersTitle: 'Options asked about this dish',
    modifiersEmpty: 'No options attached.',
    modifierGroupsTitle: 'Option groups',
    // The one screen where a code is information rather than noise (owner's request, 2026-09-19).
    codesTitle: 'Names and codes',
    codesIntro:
      'Every menu object and the short code stored behind it. Codes are generated from the name when something is created and never change afterwards, because recipes are matched by them.',
    codesFilter: 'Search a name or a code',
    codesEmpty: 'There is no menu yet.',
    codesNoMatch: 'Nothing matches that.',
    codesKinds: {
      category: 'Category',
      dish: 'Dish',
      variant: 'Size',
      group: 'Option group',
    },
    modifierGroupsEmpty: 'No option groups yet.',
    addModifierGroup: 'Add an option group',
    groupCode: 'Group code',
    groupName: 'Group name',
    minSelect: 'Choose at least',
    maxSelect: 'Choose at most',
    required: 'A choice is required',
    addOption: 'Add an option',
    optionName: 'Option name',
    priceDelta: 'Price change',
    priceDeltaHint:
      'Leave at 0 for a free choice. Negative is allowed — "no rice" can be a discount.',
    applyToCategory: 'Apply to every dish in a section',
    applyToCategoryHint:
      'The menu stores options per dish, so one dish can opt out. This applies them in bulk.',
    replaceExisting: 'Replace each dish’s existing options instead of adding to them',
    apply: 'Apply',
    applied: (count: number) => `Applied to ${String(count)} ${count === 1 ? 'dish' : 'dishes'}.`,
  },

  stockLedger: {
    title: 'Stock on hand',
    intro:
      'What the ledger says is on the shelf right now. Every figure here is derived from movements — nothing is stored, so nothing can drift.',
    empty: 'Nothing has moved yet. Record a delivery and it appears here.',
    item: 'Item',
    quantity: 'On hand',
    value: 'Value',
    // Deliberately blunt. A negative is not an error state to be apologised for — it is the most
    // useful thing this screen can say, and the words have to tell a manager what to *do*.
    negativeBanner: (count: number) =>
      count === 1
        ? '1 item has been used without a recorded delivery'
        : `${String(count)} items have been used without a recorded delivery`,
    negativeHelp:
      'The ledger has no record of this stock arriving, so it shows less than nothing. Record the missing delivery, or count the shelf and let the count correct it.',
    negativeTag: 'No delivery recorded',
    expiringTitle: 'Expiring soon',
    expiringEmpty: 'Nothing expiring in the next 7 days.',
    expiringOn: 'Expires',
    // Decision D24.
    expiresOn: (date: string) => `Expires ${date}`,
    remaining: 'Left',
    noExpiry: 'No expiry date',
    showZero: 'Include items at zero',
    history: 'History',
    movementOn: 'Date',
    movementType: 'Movement',
    movementQuantity: 'Change',
    movementNote: 'Note',
    basisTheoretical: 'From a recipe',
    basisActual: 'Counted',
    receiveTitle: 'Record a delivery',
    receiveIntro:
      'What arrived, how much of it, and what it cost. This is the anchor every later figure rests on — stock that arrives unrecorded shows up later as a position below zero.',
    produceTitle: 'Make a batch',
    produceIntro:
      'Making a preparation uses up its ingredients and creates a new batch. The batch costs what the ingredients it used actually cost, not what they cost today.',
    pickItem: 'Choose an item',
    quantityIn: 'Quantity',
    unitCost: 'Cost per unit',
    expiryDate: 'Use by',
    expiryHint:
      'Optional. Dated stock is always used before undated stock, so leaving this blank means this batch waits behind everything that has a date.',
    storage: 'Where it is kept',
    record: 'Record it',
    recorded: 'Recorded.',
    make: 'Make it',
    made: (quantity: string, cost: string) =>
      `Made ${quantity}. This batch costs ${cost} per unit.`,
    shortfallWarning: (quantity: string) =>
      `${quantity} of this was not in stock. It has been recorded anyway and the position is now below zero — record the missing delivery, or count the shelf.`,
    failed: 'That could not be recorded.',
    countTitle: 'Stock count',
    countIntro:
      'Write down what is actually on the shelf. Nothing changes the ledger until somebody else approves the count — that second pair of eyes is the point of it.',
    startCount: 'Start a count',
    book: 'Book says',
    counted: 'Counted',
    variance: 'Difference',
    saveCount: 'Save what is counted',
    submitCount: 'Submit for approval',
    approveCount: 'Approve, and correct the ledger',
    approveExplains:
      'Approving posts a correction for every line that differs, so the book matches the shelf. It must be somebody other than the person who counted.',
    approveRefused: 'That count was not approved.',
    status: {
      draft: 'Being counted',
      submitted: 'Waiting for approval',
      approved: 'Approved — the ledger has been corrected',
    },
    types: {
      receipt: 'Delivery',
      production: 'Made here',
      consumption: 'Used',
      wastage: 'Wasted',
      staff_meal: 'Staff meal',
      complimentary: 'Complimentary',
      transfer: 'Transfer',
      adjustment: 'Correction',
      count: 'Stock count',
    },
  },

  cost: {
    title: 'Dish costs',
    intro:
      'What each dish costs to make, against what it sells for. Worst first — the dish losing the most is at the top.',
    empty: 'No dishes costed yet. Add recipes to the menu and they appear here.',
    averageFoodCost: 'Average food cost',
    dishesCosted: 'Dishes',
    uncosted: 'Without a recipe',
    dish: 'Dish',
    price: 'Price',
    cost: 'Cost',
    foodCost: 'Food cost',
    margin: 'Margin',
    high: 'High',
    // Owner defect sheet row 23: 2083% carried the same word as 36%. A dish costing more
    // than it sells for is not an expensive dish, it is a plate sold at a loss.
    atALoss: 'Sold at a loss',
    noRecipe: 'No recipe',
    unconfirmed: 'Unconfirmed recipe',
    openRecipe: 'Recipe',
    showBreakdown: 'Breakdown',
    hideBreakdown: 'Hide',
    breakdown: 'Breakdown',
  },

  stock: {
    title: 'Ingredients & preparations',
    intro:
      'Everything the kitchen holds. An ingredient is bought; a preparation is made here from other items — and both hold stock, expire and have a cost.',
    empty: 'Nothing here yet.',
    all: 'Everything',
    ingredients: 'Bought in',
    preparations: 'Made here',
    code: 'Code',
    name: 'Name',
    baseUnit: 'Unit',
    unitCost: 'Cost per unit',
    shelfLife: 'Shelf life',
    days: (n: number) => `${String(n)} ${n === 1 ? 'day' : 'days'}`,
    hours: (n: number) => `${String(n)} ${n === 1 ? 'hour' : 'hours'}`,
    yieldFactor: 'Usable after trim',
    batchYield: 'Batch makes',
    usedBy: 'What uses this',
    usedByNone: 'Nothing uses this yet.',
    usedByPreparations: 'Preparations',
    usedByDishes: 'Dishes',
    close: 'Close',
  },

  recipe: {
    title: 'Recipe',
    // The chef's screen. Grams, never rupees — `seed/organization.yaml` is explicit that a chef
    // holds `recipe.manage` and not `cost.view`, so nothing here shows a price.
    intro:
      'What goes into one portion, in the unit each item is stored in. Saving makes a new version; past orders keep the version they were costed against.',
    empty: 'No recipe yet. Add the first ingredient below.',
    component: 'Ingredient or preparation',
    quantity: 'Quantity',
    addLine: 'Add',
    removeLine: 'Remove',
    notes: 'Notes for the kitchen',
    save: 'Save this recipe',
    saving: 'Saving…',
    saved: 'Saved as version',
    version: (n: number) => `Version ${String(n)}`,
    unconfirmed: 'Nobody has checked these quantities',
    unconfirmedWhy:
      'This recipe came from the starter library, which is mostly estimated. Confirm it once a chef has weighed a real portion — until then every cost computed from it is a proposal.',
    // Owner defect sheet row 24: Save was the only way off this page, so it was pressed to
    // leave and every press made another version of the same recipe.
    back: 'Back',
    unsaved: 'This recipe has unsaved changes.',
    leaveAnyway: 'Leave without saving',
    keepEditing: 'Keep editing',
    confirm: 'Confirm these quantities',
    confirming: 'Confirming…',
    confirmed: 'Confirmed by a chef',
    readOnly: 'You can read recipes but not change them. A chef holds recipe.manage.',
    duplicate: 'That item is already on the recipe. Change its quantity instead.',
    needsLines: 'A recipe needs at least one ingredient.',
    noQuantity: 'Enter a quantity greater than zero.',
    pickOne: 'Choose an ingredient or preparation.',
    chooseComponent: 'Choose…',
    quantityFor: (name: string) => `Quantity of ${name}`,
    confirmBlocked: 'Save your changes before confirming, so what gets confirmed is what you see.',
  },

  // M06. The wording on the receiving screen is the module, so it is worth reading rather than
  // skimming: `invoicedLabel` and `receivedLabel` are deliberately "What the bill says" and "What
  // the scale says" rather than "Quantity" and "Actual". A store manager who types the invoiced
  // figure into the received box destroys the entire value of this module while every test stays
  // green, and the only defence against that is the two fields not sounding interchangeable.
  procurement: {
    suppliersTitle: 'Suppliers',
    suppliersIntro:
      'Who you buy from, and what they owe you. Every delivery is recorded against a supplier here, which is what makes short deliveries visible at the end of a quarter instead of never.',
    suppliersEmpty:
      'No suppliers yet. Add the first one, then raise an order against it — a delivery has to arrive from somebody for its variance to mean anything.',
    addSupplier: 'Add a supplier',
    editSupplier: 'Edit',
    supplierName: 'Business name',
    supplierNameHint:
      'One row per business. Two spellings of the same supplier cannot be added up, and a variance report split across both understates what they owe you.',
    contactPerson: 'Who you speak to',
    phone: 'Phone',
    email: 'Email',
    gstin: 'GSTIN',
    gstinHint:
      'Optional. Checked for the right shape only — a well-formed GSTIN has not been verified with anyone.',
    paymentTerms: 'Payment terms (days)',
    save: 'Save',
    saving: 'Saving…',
    cancel: 'Cancel',
    active: 'Active',
    inactive: 'No longer used',
    deactivate: 'Stop using this supplier',
    reactivate: 'Use this supplier again',
    deactivateHint:
      'Nothing is deleted. Past deliveries keep pointing here, so last quarter still adds up.',
    variance: 'Delivery record',

    ordersTitle: 'Purchase orders',
    ordersIntro:
      'What you asked for, so that what arrives can be compared with it. An order is a draft until you send it; after that its lines are fixed.',
    ordersEmpty: 'No orders yet.',
    newOrder: 'Raise an order',
    orderNumber: 'Order',
    supplier: 'Supplier',
    expectedAt: 'Expected',
    expectedAtHint: 'Optional. Used to tell you which suppliers deliver late.',
    total: 'Ordered value',
    status: 'Status',
    statuses: {
      draft: 'Draft',
      sent: 'Sent',
      partial: 'Part delivered',
      received: 'Delivered',
      cancelled: 'Cancelled',
    } as Record<string, string>,
    item: 'Item',
    pickItem: 'Choose an item…',
    quantityOrdered: 'Quantity',
    unitPrice: 'Price per unit',
    addLine: 'Add another item',
    removeLine: 'Remove',
    createOrder: 'Save as draft',
    creating: 'Saving…',
    sendOrder: 'Send to supplier',
    sending: 'Sending…',
    sentHint: 'Sending fixes the lines. Cancel and raise another if the order was wrong.',
    cancelOrder: 'Cancel this order',
    cancelReason: 'Why is it being cancelled?',
    cancelReasonHint:
      'Recorded against the order for good. A cancellation nobody has to explain is the one that hides a mistake.',
    confirmCancel: 'Cancel the order',
    cancelling: 'Cancelling…',
    needsLines: 'An order needs at least one item.',
    needsSupplier: 'Choose a supplier.',
    badQuantity: 'Enter a quantity greater than zero.',
    badPrice: 'Enter a price.',
    duplicateItem: 'That item is already on the order. Change its quantity instead.',

    receiveTitle: 'Book in a delivery',
    receiveIntro:
      'Weigh it before you sign. Write down what the bill claims and what the scale actually says — they are two different numbers, and the difference between them is the cheapest money in this restaurant.',
    ordered: 'Ordered',
    invoicedLabel: 'What the bill says',
    receivedLabel: 'What the scale says',
    rejectedLabel: 'Refused on quality',
    rejectionReason: 'Why was it refused?',
    invoiceNumber: 'Invoice number',
    invoiceNumberHint:
      'One invoice can only be booked once. Booking it twice would double the stock it brought in.',
    invoiceAmount: 'Invoice total (tax included)',
    taxAmount: 'Of which tax',
    taxAmountHint:
      'On the 5% scheme this tax is a cost you carry, not something you claim back, so it belongs in what the stock cost you.',
    postReceipt: 'Book it in',
    posting: 'Booking in…',
    receiptNeedsLines: 'Enter what arrived for at least one item.',
    receiptBadNumber: 'Enter a quantity, or zero if none of it arrived.',
    rejectedNeedsReason: 'Say why it was refused.',

    postedTitle: 'Booked in',
    // Defect sheet row 22.
    receivedBy: (person: string) => `Received by ${person}`,
    // The headline, not a repeat of the page title. A Notice whose title says the same thing as the
    // heading above it is a box a person learns to skip, and this is the one box on the screen with
    // the numbers that matter in it.
    postedHeadline: (short: string, accepted: string) =>
      `${short} billed and not delivered. ${accepted} of stock booked in.`,
    postedIntro:
      'What this delivery actually cost you, now the weights are recorded and can no longer be changed.',
    accepted: 'On the shelf',
    shortDelivery: 'Billed and not delivered',
    orderShortfall: 'Still owed on this order',
    landedCost: 'Cost per unit, tax included',
    shortDeliveryValue: 'Value of the short delivery',
    acceptedValue: 'Value booked into stock',
    invoiceLineTotal: 'Invoice lines add up to',
    backToOrders: 'Back to orders',
    backToSuppliers: 'Suppliers',

    varianceTitle: 'Delivery record',
    varianceIntro:
      'What this supplier billed you for against what actually arrived, over the last 90 business days. Biggest loss first — the top row is the one worth a phone call.',
    varianceEmpty:
      'No deliveries from this supplier in this period. Book one in and this fills itself.',
    varianceHeadline: (name: string, deliveries: number, amount: string) =>
      `${name}: ${String(deliveries)} ${deliveries === 1 ? 'delivery' : 'deliveries'}, ${amount} billed and not delivered.`,
    varianceClean: (name: string) =>
      `${name} has delivered everything they billed for in this period.`,
    invoiced: 'Billed',
    received: 'Arrived',
    rejected: 'Refused',
    deliveries: 'Deliveries',
    period: 'Business days',
  },

  // M07. The waiter's words. Short, because they are read on a phone in a dim room mid-service, and
  // every status is a word as well as a colour.
  orders: {
    navTables: 'Tables',
    floorTitle: 'Tables',
    floorEmpty: 'No tables yet. The owner adds them under Floor plan.',
    loadingFloor: 'Loading the tables',
    seats: (count: number) => `${String(count)} seats`,
    tableStatuses: {
      free: 'Free',
      occupied: 'Occupied',
      reserved: 'Reserved',
      cleaning: 'Being cleared',
      out_of_service: 'Out of service',
    } as Record<string, string>,
    orderLabel: (number: string) => `Order ${number}`,
    billAsked: 'Bill asked for',
    // Who is serving a table (2026-09-14). The waiter was stored on every order and shown nowhere.
    waiterLabel: (name: string) => `Waiter: ${name}`,
    noWaiter: 'No waiter yet',
    counterOrder: 'Counter order',
    assignToMe: 'Assign to me',
    assigning: 'Assigning…',
    changeWaiter: 'Change waiter',
    moveTitle: (number: string) => `Who should serve order ${number}?`,
    moveChoose: 'Choose a waiter',
    moveReason: 'Why is it moving?',
    moveReasonHint: 'A few words, such as "shift ended". The reason stays with the order.',
    moveTo: (name: string) => `Move to ${name}`,
    keepWaiter: 'Keep the waiter',
    whoIsServing: (code: string) => `Who is serving ${code}?`,
    leaveUnassigned: 'Leave unassigned',
    loadingWaiters: 'Loading the waiters',
    // Backlog-issues B2: a table after the bill, and an order that should never have been opened.
    markReady: (code: string) => `Mark ${code} ready`,
    readyIn: (minutes: number) => `Ready in ${String(minutes)} min`,
    busyOn: 'Busy mode on',
    busyOff: 'Busy mode off',
    askForBill: 'Ask for bill',
    cancelOrder: 'Cancel order',
    cancelTitle: (number: string) => `Cancel order ${number}?`,
    cancelNothingSent: 'Nothing has gone to the kitchen yet.',
    cancelSent: (count: number) =>
      `${String(count)} ${count === 1 ? 'dish has' : 'dishes have'} already gone to the kitchen. Cancelling keeps a record of that, with your reason.`,
    cancelReason: 'Why is it being cancelled?',
    cancelReasonHint: 'A few words, such as "opened by mistake". The reason stays with the order.',
    keepOrder: 'Keep the order',
    // Not "Cancel order" again: the button that opens the sheet already says that, and two buttons
    // with one name are ambiguous to a reader and indistinguishable to a screen reader.
    confirmCancel: 'Yes, cancel it',
    cancelling: 'Cancelling…',
    loadingOrder: 'Loading the order',
    loadingMenu: 'Loading the menu',
    backToTables: 'Tables',
    nothingYet: 'Nothing on this order yet. Tap a dish to add it.',
    lineStatuses: {
      pending: 'Not sent',
      sent: 'Sent',
      preparing: 'Cooking',
      ready: 'Ready',
      served: 'Served',
      cancelled: 'Taken off',
      returned: 'Sent back',
    } as Record<string, string>,
    takeOff: 'Take off',
    // Backlog-issues B11: a change shown before the server answers. `adding` is the one already
    // defined below for the Add to order button — the same word, for a line not yet priced.
    saving: 'Saving…',
    takeOffReason: 'Why is it coming off?',
    confirmTakeOff: 'Take it off',
    keep: 'Keep it',
    required: 'Required',
    upTo: (max: number) => `Choose up to ${String(max)}`,
    addToOrder: 'Add to order',
    adding: 'Adding…',
    from: (price: string) => `from ${price}`,
    sendToKitchen: 'Send to kitchen',
    sending: 'Sending…',
    bill: 'Bill',
    billTitle: 'Bill',
    provisional: 'Provisional bill. The invoice number is given when it is settled.',
    subtotal: 'Subtotal',
    discounts: 'Discounts',
    charges: 'Charges',
    tax: 'Tax',
    total: 'To pay',
    paidBy: 'Paid by',
    methods: { upi: 'UPI', cash: 'Cash', card: 'Card' } as Record<string, string>,
    settle: (amount: string) => `Settle ${amount}`,
    settling: 'Settling…',
    settledTitle: 'Settled',
    invoiceNumber: (number: string) => `Invoice ${number}`,
    nextTable: 'Back to tables',
    splitPayment: 'Split the payment',
    addPayment: 'Add another payment',
    removePayment: 'Remove',
    paymentLabel: (n: number) => `Payment ${String(n)}`,
    amountFor: (n: number) => `Amount for payment ${String(n)}`,
    amountProblem: 'Enter an amount for every payment.',
    splitDishes: 'Split by dishes',
    splitDishesHint: 'Tick the dishes that go on a separate bill. Each bill gets its own invoice.',
    moveDishes: 'Move to a separate bill',
    moving: 'Moving…',
    movedTitle: 'Moved to a separate bill',
    openMoved: (number: string) => `Open the bill for order ${number}`,
    fewer: (thing: string) => `One fewer ${thing}`,
    more: (thing: string) => `One more ${thing}`,
    // Backlog-issues B7, decision D2: discounts, comps and the optional service charge.
    discountsTitle: 'Discounts and comps',
    discountKind: 'What kind',
    discountKinds: {
      percentage: 'Percentage off',
      flat: 'Amount off',
      comp: 'Comp (on the house)',
    } satisfies Record<'percentage' | 'flat' | 'comp', string>,
    percentOff: 'Percent off',
    amountOff: 'Amount off (₹)',
    comesOff: 'Comes off',
    wholeBill: 'The whole bill',
    discountReason: 'Why',
    discountReasons: [
      'Food came out wrong',
      'Long wait',
      'Regular guest',
      "Owner's guest",
      'Staff meal',
      'Other',
    ] as readonly string[],
    discountNote: 'Note (optional)',
    chooseReason: 'Choose why.',
    otherNeedsNote: 'Say what happened in the note.',
    percentProblem: 'Enter a percentage from 0 to 100, like 10 or 12.5.',
    amountOffProblem: 'Enter the amount to take off, like 50 or 49.50.',
    apply: 'Apply',
    applying: 'Applying…',
    removeDiscount: 'Remove',
    serviceCharge: 'Service charge (optional)',
    addServiceCharge: 'Add service charge',
    removeServiceCharge: 'Remove service charge',
  },
  // M07 chunk K. What happens to a bill after it is settled, and the till. A settled bill is never
  // edited, so every action here is named for the new document it creates.
  bills: {
    nav: 'Bills',
    waiterColumn: 'Waiter',
    title: "Today's bills",
    intro:
      'A settled bill is never edited. Money going back is a credit note; a bill raised in error is cancelled on the day it was issued.',
    loading: 'Loading the bills',
    empty: 'No bills settled today yet.',
    statuses: {
      settled: 'Settled',
      voided: 'Cancelled',
      issued: 'Issued',
      cancelled: 'Cancelled',
    } as Record<string, string>,
    orderColumn: 'Order',
    statusColumn: 'Status',
    totalColumn: 'Total',
    nextPage: 'Next page',
    firstPage: 'Back to the first page',
    backToBills: 'Bills',
    loadingInvoice: 'Loading the invoice',
    notSettled: 'This order has not been settled, so it has no invoice yet.',
    invoiceTitle: (number: string) => `Invoice ${number}`,
    cancelledTitle: 'This invoice was cancelled',
    taxable: 'Taxable value',
    cgst: 'CGST',
    sgst: 'SGST',
    otherTax: 'Other tax',
    discounts: 'Discounts',
    charges: 'Charges',
    total: 'Total',
    paymentsTitle: 'Payments',
    refund: 'Refund',
    creditTitle: 'Credit note',
    creditIntro:
      'Choose the dishes coming off the bill and how many of each. The tax on them is worked out for you.',
    billedCount: (count: number, total: string) => `${String(count)} billed · ${total}`,
    alreadyCredited: (count: number, amount: string) =>
      `${String(count)} already credited · ${amount}`,
    reason: 'Why is it being credited?',
    refundLegend: 'Money given back',
    refundMethods: { none: 'None', cash: 'Cash', upi: 'UPI', card: 'Card' } as Record<
      string,
      string
    >,
    refundAmount: 'Amount given back',
    noDishes: 'Choose at least one dish to credit.',
    reasonNeeded: 'Say why, in a few words.',
    refundAmountNeeded: 'Enter the amount given back.',
    issueCredit: 'Issue credit note',
    issuing: 'Issuing…',
    creditIssued: (number: string) => `Credit note ${number} issued`,
    creditTotal: (total: string) => `The bill is reduced by ${total}.`,
    refunded: (method: string, amount: string) => `${method} refund of ${amount}`,
    anotherCredit: 'Issue another credit note',
    // Decision D27.
    creditNotesTitle: 'Credit notes on this bill',
    creditNoteTitle: (number: string) => `Credit note ${number}`,
    againstInvoice: (invoice: string, date: string) => `Against invoice ${invoice} · ${date}`,
    gstin: (gstin: string) => `GSTIN ${gstin}`,
    print: 'Print',
    // ---- the printed bill (F10). Every particular here is Rule 46's; the declaration is
    // Rule 5(1)(f)'s, verbatim from CBIC's own text of the CGST Rules 2017 read on 2026-09-20.
    // "supplies", not "supplier" — secondary sources disagree and the instrument does not.
    compositionDeclaration: 'Composition taxable person, not eligible to collect tax on supplies',
    taxInvoiceTitle: 'Tax invoice',
    billOfSupplyTitle: 'Bill of supply',
    fssai: (licence: string) => `FSSAI ${licence}`,
    numberLabel: 'Bill no.',
    dateLabel: 'Date',
    orderLabel: 'Order',
    recipientLabel: 'Customer',
    recipientGstinLabel: 'Customer GSTIN',
    itemHeading: 'Item',
    qtyHeading: 'Qty',
    amountHeading: 'Amount',
    taxableLabel: 'Taxable value',
    cgstLabel: 'CGST',
    sgstLabel: 'SGST',
    discountLabel: 'Discount',
    chargesLabel: 'Charges',
    roundOffLabel: 'Rounding',
    totalLabel: 'Total',
    thankYou: 'Thank you. Please come again.',
    printBill: 'Print bill',
    printCreditNote: (number: string) => `Print credit note ${number}`,
    creditTotalLabel: 'Total credited',
    cancelInvoice: 'Cancel this invoice',
    cancelHint:
      'Only for a bill issued in error, on the day it was issued. It keeps its number and moves no money.',
    cancelReason: 'What was the error?',
    keepInvoice: 'Keep it',
    confirmCancel: 'Cancel the invoice',
    cancelling: 'Cancelling…',
  },
  cash: {
    nav: 'Cash',
    title: 'Till',
    loading: 'Loading the till',
    noneOpen: 'No till is open. Count the float into the drawer, then open it.',
    openingFloat: 'Opening float',
    openingFloatHint: 'The cash in the drawer before the first bill.',
    floatNeeded: 'Enter the opening float, even if it is ₹0.',
    open: 'Open the till',
    opening: 'Opening…',
    openFor: (date: string) => `Till open · business day ${date}`,
    blindNote:
      'What the till should hold is shown once it is counted, so the count records what is in the drawer.',
    payoutsSoFar: 'Paid out so far',
    reason: 'Reason',
    reasonNeeded: 'Say why, in a few words.',
    recording: 'Recording…',
    payout: {
      title: 'Pay out',
      hint: 'Cash handed out of the till: the vegetable seller, ice, a courier.',
      amount: 'Amount paid out',
      amountProblem: 'Enter the amount paid out.',
      record: 'Record payout',
      recorded: 'Payout recorded',
    },
    adjustment: {
      title: 'Adjust',
      hint: 'Cash found or missing after the count. Recorded by someone other than whoever closed the till, and shown beside the original figure, never instead of it.',
      // Decision D18.
      which: 'Was cash found or missing?',
      found: 'Cash found (extra)',
      missing: 'Cash missing',
      amount: 'Amount',
      amountProblem: 'Enter the amount found or missing, like 400 or 49.50.',
      record: 'Record adjustment',
      recorded: 'Adjustment recorded',
    },
    closeTitle: 'Count and close',
    closeHint: 'Count each note and coin in the drawer. Leave a box empty if there are none.',
    countOf: (denomination: string) => `How many ₹${denomination}`,
    countNeeded: 'Count at least one denomination before closing.',
    wholeCount: (denomination: string) => `The count of ₹${denomination} must be a whole number.`,
    close: 'Close the till',
    closing: 'Closing…',
    closedNotice: 'Till closed',
    countedAgainst: (counted: string, expected: string) =>
      `Counted ${counted} · should have held ${expected}`,
    exact: 'Exact',
    short: (amount: string) => `Short by ${amount}`,
    over: (amount: string) => `Over by ${amount}`,
    afterAdjustments: (word: string) => `After adjustments: ${word}`,
    closedTitle: 'Closed tills',
    businessDay: (date: string) => `Business day ${date}`,
    adjust: 'Adjust this till',
    olderTills: 'Older tills are not shown here.',
    // Decisions D13 and D16.
    closedBy: (person: string) => `Closed by ${person}`,
    adjustedBy: (person: string, byCloser: boolean) =>
      byCloser ? `Adjusted by ${person}, the same person who closed it` : `Adjusted by ${person}`,
    // Backlog-issues B7, decision D3.
    outsideTill: (amount: string) => `${amount} taken in cash today outside any till`,
    outsideTillHint: (payments: number) =>
      `${payments === 1 ? 'One payment was' : `${String(payments)} payments were`} settled in cash while no till was open. No count expects it, so check it reached the drawer.`,
  },
  // Backlog-issues B8: the licence number printed on every bill.
  // Backlog-issues B11b: the component gallery at /design, a development-only screen for
  // developers, designers and reviewers. Its words are here rather than inline because every
  // other screen's are, and a gallery that breaks the project's own rule is poor evidence.
  gallery: {
    title: 'Design gallery',
    intro:
      'Every component this product is built from, in the states it actually ships. The pictures ' +
      'in __screenshots__ are taken from this page, so a token that moves a button by a pixel ' +
      'becomes a diff somebody reads.',
    components: 'Components',
    waiterPatterns: 'Waiter patterns',
  },

  // Backlog-issues B12e. A supplier sells by the kilo and the ledger holds grams (invariant 5), so
  // a box that says only "Quantity" is how 12 kg gets typed as 12 g and a plate of cabbage ends up
  // costing more than a car. The unit is named beside the number, always.
  units: {
    quantity: 'Quantity',
    quantityIn: (unit: string) => `Quantity (${unit})`,
    pricePerUnit: 'Price per unit',
    pricePer: (unit: string) => `Price per ${unit}`,
    recordAnyway: 'Record it anyway',
  },

  licence: {
    expired: (date: string) => `The FSSAI licence ran out on ${date}`,
    expiredHint:
      'Its number still prints on every bill. An owner renews it, then updates the date in Settings.',
    expiring: (date: string) => `The FSSAI licence runs out on ${date}. Renew it before then.`,
  },
  // The kitchen display, read at two metres by somebody wearing a glove. Every word here is short
  // on purpose: at that distance a sentence is a paragraph, and a chef reads a screen the way a
  // driver reads a road sign.
  //
  // There is deliberately no "Served". A dish is served when it reaches a table, which this screen
  // cannot see — the waiter marks it from the order (M08 spec decision 5).
  kitchen: {
    title: 'Kitchen',
    loading: 'Loading the rail…',
    stationLabel: 'Station',
    allStations: 'All stations',
    empty: 'Nothing to cook. New tickets appear here as orders are sent.',
    takeaway: 'Takeaway',
    minutesShort: 'min',
    late: 'LATE',
    remake: 'REMAKE',
    round: (n: number) => `Round ${String(n)}`,
    openTicket: 'Open',
    connecting: 'Connecting to the kitchen…',
    // A banner, not a toast: it stays up until the screen is live again, because a display that
    // has quietly stopped updating is worse than one that is obviously broken.
    reconnecting: 'Not live — reconnecting. What is on screen may be out of date.',
    // Named for the outcome, not the state it moves to.
    step: {
      acknowledged: 'Seen it',
      preparing: 'Start cooking',
      ready: 'Ready',
      // Present so the map is total; neither is ever offered as a next step.
      new: 'New',
      served: 'Served',
      cancelled: 'Cancelled',
    },
    ticket: {
      back: 'Back to the rail',
      title: (number: string) => `Order ${number}`,
      lineReady: 'This dish is ready',
      lineStart: 'Start this dish',
      remakeTitle: 'Send it back',
      remakeReason: 'Why is it being remade?',
      // Free text, not a dropdown. A remake reason is how a kitchen learns which dishes come back
      // and why; five fixed options is how it stops writing them down.
      remakeHint: 'A few words. It goes on the record and nobody is blamed for it.',
      remakeSubmit: 'Remake it',
      remade: (reason: string) => `Being remade: ${reason}`,
    },
  },

  // Logging waste, on a phone, one-handed, standing at a bin. `docs/waste-model.md`: if logging
  // waste is slow it does not get logged and the module is fiction — so every word here is short
  // and every step is a tap.
  //
  // No cost appears in any of these strings before the waste is logged. That is deliberate and it
  // is the same rule as the blind cash count and the blind goods-receipt weight: a figure shown
  // while somebody is deciding what to record is a figure some people record towards.
  waste: {
    title: 'Log waste',
    loading: 'Loading…',
    pickItem: 'What was thrown away?',
    howMuch: (unit: string) => `How much? (${unit})`,
    why: 'Why?',
    logged: (reason: string) => `Logged: ${reason}`,
    // Shown only after. This is the teaching half of the rule.
    costHint: 'That is what it cost. Nobody is asked to know this — the system works it out.',
    awaitingApproval: 'A manager will check this one.',
    logAnother: 'Log something else',
    // The owner's decision, 2026-09-18: a nudge, never a block. `docs/waste-model.md` is why —
    // anything that makes honest reporting harder gets you less honest reporting, not more
    // photographs. So this asks after the log is saved, when the cook is no longer holding a tray,
    // and the log stands either way.
    photoWanted: 'A photo makes this reason count for something',
    photoWantedHint:
      'This reason is one somebody will ask about later. A picture now saves the conversation — but the log is already saved either way.',
    photoSkipped: 'Logged without a photo.',
    stage: {
      receiving: 'At the door',
      storage: 'In storage',
      prep: 'In prep',
      service: 'In service',
    },
    summary: {
      title: 'Waste',
      loading: 'Working it out…',
      empty: 'Nothing logged in this period. Waste appears here as it is recorded.',
      total: 'Lost in this period',
      range: (since: string, until: string) => `${since} to ${until}`,
      events: (count: number) => (count === 1 ? '1 time' : `${String(count)} times`),
      // The point of the whole report: not one number, but which stage to look at.
      hint: 'Each stage has a different owner and a different fix. The biggest is where to start.',
      stageHeading: 'Stage',
      reasonHeading: 'Reason',
      timesHeading: 'Times',
      costHeading: 'Cost',
      shareHeading: 'Share',
    },
  },

  // M10. A customer a waiter can greet, and the two DPDP rights.
  //
  // **Nothing here calls the consent obligations current law.** `docs/compliance-rules.md` §B2: the
  // DPDP Act 2023's notice and consent provisions are notified and commence 13 May 2027. This
  // product builds to that standard now because consent architecture cannot be retrofitted; saying
  // it is required today would be saying something untrue about Indian law.
  customers: {
    title: 'Customers',
    loading: 'Finding them…',
    loadingHistory: 'Looking up their visits…',
    backToList: 'Customers',
    searchLabel: 'Search by number or name',
    // The branch rule, said where somebody would otherwise wonder why a regular is missing.
    branchHint: 'Customers of this branch. Switch branch to see another one’s.',
    empty:
      'No customers here yet. They appear when somebody is added at the counter, or when a guest gives their number after rating a meal.',
    noName: 'No name yet',
    noResults: 'Nobody here matches that.',
    visitSummary: (count: number) =>
      count === 0
        ? 'First visit not recorded yet'
        : count === 1
          ? '1 visit'
          : `${String(count)} visits`,
    lastVisitHeading: 'Last visit',
    visitsHeading: 'Visits',
    nameHeading: 'Name',
    phoneHeading: 'Number',

    preferencesTitle: 'How they like things',
    // The only preference that leaves this screen, and the reason the word "allergy" is on it.
    preferencesHint:
      'An allergy is copied onto the order when they are seated, and the kitchen sees it on the ticket. Everything else stays here, for whoever is serving them.',
    noPreferences: 'Nothing recorded yet.',
    allergyBadge: 'Allergy',
    allergyPlaceholder: 'Peanuts, shellfish, …',
    addAllergy: 'Add allergy',
    removePreference: 'Remove',

    consentTitle: 'What they agreed to',
    consentHint:
      'Each one is separate, and each can be turned off on its own. A number given for a bill is not permission to send offers.',
    neverAsked: 'Never asked',
    consentState: (granted: boolean, on: string) =>
      granted ? `On since ${on.slice(0, 10)}` : `Off since ${on.slice(0, 10)}`,
    grant: 'Turn on',
    withdraw: 'Turn off',
    purpose: {
      order_contact: 'About this visit',
      service_recognition: 'Remembering how they like things',
      feedback_followup: 'Following up on a complaint',
      marketing: 'Offers and news',
    },

    eraseTitle: 'Erase their details',
    eraseStart: 'Erase at their request',
    eraseConfirmTitle: (phone: string) => `Erase everything about ${phone}?`,
    // Names what goes and what stays, because it cannot be undone and "Are you sure?" says nothing.
    eraseConfirmBody:
      'Their name, number, email and preferences are destroyed and cannot be recovered. Every bill stays, because a bill is a financial record. If they come back tomorrow they will be a new customer with no history.',
    eraseConfirm: 'Yes, erase their details',
    eraseCancel: 'Keep them',
    erasedTitle: 'Details erased',
    erasedBody:
      'This person asked for their details to be erased. Their bills are still on the books; nothing more can be recorded about them.',
    erasureKept: (orders: number, value: string) =>
      `${String(orders)} bill(s) kept, worth ${value}. Nothing on the books moved.`,

    visitsTitle: 'What they have eaten here',
    noVisits: 'No visits at this branch yet.',
    dayHeading: 'Business day',
    itemsHeading: 'What they had',
    totalHeading: 'Bill',
  },

  complaints: {
    title: 'Complaints',
    loading: 'Opening the list…',
    // A complaint nobody resolves is worse than no system, so the empty state says what "open" means.
    empty:
      'Nothing open. A complaint stays here until somebody has written down what was done about it.',
    reference: (value: string) => `Complaint ${value}`,
    severityHeading: 'Severity',
    whatHappenedHeading: 'What happened',
    severity: {
      low: 'Low',
      medium: 'Medium',
      high: 'High',
      critical: 'Critical',
    },
    status: {
      open: 'Nobody yet',
      investigating: 'Being looked at',
      resolved: 'Sorted',
      closed: 'Closed',
    },
    resolveTitle: 'What was done about it?',
    resolutionPlaceholder: 'Remade the dish and comped it',
    resolutionHint: 'Required. A complaint marked sorted with nothing written down is paperwork.',
    resolve: 'Mark it sorted',
    close: 'Close it',
    cameBack: 'They came back',
    notYet: 'Not back yet',
  },

  feedback: {
    title: 'What diners said',
    loading: 'Reading the day…',
    empty:
      'Nothing for this day. Most tables never rate a meal, which is normal — the ones who do are the signal.',
    dayLabel: 'Business day',
    foodHeading: 'Food',
    serviceHeading: 'Service',
    returnHeading: 'Would return',
    commentHeading: 'What they said',
    sourceHeading: 'How',
    source: {
      qr: 'QR on the bill',
      app: 'App',
      staff: 'Entered by staff',
      call: 'Phone call',
    },
    wouldReturn: (answer: boolean | null) => (answer === null ? '—' : answer ? 'Yes' : 'No'),
    rating: (value: number | null) => (value === null ? '—' : `${String(value)}/5`),
  },

  messages: {
    title: 'Messages',
    loading: 'Opening your messages…',
    empty:
      'No conversations yet. Start one with whoever you need — the person who finds a problem first is usually the one nobody thought to ask.',
    unreadFilter: 'Unread only',
    allFilter: 'All',
    unread: (count: number) => (count === 1 ? '1 unread' : `${String(count)} unread`),
    urgent: 'Urgent',
    muted: 'Muted',
    startTitle: 'Start a conversation',
    startGroupName: 'What is it about?',
    startGroupNamePlaceholder: 'Evening shift, Fridge repair…',
    startWith: 'Who is in it?',
    start: 'Start it',
    starting: 'Starting…',
    // A direct thread between two people is one row forever, so this is not an error.
    startedAlready: 'You already have a conversation with them. Here it is.',
    direct: 'Direct message',
    group: 'Group',
    noTitle: 'Untitled',
    live: 'Live',
    reconnecting: 'Reconnecting — new messages may be late',
    backToInbox: 'Back to messages',
    threadLoading: 'Opening the conversation…',
    threadEmpty: 'Nothing said yet.',
    composePlaceholder: 'Write a message',
    send: 'Send',
    sending: 'Sending…',
    priorityLabel: 'How urgent?',
    priority: {
      normal: 'Normal',
      high: 'Important',
      urgent: 'Urgent',
    },
    deleted: 'Message deleted',
    deleteAction: 'Delete',
    deleting: 'Deleting…',
    promote: 'Make this a task',
    promoting: 'Making a task…',
    promoted: 'Made into a task',
    attach: 'Attach a photo',
    left: (name: string, on: string) => `${name} left on ${on}`,
    participants: (count: number) => (count === 1 ? '1 person' : `${String(count)} people`),
  },

  tasks: {
    title: 'Tasks',
    loading: 'Reading the board…',
    empty:
      'Nothing on the board. A task is an instruction somebody is accountable for, so an empty board is good news — as long as the instructions are actually being written down.',
    mineFilter: 'Only mine',
    allFilter: 'Everyone',
    newTitle: 'Add a task',
    titleLabel: 'What needs doing?',
    titlePlaceholder: 'Deep-clean the fryer',
    descriptionLabel: 'Anything else to know?',
    assigneeLabel: 'Who is doing it?',
    assigneeNobody: 'Nobody yet',
    // The P1 design's split: writing down your own work is not the same act as giving work out.
    assigneeHint: 'Only a manager can give a task to somebody else.',
    dueLabel: 'By when?',
    priorityLabel: 'How urgent?',
    priority: {
      low: 'Whenever',
      normal: 'Normal',
      high: 'Important',
      urgent: 'Urgent',
    },
    create: 'Add it',
    creating: 'Adding…',
    status: {
      created: 'Waiting for somebody',
      assigned: 'Assigned',
      accepted: 'Accepted',
      in_progress: 'In progress',
      completed: 'Finished — waiting to be checked',
      verified: 'Checked and closed',
      cancelled: 'Cancelled',
    },
    overdue: 'Overdue',
    dueBy: (when: string) => `By ${when}`,
    assignedTo: (name: string) => `With ${name}`,
    unassigned: 'Nobody yet',
    backToBoard: 'Back to tasks',
    detailLoading: 'Opening the task…',
    historyTitle: 'What has happened',
    historyEntry: (who: string, what: string) => `${who} — ${what}`,
    move: {
      accepted: 'I will do it',
      in_progress: 'Started it',
      completed: 'Finished it',
      verified: 'Checked and close it',
      cancelled: 'Cancel it',
    },
    sendBack: 'Send it back',
    sendBackHint: 'Say what still needs doing. The person who did it sees this.',
    noteLabel: 'Anything to add?',
    moving: 'Saving…',
    // Rendered instead of a disabled button nobody can explain.
    nothingToDo: 'Nothing for you to do on this one right now.',
    verifiedBySomebodyElse: 'Somebody else has to check work you finished yourself.',
  },

  attachments: {
    add: 'Add a photo or PDF',
    adding: 'Uploading…',
    // The allow-list, said once, in the words of the thing rather than of a content type.
    allowed: 'Photos and PDFs, up to 10 MB.',
    rejectedType: 'That kind of file cannot be attached. Photos and PDFs only.',
    rejectedSize: 'That file is larger than 10 MB.',
    failed: 'That did not upload. Try again.',
    remove: 'Remove',
    open: 'Open',
    opening: 'Opening…',
    // Success, named. Silence after an upload reads as failure, and the natural response is to
    // send the photo again — three times, over a restaurant's connection.
    attached: (name: string) => `${name} is attached.`,
    openFailed: 'That file could not be opened. Try again.',
    count: (count: number) => (count === 1 ? '1 attachment' : `${String(count)} attachments`),
  },

  shifts: {
    mineTitle: 'My shifts',
    rosterTitle: 'Roster',
    loading: 'Reading the roster…',
    mineEmpty: 'You are not on the roster yet. Ask your manager to put you on a shift.',
    rosterEmpty: 'Nobody is on the roster yet. Put somebody on a shift and the week fills in.',
    backToRoster: 'Back to the roster',
    // The status is the server's word, not this screen's arithmetic.
    status: {
      scheduled: 'Scheduled',
      present: 'Present',
      late: 'Late',
      absent: 'Absent',
      leave: 'On leave',
    },
    // The truth, rather than an absence nobody asserted.
    didNotClockIn: 'Did not clock in',
    stillOpen: 'Still clocked in',
    between: (start: string, end: string) => `${start.slice(0, 5)} to ${end.slice(0, 5)}`,
    clockIn: 'Clock in',
    clockOut: 'Clock out',
    clocking: 'Saving…',
    done: 'Finished for the day',
    onNowTitle: 'On now',
    onNowEmpty: 'Nobody is on a shift right now.',
    weekTitle: 'The next two weeks',
    noSection: 'No section',
    markAbsent: 'Mark absent',
    staffTitle: 'Put somebody on a shift',
    whoLabel: 'Who?',
    whichShiftLabel: 'Which shift?',
    // A disabled control is only honest if something on screen explains it. Three lists feed one
    // button here, and any of them being empty produced the same dead button with no way to tell
    // which — found on 2026-09-19 by an owner who could not put anybody on a shift.
    noShiftsYet: 'No shifts exist yet. Add one in Shifts under Set up, then come back here.',
    // The screen that did not exist until 2026-09-19, without which no restaurant could roster
    // anybody. See ShiftsSetupScreen for the full story.
    setupTitle: 'Shifts',
    setupIntro:
      'The shifts your restaurant runs. Everything about the roster, hours worked and who was on the floor starts here.',
    setupEmpty:
      'No shifts yet. Add your first one below — most restaurants start with a morning and an evening.',
    addTitle: 'Add a shift',
    addHint:
      'A shift may end before it starts. An evening shift in a place that closes at two is 17:30 to 00:30, and that is fine.',
    shiftName: 'Name',
    startsAt: 'Starts',
    endsAt: 'Ends',
    addShift: 'Add shift',
    adding: 'Adding…',
    added: 'Shift added.',
    crossesMidnight: 'Past midnight',
    notInUse: 'Not in use',
    noStaffYet: 'Nobody has been added yet. Add your people in Staff, then come back here.',
    sectionLabel: 'Which section?',
    dayLabel: 'Which day?',
    // Invariant 4, said to a person rather than to a reader of the schema.
    dayHint:
      'A restaurant day runs from five in the morning to five the next morning, so an evening shift that ends after midnight still belongs to the day it started.',
    staff: 'Put them on it',
    staffing: 'Saving…',
  },

  // M13. Every heading is what somebody came to find out, not the name of a table.
  reports: {
    todayTitle: 'Today',
    salesTitle: 'Sales',
    varianceTitle: 'Food-cost variance',
    dishesTitle: 'Dish performance',
    wasteTitle: 'Waste',
    loading: 'Working it out…',
    businessDay: (day: string) => `Business day ${day}`,
    period: (since: string, until: string) => `${since} to ${until}`,
    // A restaurant's day is not midnight to midnight, and the report says so rather than
    // leaving somebody to wonder why 2am is on yesterday.
    businessDayHint:
      'A restaurant day runs from five in the morning, so a bill settled at two in the morning belongs to the night before.',
    empty: 'Nothing was recorded in this period.',
    // The comparison, in words. Never a colour on its own, and never red for a quiet Tuesday.
    versusPrevious: 'vs the period before',
    versusYesterday: 'vs yesterday',
    noBaseline: 'Nothing to compare against yet',
    exportCsv: 'Download as a spreadsheet',
    exportFailed: 'That did not download. Try again.',

    revenue: 'Revenue',
    covers: 'Covers',
    averageBill: 'Average bill',
    openOrders: 'Open orders',
    openOrdersHint: 'Bills still running right now.',
    rating: 'Rating',
    ratingsCounted: (count: number) =>
      count === 0
        ? 'No ratings yet'
        : `From ${String(count)} ${count === 1 ? 'rating' : 'ratings'}`,
    day: 'Day',
    bills: 'Bills',
    tax: 'Tax',
    discounts: 'Discounts',
    paymentsTitle: 'How it was paid',
    method: {
      cash: 'Cash',
      card: 'Card',
      upi: 'UPI',
      wallet: 'Wallet',
      other: 'Other',
    } as Record<string, string | undefined>,

    // The variance report. Every word here was chosen to avoid accusing anybody.
    theoretical: 'Recipes say',
    actual: 'Shelf says',
    variance: 'Difference',
    wasteAttributed: 'Explained as waste',
    unexplained: 'Unexplained',
    unexplainedHint:
      'The part of the difference nobody wrote a reason for. It is a question to ask, not an accusation — a missed waste log looks exactly like this.',
    varianceIntro:
      'What the recipes say was used, against what the shelf says was used. The two are never added together.',
    item: 'Ingredient',
    quantity: 'Quantity',
    value: 'Value',

    // The quadrant. Advice with the numbers beside it, never an action.
    dish: 'Dish',
    units: 'Sold',
    margin: 'Margin',
    foodCostPercent: 'Food cost',
    prepTime: 'Kitchen time',
    quadrant: {
      star: 'Star',
      plough_horse: 'Plough-horse',
      hidden_gem: 'Hidden gem',
      dog: 'Dog',
    } as Record<string, string | undefined>,
    quadrantHint: 'Where each dish sits on popularity against margin, for this period.',
    adviceHeading: 'What to think about',
    minutes: (seconds: number) => `${String(Math.round(seconds / 60))} min`,

    // The waste report. The total is the heading; the stages are the answer.
    wasteTotal: 'Thrown away',
    wasteIntro:
      'Split by where it happened. One total is a number nobody can act on — receiving is the store manager at the gate, prep is the chef and the batch size.',
    stageHeading: 'Where',
    reasonHeading: 'Why',
    timesHeading: 'Times',
    costHeading: 'Cost',
    shareHeading: 'Share',
    // The stage labels themselves are M09's (`strings.waste.stage`) — four stages spelled twice
    // would eventually be four stages spelled two different ways.
    toFloor: 'Back to the floor',
  },

  // M14. The trail says what happened in a sentence; the centre says what is true right now.
  audit: {
    title: 'Audit trail',
    intro:
      'Who changed what, and what the value was before. Every price change, void, discount, role grant and stock adjustment is here, and nothing in it can be edited.',
    loading: 'Reading the trail…',
    empty: 'Nothing has been recorded in this range.',
    entityLabel: 'What kind of thing?',
    entityHint: 'For example: order, menu_item_variant, employee. Leave it blank for everything.',
    sinceLabel: 'From',
    untilLabel: 'To',
    showValues: 'Show the values',
    hideValues: 'Hide the values',
    field: 'Field',
    before: 'Before',
    after: 'After',
    reason: (why: string) => `Reason given: ${why}`,
  },

  notifications: {
    title: 'Alerts',
    loading: 'Checking…',
    // An empty centre is the right answer when nothing is wrong, and it says so rather than
    // leaving somebody to wonder whether it is broken.
    // Severity as a word, because colour never carries meaning alone (design-system rule 5) and
    // because a stripe alone says "this one is different" without saying how.
    severity: {
      critical: 'Act now',
      warning: 'Soon',
      caution: 'Soon',
      info: 'For information',
    } as Record<string, string>,
    allClear: 'Nothing needs you right now.',
    allClearHint:
      'Alerts appear here on their own — stock gone negative, a batch about to expire, a complaint nobody has resolved, a task past its time, a till that did not balance.',
    markRead: 'Mark as read',
    dismiss: 'Dismiss',
    // The distinction that matters: dismissing hides the alert, not the problem.
    dismissHint: 'Dismissing hides this alert. It does not change what it is about.',
    open: 'Go and deal with it',
    unread: (count: number) => (count === 1 ? '1 alert' : `${String(count)} alerts`),
    kind: {
      'stock.negative': 'Stock',
      'stock.expiring': 'Expiring',
      'stock.count_awaiting': 'Stock count',
      'complaint.open': 'Complaint',
      'task.overdue': 'Task',
      'cash.variance': 'Till',
    } as Record<string, string | undefined>,
  },

  // M17. Every word here is chosen so a person reading about themselves is being given feedback
  // rather than being told a verdict.
  performance: {
    workloadTitle: 'Who is carrying the load',
    workloadIntro:
      'A share of the covers against a share of the hours. Somebody handling a third of the work on a fifth of the roster is a fact about the rota, and the rota is usually what to change.',
    workloadFooter:
      'This screen carries no score and no ranking. It is here so a conversation about workload does not have to start with one.',
    loading: 'Working it out…',
    empty: 'Nobody was rostered in this period.',
    period: (since: string, until: string) => `${since} to ${until}`,
    person: 'Who',
    hours: 'Hours',
    covers: 'Covers',
    assists: 'Assists',
    shareOfWork: 'Share of the work',
    shareOfHours: 'Share of the hours',
    reading: 'What it says',
    carryingMore: 'Carrying more than their share of the roster',

    mineTitle: 'My performance',
    periodLabel: 'Which period?',
    noPeriods: 'No periods have been set up yet. Ask your manager.',
    stillOpen: 'still open',
    pickAPeriod: 'Choose a period to see your own figures.',
    nothingYet: 'There are no figures for you in that period yet.',
    points: 'Points',
    hoursWorked: (hours: string) => `From ${hours} hours worked.`,
    yourPlace: (rank: number, of: number) => `You were ${String(rank)} of ${String(of)}.`,
    // Said plainly rather than implied by a greyed-out row: somebody looking at a bad number needs
    // to know it did not count against them.
    contextOnly: 'This one is not yours to fix, and it counts for nothing.',
    metric: {
      volume: 'How much you served',
      accuracy: 'Orders that went out right',
      rating: 'What guests said',
      attendance: 'Shifts you worked',
      assists: 'Helping other sections',
      kitchen_delay: 'How late the kitchen ran',
    } as Record<string, string | undefined>,

    disputeTitle: 'Something not right?',
    disputeHint:
      'Say what you think is wrong. Somebody has to answer it before this period can be finalised, and the answer is written down.',
    disputeLabel: 'What happened?',
    disputeSubmit: 'Send it',
    disputeSent: 'Sent. Somebody will answer it before this period is finalised.',
  },

  // M18. Every word is chosen so a person reads a risk and not an accusation, and so that a rule
  // which is not law today says so in the sentence rather than in a colour.
  compliance: {
    title: 'What puts your licences at risk',
    intro:
      'Checked against your restaurant’s settings, menu and bills. Each one says where the rule comes from and when that was last checked, so you can look it up yourself.',
    loading: 'Checking…',
    clear: 'Nothing to act on. Everything checked came back clear.',
    outstanding: (count: number) =>
      count === 1 ? '1 thing to look at' : `${String(count)} things to look at`,
    detected: (at: string) => `First detected by this system on ${at}.`,
    // The sentence that stops a date being misread during an inspection.
    detectedNote: 'That is when this system noticed, which may be later than when it started.',
    risk: 'Why it matters',
    action: 'What to do',
    source: 'Where the rule comes from',
    checkedOn: (on: string) => `Citation last checked ${on}.`,
    commenced: (on: string) => `In force from ${on}.`,
    severity: {
      critical: 'Act on this',
      warning: 'Worth fixing',
      advisory: 'For information',
    } as Record<string, string | undefined>,
    // Never folded into severity. Only the first is a current obligation.
    status: {
      in_force: 'This is law today.',
      notified_not_in_force: 'Notified, but not in force yet — this is not law today.',
      unsettled: 'The legal position is unsettled and being appealed.',
      unverified: 'We have not been able to verify this against the instrument.',
    } as Record<string, string | undefined>,
    state: {
      open: '',
      acknowledged: 'Marked as seen.',
      suppressed: 'Set aside.',
      resolved: 'Resolved.',
    } as Record<string, string | undefined>,
    acknowledge: 'Mark as seen',
    suppress: 'Set aside…',
    suppressLabel: 'Why is this being set aside?',
    suppressHint:
      'This stays on the record with your name against it. Setting something aside does not remove it from the export.',
    suppressSubmit: 'Set it aside',
    cancel: 'Cancel',
    exportCsv: 'Download the record',
    historyTitle: 'Everything ever raised',
    historyIntro:
      'Including what has since been put right. Nothing is ever deleted from this list.',
    empty: 'Nothing has been raised yet.',
  },

  analytics: {
    title: 'Trends',
    // Says what the screen is for in the owner's own terms. M19's rule: every screen either shows
    // a shape a table cannot, or produces an action with a rupee figure on it.
    intro: 'How the numbers have moved, and how your branches compare.',
    loading: 'Working it out…',
    empty: 'Nothing was taken in this period.',
    noBranchData: 'No branch has traded in this period.',
    // A branch with no dine-in guests has no spend per guest. Saying "no dine-in guests" rather
    // than showing a zero keeps a shut branch out of last place, where zero would put it.
    noDineIn: 'No dine-in guests',

    metric: {
      revenue: 'Revenue',
      covers: 'Guests',
      orders: 'Bills',
      discounts: 'Discounts',
      average_bill: 'Average bill',
    } as Record<string, string | undefined>,
    metricLabel: 'Show',

    bucket: {
      day: 'By day',
      week: 'By week',
    } as Record<string, string | undefined>,
    bucketLabel: 'Group',

    acrossBranches: 'All my branches together',
    acrossBranchesHint:
      'Revenue, guests and bills add up across branches. Tax never does — two branches can hold different GST registrations, so a combined tax figure would mean nothing.',
    branchCount: (count: number) =>
      count === 1 ? 'One branch' : `${String(count)} branches`,

    comparisonTitle: 'Branches compared',
    // Decision 2, the owner's: size-neutral, so a 22-seat branch can beat a 60-seat one.
    comparisonBasis: 'Spend per dine-in guest',
    comparisonBasisHint:
      'Dine-in takings divided by guests seated. Takeaway and delivery are left out on purpose — they have no guest count, and counting them here would flatter a delivery-heavy branch.',
    // The recorded blind spot of decision 2, shown beside it rather than left to be discovered.
    footfallTitle: 'Guests a trading day',
    footfallHint:
      'Shown beside spend per guest because the two can disagree: a branch whose guests have stopped coming but whose remaining guests spend well looks healthy on spend alone.',
    tradedDays: (traded: number, of: number) =>
      `traded ${String(traded)} of ${String(of)} days`,
    tradingDays: (days: number) =>
      days === 1 ? 'traded 1 day' : `traded ${String(days)} days`,

    // Drill-through. M19 criterion 6: every figure opens the rows it came from, already filtered.
    openDay: (span: string, value: string) => `Open the bills for ${span} — ${value}`,
    openBranch: (name: string, value: string) => `Open the sales report for ${name} — ${value}`,

    tableTitle: 'The same figures as a table',
    colPeriod: 'Period',
    colValue: 'Value',
    colTraded: 'Days traded',
    colBranch: 'Branch',
    colRevenue: 'Revenue',
    colCovers: 'Guests',
    colOrders: 'Bills',
    colSpend: 'Spend per guest',
  },

  errors: {
    // Backlog-issues B12 (D12): what a person quotes when they report a problem.
    issue: (number: number) => `Issue ${String(number)}`,
    title: 'Something went wrong',
    forbidden: 'You do not have access to this.',
    forbiddenHint: 'If you think you should, ask an owner or manager to check your roles.',
  },
} as const;
