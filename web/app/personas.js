// Training Game opponent personas (#429 phase 1). Dependency-free ES module so node can test it.
//
// Every number cites docs/research/2026-10-30-population-stats.md (§ = section of that note).
// Each seat is one *instance*: createPlayer draws its own stats from the type's distribution and its
// own innate tells, so two nits at the same table play and leak differently (owner direction on #429).
//
// API
//   TYPES                         the persona keys (index.html PERSONAS / personaPool use the same keys)
//   MEANS, KAPPA, TELLS, SIZES    the type tables (means, Beta concentrations, tell priors, size habits)
//   mulberry32(seed) -> rng       a seeded uniform [0,1) stream; every draw takes an rng () => number
//   createPlayer(type, rng, over) one instance: { type, p: drawn params, tells, pace }
//   decide(player, sit, rng)      { type: fold|check|call|raise, to?, q, ms } from what the seat may see
//   eqToQ(street, eq) / qToEq     equity vs one random hand <-> percentile of that equity on the street
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
//   hand: pct (preflop class percentile 0..100, lower = stronger), eq (postflop equity vs one random hand)

export const TYPES = ["nit", "weak", "tag", "lag", "fish", "station", "maniac", "pro"];
const T = (nit, weak, tag, lag, fish, station, maniac, pro) => ({ nit, weak, tag, lag, fish, station, maniac, pro });

// Means in % of the opportunity (§7.1, §7.2). Regular RFI from charts [PSK][PT]; everything else is the
// centre of the §2 ranges or a [가정] value of the note. pro postflop ("GTO" in §7.2) is GTO-near plus
// the measured overfold of [U25][U26] (fold + 3/8/5 %p); the GTO-near base is [가정].
// Departures from §7.1/§7.2, each fitted by web/app/test/personas.test.mjs against a regular table and
// kept inside the §2 ranges:
//   fish/station RFI ×1.4/×1.5 and cold call 22→30/35→45: §7.1 ([가정] there) gave VPIP 22/31, below the
//     cited 30–45/40–65 [PN][DC][BR-PFR] it was meant to sum to;
//   fold turn/river fish 45→50/45→50, station 28→35/30→50, station fold flop 25→33: WTSD came out
//     above the cited 30–36/35–45 [BR-WTSD][DC];
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
  foldCbF: T(55, 55, 48, 40, 38, 33, 32, 45),
  foldCbT: T(62, 65, 50, 45, 50, 35, 28, 50),
  foldR: T(65, 65, 57, 50, 50, 50, 28, 55),
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
  };
  const u = rng();
  tells.persist = u < tl.sticky[t] ? "sticky" : u < tl.sticky[t] + tl.giveUp[t] ? "giveup" : "none";
  if (tells.uniformTiming) { tells.timingStrength = 0; tells.fastCallMedium = 0; tells.tankStrong = 0; }
  if (type === "gto") for (const k in tells) tells[k] = typeof tells[k] === "number" ? (k.endsWith("Dir") ? 1 : 0) : (k === "persist" ? "none" : false);
  // The baseline pace a seat thinks at, 0.9–1.9 s ([가정]: the old fixed 1.5 s sits in the middle).
  const pace = 900 + 1000 * rng();
  const pl = { type: t, p: Object.assign(p, over.p || {}), tells: Object.assign(tells, over.tells || {}), pace: over.pace ?? pace };
  return pl;
}

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
const CHAIN = [1, 0.31, 0.31 * 0.82, 0.31 * 0.82 * 0.78], SURVIVOR = [0, 0, 0.25, 0.3];
function rangeShift(pl, street, facing) {
  const w = clip(pl.p.rfiCO + pl.p.coldcall, 0.03, 0.9), c = invPhi(1 - w);
  const m = Math.exp(-c * c / 2) / Math.sqrt(2 * Math.PI) / w;   // E[z | top-w]
  return CHAIN[street] * m + (facing ? SURVIVOR[street] : 0);
}
// Beating k opponents at once ≈ beating each, so a percentile becomes q^k multiway.
function strengthOf(pl, sit) {
  const z = invPhi(eqToQ(sit.street, sit.hand.eq)) - rangeShift(pl, sit.street, sit.toCall > 0);
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
function preflop(pl, sit, rng) {
  const P = pl.p, t = pl.type, pre = sit.preflop, pos = POS_MAP[sit.pos] || "CO", pct = sit.hand.pct / 100;
  const s = 1 - pct;   // strength for the size tell
  const bb = sit.bb;
  const width = pos === "BB" ? P.rfiSB : P["rfi" + pos];
  const limpShare = pos === "SB" ? P.limpSB : P.limp;
  if (pre.raises === 0) {
    if (pos === "BB") {   // limped to the BB: raise the top of a CO-like raising range, else check
      if (pct <= P.rfiCO * (1 - P.limp) * 0.5) return raiseTo(sit, bb * (3 + 1.5 * pre.limpers) * tellShift(pl, s)) || passive(sit);
      return passive(sit);
    }
    const raiseW = width * (1 - limpShare);
    if (pre.limpers > 0) {   // iso-raise the top, over-limp what the type would have limped
      if (pct <= raiseW * 0.8) return raiseTo(sit, bb * (openSize(pl, rng) + SIZES.perLimper[t] * pre.limpers) * tellShift(pl, s)) || passive(sit);
      if (pct <= width * (0.3 + 0.7 * limpShare)) return passive(sit);
      return foldOrCheck(sit);
    }
    if (pct <= raiseW) return raiseTo(sit, bb * openSize(pl, rng) * tellShift(pl, s)) || passive(sit);
    if (pct <= width) return passive(sit);
    return foldOrCheck(sit);
  }
  // The open was bigger than a standard 2.5x: everyone continues tighter (pot odds), stations least.
  const sizeAdj = clip(Math.sqrt(2.5 * bb / Math.max(pre.openTo || 2.5 * bb, 2 * bb)), 0.45, 1.2);
  if (pre.raises === 1 && !pre.iRaised) {
    const steal = STEAL.has(POS_MAP[pre.openerPos] || "UTG");
    const tb = (steal ? P.threebetSteal : P.threebet) * sizeAdj;
    let call;
    if (pre.limped) call = width * (1 - 0.5 * P.f3b);     // limp then face a raise: limp-call most of it
    else if (pos === "BB") call = P.bbDefend * ({ BTN: 1, SB: 1.1, CO: 0.85, HJ: 0.7 }[POS_MAP[pre.openerPos]] ?? 0.6) - tb;
    else if (pos === "SB") call = P.coldcall * 0.6;
    else call = P.coldcall;
    call = Math.max(0, call * sizeAdj);
    const valueW = tb * 0.7;                               // 3-bets: 70% from the top, 30% bluffs just below the calls
    if (pct <= valueW) return raiseTo(sit, threeBetTo(pl, sit, s)) || passive(sit);
    if (pct <= valueW + call) return { type: "call" };
    if (pct <= valueW + call + tb * 0.3) return raiseTo(sit, threeBetTo(pl, sit, s)) || foldOrCheck(sit);
    return foldOrCheck(sit);
  }
  if (pre.raises === 1) return passive(sit);   // back to the opener unraised (a short all-in did not reopen)
  if (pre.raises === 2 && pre.iRaised) {   // my open got 3-bet
    const cont = width * (1 - limpShare) * (1 - P.f3b);   // of the hands that raised, not the limps
    if (pct <= Math.min(P.fourbet, cont)) return raiseTo(sit, sit.currentBet * pickOf([2.2, 2.5], rng)) || { type: "call" };
    if (pct <= cont) return { type: "call" };
    return { type: "fold" };
  }
  if (pre.raises === 2) {   // cold vs a 3-bet, or squeezed after calling the open
    if (pct <= P.fourbet * 0.5) return raiseTo(sit, sit.currentBet * 2.3) || { type: "call" };
    if (pct <= P.fourbet * 0.8 + P.coldcall * 0.1) return { type: "call" };
    return { type: "fold" };
  }
  // 4-bet and beyond: jam the top, call a little, fold the rest.
  if (pct <= P.fourbet * 0.5) return raiseTo(sit, sit.legal.maxTo) || { type: "call" };
  if (pct <= P.fourbet * (pre.iRaised ? 1.1 : 0.7)) return { type: "call" };
  return { type: "fold" };
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

function postflop(pl, sit, rng) {
  const P = pl.p, tl = pl.tells, st = sit.street, po = sit.postflop;
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
    const bs = st === 3 ? P.riverBluff : Math.min(0.55, P.riverBluff + (st === 1 ? 0.3 : 0.2));
    const valueFrom = 1 - f * (1 - bs);
    if (s >= valueFrom) {
      if (tl.actsWeak && st < 3 && s >= 0.85 && rng() < 0.6) return { type: "check" };
      return betTo(pl, sit, s, false, rng) || { type: "check" };
    }
    if (s < 0.5 && rng() < Math.min(1, f * bs / 0.5)) return betTo(pl, sit, s, true, rng) || { type: "check" };
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
  const a = (sit.street === 0 ? preflop(pl, sit, rng) : postflop(pl, sit, rng));
  if (a.type === "check" && !sit.legal.canCheck) { a.type = "fold"; }
  if (a.type === "call" && sit.toCall === 0) a.type = "check";
  const q = sit.street === 0 ? 1 - sit.hand.pct / 100 : strengthOf(pl, sit);
  a.q = q;
  a.ms = thinkMs(pl, a, q, rng);
  return a;
}
