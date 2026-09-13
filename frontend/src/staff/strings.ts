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
  },

  nav: {
    staff: 'Staff',
    branch: 'Restaurant',
    profile: 'Your profile',
    signOut: 'Sign out',
    signingOut: 'Signing out…',
    // M03 and M04 shipped their screens behind routes with nothing linking to them, so each was
    // reachable only by typing a URL. Found by the M03/M04 review. (M02's four screens were always
    // in the header — an earlier version of this comment said otherwise and was wrong.)
    settings: 'Restaurant settings',
    menu: 'Menu',
    menuOptions: 'Options and add-ons',
    stock: 'Ingredients and recipes',
    costs: 'Dish costs',
    suppliers: 'Suppliers',
    purchaseOrders: 'Purchase orders',
    onHand: 'Stock on hand',
    receive: 'Record a delivery',
    produce: 'Make a batch',
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
    loginHint: 'Optional. Leave blank for someone who never signs in — a cleaner, for example.',
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
    appearance: 'Appearance',
    appearanceHint: 'How the app looks on this device. Only you see this choice.',
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
      title: 'Appearance for everyone here',
      hint: 'The look this restaurant shows by default. Anyone who has picked a theme on their own device keeps it.',
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
      address: 'Address',
      save: 'Save settings',
      saving: 'Saving…',
      saved: 'Settings saved.',
    },

    floor: {
      title: 'Floor plan',
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
  },
  errors: {
    title: 'Something went wrong',
    forbidden: 'You do not have access to this.',
    forbiddenHint: 'If you think you should, ask an owner or manager to check your roles.',
  },
} as const;
