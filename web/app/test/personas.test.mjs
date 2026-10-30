// node --test web/app/test/personas.test.mjs — persona calibration (#429 phase 1).
// A self-contained 6-max hand simulator plays one persona seat against five neutral TAG seats and
// measures HUD stats; each type must land inside the cited target ranges of
// docs/research/2026-10-30-population-stats.md §2 (ranges, plus the tolerance below).
import { test } from "node:test";
import assert from "node:assert/strict";
import * as P from "../personas.js";

// ---------------------------------------------------------------- simulator
const POS = ["BTN", "SB", "BB", "UTG", "HJ", "CO"];   // offset from the button
const BB = 100, STACK = 100 * BB;
function erf(x) { const t = 1 / (1 + 0.3275911 * Math.abs(x)); const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x); return x >= 0 ? y : -y; }
const Phi = z => 0.5 * (1 + erf(z / Math.SQRT2));
function gauss(rng) { let u = 0; while (u === 0) u = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rng()); }

function newStats() { return { hands: 0, vpip: 0, pfr: 0, tbOpp: 0, tb: 0, f3bOpp: 0, f3b: 0, cbOpp: 0, cb: 0, fcbOpp: 0, fcb: 0, flops: 0, sd: 0 }; }

// Street-to-street rank correlation of equity vs a random hand (preflop→flop, flop→turn, turn→river),
// measured offline with tpgto.evaluate on 1500 random deals: 0.31, 0.82, 0.78 (flop→river 0.64).
const CHAIN = [0.31, 0.82, 0.78];

// One hand. Strength is abstract but shaped like real cards: a Gaussian chain of street percentiles
// with the measured correlations; the river percentile decides the showdown.
function playHand(players, button, rng, st) {
  const n = players.length;
  const seats = players.map((pl, i) => {
    const z = [gauss(rng)];
    for (const c of CHAIN) z.push(c * z[z.length - 1] + Math.sqrt(1 - c * c) * gauss(rng));
    const q = [null, Phi(z[1]), Phi(z[2]), Phi(z[3])];
    return { i, pl, pos: POS[(i - button + n) % n], stack: STACK, bet: 0, folded: false, allin: false, pct: 100 * (1 - Phi(z[0])), q, raised: false, checked: false };
  });
  const me = seats[0];
  st.hands++;
  let pot = 0, currentBet = 0, minRaise = BB, streetRaises = 0, prevAgg = null, lastAgg = null, prevBet = false, firstBettor = null, openerPos = null, openTo = 0;
  const live = () => seats.filter(s => !s.folded);
  const canAct = () => seats.filter(s => !s.folded && !s.allin);
  const post = (s, a) => { s.stack -= a; s.bet += a; };
  const sbI = (button + 1) % n, bbI = (button + 2) % n;
  post(seats[sbI], BB / 2); post(seats[bbI], BB); currentBet = BB; streetRaises = 1;
  let vpip = false, pfr = false, sawFlop = false;
  for (let street = 0; street < 4; street++) {
    if (street > 0) {
      pot += seats.reduce((a, s) => a + s.bet, 0); for (const s of seats) { s.bet = 0; s.checked = false; s.raised = false; }
      prevBet = streetRaises > (street === 1 ? 1 : 0);
      prevAgg = lastAgg; currentBet = 0; minRaise = BB; streetRaises = 0; firstBettor = null;
      if (street === 1 && !me.folded) { sawFlop = true; st.flops++; }
    }
    const order = []; let k = street === 0 ? (bbI + 1) % n : (button + 1) % n;
    for (let c = 0; c < n; c++) { order.push(k); k = (k + 1) % n; }
    if (canAct().length > (currentBet > 0 ? 0 : 1)) {
      const pending = new Set(canAct().map(s => s.i));
      let idx = 0, guard = 0;
      while (pending.size && live().length > 1 && guard++ < 400) {
        const s = seats[order[idx % n]]; idx++;
        if (!pending.has(s.i)) continue;
        pending.delete(s.i);
        if (s.folded || s.allin) continue;
        const toCall = Math.min(currentBet - s.bet, s.stack);
        const others = canAct().filter(o => o !== s).length;
        if (toCall === 0 && others === 0) continue;
        const maxTo = s.bet + s.stack;
        const legal = { canCheck: toCall === 0, canRaise: s.stack > toCall && others > 0, minTo: Math.min(currentBet + minRaise, maxTo), maxTo };
        const liveOrder = order.map(j => seats[j]).filter(o => !o.folded);
        const sit = {
          street, pos: s.pos, bb: BB, pot: pot + seats.reduce((a, o) => a + o.bet, 0), toCall, currentBet, myBet: s.bet, legal,
          nOpp: live().length - 1, ip: liveOrder[liveOrder.length - 1] === s,
          preflop: { raises: streetRaises - 1, limpers: seats.filter(o => o !== s && !o.folded && o.bet === BB && o.i !== bbI).length,
            limped: street === 0 && s.bet === BB && s.i !== bbI, iRaised: s.raised, openerPos, openTo },
          postflop: { aggressor: prevAgg === s.i, prevAggLive: prevAgg != null && prevAgg !== s.i && !seats[prevAgg].folded, prevBet,
            betIsCbet: firstBettor != null && firstBettor === prevAgg && streetRaises === 1, checkedThisStreet: s.checked, streetRaises },
          hand: { pct: s.pct, eq: street ? P.qToEq(street, s.q[street]) : null },
        };
        const a = P.decide(s.pl, sit, rng);
        if (s === me) {
          if (street === 0) {
            if (sit.preflop.raises === 1 && !s.raised && !sit.preflop.limped) { st.tbOpp++; if (a.type === "raise") st.tb++; }
            if (sit.preflop.raises === 2 && s.raised) { st.f3bOpp++; if (a.type === "fold") st.f3b++; }
            if (a.type === "call" || a.type === "raise") vpip = true;
            if (a.type === "raise") pfr = true;
          }
          if (street === 1 && sit.postflop.aggressor && streetRaises === 0) { st.cbOpp++; if (a.type === "raise") st.cb++; }
          if (street === 1 && sit.postflop.betIsCbet && !s.checkedFaced) { s.checkedFaced = true; st.fcbOpp++; if (a.type === "fold") st.fcb++; }
        }
        if (a.type === "fold") s.folded = true;
        else if (a.type === "check") s.checked = true;
        else if (a.type === "call") { post(s, toCall); if (!s.stack) s.allin = true; }
        else {
          const to = Math.max(legal.minTo, Math.min(a.to, maxTo));
          if (to - currentBet >= minRaise) minRaise = to - currentBet;
          if (street === 0 && streetRaises === 1) { openerPos = s.pos; openTo = to; }
          if (streetRaises === 0) firstBettor = s.i;
          streetRaises++; currentBet = Math.max(currentBet, to); post(s, to - s.bet); if (!s.stack) s.allin = true;
          s.raised = true; lastAgg = s.i;
          for (const o of canAct()) if (o !== s) pending.add(o.i);
        }
      }
    }
    if (live().length === 1) break;
  }
  if (vpip) st.vpip++;
  if (pfr) st.pfr++;
  if (sawFlop && !me.folded && live().length > 1) st.sd++;
}

function measure(type, hands, seed) {
  const rng = P.mulberry32(seed), st = newStats();
  let players = null;
  for (let h = 0; h < hands; h++) {
    // A fresh table of instances every 100 hands: the result is the type's population, not one draw.
    if (h % 100 === 0) players = [P.createPlayer(type, rng), ...Array.from({ length: 5 }, () => P.createPlayer("tag", rng))];
    playHand(players, h % 6, rng, st);
  }
  const pc = (a, b) => (b ? (100 * a) / b : NaN);
  return { VPIP: pc(st.vpip, st.hands), PFR: pc(st.pfr, st.hands), "3bet": pc(st.tb, st.tbOpp), F3B: pc(st.f3b, st.f3bOpp),
    cbet: pc(st.cb, st.cbOpp), FCB: pc(st.fcb, st.fcbOpp), WTSD: pc(st.sd, st.flops) };
}

// Target ranges from the note §2.1 / §2.3 (pro postflop "GTO 근접" → the §7.2 pro means ± a GTO-like band, [가정]).
const TARGETS = {
  nit: { VPIP: [8, 16], PFR: [6, 13], "3bet": [2, 5], cbet: [55, 70], FCB: [50, 60], WTSD: [18, 24] },
  weak: { VPIP: [15, 21], PFR: [8, 13], "3bet": [2, 4], cbet: [50, 65], FCB: [50, 60], WTSD: [21, 25] },
  tag: { VPIP: [20, 25], PFR: [17, 21], "3bet": [5, 9], cbet: [55, 75], FCB: [40, 56], WTSD: [25, 29] },
  lag: { VPIP: [26, 35], PFR: [22, 28], "3bet": [9, 14], cbet: [60, 80], FCB: [35, 45], WTSD: [26, 31] },
  fish: { VPIP: [30, 45], PFR: [5, 12], "3bet": [1, 4], cbet: [40, 60], FCB: [30, 45], WTSD: [30, 36] },
  station: { VPIP: [40, 65], PFR: [2, 8], "3bet": [0.5, 3], cbet: [30, 50], FCB: [15, 35], WTSD: [35, 45] },
  maniac: { VPIP: [45, 80], PFR: [30, 60], "3bet": [15, 30], cbet: [80, 95], FCB: [25, 40], WTSD: [30, 40] },
  pro: { VPIP: [22, 28], PFR: [18, 24], "3bet": [7, 11], cbet: [50, 70], FCB: [38, 52], WTSD: [26, 30] },
};
// Tolerance in %p beyond the cited range: preflop stats are tight by construction, postflop ones
// emerge from a simplified strength model and a TAG-only table.
const TOL = { VPIP: 3, PFR: 3, "3bet": 2, cbet: 6, FCB: 6, WTSD: 5 };
// maniac WTSD 30–40 is [가정] in the note, and the neutral table never calls a maniac down lighter
// (real opponents do), so his pots end before showdown more often here: ±10.
const TOL_OVERRIDE = { maniac: { WTSD: 10 } };
const HANDS = 20000;

const RESULTS = {};
for (const type of P.TYPES) {
  test(`calibration: ${type} lands in the cited ranges`, () => {
    const m = measure(type, HANDS, 1000 + P.TYPES.indexOf(type));
    RESULTS[type] = m;
    const bad = [];
    for (const [k, [lo, hi]] of Object.entries(TARGETS[type])) {
      const tol = TOL_OVERRIDE[type]?.[k] ?? TOL[k];
      if (!(m[k] >= lo - tol && m[k] <= hi + tol)) bad.push(`${k} ${m[k].toFixed(1)} not in [${lo}, ${hi}] ± ${tol}`);
    }
    assert.deepEqual(bad, [], `${type}: ${bad.join("; ")} — tune MEANS in web/app/personas.js (cite the note)`);
  });
}
test("calibration table", () => {
  const keys = ["VPIP", "PFR", "3bet", "F3B", "cbet", "FCB", "WTSD"];
  console.log(["type", ...keys].join("\t"));
  for (const t of P.TYPES) if (RESULTS[t]) console.log([t, ...keys.map(k => RESULTS[t][k].toFixed(1))].join("\t"));
});

// ---------------------------------------------------------------- instance spread
test("instances of one type differ, inside the configured bounds", () => {
  const rng = P.mulberry32(7);
  for (const type of P.TYPES) {
    const pls = Array.from({ length: 300 }, () => P.createPlayer(type, rng));
    for (const key of ["threebet", "f3b", "coldcall", "bbDefend", "cbetF", "foldCbF", "foldR", "riverBluff"]) {
      const mu = P.MEANS[key][type] / 100, k = P.kappaOf(type, key), [lo, hi] = P.bounds(mu, k);
      const xs = pls.map(p => p.p[key]);
      const m = xs.reduce((a, b) => a + b) / xs.length, sd = Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length);
      assert.ok(sd > 0, `${type}.${key}: every instance drew the same value`);
      assert.ok(xs.every(x => x >= lo - 1e-12 && x <= hi + 1e-12), `${type}.${key}: a draw left [${lo}, ${hi}]`);
      const want = Math.sqrt(mu * (1 - mu) / (k + 1));
      assert.ok(sd > 0.5 * want && sd < 1.3 * want, `${type}.${key}: spread ${sd.toFixed(4)} far from Beta SD ${want.toFixed(4)}`);
      assert.ok(Math.abs(m - mu) < 3 * want / Math.sqrt(xs.length) + 0.01, `${type}.${key}: mean ${m.toFixed(3)} drifted from ${mu}`);
    }
    const rf = pls.map(p => p.p.rfiCO);
    assert.ok(new Set(rf).size > 250, `${type}: RFI does not vary per instance`);
    // Tells are traits, not constants: within a type both values of a Bernoulli trait show up when its prior is mid-range.
    if (P.TELLS.uniformTiming[type] > 0.1 && P.TELLS.uniformTiming[type] < 0.9) {
      const on = pls.filter(p => p.tells.uniformTiming).length;
      assert.ok(on > 0 && on < pls.length, `${type}: uniformTiming is the same for all instances`);
    }
    const ss = pls.map(p => p.tells.sizeStrength);
    assert.ok(Math.max(...ss) - Math.min(...ss) > 0.1 || type === "pro", `${type}: size tell strength does not vary`);
  }
});

test("two nits at one table are different players", () => {
  const rng = P.mulberry32(11);
  const a = P.createPlayer("nit", rng), b = P.createPlayer("nit", rng);
  assert.notDeepEqual(a.p, b.p);
  assert.notDeepEqual([a.tells, a.pace], [b.tells, b.pace]);
});

// ---------------------------------------------------------------- tells
function corr(xs, ys) {
  const n = xs.length, mx = xs.reduce((a, b) => a + b) / n, my = ys.reduce((a, b) => a + b) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; syy += (ys[i] - my) ** 2; }
  return sxy / Math.sqrt(sxx * syy);
}
function riverBets(pl, rng, nSit = 6000) {
  const qs = [], sizes = [], ms = [];
  for (let i = 0; i < nSit; i++) {
    const q = rng(), pot = 2000;
    const sit = { street: 3, pos: "BTN", bb: BB, pot, toCall: 0, currentBet: 0, myBet: 0, legal: { canCheck: true, canRaise: true, minTo: BB, maxTo: STACK },
      nOpp: 1, ip: true, preflop: {}, postflop: { aggressor: true, prevAggLive: false, prevBet: true, betIsCbet: false, checkedThisStreet: false, streetRaises: 0 },
      hand: { pct: 50, eq: P.qToEq(3, q) } };
    const a = P.decide(pl, sit, rng);
    ms.push([a.q, a.ms]);
    if (a.type === "raise") { qs.push(a.q); sizes.push(Math.log(a.to / pot)); }
  }
  return { qs, sizes, ms };
}
test("size tell: a tell instance sizes by strength, a no-tell instance does not", () => {
  const rng = P.mulberry32(21);
  const tell = P.createPlayer("fish", rng, { tells: { sizeStrength: 0.8, sizeDir: 1 } });
  const rev = P.createPlayer("fish", rng, { tells: { sizeStrength: 0.8, sizeDir: -1 } });
  const none = P.createPlayer("fish", rng, { tells: { sizeStrength: 0 } });
  const t = riverBets(tell, rng), r = riverBets(rev, rng), z = riverBets(none, rng);
  assert.ok(t.qs.length > 500 && z.qs.length > 500, "too few river bets to measure");
  const ct = corr(t.qs, t.sizes), cr = corr(r.qs, r.sizes), cz = corr(z.qs, z.sizes);
  console.log(`size-strength corr: tell ${ct.toFixed(2)}, reversed ${cr.toFixed(2)}, none ${cz.toFixed(2)}`);
  assert.ok(ct > 0.3, `tell instance corr ${ct.toFixed(2)} <= 0.3`);
  assert.ok(cr < -0.3, `reversed instance corr ${cr.toFixed(2)} >= -0.3`);
  assert.ok(Math.abs(cz) < 0.08, `no-tell instance corr ${cz.toFixed(2)} is not ~0`);
});

test("timing tell: think delay carries strength for a tell instance only, always bounded", () => {
  const rng = P.mulberry32(31);
  const slow = P.createPlayer("fish", rng, { tells: { uniformTiming: false, timingStrength: 0.8, timingDir: 1, fastCallMedium: 0, tankStrong: 0 } });
  const snap = P.createPlayer("fish", rng, { tells: { uniformTiming: false, timingStrength: 0.8, timingDir: -1, fastCallMedium: 0, tankStrong: 0 } });
  const flat = P.createPlayer("tag", rng, { tells: { uniformTiming: true, timingStrength: 0, fastCallMedium: 0, tankStrong: 0 } });
  const c = pl => { const { ms } = riverBets(pl, rng, 4000); assert.ok(ms.every(([, m]) => m >= P.MS_MIN && m <= P.MS_MAX), "think delay left [MS_MIN, MS_MAX]"); return corr(ms.map(x => x[0]), ms.map(x => x[1])); };
  const cs = c(slow), cn = c(snap), cf = c(flat);
  console.log(`strength-delay corr: slow=strong ${cs.toFixed(2)}, reversed ${cn.toFixed(2)}, uniform ${cf.toFixed(2)}`);
  assert.ok(cs > 0.3 && cn < -0.3 && Math.abs(cf) < 0.08);
});

test("river raise = nuts only", () => {
  const rng = P.mulberry32(41);
  const pl = P.createPlayer("station", rng, { tells: { riverNutsOnly: true, actsWeak: false } });
  for (let i = 0; i < 3000; i++) {
    const q = rng();
    const sit = { street: 3, pos: "BB", bb: BB, pot: 3000, toCall: 1000, currentBet: 1000, myBet: 0, legal: { canCheck: false, canRaise: true, minTo: 2000, maxTo: STACK },
      nOpp: 1, ip: false, preflop: {}, postflop: { aggressor: false, prevAggLive: true, prevBet: true, betIsCbet: true, checkedThisStreet: true, streetRaises: 1 },
      hand: { pct: 50, eq: P.qToEq(3, q) } };
    const a = P.decide(pl, sit, rng);
    if (a.type === "raise") assert.ok(a.q >= 0.97, `raised the river with q ${a.q.toFixed(2)}`);
  }
});

test("unknown type fails with the fix", () => {
  assert.throws(() => P.createPlayer("shark", P.mulberry32(1)), /use one of nit, weak/);
});
