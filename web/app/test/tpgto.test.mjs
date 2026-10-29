// node --test web/app/test/   — the browser port must match the Python vectors exactly (#335).
// Regenerate the vectors with `python -m stalker.tools.web_vectors` after changing the Python side.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as T from "../tpgto.js";

const here = new URL(".", import.meta.url);
const V = JSON.parse(readFileSync(new URL("vectors.json", here), "utf8"));
T.setEquityTable(JSON.parse(readFileSync(new URL("../assets/hu_equity.json", here), "utf8")));
const DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz";

function encode(steps) {
  let s = "", nut = null;
  for (const v of steps) {
    if (v < 0) { s += "-"; continue; }
    if (v >= T.NUT_BASE) nut = Math.floor(v / T.NUT_BASE) - 1;
    s += DIGITS[v % T.NUT_BASE];
  }
  return [s, nut];
}

function seqSum(a) { let s = 0.0; for (const v of a) s += v; return s; }

test("schema and constants match the Python side", () => {
  assert.equal(V.schema, "stalker.web.tpgto.vectors");
  assert.equal(V.schema_version, 1);
  const c = V.constants;
  assert.deepEqual(c.TIER_K, T.TIER_K, "TIER_K differs: update tpgto.js to stalker/e3/tp_key.py");
  assert.deepEqual(c.TIER_DEPTH, T.TIER_DEPTH);
  assert.equal(c.NUT_BASE, T.NUT_BASE);
  assert.equal(c.NUT_TOP, T.NUT_TOP);
  assert.equal(c.NUT_K, T.NUT_K, "board.nut step count differs: update NUT_K in tpgto.js");
  assert.equal(c.EQ_RUNOUTS, T.EQ_RUNOUTS);
});

test("numpy default_rng(...).choice(replace=False) runouts", () => {
  let bad = 0;
  for (const { board, runouts } of V.rng) {
    const r = new T.NumpyRng([20261028, ...board]);
    const live = [...Array(52).keys()].filter((c) => !board.includes(c));
    for (const want of runouts) if (r.choiceNoReplace(live, want.length).join() !== want.join()) bad++;
  }
  assert.equal(bad, 0, `${bad} runouts differ from numpy`);
});

test("every decision: legal, public key, step array, key, range sums; plus final board and payoff", () => {
  const fails = { legal: 0, public: 0, steps: 0, key: 0, sums: 0, end: 0 };
  const times = [];
  let total = 0;
  const first = [];
  for (const h of V.hands) {
    const policy = V.policies[`${h.n}/${h.tier}`];
    let s = T.dealFromPermutation(h.perm, h.n);
    let ranges = T.initialRanges(h.n);
    for (const d of h.decisions) {
      total++;
      const t0 = performance.now();
      const dk = T.decisionKey(s, ranges, h.tier);
      const next = T.updateRanges(policy, dk, ranges, d.a);
      times.push(performance.now() - t0);
      const [enc, nut] = encode(dk.steps);
      const ok = {
        legal: dk.acts.join() === d.legal.join(), public: dk.public === d.public,
        steps: enc === d.steps && nut === d.nut, key: dk.key === d.key,
        sums: next.every((r, i) => seqSum(r) === d.sums[i]),
      };
      for (const f in ok) if (!ok[f]) { fails[f]++; if (first.length < 5) first.push({ f, n: h.n, tier: h.tier, hist: s.history.join(" "), want: d[f === "legal" ? "legal" : f], got: f === "key" ? dk.key : f === "public" ? dk.public : undefined }); }
      ranges = next;
      s = T.apply(s, d.a);
    }
    if (!s.done || s.board.join() !== h.board.join() || T.payoff(s).join() !== h.payoff.join()) fails.end++;
  }
  times.sort((a, b) => a - b);
  const q = (p) => times[Math.min(times.length - 1, Math.floor(p * times.length))].toFixed(2);
  const matched = total - Math.max(...Object.values(fails).slice(0, 5));
  console.log(`tpgto vectors: ${total} decisions in ${V.hands.length} hands; key match ${((100 * (total - fails.key)) / total).toFixed(1)}%; ` +
    `failures ${JSON.stringify(fails)}; decision (key + range update) ms P50 ${q(0.5)} P95 ${q(0.95)} max ${times[times.length - 1].toFixed(2)}`);
  assert.ok(total >= 200, `only ${total} decisions; regenerate with more hands`);
  assert.ok(matched >= 0);
  assert.deepEqual(fails, { legal: 0, public: 0, steps: 0, key: 0, sums: 0, end: 0 }, `first mismatches: ${JSON.stringify(first)}`);
});

test("actionProbs returns the table row for the actor's hole, uniform when missing", () => {
  const h = V.hands.find((x) => x.tier === "mid");
  const policy = V.policies[`${h.n}/${h.tier}`];
  const s = T.dealFromPermutation(h.perm, h.n);
  const r = T.actionProbs(policy, s, T.initialRanges(h.n), h.tier);
  assert.equal(r.key, h.decisions[0].key);
  const row = policy[r.key];
  assert.deepEqual(r.probs, row ? row : r.acts.map(() => 1 / r.acts.length));
  const u = T.actionProbs({}, s, T.initialRanges(h.n), h.tier);
  assert.ok(u.probs.every((p) => p === 1 / u.acts.length) && !u.fromTable);
});

test("newHand with a fixed board deals that board", () => {
  const s0 = T.newHand({ n: 6, holes: [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9], [10, 11]], board: [51, 50, 49, 48, 47] });
  let s = s0;
  while (!s.done) s = T.apply(s, T.legal(s).includes("c") ? "c" : "k");
  assert.deepEqual(s.board, [51, 50, 49, 48, 47]);
  assert.equal(T.payoff(s).reduce((a, b) => a + b, 0), 0);
  assert.throws(() => T.apply(s0, "k"), /illegal action/);
});

// ---------------------------------------------------------------- real no-limit sizes (off menu)
const holes6 = [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9], [10, 11]];
const chipsOk = (s) => s.stack.every((x, i) => x + s.total[i] === T.STACK && x >= 0);

test("off-menu: min-raise and 5x open preflop", () => {
  const s = T.newHand({ n: 6, holes: holes6 });
  assert.deepEqual(T.betRange(s), { min: 200, max: T.STACK });
  assert.throws(() => T.applyBet(s, 199), /min raise/);
  assert.throws(() => T.applyBet(s, T.STACK + 1), /all in/);
  const mr = T.translateBet(s, 200);
  assert.equal(mr.action, "r");                       // below the 2.5BB open: the smallest menu size
  const s1 = T.applyBet(s, 200);
  assert.equal(s1.bet[0], 200); assert.equal(T.pot(s1), 350); assert.ok(chipsOk(s1));
  assert.deepEqual(s1.history, ["0:r"]); assert.equal(s1.log[0].real, true);
  const five = T.translateBet(s, 500);              // between r (250) and all in: PHM picks r
  assert.equal(five.action, "r"); assert.ok(five.prob >= 0.5 && five.prob <= 1);
  const s2 = T.applyBet(s, 500);
  assert.equal(T.toCall(s2, 1), 500); assert.ok(chipsOk(s2));
  // The next min raise follows the real raise size (500 - 100 = 400): 900.
  assert.equal(T.betRange(s2).min, 900);
  const d = T.decisionKey(s2, T.initialRanges(6), "mid");
  assert.match(d.key, /^1\|0\|3\|1\|0\|\d\|0\|fcra\|e\d+$/);
  assert.equal(d.public.split("|")[5], String(T.potOddsStep(s2, 1)));
  // A near-all-in size maps to the all in.
  assert.equal(T.translateBet(s, 9000).action, "a");
  assert.equal(T.translateBet(s, T.STACK).action, "a");
});

test("off-menu: 150% pot bet postflop, keys from real chips, hand settles", () => {
  let s = T.newHand({ n: 6, holes: holes6, board: [51, 46, 41, 36, 31] });
  for (const a of ["f", "f", "f", "f", "c", "c"]) s = T.apply(s, a);   // limped pot of 200, heads-up SB/BB
  assert.equal(s.street, 1); assert.equal(T.pot(s), 200); assert.equal(s.toAct, 4);
  const to = 300;                                    // 150% pot: above b75 (150), below all in
  const tr = T.translateBet(s, to);
  assert.ok(["b75", "a"].includes(tr.action));
  assert.equal(tr.lower, "b75"); assert.equal(tr.upper, "a");
  const ranges = T.initialRanges(6);
  const d0 = T.decisionKey(s, ranges, "pro");
  const r1 = T.updateRanges({}, d0, ranges, tr.action);
  s = T.applyBet(s, to);
  assert.equal(T.pot(s), 500); assert.ok(chipsOk(s));
  const d1 = T.decisionKey(s, r1, "pro");            // BB faces the real 300 into 200
  assert.equal(d1.public.split("|")[7], String(T.potOddsStep(s, 5)));
  assert.equal(T.potOddsStep(s, 5), 3);              // 300 / 800 = 37.5%
  assert.match(d1.key, /\|e\d+\|n\d+$/);              // heads-up postflop pro key carries board.nut
  // A raise to an arbitrary size, then calls to the end.
  const r = T.betRange(s);
  assert.equal(r.min, 600);
  s = T.applyBet(s, 1234);
  assert.ok(chipsOk(s));
  while (!s.done) s = T.apply(s, T.legal(s).includes("c") ? "c" : "k");
  assert.equal(T.payoff(s).reduce((x, y) => x + y, 0), 0);
  assert.equal(s.total[4], s.total[5]);
});

test("off-menu: no bet possible when calling puts the actor all in", () => {
  let s = T.newHand({ n: 6, holes: holes6 });
  s = T.apply(s, "a");
  for (const a of ["f", "f", "f", "f"]) s = T.apply(s, a);
  assert.equal(T.betRange(s), null);
  assert.throws(() => T.translateBet(s, 500), /no bet or raise/);
});
