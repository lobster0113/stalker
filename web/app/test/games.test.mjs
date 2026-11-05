// node --test web/app/test/games.test.mjs  (#465)
import { test } from "node:test";
import assert from "node:assert/strict";
import * as G from "../games.js";

const act = (o = {}) => ({ st: 1, seat: 0, hero: true, type: "check", txt: "체크", pot: 100, bets: [0, 0], stacks: [9900, 9900], folded: [false, false], ...o });
const hand = (no, acts = [act()]) => ({ no, cards: "A♠ K♦", net: 1, folded: false, board: [], seats: [{ i: 0, name: "나", pos: "BTN", hero: true, stack: 10000 }], acts });

test("a broken record never breaks loading", () => {
  assert.deepEqual(G.loadGames("not json"), []);
  assert.deepEqual(G.loadGames(null), []);
  assert.deepEqual(G.loadGames({ schema: "x" }), []);
  const ok = JSON.parse(G.serialize(G.addHand([], { id: "g1", ts: 1 }, hand(1))));
  ok.games[0].hands.push({ no: "bad" }, null, { ...hand(2), acts: [{ st: "x" }] });
  const back = G.loadGames(ok);
  assert.equal(back.length, 1);
  assert.equal(back[0].hands.length, 1, "only the valid hand is kept");
});

test("storage is bounded: oldest hands drop first, games cap, bytes cap", () => {
  let gs = [];
  for (let i = 1; i <= 350; i++) gs = G.addHand(gs, { id: "g" + Math.ceil(i / 10), ts: i }, hand(i));
  const n = gs.reduce((a, g) => a + g.hands.length, 0);
  assert.ok(n <= G.LIMITS.hands && gs.length <= G.LIMITS.games, `${n} hands, ${gs.length} games`);
  assert.equal(gs.at(-1).hands.at(-1).no, 350, "newest kept");
  assert.ok(gs[0].hands[0].no > 1, "oldest dropped");
  const fat = hand(1, [act({ txt: "x".repeat(400_000) })]);
  let big = [];
  for (let i = 0; i < 6; i++) big = G.addHand(big, { id: "b", ts: 1 }, { ...fat, no: i });
  assert.ok(G.serialize(big).length <= G.LIMITS.bytes);
});

test("verdict thresholds and leak cells", () => {
  assert.equal(G.verdict({ p: 0.6 }).text, "잘함");
  assert.equal(G.verdict({ p: 0.15 }).text, "아쉬움");
  assert.equal(G.verdict({ p: 0.02 }).text, "실수");
  assert.equal(G.verdict({ p: 0.02, leak: true }).text, "채점 안 함");
  assert.equal(G.verdict(null), null);
});

test("reasons come from the numbers: a bet that folds out the weaker hands is called out", () => {
  const an = { name: "벳 75%", p: 0.4, top: "체크", topP: 0.5, beats: 0.9, reply: { canFold: true, weakFold: 0.78, strongFold: 0.05, strongOfContinuing: 0.85, fold: 0.74 } };
  const r = G.reasons(an, act({ type: "raise" }));
  const all = r.map((x) => x.text).join("\n");
  assert.match(all, /나보다 약한 핸드의 78%가 폴드/);
  assert.match(all, /밸류를 못 받아요/);
  assert.ok(r.some((x) => x.kind === "bad"));
  const keep = G.reasons({ ...an, reply: { ...an.reply, weakFold: 0.1, strongOfContinuing: 0.2 } }, act({ type: "raise" }));
  assert.ok(keep.some((x) => x.kind === "good"));
});

test("reasons: a fold of a hand with enough equity, and mock tables say what is missing", () => {
  const f = G.reasons({ name: "폴드", p: 0.2, top: "콜", topP: 0.7, beats: 0.6, eq: 0.55, need: 0.3, reply: null }, act({ type: "fold" }));
  assert.match(f.map((x) => x.text).join(" "), /필요한 에퀴티는 30%인데 내 에퀴티는 공개 레인지 대비 55%/);
  assert.match(G.reasons(null, act())[0].text, /모의 상대/);
});

test("handStats counts hero decisions and compared ones", () => {
  const h = hand(1, [act({ an: { p: 0.3 } }), act({ hero: false }), act()]);
  assert.deepEqual(G.handStats(h), { decisions: 2, compared: 1 });
});
