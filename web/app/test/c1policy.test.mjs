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
  assert.ok(r.fromTable, `c1 key ${r.key} is not in mid-3.json`);
  assert.equal(r.probs.length, r.acts.length);
  const legacy = T.actionProbs(pol, s, T.initialRanges(3), "mid");
  assert.equal(legacy.fromTable, false, "the legacy key must not hit a c1 table (that was the silent miss)");
});

test("every shipped 2–5인 c1 policy answers its first preflop decision from the table", () => {
  for (const n of [2, 4, 5]) {
    const meta = INDEX.tiers.mid.by_players[String(n)];
    const pol = read(`../policy/${meta.file}`).policy;
    const r = T.actionProbs(pol, firstDecision(n, meta), T.initialRanges(n), "mid", meta.key_variant);
    assert.ok(r.fromTable, `${n}-handed: c1 key ${r.key} is not in ${meta.file}`);
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

test("c1 postflop throws (b1 step fields not ported) and an unknown variant is refused", () => {
  const meta = INDEX.tiers.mid.by_players["3"];
  let s = firstDecision(3, meta);
  while (s.street === 0) s = T.apply(s, T.legal(s).includes("c") ? "c" : "k");
  assert.throws(() => T.decisionKey(s, T.initialRanges(3), "mid", "c1"), /c1 postflop key needs the b1 step fields/);
  assert.throws(() => T.decisionKey(firstDecision(3, meta), T.initialRanges(3), "mid", "b1"), /key variant "b1"/);
});
