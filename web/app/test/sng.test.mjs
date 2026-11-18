// Single-table SNG eliminations (#987): the page's own sngCompact, on synthetic tables. Busted seats leave,
// survivors keep their chair (ring) and are renumbered, and the button skips the empty chairs.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const page = readFileSync(resolve(web, "demo", "index.html"), "utf8");
const m = page.match(/^function sngCompact\(seats, button\) \{[\s\S]*?^\}/m);
assert.ok(m, "index.html: function sngCompact(seats, button) not found (renamed? update this test)");
const sngCompact = new Function(`${m[0]}\nreturn sngCompact;`)();

// stacks[i] = chips of seat i; seat 0 is the hero (as on the page)
const table = stacks => stacks.map((stack, i) => ({ i, isHero: i === 0, stack, name: `s${i}` }));
const nextIdx = (i, n) => (i + 1) % n;
// The next hand's button after compaction (the page does G.button = nextIdx(G.button) at hand start).
const nextButton = (seats, button) => { const c = sngCompact(seats, button); return { ...c, btn: c.seats[nextIdx(c.button, c.seats.length)] }; };

test("busted seats leave the table; survivors keep their chair and are renumbered 0..n-1", () => {
  const s = table([10, 0, 5, 0, 0, 7, 0, 0, 3]);   // 9 seats, 5 busted -> 4 left (the 9-max SNG bubble)
  const { seats } = sngCompact(s, 0);
  assert.deepEqual(seats.map(x => x.name), ["s0", "s2", "s5", "s8"]);
  assert.deepEqual(seats.map(x => x.i), [0, 1, 2, 3]);
  assert.deepEqual(seats.map(x => x.ring), [0, 2, 5, 8]);
  assert.ok(seats[0].isHero);
});

test("the button moves to the first survivor after the old button, skipping empty chairs", () => {
  // old button on a survivor (chair 2): next button is chair 5 (3 and 4 busted)
  assert.equal(nextButton(table([10, 0, 5, 0, 0, 7, 0, 0, 3]), 2).btn.ring, 5);
  // old button busted (chair 3): next button is the first survivor after it, chair 5
  assert.equal(nextButton(table([10, 0, 5, 0, 0, 7, 0, 0, 3]), 3).btn.ring, 5);
  // wraps past the end: old button chair 8 survives -> hero chair 0; chair 7 busted -> chair 8
  assert.equal(nextButton(table([10, 0, 5, 0, 0, 7, 0, 0, 3]), 8).btn.ring, 0);
  assert.equal(nextButton(table([10, 0, 5, 0, 0, 7, 0, 0, 3]), 7).btn.ring, 8);
});

test("a second shrink keeps the original chairs (ring is not renumbered)", () => {
  const a = sngCompact(table([10, 0, 5, 0, 0, 7, 0, 0, 3]), 0).seats;
  a[2].stack = 0;   // chair 5 busts next
  const b = sngCompact(a, 1).seats;
  assert.deepEqual(b.map(x => x.ring), [0, 2, 8]);
  assert.deepEqual(b.map(x => x.i), [0, 1, 2]);
});

test("down to heads-up the button still alternates between the two survivors", () => {
  let seats = sngCompact(table([10, 0, 5, 0, 0, 0, 0, 0, 0]), 4).seats, btn = sngCompact(table([10, 0, 5, 0, 0, 0, 0, 0, 0]), 4).button;
  assert.equal(seats.length, 2);
  const seen = [];
  for (let h = 0; h < 4; h++) { btn = nextIdx(btn, 2); seen.push(seats[btn].ring); }
  assert.deepEqual(seen, [0, 2, 0, 2]);
});

test("nobody busted: the table is unchanged", () => {
  const s = table([10, 5, 5, 5, 5, 5]);
  const c = sngCompact(s, 3);
  assert.equal(c.seats.length, 6); assert.equal(c.button, 3);
  assert.deepEqual(c.seats.map(x => x.ring), [0, 1, 2, 3, 4, 5]);
});
