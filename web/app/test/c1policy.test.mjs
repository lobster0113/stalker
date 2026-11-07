// #604: the 2–5인 mid policies are c1 tables; the page looks them up with c1 keys when the index says so.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as T from "../tpgto.js";

const here = new URL(".", import.meta.url);
const read = (p) => JSON.parse(readFileSync(new URL(p, here), "utf8"));
T.setEquityTable(read("../assets/hu_equity.json"));
const INDEX = read("../policy/index.json");
const HOLES = [["As", "Ah"], ["Kd", "Qd"], ["7c", "2h"], ["Ts", "9s"], ["5d", "5c"], ["Jh", "4c"]].map((h) => h.map(T.card));

const firstDecision = (n, meta) => T.newHand({ n, holes: HOLES.slice(0, n), ...T.menuOf(meta) });

test("3-handed mid: the first preflop decision's c1 key is a row of mid-3.json (index key_variant c1)", () => {
  const meta = INDEX.tiers.mid.by_players["3"];
  assert.equal(meta.key_variant, "c1");
  const pol = read("../policy/mid-3.json").policy;
  const s = firstDecision(3, meta);
  const r = T.actionProbs(pol, s, T.initialRanges(3), "mid", meta.key_variant);
  assert.ok(r.key.startsWith("BTN|n3|0|"), r.key);
  assert.equal(r.fromTable, "exact", `c1 key ${r.key} is not in mid-3.json`);
  assert.equal(r.probs.length, r.acts.length);
  const legacy = T.actionProbs(pol, s, T.initialRanges(3), "mid");
  assert.equal(legacy.fromTable, false, "the legacy key must not hit a c1 table (that was the silent miss)");
});

test("every shipped 2–5인 c1 policy answers its first preflop decision from the table", () => {
  for (const n of [2, 4, 5]) {
    const meta = INDEX.tiers.mid.by_players[String(n)];
    const pol = read(`../policy/${meta.file}`).policy;
    const r = T.actionProbs(pol, firstDecision(n, meta), T.initialRanges(n), "mid", meta.key_variant);
    assert.equal(r.fromTable, "exact", `${n}-handed: c1 key ${r.key} is not in ${meta.file}`);
  }
});

test("a policy without key_variant (6-max mid) keeps the legacy key", () => {
  const meta = INDEX.tiers.mid;
  assert.equal(meta.key_variant, undefined);
  const s = firstDecision(6, meta), ranges = T.initialRanges(6);
  const d = T.decisionKey(s, ranges, "mid", meta.key_variant);
  assert.equal(d.public, T.publicKey(s, s.toAct, "full"));
  assert.equal(d.key, T.decisionKey(s, ranges, "mid").key);
  assert.equal(d.variant, "");
});

// mid-3.json rows are integers over q (the page divides on load, web/demo/index.html tpgLoad).
const decoded = (doc) => { const q = doc.q || 255, pol = new Map(); for (const k in doc.policy) pol.set(k, Float64Array.from(doc.policy[k], (v) => v / q)); return { pol, q }; };

test("3-handed mid c1 postflop (#608): seeded hands reach the flop and their c1+b1 keys read mid-3.json rows", () => {
  const meta = INDEX.tiers.mid.by_players["3"];
  const doc = read("../policy/mid-3.json"), { pol, q } = decoded(doc);
  // The table keeps postflop rows seen >= min_visits times, so most limped or multiway flops miss. A single
  // raised pot (BTN opens its likeliest raise, SB folds, BB calls, then checks down) hits within a few deals.
  let post = 0, hits = 0;
  for (let h = 0; h < 30 && hits === 0; h++) {
    const perm = Array.from({ length: 52 }, (_, i) => (i * 17 + h * 5) % 52);
    let s = T.newHand({ n: 3, holes: [perm.slice(0, 2), perm.slice(2, 4), perm.slice(4, 6)], board: perm.slice(6, 11), ...T.menuOf(meta) });
    let ranges = T.initialRanges(3);
    while (!s.done) {
      const r = T.actionProbs(pol, s, ranges, "mid", "c1");
      let a;
      if (s.street === 0) {
        if (s.toAct === 0) a = r.acts.filter((x) => x[0] === "r").reduce((b, x) => (r.probs[r.acts.indexOf(x)] > r.probs[r.acts.indexOf(b)] ? x : b));
        else a = s.toAct === 1 ? "f" : r.acts.includes("c") ? "c" : "k";
      } else {
        post++;
        if (!r.key.startsWith("call|")) assert.match(r.key, /\|e\d+\|o[-0-3]v[-0-2]k[-0-2]$/, r.key);
        if (r.fromTable === "exact") {
          hits++;
          const row = doc.policy[r.key];
          assert.equal(r.probs.length, row.length);
          r.probs.forEach((p, i) => assert.ok(Math.abs(p - row[i] / q) < 1e-9, `${r.key}: ${p} vs ${row[i]}/${q}`));
        }
        a = r.acts.includes("k") ? "k" : "c";
      }
      ranges = T.updateRanges(pol, r, ranges, a);
      s = T.apply(s, a);
    }
  }
  console.log(`c1 mid-3 postflop: ${post} decisions, ${hits} from the table`);
  assert.ok(post > 0, "no postflop decision reached");
  assert.ok(hits > 0, `no c1 postflop key of ${post} was a row of mid-3.json`);
});

test("an unknown key variant is refused", () => {
  const meta = INDEX.tiers.mid.by_players["3"];
  assert.throws(() => T.decisionKey(firstDecision(3, meta), T.initialRanges(3), "mid", "b1"), /key variant "b1"/);
});

test("c1 call-or-fold spot (#610): a policy holding the call| row answers it from the table", () => {
  // Per-seat-count exports used to drop the shared call| keys, so these spots always played uniform.
  const meta = INDEX.tiers.mid.by_players["3"];
  let s = firstDecision(3, meta), ranges = T.initialRanges(3);
  const empty = new Map();
  for (let i = 0; i < 4 && !s.done; i++) {
    const lg = T.legal(s);
    if (lg.join("") === "fc") break;
    const r = T.actionProbs(empty, s, ranges, "mid", "c1");
    const a = lg.includes("a") ? "a" : lg[lg.length - 1];   // shove (or the largest size) until someone faces it
    ranges = T.updateRanges(empty, r, ranges, a);
    s = T.apply(s, a);
  }
  assert.equal(T.legal(s).join(""), "fc", `no call-or-fold spot reached: legal ${T.legal(s).join(",")}`);
  const miss = T.actionProbs(empty, s, ranges, "mid", "c1");
  assert.ok(miss.key.startsWith("call|"), miss.key);
  assert.equal(miss.fromTable, false);
  const q = 255, row = [37, 218], pol = new Map([[miss.key, Float64Array.from(row, (v) => v / q)]]);
  const r = T.actionProbs(pol, s, ranges, "mid", "c1");
  assert.equal(r.fromTable, "exact", `${r.key} not read from the fixture row`);
  r.probs.forEach((p, i) => assert.ok(Math.abs(p - row[i] / q) < 1e-9, `${r.key}: ${p} vs ${row[i]}/${q}`));
  const obj = T.actionProbs({ [miss.key]: row.map((v) => v / q) }, s, ranges, "mid", "c1");
  assert.equal(obj.fromTable, "exact");
});

// ---------------------------------------------------------------- #623 miss backoff (ADR 0022)

// A c1 call-or-fold spot and a postflop decision of a seeded 3-handed hand (keys: "call|..." and "...|e<n>|o..").
function spots() {
  const meta = INDEX.tiers.mid.by_players["3"], empty = new Map();
  let s = firstDecision(3, meta), ranges = T.initialRanges(3);
  for (let i = 0; i < 4 && !s.done && T.legal(s).join("") !== "fc"; i++) {
    const lg = T.legal(s), r = T.actionProbs(empty, s, ranges, "mid", "c1"), a = lg.includes("a") ? "a" : lg[lg.length - 1];
    ranges = T.updateRanges(empty, r, ranges, a); s = T.apply(s, a);
  }
  const call = { s, ranges };
  s = firstDecision(3, meta); ranges = T.initialRanges(3);
  while (s.street === 0) {
    const r = T.actionProbs(empty, s, ranges, "mid", "c1"), a = r.acts.includes("c") ? "c" : "k";
    ranges = T.updateRanges(empty, r, ranges, a); s = T.apply(s, a);
  }
  return { call, post: { s, ranges } };
}

test("backoff (#623): exact, else the L1 mean row, else L2, else uniform — fromTable says which", () => {
  const { post } = spots(), { s, ranges } = post;
  const d = T.decisionKey(s, ranges, "mid", "c1"), m = d.acts.length, k1 = T.coarseKey(d.key, 1), k2 = T.coarseKey(d.key, 2);
  assert.notEqual(k1, d.key); assert.notEqual(k2, k1);
  // Keys sharing the L1 key (another b1 label / stack field), and one sharing only the L2 key (other facts).
  const sib1a = d.key.replace(/\|o[^|]*$/, "|o9v9k9"), sib1b = d.key.replace(/\|s[^|]*\|/, "|s1:1|").replace(/\|o[^|]*$/, "|o8v8k8");
  assert.equal(T.coarseKey(sib1a, 1), k1); assert.equal(T.coarseKey(sib1b, 1), k1);
  const sib2 = d.key.replace(/\|u\d*\|/, "|u99|");
  assert.notEqual(T.coarseKey(sib2, 1), k1); assert.equal(T.coarseKey(sib2, 2), k2);
  const row = (a) => Float64Array.from({ length: m }, (_, i) => (i === a ? 1 : 0));
  const exact = new Map([[d.key, row(0)], [sib1a, row(1)]]);
  const re = T.actionProbs(exact, s, ranges, "mid", "c1");
  assert.equal(re.fromTable, "exact");
  assert.deepEqual(re.probs, Array.from(row(0)));
  const l1 = new Map([[sib1a, row(0)], [sib1b, row(1)], [sib2, row(m - 1)]]);
  const r1 = T.actionProbs(l1, s, ranges, "mid", "c1");
  assert.equal(r1.fromTable, "L1");
  assert.deepEqual(r1.probs, Array.from({ length: m }, (_, i) => (row(0)[i] + row(1)[i]) / 2));
  const l2 = new Map([[sib2, row(m - 1)]]);
  const r2 = T.actionProbs(l2, s, ranges, "mid", "c1");
  assert.equal(r2.fromTable, "L2");
  assert.deepEqual(r2.probs, Array.from(row(m - 1)));
  // A row of another length under the same coarse key is never used.
  const other = new Map([[sib1a, Float64Array.from({ length: m + 1 }, () => 1 / (m + 1))]]);
  const u = T.actionProbs(other, s, ranges, "mid", "c1");
  assert.equal(u.fromTable, false);
  assert.ok(u.probs.every((p) => p === 1 / m));
  // Range updates read the same backoff rows: combos whose key coarsens to k2 take the L2 row (never action 0),
  // those at the equity steps next to it its L4 mean (the same row, #652), the others have no row and stay uniform.
  const after = T.updateRanges(l2, r2, ranges, 0);
  let same = 0;
  for (let i = 0; i < after[d.seat].length; i++) {
    if (d.steps[i] < 0) continue;
    const ki = T.key(d.public, d.steps[i]), from = T.backoffRow(l2, ki, m, "c1", T.TIER_K.mid - 1).from;
    if (T.coarseKey(ki, 2) === k2) { same++; assert.equal(from, "L2"); assert.equal(after[d.seat][i], 0, "range update ignored the L2 row"); }
    else if (from === "L4") { assert.equal(after[d.seat][i], 0, "range update ignored the L4 row"); }
    else if (ranges[d.seat][i] > 0) { assert.equal(from, false); assert.ok(after[d.seat][i] > 0, "a combo without any row was not uniform"); }
  }
  assert.ok(same > 0);
  const viaUniform = T.updateRanges(new Map(), T.actionProbs(new Map(), s, ranges, "mid", "c1"), ranges, 0);
  assert.ok(viaUniform[d.seat].some((w) => w > 0));
});

test("backoff (#623): a call| key backs off only at L2 (opponent count)", () => {
  const { call } = spots(), { s, ranges } = call;
  const d = T.decisionKey(s, ranges, "mid", "c1");
  assert.ok(d.key.startsWith("call|"), d.key);
  assert.equal(T.coarseKey(d.key, 1), d.key);
  const parts = d.key.split("|"); parts[2] = String(Number(parts[2]) + 1);
  const sib = parts.join("|"), pol = new Map([[sib, Float64Array.from([0.25, 0.75])]]);
  const r = T.actionProbs(pol, s, ranges, "mid", "c1");
  assert.equal(r.fromTable, "L2");
  assert.deepEqual(r.probs, [0.25, 0.75]);
});

test("backoff (#623): legacy tables (6-max beginner, mid, pro) never back off", () => {
  for (const tier of ["beginner", "mid", "pro"]) {
    const meta = INDEX.tiers[tier];
    assert.equal(meta.key_variant, undefined, `${tier}-6 is not a legacy table any more`);
    const { pol } = decoded(read(`../policy/${meta.file}`));
    let s = firstDecision(6, meta), ranges = T.initialRanges(6), seen = 0;
    while (!s.done && seen < 12) {
      const r = T.actionProbs(pol, s, ranges, tier, meta.key_variant);
      assert.ok(r.fromTable === "exact" || r.fromTable === false, `${tier}: ${r.fromTable}`);
      const row = pol.get(r.key);
      if (row && row.length === r.acts.length) assert.deepEqual(r.probs, Array.from(row));
      else assert.ok(r.probs.every((p) => p === 1 / r.acts.length), `${tier} miss is not uniform: ${r.key}`);
      const a = r.acts.includes("c") ? "c" : r.acts.includes("k") ? "k" : r.acts[0];
      ranges = T.updateRanges(pol, r, ranges, a); s = T.apply(s, a); seen++;
    }
  }
  // The same table and key: a c1 lookup backs off to the sibling's row, a legacy one stays uniform.
  const { post } = spots(), d = T.decisionKey(post.s, post.ranges, "mid", "c1");
  const sib = d.key.replace(/\|o[^|]*$/, "|o9v9k9"), pol = new Map([[sib, Float64Array.from({ length: d.acts.length }, (_, i) => (i ? 0 : 1))]]);
  assert.equal(T.actionProbs(pol, post.s, post.ranges, "mid", "c1").fromTable, "L1");
  assert.equal(T.actionProbs(pol, post.s, post.ranges, "mid", "").fromTable, false);
});

test("backoff (#623): coarse tables of the largest c1 file are built once per policy", () => {
  const big = Object.values(INDEX.tiers.mid.by_players).filter(e => e.key_variant === "c1").sort((a, b) => b.bytes - a.bytes)[0];
  const { pol } = decoded(read("../policy/" + big.file.split("/").pop()));
  const t0 = performance.now(), tabs = T.coarseTables(pol), ms = performance.now() - t0;
  assert.equal(tabs.length, 3);
  assert.equal(T.coarseTables(pol), tabs, "not cached per policy");
  assert.ok(tabs[2].size < tabs[1].size, "L3 must merge L2 keys of positions in the same group");
  console.log(`coarse tables ${big.file}: ${pol.size} keys -> L1 ${tabs[0].size}, L2 ${tabs[1].size}, L3 ${tabs[2].size} in ${ms.toFixed(0)} ms (reference only)`);
});

test("backoff L3 (#645): a key whose L2 key misses reads the mean row of its position group", () => {
  // Every c1 position name maps to tp_key.position_group at its player count (2-6), pro keys at field 1.
  const tail = "|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0";
  const want = { 2: ["blind", "blind"], 3: ["late", "blind", "blind"], 4: ["late", "late", "blind", "blind"],
                 5: ["early", "late", "late", "blind", "blind"], 6: ["early", "early", "late", "late", "blind", "blind"] };
  for (const [n, groups] of Object.entries(want)) {
    T.c1PositionNames(+n).forEach((name, seat) => {
      assert.equal(T.coarseKey(`${name}|n${n}${tail}`, 3), `${groups[seat]}|n${n}|1|1|0|2|0|*|tc0|s*|*|*|*|ka|e5`, `${name} n${n}`);
      assert.equal(T.coarseKey(`p|${name}|n${n}${tail}`, 3).split("|")[1], groups[seat]);
    });
  }
  assert.equal(T.coarseKey("call|1|2|3|fc|e4", 3), T.coarseKey("call|1|2|3|fc|e4", 2));
  assert.throws(() => T.coarseKey(`XX|n6${tail}`, 3), /c1 position name/);
  // The real decision: a table holding only another seat of the same group answers at L3; the page marks it.
  const { post } = spots(), d = T.decisionKey(post.s, post.ranges, "mid", "c1"), m = d.acts.length;
  const [name, players] = d.key.split("|"), n = +players.slice(1), names = T.c1PositionNames(n);
  const g = T.positionGroup(n, names.indexOf(name));
  const mate = names.find((x, i) => x !== name && T.positionGroup(n, i) === g);
  assert.ok(mate, `${d.key}: no other seat in group ${g}`);
  const sib = [mate, ...d.key.split("|").slice(1)].join("|");
  assert.notEqual(T.coarseKey(sib, 2), T.coarseKey(d.key, 2));
  assert.equal(T.coarseKey(sib, 3), T.coarseKey(d.key, 3));
  const pol = new Map([[sib, Float64Array.from({ length: m }, (_, i) => (i === m - 1 ? 1 : 0))]]);
  const r = T.actionProbs(pol, post.s, post.ranges, "mid", "c1");
  assert.equal(r.fromTable, "L3");
  assert.deepEqual(r.probs, Array.from({ length: m }, (_, i) => (i === m - 1 ? 1 : 0)));
});

test("backoff L4 (#652): a key whose L3 key misses reads the mean of the L3 rows at the equity steps next to it", () => {
  const { post } = spots(), d = T.decisionKey(post.s, post.ranges, "mid", "c1"), m = d.acts.length;
  const e = Number(d.key.match(/\|e(\d+)(\||$)/)[1]), top = T.TIER_K.mid - 1;
  const at = (v) => d.key.replace(/\|e\d+(?=\||$)/, `|e${v}`);
  const row = (a) => Float64Array.from({ length: m }, (_, i) => (i === a ? 1 : 0));
  const near = [e - 1, e + 1].filter((v) => v >= 0 && v <= top);
  assert.ok(near.length, d.key);
  const pol = new Map(near.map((v, j) => [at(v), row(j === 0 ? 0 : m - 1)]));
  for (const k of pol.keys()) assert.notEqual(T.coarseKey(k, 3), T.coarseKey(d.key, 3));
  const r = T.actionProbs(pol, post.s, post.ranges, "mid", "c1");
  assert.equal(r.fromTable, "L4");
  const want = Array.from({ length: m }, (_, i) => near.reduce((t, _v, j) => t + row(j === 0 ? 0 : m - 1)[i], 0) / near.length);
  assert.deepEqual(r.probs, want);
  // Two steps away is no neighbor; an L3 hit still wins over L4; legacy tables never reach it.
  const far = new Map([[at(e + 2 <= top ? e + 2 : e - 2), row(0)]]);
  assert.equal(T.actionProbs(far, post.s, post.ranges, "mid", "c1").fromTable, false);
  const both = new Map([...pol, [d.key.replace(/\|o[^|]*$/, "|o9v9k9"), row(1)]]);
  assert.equal(T.actionProbs(both, post.s, post.ranges, "mid", "c1").fromTable, "L1");
  assert.equal(T.actionProbs(pol, post.s, post.ranges, "mid", "").fromTable, false);
  // The bound: a hand-made row above the tier's top step is no neighbor of the top step.
  const topKey = at(top), over = new Map([[d.key.replace(/\|e\d+(?=\||$)/, `|e${top + 1}`), row(0)]]);
  assert.equal(T.backoffRow(over, topKey, m, "c1", top).from, false);
  assert.equal(T.backoffRow(over, topKey, m, "c1").from, "L4", "unbounded by default");
  // Range updates read the same L4 rows.
  const after = T.updateRanges(pol, r, post.ranges, m - 1);
  assert.ok(after[d.seat].some((w, i) => w > 0 && d.steps[i] >= 0));
});
