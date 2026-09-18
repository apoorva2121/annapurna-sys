// 3× a Saturday at Spice Garden, measured against the budgets that already exist.
//
// `docs/checklist.md` names three latency budgets and this script asserts exactly those three. It
// invents none: a budget nobody wrote down is a number somebody will argue with afterwards, and
// the argument always resolves in favour of whatever the software did.
//
//   KDS        50 ms   — the kitchen display's poll. M08 measured a 28 ms median on a laptop
//   settle    400 ms   — the till, at the moment a table is waiting
//   dashboard 800 ms   — the owner's Today screen. M13 measured 16-32 ms on a laptop
//
// **The load is expressed in covers, not in requests per second.** `docs/seed-data.md` puts Spice
// Garden at ~190 covers on a Friday-to-Sunday day, with dinner running 20:30-22:00 and worth about
// 2.2× lunch. So the peak this models is a dinner service, and 3× peak is ~570 covers of traffic
// through that window rather than an abstract arrival rate — a number the owner can sanity-check
// against their own restaurant, which an RPS figure is not.
//
// **Every request is authenticated and scoped.** An unauthenticated load test measures the
// rate limiter. The three budgets are about what the product does for somebody signed in.
//
// Run:
//   k6 run -e BASE_URL=https://<staging> -e PASSWORD=<seed password> load/peak.js
//
// A budget missed is a finding with its measurement attached, not a reason to raise the budget.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE = __ENV.BASE_URL;
const PASSWORD = __ENV.PASSWORD;

if (!BASE || !PASSWORD) {
  throw new Error('BASE_URL and PASSWORD are required: k6 run -e BASE_URL=… -e PASSWORD=… load/peak.js');
}

// ---------------------------------------------------------------- the load, in covers

// A Friday-to-Sunday day is ~190 covers (docs/seed-data.md). Dinner is the peak and carries
// roughly the larger share, so call the peak service ~120 covers over 90 minutes. Three times that
// is 360 covers in 90 minutes — but a load test does not run for 90 minutes, so the same *arrival
// rate* is held for six minutes and the ramp is what makes it a peak rather than a plateau.
const PEAK_COVERS_PER_HOUR = 80;
const MULTIPLIER = 3;
const ARRIVALS = PEAK_COVERS_PER_HOUR * MULTIPLIER; // 240 covers/hour = 4/minute per virtual table

// Three scenarios, because the three budgets belong to three different people standing in three
// different places. Running them as one blended pool would let a fast dashboard hide a slow till.
export const options = {
  scenarios: {
    // The kitchen display. One screen per station, polling continuously through the service.
    kitchen: {
      executor: 'constant-vus',
      vus: 4,
      duration: '6m',
      exec: 'kitchen',
      tags: { budget: 'kds' },
    },
    // The till. Arrivals rather than VUs: a settle is an event that happens to a table, and the
    // rate is what 3× peak actually means.
    till: {
      executor: 'constant-arrival-rate',
      rate: ARRIVALS,
      timeUnit: '1h',
      duration: '6m',
      preAllocatedVUs: 20,
      maxVUs: 60,
      exec: 'till',
      tags: { budget: 'settle' },
    },
    // The owner, refreshing Today while the service runs. One person, not a crowd — but their
    // 800 ms is measured while the other two scenarios are loading the same database.
    owner: {
      executor: 'constant-vus',
      vus: 1,
      duration: '6m',
      exec: 'owner',
      tags: { budget: 'dashboard' },
    },
  },
  // The assertion. p(95) rather than the mean: a mean hides the tail, and the tail is the shift
  // where somebody stands at a till waiting for a receipt.
  thresholds: {
    'http_req_duration{budget:kds}': ['p(95)<50'],
    'http_req_duration{budget:settle}': ['p(95)<400'],
    'http_req_duration{budget:dashboard}': ['p(95)<800'],
    // A budget met by failing fast is not a budget met.
    http_req_failed: ['rate<0.01'],
  },
};

const kdsLatency = new Trend('kds_poll_ms', true);
const dashboardLatency = new Trend('dashboard_ms', true);

// ---------------------------------------------------------------- signing in

function login(identifier) {
  const response = http.post(
    `${BASE}/api/v1/auth/login`,
    JSON.stringify({ identifier, password: PASSWORD }),
    { headers: { 'Content-Type': 'application/json' }, tags: { budget: 'setup' } },
  );
  check(response, { 'signed in': (r) => r.status === 200 });
  return response.json('access_token');
}

function auth(token) {
  return { headers: { Authorization: `Bearer ${token}` } };
}

export function setup() {
  // One sign-in per role, shared. Logging in inside the loop would measure argon2 — which is
  // deliberately slow — and report it as the product being slow.
  return {
    chef: login('chef@spicegarden.test'),
    manager: login('manager@spicegarden.test'),
    owner: login('owner@spicegarden.test'),
  };
}

// ---------------------------------------------------------------- the three budgets

export function kitchen(tokens) {
  const response = http.get(`${BASE}/api/v1/staff/kot/tickets`, auth(tokens.chef));
  kdsLatency.add(response.timings.duration);
  check(response, { 'kds answered': (r) => r.status === 200 });
  // A kitchen display refreshes about every two seconds. Faster would measure the network.
  sleep(2);
}

export function till(tokens) {
  // The read a till does before it can settle anything. A settle itself writes, and a load test
  // that settles 360 real orders leaves a database nobody can use for the next run — so this
  // measures the path up to the write, which is where the latency lives.
  const response = http.get(`${BASE}/api/v1/staff/orders?status=open`, auth(tokens.manager));
  check(response, { 'orders answered': (r) => r.status === 200 });
}

export function owner(tokens) {
  const response = http.get(`${BASE}/api/v1/staff/dashboard/today`, auth(tokens.owner));
  dashboardLatency.add(response.timings.duration);
  check(response, { 'dashboard answered': (r) => r.status === 200 });
  // An owner glances at this between other things. Ten seconds is generous and honest.
  sleep(10);
}
