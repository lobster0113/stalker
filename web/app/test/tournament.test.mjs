// #956 (ADR 0029 H2): stage mapping, index v2 lookup, players mismatch, env in the key. Node: node --test web/app/test/tournament.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as T from "../tpgto.js";

T.setEquityTable(JSON.parse(readFileSync(new URL("../assets/hu_equity.json", import.meta.url), "utf8")));

const entry = (stage, ante, players) => ({ file: `t-sng-${stage}${ante}.json`, env_id: "sng", stage, ante, players, payoff: "icm" });
const IDX = { schema_version: 2, tiers: {}, tournament: { sng: { b: { ante: { 0: entry("b", 0, 4) } }, e: { ante: { 1: entry("e", 1, 6) } } } } };
const sng = (players, extra = {}) => ({ envId: "sng", players, paid: 3, field: 9, tableSize: 9, ante: 0, ...extra });

test("stage letters: r = K+1 is b, r <= K is m, r >= K+2 is e (SNG never f)", () => {
  for (const [r, st] of [[9, "e"], [5, "e"], [4, "b"], [3, "m"], [2, "m"]]) assert.equal(T.tournamentStage({ players: r, paid: 3, field: 9, tableSize: 9 }), st, `r=${r}`);
  assert.throws(() => T.tournamentStage({ players: 1, paid: 3, field: 9, tableSize: 9 }), /players/);
});

test("MTT: one table in the money is f; several tables or outside the money is not", () => {
  const m = (players) => T.tournamentStage({ players, paid: 27, field: 180, tableSize: 9 });
  assert.deepEqual([47, 28, 27, 9, 8].map(m), ["e", "b", "m", "f", "f"]);
  assert.equal(m(20), "m");
});

test("web G.stage select maps onto the letters", () => {
  assert.deepEqual(Object.entries(T.WEB_STAGE_LETTER).map(([k, v]) => `${k}:${v}`), ["early:e", "mid:e", "bubble:b", "itm:m", "ft:f"]);
});

test("lookup: hit, untrained stage, other ante, other preset, v1 index", () => {
  assert.equal(T.tournamentPolicyFor(IDX, sng(4)).entry.file, "t-sng-b0.json");
  assert.equal(T.tournamentPolicyFor(IDX, sng(4)).stage, "b");
  assert.deepEqual(T.tournamentPolicyFor(IDX, sng(3)), { stage: "m", entry: null, reason: "no_stage" });
  assert.equal(T.tournamentPolicyFor(IDX, sng(4, { ante: 1 })).reason, "no_stage");
  assert.equal(T.tournamentPolicyFor(IDX, sng(6, { ante: 1 })).entry.stage, "e");
  assert.equal(T.tournamentPolicyFor(IDX, sng(4, { envId: "other" })).reason, "no_env");
  const v1 = { schema_version: 1, tiers: {}, tournament: IDX.tournament };
  assert.equal(T.tournamentPolicyFor(v1, sng(4)).reason, "no_env");
  assert.equal(T.tournamentPolicyFor({ schema_version: 1, tiers: {} }, sng(4)).reason, "no_env");
  assert.equal(T.tournamentPolicyFor(null, sng(4)).reason, "no_env");
});

test("trained survivor count differs from the table's: no policy", () => {
  const idx = { schema_version: 2, tournament: { sng: { e: { ante: { 0: entry("e", 0, 6) } } } } };
  assert.deepEqual(T.tournamentPolicyFor(idx, sng(5)), { stage: "e", entry: null, reason: "players_mismatch" });
  assert.equal(T.tournamentPolicyFor(idx, sng(6)).reason, "ok");
});

test("cash tiers are never a fallback for a tournament table", () => {
  const idx = { schema_version: 2, tiers: { mid: { file: "mid-6.json", by_players: { 4: { file: "mid-4.json" } } } }, tournament: {} };
  assert.equal(T.tournamentPolicyFor(idx, sng(4)).entry, null);
});

test("env reaches the c1 key: stage and ante slot", () => {
  const holes = [[0, 1], [2, 3], [4, 5], [6, 7]], s = T.newHand({ n: 4, holes, board: [8, 9, 10, 11, 12] });
  const r = T.initialRanges(4);
  const k = (env) => T.decisionKey(s, r, "mid", "c1", env).key;
  assert.match(k(undefined), /\|tc0\|/);
  assert.match(k({ stage: "b", ante: false }), /\|tb0\|/);
  assert.match(k({ stage: "e", ante: true }), /\|te1\|/);
});
