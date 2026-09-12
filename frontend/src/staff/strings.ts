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
    // M02-M04 shipped their screens behind routes and nothing linked to them, so every one was
    // reachable only by typing a URL. Found by the M03/M04 review.
    settings: 'Restaurant settings',
    menu: 'Menu',
    menuOptions: 'Options and add-ons',
    stock: 'Ingredients and recipes',
    costs: 'Dish costs',
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
  },

  errors: {
    title: 'Something went wrong',
    forbidden: 'You do not have access to this.',
    forbiddenHint: 'If you think you should, ask an owner or manager to check your roles.',
  },
} as const;
