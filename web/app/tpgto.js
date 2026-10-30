// tpgto.js — E3 TP-GTO in the browser: game rules, TP keys, public ranges, equity (#335).
//
// A dependency-free ES module that computes the policy-table lookup keys exactly as the Python
// trainer does (stalker/e3/game.py, stalker/e3/tp_key.py, stalker/e2/eq_view.py), so a trained
// E3 policy (key -> action probabilities) drives a static page. Exactness is checked against
// vectors from stalker/tools/web_vectors.py by web/app/test/tpgto.test.mjs.
//
// Setup (once): the preflop equity table, web/app/assets/hu_equity.json.
//   await loadEquityTable(new URL("./assets/hu_equity.json", import.meta.url))   // browser
//   setEquityTable(jsonObject)                                                     // inlined / node
//
// Cards are ints 0..51: rank = c >> 2 (0 = deuce .. 12 = ace), suit = c & 3 ("cdhs").
// Seats are numbered in preflop order: 0 = UTG ... n-3 = BTN, n-2 = SB, n-1 = BB (positionNames(n)).
// To seat a "button" at a physical table position, rotate your display; seat numbers are fixed.
//
// Game (immutable plain objects; apply returns a new state):
//   newHand({n, holes, board?, deck?, menu?, raiseCap?})  holes: n pairs; deck: remaining cards, board
//                                        dealt from the front; or board: up to 5 board cards (filler is
//                                        appended). menu "v1" (default) | "tp6" | "real"; raiseCap 3 or null.
//   dealFromPermutation(perm52, n, {menu, raiseCap}?)  same as Python G.deal given rng.permutation(52).
//   menuOf(policyMeta) -> {menu, raiseCap}: the rules a policy file was trained on (v1 + cap 3 if unsaid).
//   sizeMenu(s, menu?, raiseCap?) -> [{a, to}] sizes + all in; streetCap(s) as G.street_cap.
//   legal(s) -> ["f","c","r","a"] etc.  apply(s, a) -> state    payoff(s) -> net chips per seat
//   amountTo(s, a) -> street total the actor would have after `a`; toCall(s, p?); pot(s)
//   live(s), active(s), positionNames(n), postflopOrder(n)
//   s.history: "<seat>:<menu action>" and "/" (Python format); s.log: [{seat, action, to, real?}].
// Real no-limit (human seats): any bet/raise from the minimum raise to all in.
//   betRange(s) -> {min, max} street totals, or null (only fold/call/check).
//   splitBet(s, to) -> [{a, p}]; sampleBet(s, to, rng) -> label; translateBet(s, to, rng?) ->
//   {split, action, prob, lower, upper}; splitScore(split, scoreFn); applyBet(s, to, rng | label).
//   translationError(s, to) -> true when the split is a poor reading (translate.high_translation_error,
//   #417): grading shows that size as approximate, not as a full score.
//   Chips always move by the real amount. The table knows only its menu, so any size is translated
//   as stalker/e3/translate.py (TP.md section 6): the pseudo-harmonic split (Ganzfried & Sandholm
//   2013) between the two neighbouring legal menu sizes A < B, sizes as pot fractions after calling
//   (x = (to - top bet) / (pot + to_call)): P(A) = (b - x)(1 + a) / ((b - a)(1 + x)). An exact size
//   maps to itself, a size below the smallest menu size to it, all in to "a". The AI's reading is one
//   draw from the split with a seeded NumpyRng (rng.random() as numpy's Generator.random()), so a
//   fixed seed replays the hand and no fixed threshold can be gamed; grading weighs the split. The
//   reading goes into s.history, the human's range update (updateRanges(policy, d, ranges, label)
//   with d = decisionKey of the state before the bet), and so into later keys. A bet or raise always
//   maps to a bet or raise, so raise level, initiative and n_opp equal the mapped history's. Pot-odds
//   and SPR steps are computed from the real chips, and the legal-action field is the menu that is
//   executable at the real stacks (the same function as Python's legal, so keys stay in the table's
//   key space). AI seats only choose menu actions (apply).
// TP keys and ranges:
//   initialRanges(n) -> Float64Array(1326)[]  (reach weight per combo, COMBOS order)
//   decisionKey(s, ranges, tier) -> {seat, acts, public, steps, step, key}
//       tier: "beginner" | "mid" | "pro"; steps: Int32Array(1326) of the actor's combos (-1 dead).
//   actionProbs(policy, s, ranges, tier) -> {...decisionKey, probs}  probs = policy row for the
//       actor's real hole (uniform when the table has no entry), aligned with `acts`.
//   updateRanges(policy, d, ranges, action) -> new ranges after the actor of decision `d` took
//       `action` (name or index): Bayes update with the policy row of every combo's own key.
//   seatProbs(policy, public, steps, m) -> per-combo rows (Float64Array(1326*m), row-major).
//   updateRange(ranges, seat, probsColumn) -> low level, as tp_key.update_range.
//   equityStepOf(s, seat, ranges, tier) -> the actor's step (with board.nut encoded for pro).
//   equitySteps(s, seat, ranges, k), publicKey(s, seat, depth), key(public, step), myStep(...)
//   equityVs(board, w) -> Float64Array(1326) equity vs range w (NaN on board collisions)
//   boardNut(s, seat, ranges) -> 0..100 or null; evaluate(cards) -> score (higher wins)
//   policy: a plain object {key: [p_action...]} or a Map.
//   checkNutK(checkpoint.nut_k) -> throws if a pro table was built on another board.nut grid.
//
// Float arithmetic mirrors numpy (cumsum order, pairwise sum, quantile lerp, round-half-even), and
// numpy's default_rng(seed).choice(..., replace=False) is reproduced bit for bit (SeedSequence,
// PCG64 XSL-RR, Floyd + Fisher-Yates with Lemire bounded draws).

// ---------------------------------------------------------------- cards
export const RANKS = "23456789TJQKA";
export const SUITS = "cdhs";
export const N = 1326;
export const COMBO_HI = new Int32Array(N);
export const COMBO_LO = new Int32Array(N);
const COMBO_IDX = new Int32Array(52 * 52).fill(-1);
{
  let i = 0;
  for (let a = 0; a < 52; a++) for (let b = a + 1; b < 52; b++) {
    COMBO_HI[i] = b; COMBO_LO[i] = a; COMBO_IDX[b * 52 + a] = i; i++;
  }
}
export const COMBOS = Array.from({ length: N }, (_, i) => [COMBO_HI[i], COMBO_LO[i]]);

export function comboIndex(hole) {
  const [a, b] = hole;
  return a > b ? COMBO_IDX[a * 52 + b] : COMBO_IDX[b * 52 + a];
}

export function cardStr(c) { return RANKS[c >> 2] + SUITS[c & 3]; }
export function card(t) { return (RANKS.indexOf(t[0].toUpperCase()) << 2) | SUITS.indexOf(t[1].toLowerCase()); }

function handClass(c1, c2) {
  let r1 = c1 >> 2, r2 = c2 >> 2;
  if (r1 < r2) [r1, r2] = [r2, r1];
  if (r1 === r2) return RANKS[r1] + RANKS[r1];
  return RANKS[r1] + RANKS[r2] + ((c1 & 3) === (c2 & 3) ? "s" : "o");
}
export const HAND_CLASSES = [];
for (let r1 = 12; r1 >= 0; r1--) for (let r2 = r1; r2 >= 0; r2--) {
  if (r1 === r2) HAND_CLASSES.push(RANKS[r1] + RANKS[r1]);
  else { HAND_CLASSES.push(RANKS[r1] + RANKS[r2] + "s"); HAND_CLASSES.push(RANKS[r1] + RANKS[r2] + "o"); }
}
const NC = HAND_CLASSES.length;
const COMBO_CLS = new Int32Array(N);
const CLASS_W = new Float64Array(NC);
{
  const ci = new Map(HAND_CLASSES.map((c, i) => [c, i]));
  for (let i = 0; i < N; i++) { COMBO_CLS[i] = ci.get(handClass(COMBO_HI[i], COMBO_LO[i])); CLASS_W[COMBO_CLS[i]] += 1; }
}

// ---------------------------------------------------------------- evaluator (stalker/core/evaluator.py)
const STRAIGHT_HIGH = new Int32Array(8192);
const POPCNT = new Int32Array(8192);
const TOP = new Array(8192);
for (let m = 0; m < 8192; m++) {
  const bits = [];
  for (let r = 12; r >= 0; r--) if ((m >> r) & 1) bits.push(r);
  TOP[m] = bits; POPCNT[m] = bits.length;
  let best = -1;
  for (let hi = 12; hi > 3; hi--) { const need = 0b11111 << (hi - 4); if ((m & need) === need) { best = hi; break; } }
  if (best < 0 && (m & 0b1000000001111) === 0b1000000001111) best = 3;
  STRAIGHT_HIGH[m] = best;
}
function kick(ranks) {
  let v = 0;
  for (let i = 0; i < 5 && i < ranks.length; i++) v |= ranks[i] << (16 - 4 * i);
  return v;
}
const rc = new Int32Array(13);
/** Score of 5..7 cards; same integers as stalker.core.evaluator.evaluate. */
export function evaluate(cards) {
  rc.fill(0);
  let s0 = 0, s1 = 0, s2 = 0, s3 = 0;
  for (const c of cards) {
    const r = c >> 2; rc[r]++;
    switch (c & 3) { case 0: s0 |= 1 << r; break; case 1: s1 |= 1 << r; break; case 2: s2 |= 1 << r; break; default: s3 |= 1 << r; }
  }
  for (const m of [s0, s1, s2, s3]) {
    if (POPCNT[m] >= 5) {
      const sh = STRAIGHT_HIGH[m];
      if (sh >= 0) return (8 << 20) | (sh << 16);
      return (5 << 20) | kick(TOP[m]);
    }
  }
  let quads = -1, trips = -1, trips2 = -1, singles = 0, rankMask = 0;
  const pairs = [];
  for (let r = 12; r >= 0; r--) {
    const n = rc[r];
    if (n) rankMask |= 1 << r;
    if (n === 4) quads = r;
    else if (n === 3) { if (trips < 0) trips = r; else if (trips2 < 0) trips2 = r; }
    else if (n === 2) pairs.push(r);
    else if (n === 1) singles |= 1 << r;
  }
  if (quads >= 0) {
    let k = -1;
    for (let r = 0; r < 13; r++) if (rc[r] && r !== quads) k = r;
    return (7 << 20) | (quads << 16) | (k << 12);
  }
  if (trips >= 0) {
    const pr = Math.max(trips2, pairs.length ? pairs[0] : -1);
    if (pr >= 0) return (6 << 20) | (trips << 16) | (pr << 12);
  }
  const sh = STRAIGHT_HIGH[rankMask];
  if (sh >= 0) return (4 << 20) | (sh << 16);
  if (trips >= 0) { const k = TOP[singles]; return (3 << 20) | (trips << 16) | (k[0] << 12) | (k[1] << 8); }
  if (pairs.length >= 2) {
    const rest = singles | (pairs.length > 2 ? 1 << pairs[2] : 0);
    return (2 << 20) | (pairs[0] << 16) | (pairs[1] << 12) | (TOP[rest][0] << 8);
  }
  if (pairs.length) { const k = TOP[singles]; return (1 << 20) | (pairs[0] << 16) | (k[0] << 12) | (k[1] << 8) | (k[2] << 4); }
  return kick(TOP[singles]);
}

// ---------------------------------------------------------------- numpy-exact helpers
/** numpy's float64 add.reduce of a contiguous array (pairwise, 8-way unrolled blocks of 128). */
export function pairwiseSum(a, off = 0, n = a.length) {
  if (n < 8) {
    let res = 0.0;
    for (let i = 0; i < n; i++) res += a[off + i];
    return res;
  }
  if (n <= 128) {
    let r0 = a[off], r1 = a[off + 1], r2 = a[off + 2], r3 = a[off + 3];
    let r4 = a[off + 4], r5 = a[off + 5], r6 = a[off + 6], r7 = a[off + 7];
    let i = 8;
    for (; i < n - (n % 8); i += 8) {
      const p = off + i;
      r0 += a[p]; r1 += a[p + 1]; r2 += a[p + 2]; r3 += a[p + 3];
      r4 += a[p + 4]; r5 += a[p + 5]; r6 += a[p + 6]; r7 += a[p + 7];
    }
    let res = ((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7));
    for (; i < n; i++) res += a[off + i];
    return res;
  }
  let n2 = Math.floor(n / 2);
  n2 -= n2 % 8;
  return pairwiseSum(a, off, n2) + pairwiseSum(a, off + n2, n - n2);
}
function npSum(a) { return 0.0 + pairwiseSum(a); }

/** Python round() (half to even) for the chip amounts. */
export function pyRound(x) {
  const f = Math.floor(x), d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

/** np.searchsorted(edges, x, side="right"). */
function searchRight(edges, x) { let i = 0; while (i < edges.length && edges[i] <= x) i++; return i; }

// ---------------------------------------------------------------- numpy default_rng (SeedSequence -> PCG64)
const INIT_A = 0x43b0d7e5, MULT_A = 0x931e8875, INIT_B = 0x8b51f9dd, MULT_B = 0x58f38ded;
const MIX_MULT_L = 0xca01f9dd, MIX_MULT_R = 0x4973f715;

/** SeedSequence(entropy).generate_state(nWords, uint64) as BigInts. entropy: non-negative ints < 2^32. */
export function seedSequenceState(entropy, nWords64 = 4) {
  const POOL = 4;
  const pool = new Array(POOL).fill(0);
  let hc = INIT_A;
  const hashmix = (v) => {
    v = (v ^ hc) >>> 0;
    hc = Math.imul(hc, MULT_A) >>> 0;
    v = Math.imul(v, hc) >>> 0;
    return (v ^ (v >>> 16)) >>> 0;
  };
  const mix = (x, y) => {
    const r = (Math.imul(MIX_MULT_L, x) - Math.imul(MIX_MULT_R, y)) >>> 0;
    return (r ^ (r >>> 16)) >>> 0;
  };
  const ent = entropy.map((x) => x >>> 0);
  for (let i = 0; i < POOL; i++) pool[i] = hashmix(i < ent.length ? ent[i] : 0);
  for (let s = 0; s < POOL; s++) for (let d = 0; d < POOL; d++) if (s !== d) pool[d] = mix(pool[d], hashmix(pool[s]));
  for (let s = POOL; s < ent.length; s++) for (let d = 0; d < POOL; d++) pool[d] = mix(pool[d], hashmix(ent[s]));
  const words = [];
  let h = INIT_B;
  for (let i = 0; i < nWords64 * 2; i++) {
    let v = (pool[i % POOL] ^ h) >>> 0;
    h = Math.imul(h, MULT_B) >>> 0;
    v = Math.imul(v, h) >>> 0;
    words.push((v ^ (v >>> 16)) >>> 0);
  }
  const out = [];
  for (let i = 0; i < nWords64; i++) out.push(BigInt(words[2 * i]) | (BigInt(words[2 * i + 1]) << 32n));
  return out;
}

const M64 = (1n << 64n) - 1n, M128 = (1n << 128n) - 1n;
const PCG_MULT = (2549297995355413924n << 64n) + 4865540595714422341n;

/** numpy.random.Generator(PCG64(SeedSequence(entropy))) — only the draws `choice` needs. */
export class NumpyRng {
  constructor(entropy) {
    const v = seedSequenceState(entropy, 4);
    const initstate = (v[0] << 64n) | v[1];
    const initseq = (v[2] << 64n) | v[3];
    this.inc = ((initseq << 1n) | 1n) & M128;
    this.state = 0n;
    this._step();
    this.state = (this.state + initstate) & M128;
    this._step();
    this.hasU32 = false; this.u32 = 0;
  }
  _step() { this.state = (this.state * PCG_MULT + this.inc) & M128; }
  /** Generator.random(): a float64 in [0, 1) from the top 53 bits of one 64-bit draw. */
  random() { return Number(this.next64() >> 11n) / 9007199254740992; }
  next64() {
    this._step();
    const s = this.state;
    const x = ((s >> 64n) ^ s) & M64;
    const rot = s >> 122n;
    return ((x >> rot) | (x << ((64n - rot) & 63n))) & M64;
  }
  next32() {
    if (this.hasU32) { this.hasU32 = false; return this.u32; }
    const n = this.next64();
    this.hasU32 = true;
    this.u32 = Number(n >> 32n);
    return Number(n & 0xFFFFFFFFn);
  }
  /** random_bounded_uint64(0, rng) for rng < 2^32 - 1: Lemire's method on 32-bit draws. */
  bounded(rng) {
    if (rng === 0) return 0;
    const excl = rng + 1;
    let m = this.next32() * excl;
    let left = m % 4294967296;
    if (left < excl) {
      const threshold = (4294967295 - rng) % excl;
      while (left < threshold) { m = this.next32() * excl; left = m % 4294967296; }
    }
    return Math.floor(m / 4294967296);
  }
  /** Generator.choice(a, size, replace=False) for small populations (Floyd's algorithm + shuffle). */
  choiceNoReplace(a, size) {
    const pop = a.length;
    if (size > pop) throw new Error("choice: size > population");
    if (pop > 10000) throw new Error("choice: tail-shuffle branch not ported");
    let mask = Math.floor(1.2 * size);
    for (const sh of [1, 2, 4, 8, 16]) mask |= mask >>> sh;
    const setSize = mask + 1;
    const set = new Array(setSize).fill(-1);
    const idx = new Array(size);
    for (let j = pop - size; j < pop; j++) {
      const val = this.bounded(j);
      let loc = val & mask;
      while (set[loc] !== -1 && set[loc] !== val) loc = (loc + 1) & mask;
      if (set[loc] === -1) { set[loc] = val; idx[j - pop + size] = val; }
      else {
        loc = j & mask;
        while (set[loc] !== -1) loc = (loc + 1) & mask;
        set[loc] = j; idx[j - pop + size] = j;
      }
    }
    for (let i = size - 1; i >= 1; i--) {
      const j = this.bounded(i);
      const t = idx[j]; idx[j] = idx[i]; idx[i] = t;
    }
    return idx.map((i) => a[i]);
  }
}

// ---------------------------------------------------------------- equity (stalker/e2/eq_view.py)
export const EQ_RUNOUTS = 12;
let NUM = null, DEN = null; // 169x169 row-major: N*E and N

/** Install the 169-class preflop table ({classes, equity, pairs}, web/app/assets/hu_equity.json). */
export function setEquityTable(d) {
  if (!d || d.classes.join() !== HAND_CLASSES.join()) throw new Error("hu_equity.json: class order differs from HAND_CLASSES; re-export it with stalker/tools/web_vectors.py");
  NUM = new Float64Array(NC * NC); DEN = new Float64Array(NC * NC);
  for (let i = 0; i < NC; i++) for (let j = 0; j < NC; j++) {
    const n = d.pairs[i][j], e = d.equity[i][j];
    DEN[i * NC + j] = n; NUM[i * NC + j] = n * e;
  }
}
export async function loadEquityTable(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`hu_equity.json: HTTP ${r.status} from ${url}`);
  setEquityTable(await r.json());
}

function preflopEquity(w) {
  if (!NUM) throw new Error("preflop equity table not loaded: call setEquityTable() or loadEquityTable() first");
  const wc = new Float64Array(NC);
  for (let i = 0; i < N; i++) wc[COMBO_CLS[i]] += w[i];
  for (let c = 0; c < NC; c++) wc[c] /= CLASS_W[c];
  const eqc = new Float64Array(NC);
  for (let i = 0; i < NC; i++) {
    let n = 0.0, d = 0.0;
    const o = i * NC;
    for (let j = 0; j < NC; j++) { n += NUM[o + j] * wc[j]; d += DEN[o + j] * wc[j]; }
    eqc[i] = d > 0 ? n / d : 0.5;
  }
  const out = new Float64Array(N);
  for (let i = 0; i < N; i++) out[i] = eqc[COMBO_CLS[i]];
  return out;
}

const RUNOUT_CACHE = new Map();
/** Python _runouts: per sampled runout the usable combos, their stable score order, tie bounds. */
export function runouts(board) {
  const bk = board.join(",");
  const hit = RUNOUT_CACHE.get(bk);
  if (hit) return hit;
  const rng = new NumpyRng([20261028, ...board]);
  const onBoard = new Uint8Array(52);
  for (const c of board) onBoard[c] = 1;
  const live = [];
  for (let c = 0; c < 52; c++) if (!onBoard[c]) live.push(c);
  const need = 5 - board.length;
  const out = [];
  const hand = new Array(7);
  for (let r = 0; r < (need ? EQ_RUNOUTS : 1); r++) {
    const extra = need ? rng.choiceNoReplace(live, need) : [];
    const full = board.concat(extra);
    const dead = onBoard.slice();
    for (const c of extra) dead[c] = 1;
    const idx = [];
    for (let i = 0; i < N; i++) if (!dead[COMBO_HI[i]] && !dead[COMBO_LO[i]]) idx.push(i);
    const m = idx.length;
    const score = new Int32Array(m);
    for (let j = 0; j < 5; j++) hand[2 + j] = full[j];
    for (let t = 0; t < m; t++) { hand[0] = COMBO_HI[idx[t]]; hand[1] = COMBO_LO[idx[t]]; score[t] = evaluate(hand); }
    const order = Array.from({ length: m }, (_, t) => t).sort((x, y) => score[x] - score[y]);
    const lo = new Int32Array(m), hi = new Int32Array(m);
    for (let g = 0; g < m;) {
      let h = g;
      while (h < m && score[order[h]] === score[order[g]]) h++;
      for (let t = g; t < h; t++) { lo[order[t]] = g; hi[order[t]] = h; }
      g = h;
    }
    out.push({ idx: Int32Array.from(idx), order: Int32Array.from(order), lo, hi, extra });
  }
  if (RUNOUT_CACHE.size >= 64) RUNOUT_CACHE.delete(RUNOUT_CACHE.keys().next().value);
  RUNOUT_CACHE.set(bk, out);
  return out;
}

function boardDead(board) {
  const dead = new Uint8Array(N);
  for (let i = 0; i < N; i++) if (board.includes(COMBO_HI[i]) || board.includes(COMBO_LO[i])) dead[i] = 1;
  return dead;
}

/** Equity of every combo against range weights w (NaN where the combo collides with the board). */
export function equityVs(board, w) {
  if (!board.length) return preflopEquity(w);
  const acc = new Float64Array(N), cnt = new Float64Array(N);
  let cw = new Float64Array(N + 1);
  for (const { idx, order, lo, hi } of runouts(board)) {
    const m = idx.length;
    cw[0] = 0.0;
    for (let t = 0; t < m; t++) cw[t + 1] = cw[t] + w[idx[order[t]]];
    for (let t = 0; t < m; t++) {
      const i = idx[t], ww = w[i];
      const below = cw[lo[t]], upto = cw[hi[t]];
      const tot = cw[m] - ww;
      const tie = upto - below - ww;
      if (tot > 0) { acc[i] += (below + 0.5 * tie) / tot; cnt[i] += 1; }
    }
  }
  const out = new Float64Array(N);
  const dead = boardDead(board);
  for (let i = 0; i < N; i++) out[i] = dead[i] ? NaN : cnt[i] > 0 ? acc[i] / cnt[i] : 0.5;
  return out;
}

// Per range array (by identity) and board: seats that did not act keep the same array object.
const EQ_CACHE = new WeakMap();
function equityCached(board, w) {
  let per = EQ_CACHE.get(w);
  if (!per) { per = new Map(); EQ_CACHE.set(w, per); }
  const bk = board.join(",");
  let eq = per.get(bk);
  if (!eq) { eq = equityVs(board, w); per.set(bk, eq); }
  return eq;
}

/** k-step quantile scale of x under weights w; equal values share a step (-1 where w == 0). */
export function quantileBuckets(x, w, k) {
  const out = new Int32Array(x.length).fill(-1);
  const live = [];
  for (let i = 0; i < x.length; i++) if (w[i] > 0) live.push(i);
  if (!live.length) return out;
  const wl = Float64Array.from(live, (i) => w[i]);
  const total = npSum(wl);
  const order = Array.from({ length: live.length }, (_, t) => t).sort((a, b) => x[live[a]] - x[live[b]]);
  let cum = 0.0;
  for (let g = 0; g < order.length;) {
    let h = g, msum = 0.0;
    const v = x[live[order[g]]];
    while (h < order.length && x[live[order[h]]] === v) { msum += wl[order[h]]; h++; }
    const mass = msum / total;
    cum = cum + mass;
    const step = Math.min(Math.trunc((cum - mass / 2) * k), k - 1);
    for (let t = g; t < h; t++) out[live[order[t]]] = step;
    g = h;
  }
  return out;
}

// ---------------------------------------------------------------- game (stalker/e3/game.py)
export const BB = 100, SB = 50, STACK = 100 * BB, RAISE_CAP = 3;
const PREFLOP_RAISE = [2.5, 3.0, 2.2];
// Size menus, as stalker/e3/game.py (module doc there): v1 (the served policies), tp6 (#339), real (#382).
// Labels are read per spot: an open "r4" is 4BB, a raise "r4" is 4x the current bet.
export const MENUS = ["v1", "tp6", "real"];
const TP6_OPEN = [["r22", 2.2], ["r", 2.5], ["r3", 3.0]];                       // BB
const TP6_RAISE = [["r25", 2.5], ["r", 3.0], ["r4", 4.0]];                      // x the current bet
const TP6_BET = [["b33", 0.33], ["b50", 0.5], ["b75", 0.75], ["b100", 1.0], ["b150", 1.5]];   // x the pot
export const REAL_OPEN = [["r2", 2.0], ["r22", 2.2], ["r", 2.5], ["r3", 3.0], ["r35", 3.5], ["r4", 4.0], ["r5", 5.0],
  ["r6", 6.0], ["r8", 8.0], ["r10", 10.0]];
export const REAL_RAISE = [["r25", 2.5], ["r", 3.0], ["r4", 4.0], ["r5", 5.0], ["r7", 7.0], ["r10", 10.0]];
// Preflop re-raises by raise count before the re-raise (2 = facing an open: 3-bet, 3 = facing a 3-bet: 4-bet).
export const REAL_PREFLOP_RAISE = {
  2: [["r25", 2.5], ["r", 3.0], ["r35", 3.5], ["r4", 4.0], ["r5", 5.0]],
  3: [["r2", 2.0], ["r22", 2.2], ["r25", 2.5], ["r", 3.0]],
};
export const REAL_BET = [["b20", 0.2], ["b33", 0.33], ["b50", 0.5], ["b75", 0.75], ["b100", 1.0], ["b150", 1.5],
  ["b200", 2.0], ["b300", 3.0]];
export const SIZE_LABELS = [...new Set(["r", "b33", "b75", ...[TP6_OPEN, TP6_RAISE, TP6_BET, REAL_OPEN, REAL_RAISE, REAL_BET]
  .flatMap((t) => t.map(([name]) => name))])];   // every bet/raise label but "a"
const ISO_BASE = 250, ISO_PER_LIMPER = 100;
export const ALLIN_MERGE = 0.8;   // raise cap null: a raise to >= 80% of the stack is the all-in
const POSITIONS = { 6: ["UTG", "HJ", "CO", "BTN", "SB", "BB"], 9: ["UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN", "SB", "BB"] };

export function positionNames(n) {
  if (n === 2) return ["SB", "BB"];
  if (POSITIONS[n]) return POSITIONS[n].slice();
  return [...Array.from({ length: n - 3 }, (_, i) => `EP${i}`), "BTN", "SB", "BB"];
}
export function postflopOrder(n) {
  if (n === 2) return [1, 0];
  return [n - 2, n - 1, ...Array.from({ length: n - 2 }, (_, i) => i)];
}

/** The rules a policy was trained on, from its metadata ({menu, raise_cap}); v1 with cap 3 when absent. */
export function menuOf(meta) {
  const menu = meta && meta.menu != null ? meta.menu : "v1";
  if (!MENUS.includes(menu)) throw new Error(`policy menu ${JSON.stringify(menu)}: tpgto.js knows ${MENUS.join(", ")}; update tpgto.js to stalker/e3/game.py`);
  const raiseCap = meta && meta.raise_cap !== undefined ? meta.raise_cap : RAISE_CAP;
  return { menu, raiseCap };
}

/** A new hand. holes: n pairs; deck: remaining cards (board dealt from the front), or board. */
export function newHand({ n = 6, holes, board = null, deck = null, menu = "v1", raiseCap = RAISE_CAP }) {
  if (!(n >= 2 && n <= 9)) throw new Error(`n=${n}: E3 supports 2..9 players`);
  if (!MENUS.includes(menu)) throw new Error(`menu ${JSON.stringify(menu)}: use one of ${MENUS.join(", ")}`);
  if (!holes || holes.length !== n) throw new Error(`holes: need ${n} pairs`);
  const used = new Set(holes.flat());
  if (deck == null) {
    const b = board || [];
    for (const c of b) used.add(c);
    deck = [...b, ...Array.from({ length: 52 }, (_, c) => c).filter((c) => !used.has(c))];
  }
  const bet = new Array(n).fill(0);
  bet[n - 2] = SB; bet[n - 1] = BB;
  return Object.freeze({
    n, hole: holes.map((h) => [h[0], h[1]]), deck: deck.slice(), stack: bet.map((b) => STACK - b), bet,
    total: bet.slice(), folded: new Array(n).fill(false), acted: new Array(n).fill(false),
    street: 0, board: [], toAct: 0, raises: 1, lastRaise: BB, history: [], log: [], done: false,
    menu, raiseCap: raiseCap === undefined ? RAISE_CAP : raiseCap,
  });
}

/** G.deal given d = rng.permutation(52): hole i = (d[2i], d[2i+1]), deck = d[2n:]. */
export function dealFromPermutation(d, n = 6, rules = {}) {
  return newHand({ n, holes: Array.from({ length: n }, (_, i) => [d[2 * i], d[2 * i + 1]]), deck: d.slice(2 * n), ...rules });
}

const max = (a) => a.reduce((x, y) => (y > x ? y : x), -Infinity);
export function pot(s) { return s.total.reduce((x, y) => x + y, 0); }
export function toCall(s, p = s.toAct) { return max(s.bet) - s.bet[p]; }
export function live(s) { const o = []; for (let i = 0; i < s.n; i++) if (!s.folded[i]) o.push(i); return o; }
export function active(s) { const o = []; for (let i = 0; i < s.n; i++) if (!s.folded[i] && s.stack[i] > 0) o.push(i); return o; }

function nextToAct(s, p) {
  const order = s.street === 0 ? Array.from({ length: s.n }, (_, i) => i) : postflopOrder(s.n);
  const k = order.indexOf(p);
  for (const j of [...order.slice(k + 1), ...order.slice(0, k + 1)]) if (!s.folded[j] && s.stack[j] > 0) return j;
  return p;
}

function raiseTo(s) {
  const cur = max(s.bet);
  if (s.street === 0) {
    const k = Math.min(s.raises - 1, PREFLOP_RAISE.length - 1);
    return k === 0 ? pyRound(PREFLOP_RAISE[0] * BB) : pyRound(cur * PREFLOP_RAISE[k]);
  }
  return 3 * cur;
}

// [label, street total] for every bet/raise size the menu offers here, before the stack checks (G._sizes).
function sizes(s) {
  const cur = max(s.bet), p = s.toAct, call = toCall(s);
  if (s.menu === "v1") {
    if (call > 0 || s.street === 0) return [["r", Math.max(raiseTo(s), cur + s.lastRaise)]];
    return [["b33", 0.33], ["b75", 0.75]].map(([name, f]) => [name, s.bet[p] + Math.max(BB, pyRound(pot(s) * f))]);
  }
  const least = cur + s.lastRaise, real = s.menu === "real";
  const opens = real ? REAL_OPEN : TP6_OPEN, bets = real ? REAL_BET : TP6_BET;
  let raises = real ? REAL_RAISE : TP6_RAISE;
  if (s.street === 0 && s.raises <= 1) {
    let limpers = 0;
    for (let i = 0; i < s.n - 1; i++) if (s.bet[i] === BB) limpers++;   // the big blind's own BB is not a limp
    if (limpers && real) return opens.map(([name, x]) => [name, Math.max(least, pyRound(x * BB) + ISO_PER_LIMPER * limpers)]);
    if (limpers) return [["r", Math.max(least, ISO_BASE + ISO_PER_LIMPER * limpers)]];
    return opens.map(([name, x]) => [name, Math.max(least, pyRound(x * BB))]);
  }
  if (real && s.street === 0) raises = REAL_PREFLOP_RAISE[s.raises] || [];   // past the 4-bet: all in only
  if (call > 0) return raises.map(([name, x]) => [name, Math.max(least, pyRound(x * cur))]);
  return bets.map(([name, f]) => [name, s.bet[p] + Math.max(BB, pyRound(pot(s) * f))]);
}

/** The raise cap on this street (null = none): the real menu caps preflop at RAISE_CAP (G.street_cap). */
export function streetCap(s) { return s.menu === "real" && s.street === 0 ? RAISE_CAP : s.raiseCap; }

// Sizes kept after the stack checks: below all in by more than 1BB (and below ALLIN_MERGE of the stack
// when the street has no cap), each chip amount once (G._offered).
function offered(s) {
  const p = s.toAct, room = s.stack[p] + s.bet[p];
  const top = streetCap(s) !== null ? room - BB : Math.min(room - BB, ALLIN_MERGE * room);
  const out = [];
  for (const [name, to] of sizes(s)) if (to < top && out.every(([, t]) => t !== to)) out.push([name, to]);
  return out;
}

export function legal(s) {
  if (s.done) return [];
  const p = s.toAct, call = toCall(s);
  const others = active(s).filter((i) => i !== p);
  const acts = [];
  if (call > 0) acts.push("f");
  acts.push(call > 0 || s.street === 0 ? "c" : "k");
  if (s.stack[p] > call && others.length && !s.acted[p]) {   // acted and still to act: a short all in did not reopen
    const cap = streetCap(s);
    if (cap === null || s.raises < cap + (s.street === 0 ? 1 : 0)) for (const [name] of offered(s)) acts.push(name);
    acts.push("a");
  }
  return acts;
}

/** The actor's street total after action a (a check keeps the current bet). */
export function amountTo(s, a) {
  const p = s.toAct, room = s.stack[p] + s.bet[p];
  if (a === "k" || a === "f") return s.bet[p];
  if (a === "a") return room;
  if (a === "c") return Math.min(max(s.bet), room);
  for (const [name, to] of sizes(s)) if (name === a) return to;
  throw new Error(`unknown action ${a} for menu ${s.menu}`);
}

/**
 * The bet/raise sizes a menu offers the actor here, smallest first, with the all in: [{a, to}].
 * By default the hand's own menu. sizeMenu(s, "real", null) gives the real-play sizes (postflop
 * without a cap, as the real training job) on a hand played under any menu: chips, stacks and the
 * raise count are the hand's, only the size table and the postflop cap change.
 */
export function sizeMenu(s, menu = s.menu, raiseCap = s.raiseCap) {
  const t = menu === s.menu && raiseCap === s.raiseCap ? s : { ...s, menu, raiseCap };
  const lg = new Set(legal(t)), room = t.stack[t.toAct] + t.bet[t.toAct];
  const out = offered(t).filter(([a]) => lg.has(a)).map(([a, to]) => ({ a, to }));
  if (lg.has("a")) out.push({ a: "a", to: room });
  return out.sort((x, y) => x.to - y.to);
}

function streetClosed(s) {
  const act = active(s), top = max(s.bet);
  if (act.some((i) => s.bet[i] !== top)) return false;
  return act.length <= 1 || act.every((i) => s.acted[i]);
}

function dealStreet(s) {
  const k = s.street === 0 ? 3 : 1;
  const ns = {
    ...s, street: s.street + 1, board: s.board.concat(s.deck.slice(0, k)), deck: s.deck.slice(k),
    bet: new Array(s.n).fill(0), raises: 0, lastRaise: BB, acted: new Array(s.n).fill(false), history: s.history.concat(["/"]),
  };
  const first = postflopOrder(s.n).find((i) => !s.folded[i] && s.stack[i] > 0);
  ns.toAct = first === undefined ? s.n - 2 : first;
  return ns;
}

function afterClose(s) {
  if (live(s).length === 1) return { ...s, done: true };
  if (active(s).length <= 1) {
    while (s.street < 3) s = dealStreet(s);
    return { ...s, done: true };
  }
  if (s.street === 3) return { ...s, done: true };
  return dealStreet(s);
}

export function apply(s, a) {
  const acts = legal(s);
  if (!acts.includes(a)) throw new Error(`illegal action ${JSON.stringify(a)} after ${s.history.join(" ")}; legal: ${acts.join(",")}`);
  if (a === "f") return act(s, "f", null);
  return act(s, a, a === "k" ? s.bet[s.toAct] : amountTo(s, a));
}

/** A full raise (at least the last raise) reopens the betting; a short all in below it does not (G._reopens). */
function reopens(s, to) { return to - max(s.bet) >= s.lastRaise; }

// One action with its real street total `to` (null for a fold); `label` is the menu action that
// goes into the history (for an off-menu bet, its translation).
function act(s, label, to, real = null) {
  const p = s.toAct;
  const hist = s.history.concat([`${p}:${label}`]);
  const log = s.log.concat([{ seat: p, action: label, to, ...(real ? { real: true } : {}) }]);
  let ns;
  if (to === null) {
    const folded = s.folded.slice(); folded[p] = true;
    ns = { ...s, folded, history: hist, log };
    if (live(ns).length === 1) return Object.freeze({ ...ns, done: true });
  } else {
    const add = to - s.bet[p];
    const stack = s.stack.slice(), bet = s.bet.slice(), total = s.total.slice();
    stack[p] -= add; bet[p] = to; total[p] += add;
    const top = max(s.bet), raised = to > top;
    const acted = raised && reopens(s, to) ? new Array(s.n).fill(false) : s.acted.slice();
    acted[p] = true;
    ns = { ...s, stack, bet, total, acted, history: hist, log, raises: s.raises + (raised ? 1 : 0),
      lastRaise: raised ? Math.max(s.lastRaise, to - top) : s.lastRaise };
  }
  if (streetClosed(ns)) return Object.freeze(afterClose(ns));
  return Object.freeze({ ...ns, toAct: nextToAct(ns, p) });
}

// ---------------------------------------------------------------- real no-limit sizes
// A human may bet or raise to any street total from the minimum raise to all in. The policy table
// only knows the menu, so an off-menu size is translated to a menu action (pseudo-harmonic mapping,
// Ganzfried & Sandholm 2013) for the history label, the key lookup and the range update.

/** {min, max} street totals the actor may bet/raise to, or null when only fold/call/check remain. */
export function betRange(s) {
  if (s.done) return null;
  const p = s.toAct, call = toCall(s), room = s.stack[p] + s.bet[p];
  if (!(s.stack[p] > call && !s.acted[p] && active(s).some((i) => i !== p))) return null;
  const min = max(s.bet) + Math.max(s.lastRaise, BB);
  return { min: Math.min(min, room), max: room };
}

/** Bet size as a fraction of the pot after calling: the x of the pseudo-harmonic mapping. */
export function potFraction(s, to) {
  const top = max(s.bet), call = toCall(s);
  return (to - top) / (pot(s) + call);
}

/**
 * stalker/e3/translate.split: [{a, p}] for a bet/raise to street total `to` (TP.md section 6).
 * The legal menu sizes (and the all in) sorted by chips; an exact size maps to itself, a size below
 * the smallest to it; between neighbours A < B (pot fractions a < b, size x) A gets
 * f = (b - x)(1 + a) / ((b - a)(1 + x)) and B gets 1 - f. A capped street leaves only "a".
 */
export function splitBet(s, to) {
  const r = betRange(s);
  if (!r) throw new Error(`no bet or raise possible here; legal: ${legal(s).join(",")}`);
  if (!Number.isInteger(to)) throw new Error(`bet to ${to}: chips are integers`);
  if (to > r.max) throw new Error(`bet to ${to} is more than all in (${r.max}); choose ${r.min} (min raise) to ${r.max}`);
  if (to < r.min) throw new Error(`bet to ${to} is below the min raise ${r.min}; choose ${r.min} to ${r.max} (all in)`);
  const menu = sizeMenu(s);
  const exact = menu.find((m) => m.to === to);
  if (exact) return [{ a: exact.a, p: 1.0 }];
  if (to < menu[0].to) return [{ a: menu[0].a, p: 1.0 }];
  let j = 1;
  while (menu[j].to < to) j++;
  const A = menu[j - 1], B = menu[j];
  const a = potFraction(s, A.to), b = potFraction(s, B.to), x = potFraction(s, to);
  const f = (b - x) * (1 + a) / ((b - a) * (1 + x));
  return [{ a: A.a, p: f }, { a: B.a, p: 1.0 - f }];
}

/** stalker/e3/translate.sample: one label from splitBet with a seeded NumpyRng (one draw when split). */
export function sampleBet(s, to, rng) {
  const out = splitBet(s, to);
  if (out.length === 1) return out[0].a;
  if (!rng || typeof rng.random !== "function") throw new Error("sampleBet: pass a seeded NumpyRng (the AI's reading is random, TP.md section 6)");
  return rng.random() < out[0].p ? out[0].a : out[1].a;
}

/**
 * Menu translation of a real bet/raise to street total `to`:
 * {split, action, prob, lower, upper}. `split` is splitBet (grading weighs the score of each label by
 * its probability). With a seeded NumpyRng, `action` is the AI's reading drawn as sampleBet; without
 * one it is the likelier side (display only, never the reading). `prob` is `action`'s probability.
 */
export function translateBet(s, to, rng = null) {
  const split = splitBet(s, to);
  let action;
  if (split.length === 1) action = split[0].a;
  else if (rng) action = rng.random() < split[0].p ? split[0].a : split[1].a;
  else action = split[0].p >= split[1].p ? split[0].a : split[1].a;
  const m = split.find((x) => x.a === action);
  return { split, action, prob: m.p, lower: split[0].a, upper: split[split.length - 1].a };
}

/** Score weighted by the split: sum of p x score(label) (TP.md section 6 grading). */
export function splitScore(split, score) {
  let v = 0.0;
  for (const { a, p } of split) v += p * score(a);
  return v;
}

// stalker/e3/translate.py pre-registered rule (#417); the constants and their calibration live there.
export const TV_HIGH = 0.25, GAP_HIGH = 2.0, F_BAND = [0.2, 0.8];

/**
 * stalker/e3/translate.high_translation_error: true when the split of a bet/raise to `to` is not a
 * trustworthy reading. One neighbour all in and the other not, below ALLIN_MERGE of the stack; or the
 * size far from both (F_BAND) with neighbours more than GAP_HIGH apart as pot fractions.
 */
export function translationError(s, to) {
  const split = splitBet(s, to);
  if (split.length < 2) return false;
  const [A, B] = split, p = s.toAct;
  if (B.a === "a") return to < ALLIN_MERGE * (s.stack[p] + s.bet[p]);
  if (!(F_BAND[0] < A.p && A.p < F_BAND[1])) return false;
  const menu = sizeMenu(s), ta = menu.find((m) => m.a === A.a).to, tb = menu.find((m) => m.a === B.a).to;
  return potFraction(s, tb) > GAP_HIGH * potFraction(s, ta);
}

/**
 * A real bet/raise to street total `to` (any size in betRange); chips move by `to`, the history gets
 * the AI's reading. `how`: a seeded NumpyRng (drawn as sampleBet) or a label already read for this
 * bet (it must be in the split).
 */
export function applyBet(s, to, how) {
  let label;
  if (typeof how === "string") {
    const split = splitBet(s, to);
    if (!split.some((x) => x.a === how)) throw new Error(`applyBet: ${how} is not a reading of ${to} (split ${split.map((x) => x.a).join(",")})`);
    label = how;
  } else label = sampleBet(s, to, how);
  return act(s, label, to, to !== amountTo(s, label));
}

/** Net chips per seat relative to the start of the hand (sums to zero). */
export function payoff(s) {
  if (!s.done) throw new Error("hand is not over");
  const lv = live(s), out = s.total.map((t) => -t), P = pot(s);
  if (lv.length === 1) { out[lv[0]] += P; return out; }
  const score = new Map(lv.map((i) => [i, evaluate([...s.hole[i], ...s.board])]));
  const best = max([...score.values()]);
  const winners = postflopOrder(s.n).filter((i) => score.has(i) && score.get(i) === best);
  const share = Math.floor(P / winners.length), odd = P % winners.length;
  for (const i of winners) out[i] += share;
  out[winners[0]] += odd;
  return out;
}

// ---------------------------------------------------------------- TP keys (stalker/e3/tp_key.py)
export const TIER_K = { beginner: 5, mid: 11, pro: 17 };
export const TIER_DEPTH = { beginner: "basic", mid: "full", pro: "pro" };
export const K_PRO = TIER_K.pro;
// board.nut steps in the pro table: tp_key.NUT_K (5 since #332/#338). Pro checkpoints carry it as
// "nut_k"; checkNutK refuses a table built on another grid, as E3MCCFR.from_state does. The node test
// fails when this differs from the Python constant recorded in the vectors.
export const NUT_K = 5;
export function checkNutK(nutK) {
  if (nutK !== undefined && nutK !== NUT_K) throw new Error(`policy board.nut has ${nutK} steps; tpgto.js uses ${NUT_K}: update NUT_K to stalker/e3/tp_key.py and rerun python -m stalker.tools.web_vectors`);
}
export const NUT_BASE = 1000;
export const NUT_TOP = 0.10;
const FOLDY_MIN_OPPS = 6, FOLDY_PRIOR = 0.5, FOLDY_PRIOR_N = 6.0;
const AGGRESSIVE = new Set([...SIZE_LABELS, "a"]);   // tp_key.AGGRESSIVE: every menu's bet/raise labels
const POT_ODDS_EDGES = [0.2, 0.3, 0.4];
const SPR_EDGES = [1.0, 3.0, 6.0];

export function initialRanges(n) { return Array.from({ length: n }, () => new Float64Array(N).fill(1)); }

export function initiative(s, seat) {
  if (s.street === 0) return 0;
  let st = 0, last = null;
  for (const h of s.history) {
    if (h === "/") { st++; continue; }
    if (st !== s.street - 1) continue;
    const [p, a] = h.split(":");
    if (AGGRESSIVE.has(a)) last = Number(p);
  }
  return last === null ? 0 : last === seat ? 1 : 2;
}
export function raiseLevel(s) { return Math.min(s.street === 0 ? s.raises - 1 : s.raises, 3); }
export function potOddsStep(s, seat) {
  const call = toCall(s, seat);
  if (call <= 0) return 0;
  return 1 + searchRight(POT_ODDS_EDGES, call / (pot(s) + call));
}
export function sprStep(s, seat) {
  if (s.street === 0) return 0;
  const others = live(s).filter((i) => i !== seat).map((i) => s.stack[i]);
  const eff = Math.min(s.stack[seat], others.length ? max(others) : 0);
  return searchRight(SPR_EDGES, eff / Math.max(pot(s), 1));
}
export function positionGroup(n, seat) {
  if (seat >= n - 2) return "blind";
  return seat >= n - 4 ? "late" : "early";
}
export function scaleStep(v, k) { return Math.min(Math.trunc(v * k / 100.0 + 1e-9), k - 1); }
export function foldyStep(folds = 0, opportunities = 0) {
  if (opportunities < FOLDY_MIN_OPPS) return "N";
  const rate = (folds + FOLDY_PRIOR * FOLDY_PRIOR_N) / (opportunities + FOLDY_PRIOR_N);
  return String(scaleStep(100.0 * rate, K_PRO));
}

export function publicKey(s, seat, depth = "full") {
  const nOpp = Math.min(live(s).length - 1, 3);
  const lg = legal(s).join("");
  if (lg === "fc" || lg === "c") return `call|${s.street}|${nOpp}|${potOddsStep(s, seat)}|${lg}`;
  if (depth === "basic") {
    return `b|${positionGroup(s.n, seat)}|${s.street}|${Math.min(nOpp, 2)}|${Math.min(raiseLevel(s), 2)}|${potOddsStep(s, seat)}|${lg}`;
  }
  const full = `${seat}|${s.street}|${nOpp}|${raiseLevel(s)}|${initiative(s, seat)}|${potOddsStep(s, seat)}|${sprStep(s, seat)}|${lg}`;
  return depth === "pro" ? `p|${full}|f${foldyStep()}` : full;
}

export function key(pub, step) {
  if (step >= NUT_BASE) return `${pub}|e${step % NUT_BASE}|n${Math.floor(step / NUT_BASE) - 1}`;
  return `${pub}|e${step}`;
}

export function multiEquity(s, seat, ranges) {
  let eq = new Float64Array(N).fill(1);
  for (const q of live(s)) {
    if (q === seat) continue;
    const e = equityCached(s.board, ranges[q]);
    const nx = new Float64Array(N);
    for (let i = 0; i < N; i++) nx[i] = eq[i] * e[i];
    eq = nx;
  }
  return eq;
}

const UNIFORM = new Float64Array(N).fill(1);

/** np.quantile(a, q) with the default linear method. */
function npQuantile(a, q) {
  const s = Float64Array.from(a).sort();
  const n = s.length, vi = (n - 1) * q;
  if (vi >= n - 1) return s[n - 1];
  const prev = Math.floor(vi);
  const lo = s[prev], hi = s[prev + 1], g = vi - prev, diff = hi - lo;
  return g >= 0.5 ? hi - diff * (1 - g) : lo + diff * g;
}

export function boardNut(s, seat, ranges) {
  const lv = live(s);
  if (s.street === 0 || lv.length !== 2) return null;
  const opp = lv[1] === seat ? lv[0] : lv[1];
  const strength = equityCached(s.board, UNIFORM);
  const okv = [];
  for (let i = 0; i < N; i++) if (!Number.isNaN(strength[i])) okv.push(strength[i]);
  const qv = npQuantile(okv, 1 - NUT_TOP);
  const share = [];
  const w = new Float64Array(N), wt = new Float64Array(N);
  for (const q of [seat, opp]) {
    for (let i = 0; i < N; i++) {
      const ok = !Number.isNaN(strength[i]);
      w[i] = ranges[q][i] * (ok ? 1 : 0);
      wt[i] = w[i] * (ok && strength[i] >= qv ? 1 : 0);
    }
    const ws = npSum(w);
    share.push(ws > 0 ? npSum(wt) / ws : 0.0);
  }
  const total = share[0] + share[1];
  return total <= 0 ? 50.0 : 100.0 * share[1] / total;
}

export function nutStep(s, seat, ranges) {
  const v = boardNut(s, seat, ranges);
  return v === null ? null : scaleStep(v, NUT_K);
}

export function equitySteps(s, seat, ranges, k) {
  const eq = multiEquity(s, seat, ranges);
  const x = new Float64Array(N), w = new Float64Array(N);
  for (let i = 0; i < N; i++) { const ok = !Number.isNaN(eq[i]); x[i] = ok ? eq[i] : 0; w[i] = ok ? 1 : 0; }
  const steps = quantileBuckets(x, w, k);
  if (k === K_PRO) {
    const nut = nutStep(s, seat, ranges);
    if (nut !== null) for (let i = 0; i < N; i++) if (steps[i] >= 0) steps[i] += NUT_BASE * (nut + 1);
  }
  return steps;
}

export function myStep(steps, s, seat) { return steps[comboIndex(s.hole[seat])]; }

export function updateRange(ranges, seat, probs) {
  const out = ranges.slice();
  const r = new Float64Array(N);
  for (let i = 0; i < N; i++) r[i] = ranges[seat][i] * probs[i];
  out[seat] = r;
  return out;
}

// ---------------------------------------------------------------- policy-facing API
function tierOf(tier) {
  if (!(tier in TIER_K)) throw new Error(`tier ${JSON.stringify(tier)}: use one of ${Object.keys(TIER_K).join(", ")}`);
  return { k: TIER_K[tier], depth: TIER_DEPTH[tier] };
}

function policyRow(policy, k, m) {
  const p = policy instanceof Map ? policy.get(k) : policy ? policy[k] : undefined;
  if (p && p.length === m) return p;
  return null;
}

/** The actor's TP key at state s: {seat, acts, public, steps, step, key}. */
export function decisionKey(s, ranges, tier) {
  const { k, depth } = tierOf(tier);
  const seat = s.toAct;
  const steps = equitySteps(s, seat, ranges, k);
  const pub = publicKey(s, seat, depth);
  const step = myStep(steps, s, seat);
  return { seat, tier, acts: legal(s), public: pub, steps, step, key: key(pub, step) };
}

export function equityStepOf(s, seat, ranges, tier) {
  return myStep(equitySteps(s, seat, ranges, tierOf(tier).k), s, seat);
}

/** Per-combo action probabilities, row-major (combo i, action a) at i*m + a; zeros on dead combos. */
export function seatProbs(policy, pub, steps, m) {
  const out = new Float64Array(N * m);
  const rows = new Map();
  const uni = 1.0 / m;
  for (let i = 0; i < N; i++) {
    const v = steps[i];
    if (v < 0) continue;
    let row = rows.get(v);
    if (row === undefined) { row = policyRow(policy, key(pub, v), m); rows.set(v, row); }
    for (let a = 0; a < m; a++) out[i * m + a] = row ? row[a] : uni;
  }
  return out;
}

/** decisionKey plus the policy row for the actor's real hole (uniform when the table is silent). */
export function actionProbs(policy, s, ranges, tier) {
  const d = decisionKey(s, ranges, tier);
  const m = d.acts.length;
  const row = policyRow(policy, d.key, m);
  return { ...d, probs: row ? Array.from(row) : new Array(m).fill(1.0 / m), fromTable: !!row };
}

/** Ranges after the actor of decision d took `action` (name or index). */
export function updateRanges(policy, d, ranges, action) {
  const m = d.acts.length;
  const a = typeof action === "number" ? action : d.acts.indexOf(action);
  if (a < 0 || a >= m) throw new Error(`action ${JSON.stringify(action)} not in ${d.acts.join(",")}`);
  const P = seatProbs(policy, d.public, d.steps, m);
  const col = new Float64Array(N);
  for (let i = 0; i < N; i++) col[i] = P[i * m + a];
  return updateRange(ranges, d.seat, col);
}
