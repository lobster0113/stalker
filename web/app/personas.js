// Training Game opponent personas (#429 phase 1, hand matrix phase 1b). Dependency-free ES module so node can test it.
//
// Every number cites docs/research/2026-10-30-population-stats.md (§ = section of that note).
// Each seat is one *instance*: createPlayer draws its own stats from the type's distribution and its
// own innate tells, so two nits at the same table play and leak differently (owner direction on #429).
//
// API
//   TYPES                         the persona keys (index.html PERSONAS / personaPool use the same keys)
//   MEANS, KAPPA, TELLS, SIZES    the type tables (means, Beta concentrations, tell priors, size habits)
//   mulberry32(seed) -> rng       a seeded uniform [0,1) stream; every draw takes an rng () => number
//   createPlayer(type, rng, over) one instance: { type, p: drawn params, tells, pace, orders (its hand matrix) }
//   decide(player, sit, rng)      { type: fold|check|call|raise, to?, q, ms } from what the seat may see
//   CLASSES, classOfCards, PREF   the 169 classes, card → class, per-type hand-feature weights
//   ladder, openLadder, gridOf    range construction (which hands take each action) and a 13×13 text view
//   categorize(hole, board)       postflop hand category: made class + draw + board texture
//   eqToQ(street, eq) / qToEq     equity vs one random hand <-> percentile (used when no cards are given)
//   thinkMs(player, act, q, rng)  the think delay that carries the timing tell, bounded [MS_MIN, MS_MAX]
//
// `sit` (all public, plus the seat's own cards reduced to numbers):
//   street 0..3, pos ("UTG" "HJ" "CO" "BTN" "SB" "BB", 9-max names map to the nearest), bb, pot (chips,
//   bets in front included), toCall, currentBet, myBet, legal {canCheck, canRaise, minTo, maxTo},
//   nOpp (live opponents), ip (acts last postflop),
//   preflop: raises (0 unopened, 1 open, 2 three-bet, ...), limpers, limped (this seat limped),
//            iRaised (this seat raised earlier this street), openerPos, openTo (chips of the open)
//   postflop: aggressor (this seat made the last raise of the previous streets), prevAggLive,
//             prevBet (the previous street had a bet), betIsCbet (the bet faced is the previous aggressor's
//             first bet of this street), checkedThisStreet (this seat checked earlier this street),
//             streetRaises (bets + raises on this street so far)
//   board: the public board cards; hand: cards (the seat's own two cards), or eq (equity vs one random
//   hand) for a postflop spot without cards

export const TYPES = ["nit", "weak", "tag", "lag", "fish", "station", "maniac", "pro"];
const T = (nit, weak, tag, lag, fish, station, maniac, pro) => ({ nit, weak, tag, lag, fish, station, maniac, pro });

// Means in % of the opportunity (§7.1, §7.2). Regular RFI from charts [PSK][PT]; everything else is the
// centre of the §2 ranges or a [가정] value of the note. pro postflop ("GTO" in §7.2) is GTO-near plus
// the measured overfold of [U25][U26] (fold + 3/8/5 %p); the GTO-near base is [가정].
// Departures from §7.1/§7.2, each fitted by web/app/test/personas.test.mjs against a regular table and
// kept inside the §2 ranges:
//   fish/station RFI ×1.4/×1.5 and cold call 22→30/35→45: §7.1 ([가정] there) gave VPIP 22/31, below the
//     cited 30–45/40–65 [PN][DC][BR-PFR] it was meant to sum to;
//   fold turn/river fish 45→50/45→50, station 28→45/30→65, station fold flop 25→33: WTSD came out
//     above the cited 30–36/35–45 [BR-WTSD][DC] (stations still call down any pair, phase 1b);
//   phase 1b (real cards, made-only bettors check more down): nit fold flop/turn/river 55→50/62→67/65→76,
//     weak-tight 55→58/65→70/65→76, to keep their WTSD near the cited 18–24/21–25 [BR-WTSD];
//   maniac turn/river c-bet 70→62/60→50 and fold 33→28/35→28 ([가정] all): lifts his WTSD from 20 toward
//     the [가정] 30–40; it stays near 23 because the test table never calls a maniac down lighter.
export const MEANS = {
  rfiUTG: T(9, 11, 15, 20, 21, 30, 40, 16),
  rfiHJ: T(11, 13, 19, 25, 25, 36, 45, 20),
  rfiCO: T(15, 17, 26, 34, 31, 42, 55, 28),
  rfiBTN: T(25, 28, 43, 55, 42, 52, 70, 47),
  rfiSB: T(20, 22, 33, 45, 42, 60, 65, 40),
  limp: T(0, 10, 0, 0, 60, 80, 5, 0),            // share of opens that limp; pro limps only in the SB (30)
  threebet: T(3, 3, 7, 11, 2, 1.5, 20, 9),
  threebetSteal: T(5, 4, 11, 15, 3, 2, 25, 13),
  f3b: T(72, 70, 55, 47, 50, 35, 30, 45),
  fourbet: T(1.5, 1, 2.5, 4, 0.5, 0.3, 12, 3),   // % of all hands, the 4-bet range width
  coldcall: T(4, 6, 5, 6, 30, 45, 12, 5),
  bbDefend: T(35, 40, 55, 62, 65, 80, 75, 58),    // vs a BTN open
  cbetF: T(60, 55, 65, 72, 45, 40, 88, 60),
  cbetT: T(40, 33, 48, 55, 30, 25, 62, 45),
  cbetR: T(30, 25, 38, 45, 25, 20, 50, 35),
  foldCbF: T(50, 58, 48, 40, 38, 33, 32, 45),
  foldCbT: T(67, 70, 50, 45, 50, 45, 28, 50),
  foldR: T(76, 76, 57, 50, 50, 65, 28, 55),
  xr: T(4, 3, 7, 11, 3, 2, 16, 8),
  xrValue: T(90, 90, 70, 60, 90, 95, 40, 65),
  donk: T(1, 1, 2, 4, 10, 8, 15, 4),
  float: T(25, 15, 40, 50, 15, 10, 60, 40),
  probe: T(20, 15, 35, 45, 20, 15, 60, 35),
  riverBluff: T(10, 8, 20, 25, 10, 5, 45, 22),    // share of river bets that are bluffs; pro = [U26] HU 60–110% pot
};

// Beta concentration κ for frequency stats (§6, all [가정]). [pre, post]; F3B is wide for regulars (κ≈10, [BR-3B]).
export const KAPPA = {
  nit: [120, 120], weak: [80, 80], tag: [150, 60], lag: [80, 80],
  fish: [25, 25], station: [25, 25], maniac: [20, 20], pro: [200, 100],
};
const F3B_KAPPA = { tag: 10, lag: 10, pro: 10 };
const PRE = new Set(["rfiCO", "limp", "threebet", "threebetSteal", "f3b", "fourbet", "coldcall", "bbDefend"]);

// Open size habits in BB (§3; fish/maniac sizes [가정]). One habit per instance; pro mixes per hand.
// Real-play sizes on purpose (owner decision 2026-10-30: 5x/10x and overbets are not cut for compute).
export const SIZES = {
  open: { nit: [2.5, 3], weak: [3], tag: [2.2, 2.5], lag: [2, 2.2, 2.5], fish: [2, 2, 3, 3.5, 4, 6, 8], station: [2], maniac: [4, 5, 6], pro: [2, 2.2, 2.5, 3] },
  perLimper: { nit: 1, weak: 1, tag: 1, lag: 1, fish: 0, station: 0, maniac: 2, pro: 1 },
  // Postflop base fractions of the pot (§7.3). The base choice never looks at hand strength: only the
  // size tell does, so a no-tell instance carries no size information.
  bet: {
    nit: [0.66, 0.75, 1], weak: [0.66, 0.75, 1], tag: [0.33, 0.66], lag: [0.33, 0.66],
    fish: [0.33, 0.5, 0.75], station: [0.5], maniac: [1, 1.5, 2, 3], pro: [0.33, 0.5, 0.75, 1, 1.5],
  },
  overbet: { lag: 0.25, pro: 0.15 },   // turn/river overbet rate, polarised (§7.3 LAG, [PL]); [가정] rates
  raise: { nit: [3], weak: [3], tag: [2.5, 3], lag: [2.5, 3, 4], fish: [2.5, 3, 4], station: [2.5], maniac: [3, 4, 5], pro: [2.5, 3, 4] },
};
// The real postflop menu (TP §6 `real`), so bot bets look like the hero's own size chips.
const BET_MENU = [0.2, 0.33, 0.5, 0.75, 1, 1.5, 2, 3];
const ALLIN_MERGE = 0.8;

// Tell priors per type (§7.4). Strengths are drawn Beta(μ·10, (1−μ)·10) per instance (§7.4 last line);
// "probability" rows are Bernoulli per instance. Rows marked [가정] are not in §7.4: their direction
// comes from §5 (anecdotal [BR-TELL][GW-RR][BR-CB][BR-3B]) and the rate is this module's assumption.
export const TELLS = {
  sizeStrength: T(0.5, 0.6, 0.2, 0.15, 0.8, 0.7, 0.4, 0.05),
  sizeReverse: T(0.05, 0.05, 0.3, 0.4, 0.15, 0.1, 0.3, 0),
  timingStrength: T(0.4, 0.5, 0.15, 0.15, 0.7, 0.6, 0.5, 0.05),
  fastCallMedium: T(0.6, 0.7, 0.3, 0.3, 0.8, 0.8, 0.5, 0.1),
  tankStrong: T(0.6, 0.6, 0.3, 0.2, 0.7, 0.6, 0.4, 0.1),
  uniformTiming: T(0.3, 0.2, 0.6, 0.6, 0.05, 0.05, 0.1, 0.7),
  timingReverse: T(0.15, 0.15, 0.2, 0.2, 0.15, 0.15, 0.25, 0),      // [가정] "snap with the nuts" instances
  autopilotCbet: T(0.1, 0.1, 0.15, 0.25, 0.1, 0.05, 0.5, 0),        // [가정] [BR-CB]: micro c-bet on autopilot
  riverNutsOnly: T(0.6, 0.6, 0.2, 0.1, 0.5, 0.6, 0.05, 0),          // [가정] [GW-RR]: no river x/r → raise = nuts
  sticky: T(0.05, 0.05, 0.1, 0.15, 0.3, 0.4, 0.3, 0.05),            // [가정] calls down
  giveUp: T(0.3, 0.4, 0.2, 0.15, 0.4, 0.2, 0.1, 0.05),              // [가정] [BR-CB][BR-3B]: calls flop, folds turn
  actsWeak: T(0.1, 0.15, 0.1, 0.15, 0.3, 0.2, 0.1, 0),              // [가정] [BR-TELL]: strong hands play passive
  // Phase 1b category rules, also drawn per instance ([가정] all; directions from the owner spec):
  limpReraise: T(0, 0.1, 0, 0, 0.3, 0.2, 0, 0),                    // limp AA/KK, re-raise when raised
  madeOnly: T(0.7, 0.7, 0.2, 0.1, 0.6, 0.8, 0.05, 0.1),             // bets only made hands; else semi-bluffs draws
  chase: T(0.1, 0.15, 0.25, 0.3, 0.6, 0.5, 0.5, 0.25),              // Beta strength: calls a turn bet with a draw
};

export const MS_MIN = 600, MS_MAX = 3000;

// Percentiles of equity vs one random hand, deciles 0..100% (measured offline with tpgto.evaluate, 4000
// random deals x 300 runouts, two runs agree to ±0.02). The river is close to uniform by construction.
const EQ_DECILES = {
  1: [0, 0.25, 0.31, 0.37, 0.425, 0.48, 0.537, 0.6, 0.695, 0.8, 1],
  2: [0, 0.19, 0.27, 0.335, 0.41, 0.48, 0.555, 0.64, 0.745, 0.845, 1],
  3: [0, 0.088, 0.18, 0.28, 0.39, 0.485, 0.595, 0.7, 0.808, 0.918, 1],
};

// ------------------------------------------------------------------ random draws
export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => { a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
function normal(rng) { let u = 0; while (u === 0) u = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rng()); }
function gamma(a, rng) {
  if (a < 1) return gamma(a + 1, rng) * Math.pow(rng() || 1e-12, 1 / a);
  const d = a - 1 / 3, c = 1 / Math.sqrt(9 * d);
  for (;;) {
    let x, v;
    do { x = normal(rng); v = 1 + c * x; } while (v <= 0);
    v = v * v * v; const u = rng();
    if (u < 1 - 0.0331 * x ** 4 || Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
  }
}
export function beta(mu, kappa, rng) {
  const x = gamma(mu * kappa, rng), y = gamma((1 - mu) * kappa, rng);
  return x + y > 0 ? x / (x + y) : mu;
}
// Draws stay within mean ± 3 SD of the Beta: a 1-in-300 tail would make a "nit" that is not a nit.
export function bounds(mu, kappa) {
  const sd = Math.sqrt(mu * (1 - mu) / (kappa + 1));
  return [Math.max(0.0005, mu - 3 * sd), Math.min(0.995, mu + 3 * sd)];
}
const clip = (x, a, b) => Math.max(a, Math.min(b, x));
const pickOf = (a, rng) => a[Math.floor(rng() * a.length)];

export function kappaOf(type, key) {
  if (key === "f3b" && F3B_KAPPA[type]) return F3B_KAPPA[type];
  const k = KAPPA[type];
  return PRE.has(key) ? k[0] : k[1];
}

// ------------------------------------------------------------------ instances
const baseType = t => (t === "gto" ? "pro" : t);
export function createPlayer(type, rng, over = {}) {
  const t = baseType(type);
  if (!MEANS.rfiCO[t]) throw new Error(`unknown persona type "${type}": use one of ${TYPES.join(", ")}`);
  const p = {};
  for (const key in MEANS) {
    if (key.startsWith("rfi")) continue;
    const mu = MEANS[key][t] / 100, k = kappaOf(t, key);
    if (mu <= 0) { p[key] = 0; continue; }
    const [lo, hi] = bounds(mu, k);
    p[key] = clip(beta(mu, k, rng), lo, hi);
  }
  // One looseness draw scales every position: an instance that opens wide on the CO also does on the BTN.
  const muCO = MEANS.rfiCO[t] / 100, [lo, hi] = bounds(muCO, KAPPA[t][0]);
  const scale = clip(beta(muCO, KAPPA[t][0], rng), lo, hi) / muCO;
  for (const pos of ["UTG", "HJ", "CO", "BTN", "SB"]) p["rfi" + pos] = clip(MEANS["rfi" + pos][t] / 100 * scale, 0.01, 0.95);
  p.limpSB = t === "pro" ? 0.3 : p.limp;
  p.openSize = SIZES.open[t].length > 1 && t !== "pro" ? pickOf(SIZES.open[t], rng) : SIZES.open[t][0];

  const tl = TELLS, b = (row) => beta(clip(row[t], 0.01, 0.99), 10, rng), bern = (row) => rng() < row[t];
  const tells = {
    sizeStrength: tl.sizeStrength[t] > 0 ? b(tl.sizeStrength) : 0,
    sizeDir: bern(tl.sizeReverse) ? -1 : 1,
    uniformTiming: bern(tl.uniformTiming),
    timingStrength: b(tl.timingStrength),
    timingDir: bern(tl.timingReverse) ? -1 : 1,
    fastCallMedium: b(tl.fastCallMedium),
    tankStrong: b(tl.tankStrong),
    autopilotCbet: bern(tl.autopilotCbet),
    riverNutsOnly: bern(tl.riverNutsOnly),
    persist: "none",
    actsWeak: bern(tl.actsWeak),
    limpReraise: bern(tl.limpReraise),
    madeOnly: bern(tl.madeOnly),
    chase: b(tl.chase),
  };
  const u = rng();
  tells.persist = u < tl.sticky[t] ? "sticky" : u < tl.sticky[t] + tl.giveUp[t] ? "giveup" : "none";
  if (tells.uniformTiming) { tells.timingStrength = 0; tells.fastCallMedium = 0; tells.tankStrong = 0; }
  if (type === "gto") for (const k in tells) tells[k] = typeof tells[k] === "number" ? (k.endsWith("Dir") ? 1 : 0) : (k === "persist" ? "none" : false);
  // The baseline pace a seat thinks at, 0.9–1.9 s ([가정]: the old fixed 1.5 s sits in the middle).
  const pace = 900 + 1000 * rng();
  const pl = { type: t, p: Object.assign(p, over.p || {}), tells: Object.assign(tells, over.tells || {}), pace: over.pace ?? pace,
    orders: buildOrders(t, rng), cache: new Map() };
  return pl;
}

// ------------------------------------------------------------------ hand matrix (phase 1b)
// The 169 classes, ranked by the same points formula as web/demo/index.html (so `base` = 1 − its class
// percentile). Cards are ints: rank = c >> 2 (0 = deuce … 12 = ace), suit = c & 3 (tpgto.js, index.html).
const RANKS = "23456789TJQKA";
export const CLASSES = [];
(function buildClasses() {
  const pts = r => r === 12 ? 10 : r === 11 ? 8 : r === 10 ? 7 : r === 9 ? 6 : (r + 2) / 2;
  for (let hi = 12; hi >= 0; hi--) for (let lo = hi; lo >= 0; lo--) for (const suited of hi === lo ? [false] : [true, false]) {
    const pair = hi === lo;
    let s = pts(hi);
    if (pair) s = Math.max(5, s * 2);
    else { if (suited) s += 2; const gap = hi - lo - 1; s -= [0, 1, 2, 4][gap] ?? 5; if (gap <= 1 && hi < 10) s += 1; s += lo * 0.04; }
    CLASSES.push({ key: pair ? RANKS[hi] + RANKS[hi] : RANKS[hi] + RANKS[lo] + (suited ? "s" : "o"), hi, lo, suited, pair, combos: pair ? 6 : suited ? 4 : 12,
      score: s + (pair ? .3 : 0) + (suited ? .1 : 0) });
  }
  CLASSES.sort((a, b) => b.score - a.score);
  let cum = 0;
  for (const c of CLASSES) { c.base = 1 - (cum + c.combos / 2) / 1326; cum += c.combos; }
  CLASSES.forEach((c, i) => { c.i = i; c.f = features(c); });
})();
export const CLASS_INDEX = Object.fromEntries(CLASSES.map(c => [c.key, c.i]));
export function classOfCards(a, b) {
  const ra = a >> 2, rb = b >> 2, hi = Math.max(ra, rb), lo = Math.min(ra, rb);
  return CLASS_INDEX[hi === lo ? RANKS[hi] + RANKS[hi] : RANKS[hi] + RANKS[lo] + ((a & 3) === (b & 3) ? "s" : "o")];
}
// A fixed position in [0, 1) for each combo inside its class, so a range can hold part of a class and the
// part is always the same combos (a frequency becomes a deterministic set).
export const comboFrac = (a, b) => ((Math.min(a, b) * 52 + Math.max(a, b)) * 0.6180339887498949) % 1;

// Hand features the type preferences weigh (owner spec on #429, 2026-10-30 follow-up).
function features(c) {
  const gap = c.pair ? 0 : c.hi - c.lo - 1;
  const conn = c.pair ? 0 : [1, 0.6, 0.3][gap] ?? 0;
  return {
    base: c.base,
    pairHi: c.pair && c.hi >= 8 ? 1 : 0,                        // TT+
    pairSmall: c.pair && c.hi <= 6 ? 1 : 0,                     // 88-, set-mining
    ace: !c.pair && c.hi === 12 ? 1 : 0,                        // any ace
    wheelAs: !c.pair && c.hi === 12 && c.lo <= 3 && c.suited ? 1 : 0,   // A5s–A2s
    suited: c.suited ? 1 : 0,
    suitedConn: c.suited ? conn : 0,
    offConn: !c.suited && !c.pair ? conn : 0,
    broadway: !c.pair && c.lo >= 8 ? 1 : 0,                     // both T+
    suitedBroadway: c.suited && c.lo >= 8 ? 1 : 0,
    faces: !c.pair && c.lo >= 9 ? 1 : 0,                        // any two faces (J+)
    king: !c.pair && c.hi === 11 ? 1 : 0,                       // K2s/K5o style
    hiCard: c.pair ? 0 : c.hi / 12,
    kicker: c.pair ? 0 : c.lo / 12,
    offsuit: !c.pair && !c.suited ? 1 : 0,
  };
}

// Per-type preference weights over the features ([가정] all; the shape follows the owner spec and the
// note: fish overvalue any ace / any suited / two faces and play K2s/Q8o [BR-BAD][PN]; nits want big
// pairs and broadways; LAGs suited connectors/gappers and suited Ax; stations call wide offsuit).
// `pref` orders opens, limps and flats; `flat` adds call-only preferences on top of `pref`.
export const PREF = {
  nit: { base: 1, pairHi: 0.25, broadway: 0.12, suited: 0.03, suitedConn: -0.08, pairSmall: -0.06, ace: 0.03 },
  weak: { base: 1, broadway: 0.12, faces: 0.05, suited: 0.04, suitedConn: -0.04, ace: 0.04, pairSmall: 0.03 },
  tag: { base: 1, suited: 0.06, suitedConn: 0.08, wheelAs: 0.08, pairSmall: 0.04 },
  lag: { base: 0.9, suited: 0.12, suitedConn: 0.16, wheelAs: 0.14, pairSmall: 0.06 },
  fish: { base: 0.6, ace: 0.3, suited: 0.18, faces: 0.2, king: 0.12, hiCard: 0.15, pairSmall: 0.06 },
  station: { base: 0.6, ace: 0.22, faces: 0.2, hiCard: 0.25, king: 0.1, offsuit: 0.06, pairSmall: 0.08 },
  maniac: { base: 0.7, suited: 0.14, ace: 0.14, suitedConn: 0.1, hiCard: 0.12 },
  pro: { base: 1, suited: 0.08, suitedConn: 0.1, wheelAs: 0.1, pairSmall: 0.04 },
};
// Calling an open: set-mine small pairs, flat suited broadways (all types), fish flat any ace.
const FLAT_ADD = { pairSmall: 0.25, suitedBroadway: 0.12 };
const FLAT_TYPE = { fish: { ace: 0.2 }, station: { offsuit: 0.1, ace: 0.1 } };
// Polarised 3-bet/4-bet bluffs (TAG/LAG/pro): A5s–A2s first, then suited broadways and suited
// connectors — the standard solver-era bluff set ([PL] mixes; chart sources [PSK]); weights [가정].
const BLUFF = { wheelAs: 1, suitedBroadway: 0.5, suitedConn: 0.45, base: 0.2 };
// Calling a 3-bet: pairs and suited broadways keep playability ([U20] style defence); [가정].
const CALL3B = { base: 1, pairHi: 0.1, pairSmall: 0.12, suitedBroadway: 0.1, suitedConn: 0.05 };
// 3-bet shape: linear (QQ+/AK-first by raw strength) for nits, weak-tights, fish, stations (owner spec);
// polarised for regulars; maniacs 3-bet their own (wide) preference.
const THREE_STYLE = { nit: "linear", weak: "linear", fish: "linear", station: "linear", tag: "polar", lag: "polar", pro: "polar", maniac: "pref" };
// Fish and stations raise only premiums and limp the rest (owner spec; §7.1 limp shares).
const RAISE_BY_BASE = new Set(["fish", "station"]);
// Per-instance spread of every weight: w · exp(σ·N(0,1)), [가정] (wider for recreational types, §6 κ shape).
const PREF_SIGMA = { nit: 0.2, weak: 0.25, tag: 0.2, lag: 0.25, fish: 0.4, station: 0.4, maniac: 0.4, pro: 0.15 };

function order(weights) {
  const sc = CLASSES.map(c => { let v = 0; for (const k in weights) v += weights[k] * c.f[k]; return v; });
  return CLASSES.map(c => c.i).sort((a, b) => sc[b] - sc[a]);
}
function perturb(w, sigma, rng) { const o = {}; for (const k in w) o[k] = w[k] * Math.exp(sigma * normal(rng)); return o; }
const add = (...ws) => { const o = {}; for (const w of ws) for (const k in w) o[k] = (o[k] || 0) + w[k]; return o; };
function buildOrders(t, rng) {
  const sg = PREF_SIGMA[t], pref = perturb(PREF[t], sg, rng);
  const O = {
    base: order({ base: 1 }),
    pref: order(pref),
    flat: order(add(pref, perturb(FLAT_ADD, sg, rng), perturb(FLAT_TYPE[t] || {}, sg, rng))),
    bluff: order(perturb(BLUFF, sg, rng)),
    call3b: order(perturb(CALL3B, sg, rng)),
  };
  O.raise = RAISE_BY_BASE.has(t) ? O.base : O.pref;
  O.three = THREE_STYLE[t] === "pref" ? O.pref : O.base;
  O.weights = pref;
  return O;
}

// A ladder hands out a share of the 1326 combos to each step in turn, each step taking classes in its own
// order and skipping combos an earlier step already took. ends[k][c] is the combo-position bound of step k
// in class c, so a combo with position f belongs to the first step whose end exceeds f. `avail` limits the
// whole ladder to the bottom part of each class (the combos of a range this seat already chose).
export function ladder(steps, avail = null) {
  const used = new Float64Array(169), ends = [];
  for (const [ord, width] of steps) {
    let left = Math.max(0, width) * 1326;
    for (const c of ord) {
      if (left <= 1e-9) break;
      const cap = avail ? avail[c] : 1, free = cap - used[c];
      if (free <= 1e-12) continue;
      const take = Math.min(free, left / CLASSES[c].combos);
      used[c] += take; left -= take * CLASSES[c].combos;
    }
    ends.push(used.slice());
  }
  return ends;
}
const stepOf = (ends, c, f) => { for (let k = 0; k < ends.length; k++) if (f < ends[k][c]) return k; return -1; };
function cached(pl, key, build) { let v = pl.cache.get(key); if (!v) { v = build(); pl.cache.set(key, v); } return v; }
// The unopened ladder of a position: [open-raise, open-limp].
export function openLadder(pl, pos) {
  pos = POS_MAP[pos] || "CO";
  return cached(pl, "open:" + pos, () => {
    const P = pl.p, width = pos === "BB" ? P.rfiSB : P["rfi" + pos], ls = pos === "SB" ? P.limpSB : P.limp;
    return ladder([[pl.orders.raise, width * (1 - ls)], [pl.orders.pref, width * ls]]);
  });
}
// 13×13 text summary of a ladder (rows = first rank, upper right suited): the step letter per class, upper
// case when the whole class is in, lower case when only part is, "." when none.
export function gridOf(ends, letters) {
  const rows = [];
  for (let r = 12; r >= 0; r--) {
    let row = "";
    for (let q = 12; q >= 0; q--) {
      const hi = Math.max(r, q), lo = Math.min(r, q), key = hi === lo ? RANKS[hi] + RANKS[hi] : RANKS[hi] + RANKS[lo] + (q < r ? "s" : "o");
      const c = CLASS_INDEX[key];
      let ch = ".", prev = 0;
      for (let k = 0; k < ends.length; k++) { const sh = ends[k][c] - prev; if (sh > 1e-6) { ch = sh > 0.999 ? letters[k].toUpperCase() : letters[k].toLowerCase(); break; } prev = ends[k][c]; }
      row += ch;
    }
    rows.push(RANKS[r] + " " + row);
  }
  return "  " + [...RANKS].reverse().join("") + "\n" + rows.join("\n");
}

// ------------------------------------------------------------------ postflop hand categories
// made: monster (straight+, set, trips) > twopair > overpair > topGood > topWeak > middle > weak > none;
// draw: combo (flush + straight draw) > fd > oesd > gut; overcards when no pair. River drops draws.
export function categorize(hole, board) {
  const all = hole.concat(board), rc = new Array(13).fill(0), bc = new Array(13).fill(0), sc = [0, 0, 0, 0], bs = [0, 0, 0, 0];
  for (const c of all) { rc[c >> 2]++; sc[c & 3]++; }
  for (const c of board) { bc[c >> 2]++; bs[c & 3]++; }
  const h = hole.map(c => c >> 2), hs = hole.map(c => c & 3);
  const bRanks = [...new Set(board.map(c => c >> 2))].sort((a, b) => b - a);
  const mask = m => { let x = 0; for (let r = 0; r < 13; r++) if (m[r]) x |= 1 << (r + 1); if (m[12]) x |= 1; return x; };   // bit 0 = ace low
  const straight = x => { for (let top = 13; top >= 4; top--) { const w = 0b11111 << (top - 4); if ((x & w) === w) return top; } return -1; };
  const am = mask(rc), bm = mask(bc);
  const flushSuit = sc.findIndex(n => n >= 5);
  let made = "none";
  const holeFlush = flushSuit >= 0 && hs.includes(flushSuit);
  const st = straight(am), bst = straight(bm);
  const pocket = h[0] === h[1];
  if (holeFlush || (st >= 0 && st > bst)) made = "monster";
  else if (pocket && bc[h[0]] >= 1) made = "monster";                         // set (or quads)
  else if (!pocket && (bc[h[0]] >= 2 || bc[h[1]] >= 2)) made = "monster";      // trips
  else if (!pocket && bc[h[0]] >= 1 && bc[h[1]] >= 1) made = "twopair";
  else if (pocket) made = h[0] > bRanks[0] ? "overpair" : h[0] > (bRanks[1] ?? -1) ? "middle" : "weak";
  else {
    const p = bc[h[0]] ? h[0] : bc[h[1]] ? h[1] : -1;
    if (p >= 0) {
      const kick = p === h[0] ? h[1] : h[0];
      made = p === bRanks[0] ? (kick >= 8 || kick === 12 ? "topGood" : "topWeak") : p === bRanks[1] ? "middle" : "weak";
    }
  }
  let draw = "";
  if (board.length < 5 && made !== "monster") {
    const fd = sc.some((n, s) => n === 4 && hs.includes(s));
    let outs = 0;
    for (let r = 0; r < 13; r++) {
      if (rc[r]) continue;
      const bit = (1 << (r + 1)) | (r === 12 ? 1 : 0), s2 = straight(am | bit);
      const bm2 = bm | bit;
      if (s2 >= 0 && s2 > straight(bm2)) outs++;
    }
    const sd = outs >= 2 ? "oesd" : outs === 1 ? "gut" : "";
    draw = fd && sd ? "combo" : fd ? "fd" : sd;
  }
  const over = made === "none" && Math.min(h[0], h[1]) > bRanks[0];
  const tex = {
    paired: bRanks.length < board.length,
    mono: bs.some(n => n >= 3),
    twoTone: bs.some(n => n === 2),
    high: bRanks[0] >= 10,                                                     // Q+ high
    connected: bRanks.some((r, i) => i + 2 < bRanks.length && r - bRanks[i + 2] <= 4),
  };
  tex.wet = tex.mono || tex.twoTone || tex.connected;
  const key = made + (draw ? ":" + draw : "") + (over ? ":over" : "");
  return { made, draw, over, tex, key, hi: Math.max(h[0], h[1]), lo: Math.min(h[0], h[1]) };
}
const ONE_PAIR = new Set(["overpair", "topGood", "topWeak", "middle", "weak"]);

// ------------------------------------------------------------------ strength
function interp(xs, ys, x) {
  if (x <= xs[0]) return ys[0];
  for (let i = 1; i < xs.length; i++) if (x <= xs[i]) { const f = (x - xs[i - 1]) / (xs[i] - xs[i - 1] || 1); return ys[i - 1] + f * (ys[i] - ys[i - 1]); }
  return ys[ys.length - 1];
}
const DEC = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1];
export const eqToQ = (street, eq) => interp(EQ_DECILES[street], DEC, eq);
export const qToEq = (street, q) => interp(DEC, EQ_DECILES[street], q);
function invPhi(p) {   // Acklam's rational approximation, |error| < 1.2e-9
  const a = [-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924];
  const b = [-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857];
  const c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878];
  const d = [0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742];
  p = clip(p, 1e-6, 1 - 1e-6);
  if (p < 0.02425) { const q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  if (p > 1 - 0.02425) return -invPhi(1 - p);
  const q = p - 0.5, r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}
function Phi(z) { const t = 1 / (1 + 0.3275911 * Math.abs(z) / Math.SQRT2); const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z / 2); return 0.5 * (1 + (z >= 0 ? y : -y)); }
// Frequencies in the note are per opportunity, i.e. shares of the hands this player actually holds there,
// not of random hands. A seat that played a top-w preflop range holds a better than random flop, so
// strength is measured against its own range: the percentile vs random, shifted by how far the range
// carries forward. Street rank correlations 0.31 / 0.82 / 0.78 (preflop→flop→turn→river) were measured
// offline with tpgto.evaluate; SURVIVOR is the extra lift of having continued on earlier streets ([가정],
// fitted so the calibration test lands fold-to-c-bet and WTSD in the note's ranges).
const CHAIN = [1, 0.31, 0.31 * 0.82, 0.31 * 0.82 * 0.78], SURVIVOR = [0, 0, 0.4, 0.5];
function rangeShift(pl, street, facing, aggressor) {
  // The preflop raiser holds its raising range (premiums only for a fish); a caller its whole VPIP.
  const w = clip(aggressor ? pl.p.rfiCO * (1 - pl.p.limp) : pl.p.rfiCO + pl.p.coldcall, 0.03, 0.9), c = invPhi(1 - w);
  const m = Math.exp(-c * c / 2) / Math.sqrt(2 * Math.PI) / w;   // E[z | top-w]
  return CHAIN[street] * m + (facing ? SURVIVOR[street] : 0);
}
// Share of each hand category among random hands, weakest first by mean equity vs a random hand
// (measured offline: categorize + tpgto.evaluate, 40000 random deals per street x 120 runouts).
const CAT_TABLE = {
  1: [["none", 0.4309], ["none:gut", 0.0725], ["none:over", 0.057], ["none:gut:over", 0.0083], ["none:oesd", 0.0238], ["none:oesd:over", 0.0027], ["none:fd", 0.0231], ["weak", 0.1005], ["none:combo", 0.0054], ["weak:gut", 0.0049], ["none:fd:over", 0.0032], ["weak:oesd", 0.0013], ["none:combo:over", 0.0004], ["weak:fd", 0.0033], ["middle", 0.0989], ["middle:gut", 0.0042], ["middle:oesd", 0.0011], ["topWeak:gut", 0.0022], ["weak:combo", 0.0003], ["topWeak:oesd", 0.001], ["topWeak:combo", 0.0001], ["overpair:gut", 0.0004], ["middle:fd", 0.0024], ["topWeak", 0.0524], ["middle:combo", 0.0001], ["topGood:gut", 0.0012], ["overpair:combo", 0.0001], ["overpair:oesd", 0.0001], ["overpair", 0.0127], ["topGood", 0.0335], ["topGood:oesd", 0.0002], ["topWeak:fd", 0.002], ["overpair:fd", 0.0004], ["topGood:combo", 0], ["topGood:fd", 0.001], ["twopair", 0.0206], ["monster", 0.0276]],
  2: [["none", 0.2793], ["none:gut", 0.11], ["none:oesd", 0.0438], ["none:over", 0.0267], ["none:gut:over", 0.0083], ["none:fd", 0.0361], ["none:oesd:over", 0.0023], ["none:combo", 0.0208], ["none:combo:over", 0.0015], ["none:fd:over", 0.0034], ["weak", 0.1369], ["weak:gut", 0.0185], ["weak:oesd", 0.0062], ["weak:fd", 0.0139], ["weak:combo", 0.003], ["middle:gut", 0.01], ["middle:oesd", 0.0027], ["middle", 0.0748], ["middle:combo", 0.0011], ["middle:fd", 0.0071], ["topWeak:oesd", 0.0019], ["topWeak:gut", 0.0054], ["overpair:gut", 0.0009], ["topWeak", 0.0402], ["overpair", 0.0092], ["topWeak:combo", 0.0008], ["overpair:combo", 0.0001], ["topGood", 0.026], ["topGood:oesd", 0.0006], ["topWeak:fd", 0.0035], ["overpair:fd", 0.0006], ["topGood:gut", 0.0032], ["topGood:fd", 0.0024], ["overpair:oesd", 0.0001], ["topGood:combo", 0.0004], ["twopair", 0.034], ["twopair:fd", 0.0013], ["monster", 0.0627]],
  3: [["none", 0.4023], ["none:over", 0.0271], ["weak", 0.2201], ["middle", 0.0856], ["topWeak", 0.0469], ["topGood", 0.0296], ["overpair", 0.0085], ["twopair", 0.0523], ["monster", 0.1276]],
};
const CAT_START = {};
for (const st of [1, 2, 3]) {
  const m = new Map(); let cum = 0;
  const total = CAT_TABLE[st].reduce((a, [, sh]) => a + sh, 0);
  for (const [k, sh] of CAT_TABLE[st]) { m.set(k, [cum / total, sh / total]); cum += sh; }
  CAT_START[st] = m;
}
// Percentile vs random hands from the category; inside a category higher hole cards rank higher.
export function catPercentile(street, cat) {
  const m = CAT_START[street];
  const e = m.get(cat.key) || m.get(cat.made + (cat.draw ? ":" + cat.draw : "")) || m.get(cat.made) || m.get("none");
  return e[0] + e[1] * ((cat.hi * 13 + cat.lo) / 168);
}
// Beating k opponents at once ≈ beating each, so a percentile becomes q^k multiway.
function strengthOf(pl, sit) {
  const q = sit.cat ? catPercentile(sit.street, sit.cat) : eqToQ(sit.street, sit.hand.eq);
  const z = invPhi(q) - rangeShift(pl, sit.street, sit.toCall > 0, !!sit.postflop?.aggressor);
  return Math.pow(Phi(z), Math.max(1, sit.nOpp));
}

// ------------------------------------------------------------------ helpers
const POS_MAP = { UTG: "UTG", "UTG+1": "UTG", MP: "HJ", LJ: "HJ", HJ: "HJ", CO: "CO", BTN: "BTN", SB: "SB", BB: "BB" };
const STEAL = new Set(["CO", "BTN", "SB"]);
const nearestBet = f => BET_MENU.reduce((a, b) => (Math.abs(Math.log(b / f)) < Math.abs(Math.log(a / f)) ? b : a));

function raiseTo(sit, to) {
  const L = sit.legal;
  if (!L.canRaise) return null;
  to = Math.round(clip(to, L.minTo, L.maxTo));
  if (to >= ALLIN_MERGE * L.maxTo) to = L.maxTo;
  return { type: "raise", to };
}
const passive = (sit) => (sit.legal.canCheck ? { type: "check" } : { type: "call" });
const foldOrCheck = (sit) => (sit.legal.canCheck ? { type: "check" } : { type: "fold" });
// Size tell: log size moves with strength, scaled by the instance's tell strength and direction (§4, §7.4).
const tellShift = (pl, s) => Math.exp(1.6 * pl.tells.sizeStrength * pl.tells.sizeDir * (s - 0.7));

// ------------------------------------------------------------------ preflop
// Widths are the phase-1 frequencies (§7.1); which hands fill each width comes from the seat's own
// orders (hand matrix), so a fish's 40% is not a nit's 12% made wider.
const PREMIUM = new Set(["AA", "KK"]);
function preflop(pl, sit, rng) {
  const P = pl.p, t = pl.type, O = pl.orders, pre = sit.preflop, pos = POS_MAP[sit.pos] || "CO";
  const [ca, cb] = sit.hand.cards, cls = classOfCards(ca, cb), f = comboFrac(ca, cb);
  const s = CLASSES[cls].base;   // strength for the size tell
  const bb = sit.bb, polar = THREE_STYLE[t] === "polar";
  const width = pos === "BB" ? P.rfiSB : P["rfi" + pos];
  const limpShare = pos === "SB" ? P.limpSB : P.limp;
  const raiseW = width * (1 - limpShare);
  const trap = pl.tells.limpReraise && PREMIUM.has(CLASSES[cls].key);
  const step = (key, steps, avail) => stepOf(cached(pl, key, () => ladder(steps, avail)), cls, f);
  if (pre.raises === 0) {
    if (pos === "BB") {   // limped to the BB: raise the top of a CO-like raising range, else check
      if (step("bb", [[O.raise, P.rfiCO * (1 - P.limp) * 0.5]]) === 0) return raiseTo(sit, bb * (3 + 1.5 * pre.limpers) * tellShift(pl, s)) || passive(sit);
      return passive(sit);
    }
    if (trap) return passive(sit);
    if (pre.limpers > 0) {   // iso-raise the top, over-limp what the type would have limped
      const k = step("iso:" + pos, [[O.raise, raiseW * 0.8], [O.pref, width * (0.3 + 0.7 * limpShare) - raiseW * 0.8]]);
      if (k === 0) return raiseTo(sit, bb * (openSize(pl, rng) + SIZES.perLimper[t] * pre.limpers) * tellShift(pl, s)) || passive(sit);
      return k === 1 ? passive(sit) : foldOrCheck(sit);
    }
    const k = stepOf(openLadder(pl, pos), cls, f);
    if (k === 0) return raiseTo(sit, bb * openSize(pl, rng) * tellShift(pl, s)) || passive(sit);
    return k === 1 ? passive(sit) : foldOrCheck(sit);
  }
  // The open was bigger than a standard 2.5x: everyone continues tighter (pot odds), stations least.
  const sizeAdj = clip(Math.sqrt(2.5 * bb / Math.max(pre.openTo || 2.5 * bb, 2 * bb)), 0.45, 1.2);
  const r3 = x => Math.round(x * 1000);
  if (pre.raises === 1 && !pre.iRaised) {
    if (pre.limped) {   // limp then face a raise: limp-call most of the limps, re-raise the trapped aces
      if (trap) return raiseTo(sit, threeBetTo(pl, sit, s)) || { type: "call" };
      const k = step("limpcall:" + pos, [[O.raise, raiseW], [O.pref, (width - raiseW) * (1 - 0.5 * P.f3b)]]);
      return k === 1 ? { type: "call" } : { type: "fold" };
    }
    const steal = STEAL.has(POS_MAP[pre.openerPos] || "UTG");
    const tb = (steal ? P.threebetSteal : P.threebet) * sizeAdj;
    let call;
    if (pos === "BB") call = P.bbDefend * ({ BTN: 1, SB: 1.1, CO: 0.85, HJ: 0.7 }[POS_MAP[pre.openerPos]] ?? 0.6) - tb;
    else if (pos === "SB") call = P.coldcall * 0.6;
    else call = P.coldcall;
    call = Math.max(0, call * sizeAdj);
    // Polarised: value from the top, bluffs (A5s–A2s, suited broadways/connectors) before the flats take
    // them; linear: the top only, then flats.
    const steps = polar ? [[O.base, tb * 0.6], [O.bluff, tb * 0.4], [O.flat, call]] : [[O.three, tb], [O.flat, call]];
    const k = step(`vs1:${pos}:${r3(tb)}:${r3(call)}`, steps);
    const flatK = polar ? 2 : 1;
    if (k === flatK) return { type: "call" };
    if (k >= 0) return raiseTo(sit, threeBetTo(pl, sit, s)) || { type: "call" };
    return foldOrCheck(sit);
  }
  if (pre.raises === 1) return passive(sit);   // back to the opener unraised (a short all-in did not reopen)
  if (pre.raises === 2 && pre.iRaised) {   // my open got 3-bet: continue inside the hands I raised
    const cont = raiseW * (1 - P.f3b), fb = Math.min(P.fourbet, cont);
    const steps = polar ? [[O.base, fb * 0.75], [O.bluff, fb * 0.25], [O.call3b, cont - fb]] : [[O.base, fb], [O.call3b, cont - fb]];
    const k = step("vs3:" + pos, steps, openLadder(pl, pos)[0]);
    if (k === steps.length - 1) return { type: "call" };
    if (k >= 0) return raiseTo(sit, sit.currentBet * pickOf([2.2, 2.5], rng)) || { type: "call" };
    return { type: "fold" };
  }
  if (pre.raises === 2) {   // cold vs a 3-bet, or squeezed after calling the open
    const k = step("cold3", [[O.base, P.fourbet * 0.5], [O.call3b, P.fourbet * 0.3 + P.coldcall * 0.1]]);
    if (k === 0) return raiseTo(sit, sit.currentBet * 2.3) || { type: "call" };
    return k === 1 ? { type: "call" } : { type: "fold" };
  }
  // 4-bet and beyond: jam the top, call a little, fold the rest.
  const k = step("vs4:" + (pre.iRaised ? 1 : 0), [[O.base, P.fourbet * 0.5], [O.base, P.fourbet * ((pre.iRaised ? 1.1 : 0.7) - 0.5)]]);
  if (k === 0) return raiseTo(sit, sit.legal.maxTo) || { type: "call" };
  return k === 1 ? { type: "call" } : { type: "fold" };
}
const openSize = (pl, rng) => (pl.type === "pro" ? pickOf(SIZES.open.pro, rng) : pl.p.openSize);
function threeBetTo(pl, sit, s) {
  // IP 3x, OOP 3.5–4x the open (§3 regulars); maniacs go 4–5x ([가정]).
  const m = pl.type === "maniac" ? 4.5 : sit.ip || ["BTN", "CO"].includes(POS_MAP[sit.pos]) ? 3 : 3.75;
  return sit.currentBet * m * tellShift(pl, s);
}

// ------------------------------------------------------------------ postflop
function betTo(pl, sit, s, bluff, rng) {
  const t = pl.type, st = sit.street;
  let f = pickOf(SIZES.bet[t], rng);
  const ob = SIZES.overbet[t] || 0;
  if (st >= 2 && ob && rng() < ob) f = pickOf([1.5, 2], rng);
  // pro: small river bets are value-heavy, the bluffs use the bigger sizes ([U26] §2.4 pattern).
  if (t === "pro" && st === 3 && bluff) f = pickOf([0.75, 1, 1.5], rng);
  if (t === "station" && st === 3 && !bluff) f = 0.5;
  f = nearestBet(f * tellShift(pl, s));
  return raiseTo(sit, sit.myBet + f * sit.pot);
}
function raiseSize(pl, sit, s, rng) {
  const m = pickOf(SIZES.raise[pl.type], rng) * tellShift(pl, s);
  return raiseTo(sit, sit.currentBet * m + 0.2 * sit.pot);
}

const REG = new Set(["tag", "lag", "pro"]);
const DRAWS = new Set(["fd", "oesd", "combo"]);
function postflop(pl, sit, rng) {
  const a = postflopBase(pl, sit, rng), cat = sit.cat;
  if (!cat || sit.toCall === 0) return a;
  // Category rules (owner spec on #429, [가정] directions from the note §5 [BR-CB][BR-3B]).
  const t = pl.type, st = sit.street, raises = sit.postflop.streetRaises, pair = cat.made !== "none";
  if (t === "nit" && st === 2 && raises >= 2 && ONE_PAIR.has(cat.made) && !cat.draw) return { type: "fold" };   // one pair folds to a turn raise
  if (a.type === "fold") {
    if (t === "fish" && st === 1 && raises <= 1 && (pair || cat.draw)) return { type: "call" };   // top pair never folds; any pair or draw calls once
    if (t === "station" && pair) return { type: "call" };                                          // calls down any pair
    if (st === 2 && DRAWS.has(cat.draw) && rng() < pl.tells.chase) return { type: "call" };
  }
  return a;
}
function postflopBase(pl, sit, rng) {
  const P = pl.p, tl = pl.tells, st = sit.street, po = sit.postflop, cat = sit.cat;
  const s = strengthOf(pl, sit);
  if (sit.toCall === 0) {
    // Which betting frequency this spot uses (§7.2): c-bet, donk, float, probe.
    let f;
    if (po.aggressor) {
      f = [0, P.cbetF, P.cbetT, P.cbetR][st] * Math.pow(0.75, sit.nOpp - 1);
      if (st === 1 && tl.autopilotCbet) return betTo(pl, sit, s, s < 0.5, rng) || { type: "check" };
      if (st === 2 && tl.persist === "giveup") f *= 0.5;
    } else if (po.prevAggLive && po.prevBet) f = sit.ip ? P.float : P.donk;
    else if (po.prevAggLive) f = P.probe;
    // Nobody holds the initiative (limped pot, or the raiser folded): stab like a weaker c-bet ([가정]).
    else f = Math.max(P.probe, 0.6 * P.cbetF);
    // Regulars c-bet by texture: more on high dry boards (raiser's range advantage), less on low wet ones ([가정]).
    if (cat && po.aggressor && st === 1 && REG.has(pl.type)) f = Math.min(0.97, f * (cat.tex.high && !cat.tex.wet ? 1.15 : !cat.tex.high && cat.tex.wet ? 0.8 : 1));
    // "Bet only made hands": the whole frequency goes to made hands, no bluffs.
    if (cat && tl.madeOnly) {
      if (cat.made !== "none" && s >= 1 - f) return betTo(pl, sit, s, false, rng) || { type: "check" };
      return { type: "check" };
    }
    const bs = st === 3 ? P.riverBluff : Math.min(0.55, P.riverBluff + (st === 1 ? 0.3 : 0.2));
    const valueFrom = 1 - f * (1 - bs);
    if (s >= valueFrom) {
      if (tl.actsWeak && st < 3 && s >= 0.85 && rng() < 0.6) return { type: "check" };
      return betTo(pl, sit, s, false, rng) || { type: "check" };
    }
    // Semi-bluffers pick draws over air for the bluff share (the average stays near f·bs).
    const lean = cat && st < 3 ? (cat.draw ? 1.8 : 0.4) : 1;
    if (s < 0.5 && rng() < Math.min(1, lean * f * bs / 0.5)) return betTo(pl, sit, s, true, rng) || { type: "check" };
    return { type: "check" };
  }
  // Facing a bet or raise.
  const betFrac = sit.toCall / Math.max(1, sit.pot - sit.toCall);
  let fold = [0, P.foldCbF, P.foldCbT, P.foldR][st];
  if (st >= 2 && tl.persist === "sticky") fold *= 0.75;
  if (st === 2 && tl.persist === "giveup") fold = Math.min(0.9, fold * 1.35);
  fold += 0.25 * (betFrac - 0.6);                          // bigger bets get folded more
  if (po.streetRaises >= 2) fold += 0.15;                  // overfold vs raises ([U25] +15 %p)
  fold = clip(fold, 0.02, 0.97);
  let foldFrom;
  // Raise frequency: x/r when this seat checked first, a bit less as a straight raise (§7.2).
  let xr = po.checkedThisStreet ? P.xr : P.xr * 0.7;
  if (po.streetRaises >= 2) xr *= 0.3;
  const nutsOnly = st === 3 && tl.riverNutsOnly;
  const raiseFrom = nutsOnly ? 0.97 : 1 - xr * P.xrValue;
  if (sit.legal.canRaise && s >= raiseFrom) {
    if (tl.actsWeak && st < 3 && rng() < 0.6) return { type: "call" };
    return raiseSize(pl, sit, s, rng) || { type: "call" };
  }
  // Bluff raises come out of the would-fold region, which is widened by the same amount so the fold
  // rate stays the parameter (HUD fold-to-c-bet counts a bluff raise as not folding).
  const bluffRaise = nutsOnly || !sit.legal.canRaise ? 0 : xr * (1 - P.xrValue);
  foldFrom = Math.min(raiseFrom, fold + bluffRaise);
  if (s >= foldFrom) return { type: "call" };
  if (bluffRaise && rng() < bluffRaise / Math.max(0.05, foldFrom)) return raiseSize(pl, sit, s, rng) || { type: "fold" };
  return { type: "fold" };
}

// ------------------------------------------------------------------ timing
// Think delay (§5 timing tells, §7.4): pace × strength term (slow = strong, or reversed per instance),
// a long tank before strong bets/raises, fast calls with medium hands. Uniform-timing instances
// (multi-tablers) only jitter.
export function thinkMs(pl, act, q, rng) {
  const tl = pl.tells;
  let ms = pl.pace * (0.9 + 0.2 * rng());
  if (!tl.uniformTiming) {
    ms *= Math.exp(1.4 * tl.timingStrength * tl.timingDir * (q - 0.5));
    if (act.type === "raise" && q >= 0.85) ms *= 1 + 0.8 * tl.tankStrong * (tl.timingDir > 0 ? 1 : 0);
    if (act.type === "call" && q >= 0.35 && q <= 0.75) ms *= 1 - 0.55 * tl.fastCallMedium;
  }
  return Math.round(clip(ms, MS_MIN, MS_MAX));
}

export function decide(pl, sit, rng) {
  if (sit.street > 0 && sit.hand.cards && sit.board?.length >= 3) sit.cat = categorize(sit.hand.cards, sit.board);
  const a = (sit.street === 0 ? preflop(pl, sit, rng) : postflop(pl, sit, rng));
  if (a.type === "check" && !sit.legal.canCheck) { a.type = "fold"; }
  if (a.type === "call" && sit.toCall === 0) a.type = "check";
  const q = sit.street === 0 ? CLASSES[classOfCards(...sit.hand.cards)].base : strengthOf(pl, sit);
  a.q = q;
  a.ms = thinkMs(pl, a, q, rng);
  return a;
}
