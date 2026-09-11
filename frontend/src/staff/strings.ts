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
    home: 'Home',
    staff: 'Staff',
    profile: 'Your profile',
    signOut: 'Sign out',
    signingOut: 'Signing out…',
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
    columnName: 'Name',
    columnCode: 'Code',
    columnRoles: 'Roles',
    columnStatus: 'Status',
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
    employmentType: 'Employment',
    loginIdentifier: 'Login (phone or email)',
    loginHint: 'Optional. Leave blank for someone who never signs in — a cleaner, for example.',
    initialPassword: 'Initial password',
    passwordHint: 'At least 10 characters.',
    save: 'Save',
    saving: 'Saving…',
    create: 'Add employee',
    creating: 'Adding…',
    created: 'Employee added.',
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
    notFound: 'That employee was not found.',
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

  errors: {
    title: 'Something went wrong',
    forbidden: 'You do not have access to this.',
    forbiddenHint: 'If you think you should, ask an owner or manager to check your roles.',
    notFound: 'That page does not exist.',
    retry: 'Try again',
    required: 'This is required.',
  },
} as const;
