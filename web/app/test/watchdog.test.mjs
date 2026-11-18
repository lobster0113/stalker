// node --test web/app/test/watchdog.test.mjs  (#724: Gate U stall watchdog)
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createWatchdog, stallMsFrom, DEFAULT_STALL_MS } from "../../e2e/watchdog.mjs";

const fake = (stallMs, probe) => {
  let t = 0;
  const lines = [], codes = [];
  const wd = createWatchdog({ stallMs, now: () => t, probe, log: l => lines.push(l), exit: c => codes.push(c) });
  return { wd, lines, codes, tick: ms => { t += ms; } };
};

test("GATE_U_STALL_MS sets the stall window; junk falls back to the default", () => {
  assert.equal(DEFAULT_STALL_MS, 240_000);
  assert.equal(stallMsFrom({}), 240_000);
  assert.equal(stallMsFrom({ GATE_U_STALL_MS: "1" }), 1);
  assert.equal(stallMsFrom({ GATE_U_STALL_MS: "90000" }), 90_000);
  for (const bad of ["", "0", "-5", "1.5", "abc"]) assert.equal(stallMsFrom({ GATE_U_STALL_MS: bad }), 240_000, bad);
});

test("progress inside the window never fires; silence past it reports section, seconds, last step and exits 1", async () => {
  const f = fake(1000, async () => ["  page 0 x: {\"handNo\":7}"]);
  f.wd.section("12 c1 policy");
  for (let i = 0; i < 5; i++) { f.tick(900); f.wd.step(`line ${i}`); assert.equal(await f.wd.check(), false); }
  assert.deepEqual(f.lines, [], "success is quiet");
  f.tick(1500);
  assert.equal(await f.wd.check(), true);
  assert.equal(f.lines[0], "Gate U stalled in 12 c1 policy after 1.5s; last step: line 4");
  assert.equal(f.lines[1], "  page 0 x: {\"handNo\":7}");
  assert.deepEqual(f.codes, [1]);
  f.tick(5000);
  assert.equal(await f.wd.check(), false, "fires once");
  assert.deepEqual(f.codes, [1]);
});

test("a section start counts as progress; a hung or failing probe still exits", async () => {
  const f = fake(1000);
  f.tick(800); f.wd.section("2 learn");
  f.tick(800);
  assert.equal(await f.wd.check(), false);
  f.tick(300);
  assert.equal(await f.wd.check(), true);
  assert.match(f.lines[0], /^Gate U stalled in 2 learn after 1\.1s; last step: \(none\)$/);

  const lines = [], codes = [];
  let t = 0;
  const hung = createWatchdog({ stallMs: 1, now: () => t, probe: () => new Promise(() => {}), probeMs: 20, log: l => lines.push(l), exit: c => codes.push(c) });
  t = 5;
  await hung.check();
  assert.deepEqual(codes, [1]);
  assert.match(lines[1], /probe timed out/);

  const bad = fake(1, async () => { throw new Error("boom"); });
  bad.tick(2);
  await bad.wd.check();
  assert.deepEqual(bad.codes, [1]);
  assert.match(bad.lines[1], /probe failed: boom/);
});

test("with real timers, GATE_U_STALL_MS=1 ends a hung process in its first section with exit 1", () => {
  const mod = fileURLToPath(new URL("../../e2e/watchdog.mjs", import.meta.url));
  const src = `import { createWatchdog, stallMsFrom } from ${JSON.stringify(mod)};
    const wd = createWatchdog({ stallMs: stallMsFrom() }).start();
    wd.section("1 start");
    setInterval(() => {}, 1000);   // a wait that never resolves`;
  const r = spawnSync(process.execPath, ["--input-type=module", "-e", src], { env: { ...process.env, GATE_U_STALL_MS: "1" }, encoding: "utf8", timeout: 20_000 });
  assert.equal(r.status, 1, r.stderr);
  assert.match(r.stderr, /^Gate U stalled in 1 start after \d+\.\ds; last step: \(none\)$/m);
});
