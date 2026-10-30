// node --test web/app/test/tells.test.mjs — hero tell metrics on synthetic logs (#430).
import { test } from "node:test";
import assert from "node:assert/strict";
import * as T from "../tells.js";

// Seeded so every run sees the same synthetic hero.
function rng(seed) { let s = seed | 0; return () => { s = s + 0x6D2B79F5 | 0; let t = Math.imul(s ^ s >>> 15, 1 | s); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const SIZES = [33, 50, 75, 100, 150];
function hero(n, { seed = 1, street = 1, size, ms, forced = () => false, extra = {} }) {
  const r = rng(seed), out = [];
  for (let i = 0; i < n; i++) {
    const strength = r();
    out.push({ hand: "h" + i, street, action: "bet", sizePct: size(strength, r), ms: ms(strength, r), strength, madeClass: strength > .7 ? 2 : strength > .4 ? 1 : 0, forced: forced(i), timed: true, spot: null, gtoAgg: null, ...extra });
  }
  return out;
}
const tellSize = s => s < 1 / 3 ? 33 : s < 2 / 3 ? 75 : 150;
const randSize = (s, r) => SIZES[Math.floor(r() * SIZES.length)];
const flatMs = (s, r) => 1500 + r() * 1500;

test("a perfectly size-telling hero is flagged on that street", () => {
  const m = T.tellMetrics(hero(30, { size: tellSize, ms: flatMs }));
  const f = m.size[1];
  assert.equal(f.enough, true);
  assert.ok(f.rho > 0.8, `rho ${f.rho}`);
  assert.ok(f.mi > 0.8, `mi ${f.mi}`);
  assert.equal(f.leak, true);
  assert.equal(m.size[2].n, 0, "other streets stay empty");
  assert.equal(T.tellMetrics(hero(T.TH.size.min, { size: tellSize, ms: flatMs })).size[1].leak, true, "flagged at exactly the minimum");
  assert.equal(T.tellMetrics(hero(T.TH.size.min - 1, { size: tellSize, ms: flatMs })).size[1].leak, false, "one short of the minimum");
  const rep = T.tellReport(hero(30, { size: tellSize, ms: flatMs }));
  const leak = rep.leaks.find(l => l.id === "size1");
  assert.ok(leak && /플랍에서 벳 크기로 핸드 강도가 드러납니다: 강할 때 평균 팟 \d+%, 약할 때 33% .* \(n=30\)$/.test(leak.text), leak?.text);
  assert.ok(leak.fix.length > 0);
});

test("a hero who mixes sizes independent of strength is not flagged", () => {
  for (const seed of [1, 2, 3, 4, 5]) {
    const f = T.tellMetrics(hero(40, { seed, size: randSize, ms: flatMs })).size[1];
    assert.equal(f.enough, true);
    assert.equal(f.leak, false, `seed ${seed}: rho ${f.rho} mi ${f.mi}`);
  }
  const constant = T.tellMetrics(hero(40, { size: () => 75, ms: flatMs })).size[1];
  assert.equal(constant.rho, 0); assert.equal(constant.mi, 0); assert.equal(constant.leak, false);
});

test("timing: a hero who tanks with strong hands is flagged, a steady one is not", () => {
  const slow = T.tellMetrics(hero(30, { size: randSize, ms: (s, r) => 800 + s * 5000 + r() * 300 })).timing;
  assert.equal(slow.enough, true);
  assert.equal(slow.leak, true, `rho ${slow.rho} ratio ${slow.ratio}`);
  assert.ok(slow.medians[2] > slow.medians[0]);
  for (const seed of [1, 2, 3, 4, 5]) assert.equal(T.tellMetrics(hero(40, { seed, size: randSize, ms: flatMs })).timing.leak, false, `seed ${seed}`);
  assert.ok(T.tellReport(hero(30, { size: randSize, ms: (s, r) => 800 + s * 5000 })).leaks.some(l => l.id === "timing"));
});

test("timing excludes forced, instant and untimed decisions", () => {
  const ds = hero(30, { size: randSize, ms: (s, r) => 800 + s * 5000, forced: i => i < 10 });
  ds[10].ms = 120; ds[11].timed = false;
  const t = T.tellMetrics(ds).timing;
  assert.equal(t.n, 18); assert.equal(t.excluded, 12);
});

test("below the minimum the report says not enough data instead of judging", () => {
  const ds = hero(5, { size: tellSize, ms: (s) => 800 + s * 5000 });
  const m = T.tellMetrics(ds);
  assert.equal(m.size[1].enough, false); assert.equal(m.size[1].leak, false);
  assert.equal(m.timing.enough, false); assert.ok(!m.timing.leak);
  const rep = T.tellReport(ds);
  assert.equal(rep.leaks.length, 0);
  assert.equal(rep.rows.find(r => r.id === "size1").text, `데이터 부족 (n=5/최소 ${T.TH.size.min})`);
  assert.ok(rep.rows.find(r => r.id === "timing").text.startsWith(`데이터 부족 (n=5/최소 ${T.TH.timing.min})`));
  assert.equal(T.tellReport([]).rows.find(r => r.id === "river").text, `데이터 부족 (n=0/최소 ${T.TH.river.min})`);
});

test("lines: c-bet gap, value-only check-raise, river without bluffs, capped check-call, policy gap", () => {
  const ds = [];
  for (let i = 0; i < 12; i++) ds.push({ hand: "c" + i, street: 1, action: i % 2 ? "bet" : "check", sizePct: i % 2 ? 50 : null, ms: 2000, strength: i % 2 ? .8 : .3, madeClass: 1, spot: "cbet", gtoAgg: .3 });
  for (let i = 0; i < 6; i++) ds.push({ hand: "x" + i, street: 2, action: "raise", sizePct: 100, ms: 2000, strength: .85, madeClass: 3, spot: "xr" });
  for (let i = 0; i < 10; i++) ds.push({ hand: "k" + i, street: 2, action: "call", sizePct: null, ms: 2000, strength: .35, madeClass: 1, spot: "xr" });
  for (let i = 0; i < 8; i++) ds.push({ hand: "r" + i, street: 3, action: "bet", sizePct: 75, ms: 2000, strength: .9, madeClass: 2 });
  const m = T.tellMetrics(ds);
  assert.equal(m.cbet.rate, .5); assert.equal(m.cbet.leakGap, true); assert.equal(m.cbet.leakFreq, false);
  assert.equal(m.gto.enough, true); assert.ok(Math.abs(m.gto.policy - .3) < 1e-9); assert.equal(m.gto.leak, false);
  assert.equal(m.xr.leak, true); assert.equal(m.river.leakLow, true); assert.equal(m.checkCall.leak, true);
  assert.equal(m.donk.enough, false);
  const ids = T.tellReport(ds).leaks.map(l => l.id);
  for (const id of ["cbet-gap", "xr", "river", "checkcall"]) assert.ok(ids.includes(id), id);
});

test("showdown evidence links what the opponents saw to the line", () => {
  const ds = [{ hand: "a", street: 0, action: "raise", sizePct: 120, strength: .6 }, { hand: "a", street: 1, action: "bet", sizePct: 50, strength: .7 }, { hand: "b", street: 0, action: "call", strength: .5 }];
  const sd = T.tellMetrics(ds, [{ hand: "a", madeClass: 2 }, { hand: "b", madeClass: 0 }]).showdown;
  assert.equal(sd.n, 2);
  assert.deepEqual(sd.lines.map(l => l.line).sort(), ["프리플랍 C", "프리플랍 R · 플랍 B"]);
});

test("helpers: average ranks, terciles, bucket edges", () => {
  assert.deepEqual(T.ranks([3, 1, 3, 2]), [2.5, 0, 2.5, 1]);
  assert.deepEqual(T.terciles([.9, .1, .5, .2, .8, .6]), [2, 0, 1, 0, 2, 1]);
  assert.deepEqual([20, 40, 61, 62, 100, 125, 300].map(T.sizeBucket), [0, 1, 1, 2, 3, 4, 4]);
  assert.ok(Math.abs(T.spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1) < 1e-12);
});
