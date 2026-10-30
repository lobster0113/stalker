// Known-leak warnings (#441): the page's own leakVerdict / leakHTML, against synthetic cells and the
// shipped leaks files (web/app/policy/<tier>-6.leaks.json, stalker/tools/policy_leaks.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const page = readFileSync(resolve(web, "demo", "index.html"), "utf8");
const grab = re => { const m = page.match(re); assert.ok(m, `index.html: ${re} not found (renamed? update this test)`); return m[0]; };
const src = [
  grab(/^function leakVerdict\(leaks, hist, seat, group, top\) \{[\s\S]*?^\}/m),
  grab(/^const LEAK_ISSUE = .*;$/m),
  grab(/^const leakActName = .*;$/m),
  grab(/^function leakHTML\(v\) \{[\s\S]*?^\}/m),
].join("\n");
const { leakVerdict, leakHTML } = new Function(`${src}\nreturn { leakVerdict, leakHTML };`)();
const text = html => html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();

const cell = (spot, seat, group, extra = {}) => ({ spot, seat, pos: ["UTG", "HJ", "CO", "BTN", "SB", "BB"][seat], group, deals: 300, ...extra });
const LEAKS = {
  cells: [cell("first_in", 1, "AA", { measured: true, leak: true }), cell("first_in", 1, "KK", { measured: true, leak: false }),
          cell("vs_open", 2, "AA", { measured: true, leak: true })],
  leaks: [cell("first_in", 1, "AA", { best: "r", gain_bb: 4.2, gain_ci: [2.1, 6.3], open_minus_limp: { r: { bb: 4.6, ci: [2.0, 7.2] } } }),
          cell("vs_open", 2, "AA", { best: "a", gain_bb: 9.1, gain_ci: [5, 13.2], open_minus_limp: {} })],
};
const TOP = new Set(["AA", "KK", "QQ", "AKs", "JJ", "AQs", "KQs", "AJs"]);

test("a decision in a leak cell gets the strong warning with the probe's numbers", () => {
  const v = leakVerdict(LEAKS, ["0:f"], 1, "AA", TOP);
  assert.equal(v.kind, "leak"); assert.equal(v.spot, "first_in");
  const t = text(leakHTML(v));
  assert.ok(t.includes("이 스팟의 정책 답은 검증에서 손해로 확인됨 (#391): 오픈/레이즈가 +4.2 bb"), t);
  assert.ok(t.includes("채점하지 않아요"), t);
  const o = leakVerdict(LEAKS, ["0:r", "1:f"], 2, "AA", TOP);
  assert.equal(o.kind, "leak"); assert.equal(o.spot, "vs_open");
  assert.ok(text(leakHTML(o)).includes("오픈/레이즈(올인)가 +9.1 bb"));
});

test("only first-in and single-open spots, before the actor has acted, preflop", () => {
  assert.equal(leakVerdict(LEAKS, ["0:c"], 1, "AA", TOP), null, "a limp before: not first in");
  assert.equal(leakVerdict(LEAKS, ["0:a", "1:f"], 2, "AA", TOP), null, "an all-in open is not the probe's vs_open");
  assert.equal(leakVerdict(LEAKS, ["0:r", "1:r"], 2, "AA", TOP), null, "a 3-bet pot");
  assert.equal(leakVerdict(LEAKS, ["0:f", "1:r", "2:f", "3:f", "4:f", "5:r", "1:c", "/"], 1, "AA", TOP), null, "postflop");
  assert.equal(leakVerdict(LEAKS, ["1:r", "2:r", "3:f"], 1, "AA", TOP), null, "the actor already acted");
  assert.equal(leakVerdict(LEAKS, [], 0, "AA", TOP)?.kind, "soft", "seat 0 AA first in was not measured here");
});

test("top-3% hands in any unflagged cell get the soft note, measured or not; weaker hands get nothing", () => {
  const s = leakVerdict(LEAKS, ["0:f", "1:f"], 2, "AJs", TOP);
  assert.equal(s.kind, "soft");
  assert.ok(text(leakHTML(s)).includes("프리플랍 강한 핸드 구간은 정책 결함 조사 중"));
  assert.ok(text(leakHTML(s)).includes("아직 검증하지 않았어요"));
  const m = leakVerdict(LEAKS, ["0:f"], 1, "KK", TOP);
  assert.equal(m.kind, "soft", "measured, not flagged: unproven, so still the soft note");
  assert.equal(m.measured, true);
  assert.ok(text(leakHTML(m)).includes("프리플랍 강한 핸드 구간은 정책 결함 조사 중") && text(leakHTML(m)).includes("증명도 아니에요"));
  assert.ok(!leakHTML(m).includes("data-leak-warn"), "no strong warning outside flagged cells");
  assert.equal(leakVerdict(LEAKS, ["0:f"], 1, "T9o", TOP), null, "not a top hand");
  assert.equal(leakVerdict(null, ["0:f"], 1, "AA", TOP).kind, "soft", "no leaks file: soft note, never a silent grade");
  assert.equal(leakHTML(null), "");
});

test("the shipped leaks files match their policies and every leak cell triggers the warning", () => {
  const index = JSON.parse(readFileSync(resolve(web, "app", "policy", "index.json"), "utf8"));
  for (const [tier, m] of Object.entries(index.tiers)) {
    const f = resolve(web, "app", "policy", m.file.replace(/\.json$/, ".leaks.json"));
    assert.ok(existsSync(f), `${f} missing: python -m stalker.tools.policy_leaks --tier ${tier} ... (web/README.md)`);
    const L = JSON.parse(readFileSync(f, "utf8"));
    assert.equal(L.schema, "stalker.web.policy-leaks"); assert.equal(L.tier, tier); assert.equal(L.policy, m.file);
    assert.equal(L.policy_run_id, m.run_id, `${tier}: leaks were probed on another policy run; re-run the probe`);
    assert.ok(L.evidence && L.settings.deals_per_cell > 0);
    // Every measured top-3% cell the probe did not flag still gets the soft note (e.g. mid HJ AA first in).
    for (const c of L.cells.filter(c => c.measured && !c.leak && TOP.has(c.group))) {
      const before = Array.from({ length: c.seat }, (_, q) => `${q}:${c.spot === "vs_open" && q === 0 ? "r" : "f"}`);
      assert.equal(leakVerdict(L, before, c.seat, c.group, TOP)?.kind, "soft", `${tier} ${c.spot} ${c.pos} ${c.group}`);
    }
    for (const c of L.leaks) {
      const before = Array.from({ length: c.seat }, (_, q) => `${q}:${c.spot === "vs_open" && q === 0 ? "r" : "f"}`);
      const v = leakVerdict(L, before, c.seat, c.group, TOP);
      assert.equal(v?.kind, "leak", `${tier} ${c.spot} ${c.pos} ${c.group}`);
      assert.ok(c.gain_bb > L.settings.threshold_bb);
    }
  }
});
