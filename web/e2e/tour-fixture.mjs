// Synthetic tournament policy for Gate U (#956): preflop c1 keys of a seat count under one (stage, ante), rows from a
// fixed hash, so the page's reads can be checked against the file. Not a trained policy; nothing here is shipped.
import { readFileSync } from "node:fs";
import * as T from "../app/tpgto.js";

T.setEquityTable(JSON.parse(readFileSync(new URL("../app/assets/hu_equity.json", import.meta.url), "utf8")));

const hash = (s) => { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0; return h; };
const row = (key, m) => {
  const w = Array.from({ length: m }, (_, i) => 1 + (hash(`${key}#${i}`) % 7));
  const tot = w.reduce((a, b) => a + b, 0), r = w.map((x) => Math.max(1, Math.round((255 * x) / tot)));
  r[0] += 255 - r.reduce((a, b) => a + b, 0);   // sums to q = 255
  return r;
};

/** {doc, bytes}: a stalker.web.policy file for `players` seats at (stage, ante), tier beginner (basic depth, c1 keys). */
export function tourPolicy({ players, stage, ante, hands = 800 }) {
  const policy = {}, rng = new T.NumpyRng([956, players, ante]);
  for (let h = 0; h < hands; h++) {
    const deck = Array.from({ length: 52 }, (_, i) => i);
    for (let i = 51; i > 0; i--) { const j = Math.floor(rng.random() * (i + 1)); [deck[i], deck[j]] = [deck[j], deck[i]]; }
    let s = T.newHand({ n: players, holes: Array.from({ length: players }, (_, i) => [deck[2 * i], deck[2 * i + 1]]), ante: ante ? 100 : 0, stacks: Array.from({ length: players }, () => Math.round(1000 + rng.random() * 4000)), board: deck.slice(2 * players, 2 * players + 5) });
    let ranges = T.initialRanges(players);
    while (!s.done && s.street === 0) {
      const d = T.decisionKey(s, ranges, "beginner", "c1", { stage, ante: !!ante });
      if (!policy[d.key]) policy[d.key] = row(d.key, d.acts.length);
      const a = d.acts[Math.floor(rng.random() * d.acts.length)];
      s = T.apply(s, a);
    }
  }
  const doc = { schema: "stalker.web.policy", schema_version: 2, tier: "beginner", players, k: 5, depth: "basic", iterations: 400, run_id: `fixture-${stage}${ante}`, sha: "fixture",
    lbr_bb: null, lbr_stderr_bb: null, field_worst: null, job: "", strategy: "current", menu: "v1", raise_cap: 3, q: 255, min_visits: 0, key_variant: "c1",
    keys: Object.keys(policy).length, keys_dropped: 0, policy };
  return { doc, bytes: Buffer.from(JSON.stringify(doc)) };
}
