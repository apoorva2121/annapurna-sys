// Every word a guest reads. The guest bundle's own file, because ADR 0009 ships none of the staff
// code — and because the voice is different: a diner has never seen this product and will use it
// once, so nothing here assumes a second look.
//
// English only in month 1 (`docs/ui/conventions.md`), kept in one place so Hindi and Marathi are a
// data change rather than a sweep through every screen. The consent notice is the exception and
// lives in `consentNotice.ts`, versioned, because those are words somebody is held to.

export const strings = {
  scan: {
    loading: 'Opening…',
    // Names no cause. The server returns one refusal for a slug that does not exist, a slug on a
    // deactivated table, and a token that really did expire (`api/guest_deps.py`), because telling
    // a stranger which one it was is an enumeration oracle. A heading saying "expired" puts the
    // `why` back, and gets it wrong every time the code simply never existed — which is what
    // happened on 2026-09-19 and cost an hour.
    refusedTitle: 'This code did not work',
    refusedBody: 'Please scan the QR code on your table again, or ask a member of staff.',
    offlineTitle: 'We could not reach the restaurant',
    offlineBody: 'Check your connection and try again.',
    retry: 'Try again',
  },

  menu: {
    title: 'Menu',
    loading: 'Fetching the menu…',
    empty: 'The menu is not up yet. Ask a member of staff.',
    vegOnly: 'Vegetarian only',
    // The mark beside every dish name (`docs/compliance-rules.md` §A1). A word as well as a shape,
    // because colour never carries meaning alone.
    foodType: {
      veg: 'Vegetarian',
      non_veg: 'Non-vegetarian',
      egg: 'Contains egg',
    },
    allergenHeading: 'Allergens',
    caloriesLabel: (kcal: number, serving: string | null) =>
      serving === null ? `${String(kcal)} kcal` : `${String(kcal)} kcal per ${serving}`,
    choose: 'Choose',
    optional: 'Optional',
    required: 'Required',
    chooseOne: 'Choose one',
    chooseUpTo: (max: number) => `Choose up to ${String(max)}`,
  },

  bill: {
    title: 'Your bill',
    loading: 'Fetching your bill…',
    quantity: (count: number) => `× ${String(count)}`,
    subtotal: 'Subtotal',
    discount: 'Discount',
    charges: 'Charges',
    tax: 'Tax',
    roundOff: 'Round off',
    total: 'Total',
    settled: 'Paid. Thank you.',
    unsettled: 'Not paid yet',
    // The bill on the phone and the printed one are the same server figures. If they disagree,
    // that is a defect, not a rounding difference the guest should reconcile.
    hint: 'This is the same bill the restaurant will print.',
  },

  feedback: {
    title: 'How was it?',
    intro: 'Three questions. It takes about ten seconds.',
    food: 'The food',
    service: 'The service',
    wouldReturn: 'Would you come back?',
    yes: 'Yes',
    no: 'No',
    commentLabel: 'Anything else? (optional)',
    commentPlaceholder: 'The paneer was excellent',
    send: 'Send',
    sending: 'Sending…',
    thanksTitle: 'Thank you',
    thanksBody: 'The restaurant reads these.',
    alreadyTitle: 'Thank you',
    // A second tap on a slow network is not an error, and must not read like one.
    alreadyBody: 'We already have your answers for this meal.',
    nothingChosen: 'Tap a rating to send.',

    phoneLabel: 'Your phone number (optional)',
    phonePlaceholder: '98765 43210',
    withdraw: 'Turn this off',
    withdrawn: 'Turned off. Nothing more will be sent.',
  },

  ratings: {
    // Numbers, because a five-star row on a phone is five targets a thumb misses. One to five, big.
    scale: [1, 2, 3, 4, 5],
    label: (value: number) => `${String(value)} out of 5`,
  },
} as const;
