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
  assert.equal(V.schema_version, 2);
  const c = V.constants;
  assert.deepEqual(c.TIER_K, T.TIER_K, "TIER_K differs: update tpgto.js to stalker/e3/tp_key.py");
  assert.deepEqual(c.TIER_DEPTH, T.TIER_DEPTH);
  assert.equal(c.NUT_BASE, T.NUT_BASE);
  assert.equal(c.NUT_TOP, T.NUT_TOP);
  assert.equal(c.NUT_K, T.NUT_K, "board.nut step count differs: update NUT_K in tpgto.js");
  T.checkNutK(c.NUT_K);
  assert.throws(() => T.checkNutK(17), /board.nut has 17 steps/);
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

test("menus (real, real + cap 3, tp6): legal, sizes, public keys, translation split and seeded reading", () => {
  const fails = { legal: 0, amounts: 0, public: 0, split: 0, read: 0, end: 0 };
  const first = [];
  let total = 0, bets = 0, splits = 0;
  const DEPTHS = ["basic", "full", "pro"];
  for (const h of V.menus) {
    let s = T.dealFromPermutation(h.perm, h.n, { menu: h.menu, raiseCap: h.raise_cap });
    for (const d of h.decisions) {
      total++;
      const acts = T.legal(s);
      const amounts = Object.fromEntries(acts.filter((a) => !["f", "c", "k"].includes(a)).map((a) => [a, T.amountTo(s, a)]));
      const ok = {
        legal: acts.join() === d.legal.join(),
        amounts: JSON.stringify(amounts) === JSON.stringify(d.amounts),
        public: DEPTHS.every((depth, i) => T.publicKey(s, s.toAct, depth) === d.public[i]),
      };
      if (d.bet !== undefined) {
        bets++;
        const sp = T.splitBet(s, d.bet);
        if (sp.length === 2) splits++;
        ok.split = JSON.stringify(sp.map((x) => [x.a, x.p])) === JSON.stringify(d.split);
        ok.read = T.sampleBet(s, d.bet, new T.NumpyRng(d.entropy)) === d.read
          && T.translateBet(s, d.bet, new T.NumpyRng(d.entropy)).action === d.read;
      }
      for (const f in ok) if (!ok[f]) { fails[f]++; if (first.length < 5) first.push({ f, menu: h.menu, cap: h.raise_cap, n: h.n, hist: s.history.join(" "), want: d[f], got: f === "legal" ? acts : f === "amounts" ? amounts : f === "split" ? T.splitBet(s, d.bet) : undefined }); }
      s = d.bet !== undefined ? T.applyBet(s, d.bet, d.read) : T.apply(s, d.a);
    }
    if (!s.done || s.history.join() !== h.history.join() || s.board.join() !== h.board.join() || T.payoff(s).join() !== h.payoff.join()) fails.end++;
  }
  console.log(`tpgto menus: ${total} decisions in ${V.menus.length} hands, ${bets} arbitrary bets (${splits} between two sizes); failures ${JSON.stringify(fails)}`);
  assert.ok(total >= 300 && bets >= 100 && splits >= 30, "too few menu vectors; regenerate with more hands");
  assert.deepEqual(fails, { legal: 0, amounts: 0, public: 0, split: 0, read: 0, end: 0 }, `first mismatches: ${JSON.stringify(first)}`);
});

test("real menu: the owner's size lists per spot, preflop cap, no postflop cap", () => {
  const real = (n = 6, raiseCap = null) => T.newHand({ n, holes: holes6.slice(0, n), menu: "real", raiseCap });
  const play = (s, ...acts) => acts.reduce((x, a) => T.apply(x, a), s);
  const sz = (s) => Object.fromEntries(T.sizeMenu(s).map(({ a, to }) => [a, to]));
  assert.deepEqual(sz(real()), { r2: 200, r22: 220, r: 250, r3: 300, r35: 350, r4: 400, r5: 500, r6: 600, r8: 800, r10: 1000, a: T.STACK });
  assert.deepEqual(Object.values(sz(play(real(), "c"))).slice(0, 10), [300, 320, 350, 400, 450, 500, 600, 700, 900, 1100]);
  assert.deepEqual(sz(play(real(), "r")), { r25: 625, r: 750, r35: 875, r4: 1000, r5: 1250, a: T.STACK });
  assert.deepEqual(sz(play(real(), "r", "r")), { r2: 1500, r22: 1650, r25: 1875, r: 2250, a: T.STACK });
  for (const cap of [null, 3, 4]) assert.deepEqual(T.legal(play(real(6, cap), "r", "r25", "r25")), ["f", "c", "a"]);   // 5-bet: all in
  assert.deepEqual(T.legal(play(real(2), "r3", "c")), ["k", "b20", "b33", "b50", "b75", "b100", "b150", "b200", "b300", "a"]);
  const war = play(real(2), "r", "c", "b20", "r25", "r25", "r25");
  assert.ok(T.legal(war).includes("r25"));                                      // no postflop cap
  assert.ok(T.sizeMenu(war).every(({ a, to }) => a === "a" || to < T.ALLIN_MERGE * T.STACK));
  assert.throws(() => T.newHand({ n: 6, holes: holes6, menu: "v9" }), /menu "v9"/);
});

test("menuOf: policy metadata picks the rules, v1 with cap 3 by default", () => {
  assert.deepEqual(T.menuOf({}), { menu: "v1", raiseCap: 3 });
  assert.deepEqual(T.menuOf(null), { menu: "v1", raiseCap: 3 });
  assert.deepEqual(T.menuOf({ menu: "real", raise_cap: null }), { menu: "real", raiseCap: null });
  assert.throws(() => T.menuOf({ menu: "zz" }), /policy menu "zz"/);
});

test("a v1 policy reads a real-size bet on its own v1 labels; sizeMenu still lists the real sizes", () => {
  const s = T.newHand({ n: 6, holes: holes6 });                                  // v1 hand (served policies)
  assert.deepEqual(T.sizeMenu(s).map((m) => m.a), ["r", "a"]);
  assert.deepEqual(T.sizeMenu(s, "real", null).map((m) => m.to), [200, 220, 250, 300, 350, 400, 500, 600, 800, 1000, T.STACK]);
  const sp = T.splitBet(s, 400);                                                 // a real 4BB open
  assert.deepEqual(sp.map((x) => x.a), ["r", "a"]);
  const f = ((9900 / 250 - 300 / 250) * (1 + 150 / 250)) / ((9900 / 250 - 150 / 250) * (1 + 300 / 250));
  assert.equal(sp[0].p, f);
  const reads = new Set();
  for (let seed = 0; seed < 40; seed++) reads.add(T.applyBet(s, 400, new T.NumpyRng([seed])).history[0]);
  assert.deepEqual([...reads].sort(), ["0:a", "0:r"]);                           // both readings occur
  assert.equal(T.applyBet(s, 400, new T.NumpyRng([7])).history[0], T.applyBet(s, 400, new T.NumpyRng([7])).history[0]);
  assert.throws(() => T.applyBet(s, 400), /seeded NumpyRng/);
  assert.throws(() => T.applyBet(s, 400, "c"), /not a reading/);
  // Grading: the split weighs each label's score.
  assert.equal(T.splitScore(sp, (a) => (a === "r" ? 1 : 0)), f);
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
  const rng = new T.NumpyRng([386]);
  assert.throws(() => T.applyBet(s, 199, rng), /min raise/);
  assert.throws(() => T.applyBet(s, T.STACK + 1, rng), /all in/);
  const mr = T.translateBet(s, 200);
  assert.equal(mr.action, "r");                       // below the 2.5BB open: the smallest menu size
  assert.deepEqual(mr.split, [{ a: "r", p: 1 }]);
  const s1 = T.applyBet(s, 200, rng);
  assert.equal(s1.bet[0], 200); assert.equal(T.pot(s1), 350); assert.ok(chipsOk(s1));
  assert.deepEqual(s1.history, ["0:r"]); assert.equal(s1.log[0].real, true);
  const five = T.translateBet(s, 500);              // between r (250) and all in: PHM likelier on r
  assert.equal(five.action, "r"); assert.ok(five.prob >= 0.5 && five.prob <= 1);
  assert.equal(five.split[0].p + five.split[1].p, 1);
  const s2 = T.applyBet(s, 500, "r");
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
  s = T.applyBet(s, to, tr.action);
  assert.equal(T.pot(s), 500); assert.ok(chipsOk(s));
  const d1 = T.decisionKey(s, r1, "pro");            // BB faces the real 300 into 200
  assert.equal(d1.public.split("|")[7], String(T.potOddsStep(s, 5)));
  assert.equal(T.potOddsStep(s, 5), 3);              // 300 / 800 = 37.5%
  assert.match(d1.key, /\|e\d+\|n\d+$/);              // heads-up postflop pro key carries board.nut
  // A raise to an arbitrary size, then calls to the end.
  const r = T.betRange(s);
  assert.equal(r.min, 600);
  s = T.applyBet(s, 1234, new T.NumpyRng([1234]));
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

// #412: every xN size is a raise-to (street total); a short all in does not reopen the betting.
test("menu sizes are raise-to totals (TP.md section 6)", () => {
  const d = Array.from({ length: 52 }, (_, i) => i);
  let s = T.dealFromPermutation(d, 6, { menu: "real", raiseCap: null });
  assert.equal(T.amountTo(s, "r3"), 300);                   // open to 3BB
  s = T.apply(s, "r");                                      // open to 250
  assert.equal(T.amountTo(s, "r"), 750);                    // 3-bet to 3 x 250, not 250 + 750
  s = T.apply(s, "r");
  assert.equal(T.amountTo(s, "r2"), 1500);                  // 4-bet to 2 x 750
  let h = T.dealFromPermutation(d, 2, { menu: "real", raiseCap: null });
  h = T.apply(T.apply(T.apply(h, "c"), "c"), "b20");        // flop, bet 100 into 200
  assert.equal(T.amountTo(h, "r"), 300);                    // raise to 3 x 100, not 100 + 300
});

test("a short all in does not reopen the betting (G._reopens)", () => {
  const d = Array.from({ length: 52 }, (_, i) => i);
  let s = T.dealFromPermutation(d, 3);                      // BTN 0, SB 1, BB 2
  s = { ...s, stack: [s.stack[0], 450 - s.bet[1], s.stack[2]] };
  s = T.applyBet(s, 300, "r");                              // BTN opens to 300 (raise 200)
  s = T.apply(s, "a");                                      // SB all in to 450: +150 < 200
  assert.deepEqual(T.betRange(s), { min: 650, max: 10000 }); // BB has not acted: min raise by the full 200
  s = T.apply(s, "c");
  assert.equal(s.toAct, 0);
  assert.deepEqual(T.legal(s), ["f", "c"]);                 // BTN already acted: call or fold only
  assert.equal(T.betRange(s), null);
});
