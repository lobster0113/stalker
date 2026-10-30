// tells.js — how much the hero's sizing, timing and lines reveal hand strength (#430).
//
// A dependency-free ES module so node can test it on synthetic logs (web/app/test/tells.test.mjs).
// The Training Game (web/demo/index.html) logs one record per hero decision and renders tellReport().
//
// Decision record (one per hero action):
//   {hand, street: 0..3, action: "fold"|"check"|"call"|"bet"|"raise", sizePct: bet/raise size in % of
//    the pot after calling (null otherwise), ms: turn shown -> action fixed, strength: 0..1 equity vs
//    the public ranges, madeClass: 0..8 (HAND_NAMES), forced: only one legal action, timed: false when
//    ms is not an action time (Guided mode answers the TP cards first), spot: "cbet"|"donk"|"xr"|null,
//    gtoAgg: TP-GTO policy's bet/raise probability in the same state (null without the engine mirror)}
//   spot: "cbet" = flop, hero was the preflop aggressor, no bet yet; "donk" = postflop lead into the
//   previous street's aggressor before they act; "xr" = hero checked earlier this street and now faces
//   a bet (raise = check-raise, call = check-call).
// Showdown record: {hand, madeClass, strength}: a hand the opponents saw.
//
// API: tellMetrics(decisions, showdowns) -> metrics; tellReport(decisions, showdowns) -> {metrics, leaks,
//   notes} with Korean text. Every metric carries n, min and enough; a leak needs enough and an effect
//   above the preset thresholds in TH.

// Minimum samples and leak thresholds, fixed before looking at any player's data.
// Why these: at n = 20 a strength-blind hero's Spearman rho has sd ~ 0.23, so |rho| >= 0.5 plus
// MI >= 0.15 bits (after the Miller-Madow bias correction) is rarely met by chance (about 3% of
// synthetic strength-blind heroes at exactly n = 20, 0.1% at n = 40); timing also asks for a 1.5x gap
// between tercile medians (about 5% at n = 20). Lines are flagged only at near-pure frequencies.
export const TH = {
  size: { min: 20, rho: 0.5, mi: 0.15 },
  timing: { min: 20, perTercile: 5, rho: 0.45, ratio: 1.5, instantMs: 300 },
  cbet: { min: 10, high: 0.95, low: 0.15, gapMin: 4, gap: 0.2 },
  xr: { min: 6, valueShare: 0.9 },
  donk: { min: 6, valueShare: 0.9 },
  river: { min: 8, bluffLow: 0.1, bluffHigh: 0.6 },
  checkCall: { min: 10, strongLow: 0.05 },
  gto: { min: 10, diff: 0.3 },
  value: 0.6, // equity at or above which a bet is value
  bluff: 0.35, // equity below which a bet is a bluff
};
// Size buckets (% pot): ~1/3, ~1/2, ~3/4, ~pot, overbet.
export const SIZE_EDGES = [40, 62, 88, 125];
export const STREETS = ["프리플랍", "플랍", "턴", "리버"];
export const HAND_NAMES = ["하이카드", "원페어", "투페어", "트립스", "스트레이트", "플러시", "풀하우스", "포카드", "스트레이트 플러시"];
const AGG = new Set(["bet", "raise"]);

export const sizeBucket = pct => { let b = 0; while (b < SIZE_EDGES.length && pct >= SIZE_EDGES[b]) b++; return b; };

// Average ranks so ties (the same size used many times) do not invent an order.
export function ranks(xs) {
  const idx = xs.map((x, i) => i).sort((a, b) => xs[a] - xs[b]), r = new Array(xs.length);
  for (let i = 0; i < idx.length;) {
    let j = i; while (j + 1 < idx.length && xs[idx[j + 1]] === xs[idx[i]]) j++;
    for (let k = i; k <= j; k++) r[idx[k]] = (i + j) / 2;
    i = j + 1;
  }
  return r;
}
export function spearman(xs, ys) {
  const n = xs.length; if (n < 3) return 0;
  const rx = ranks(xs), ry = ranks(ys), mx = (n - 1) / 2;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const a = rx[i] - mx, b = ry[i] - mx; sxy += a * b; sxx += a * a; syy += b * b; }
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : 0; // a constant size reveals nothing
}
// Terciles by rank within the sample: 0 = weakest third, 2 = strongest.
export function terciles(xs) {
  const idx = xs.map((x, i) => i).sort((a, b) => xs[a] - xs[b] || a - b), t = new Array(xs.length);
  idx.forEach((i, k) => { t[i] = Math.min(2, Math.floor(3 * k / xs.length)); });
  return t;
}
// Plug-in mutual information in bits minus the Miller-Madow bias (cells - rows - cols + 1) / (2 n ln 2):
// small samples otherwise always look informative.
export function mutualInfo(xs, ys) {
  const n = xs.length; if (!n) return 0;
  const jx = new Map(), cx = new Map(), cy = new Map();
  for (let i = 0; i < n; i++) { const k = xs[i] + "|" + ys[i]; jx.set(k, (jx.get(k) || 0) + 1); cx.set(xs[i], (cx.get(xs[i]) || 0) + 1); cy.set(ys[i], (cy.get(ys[i]) || 0) + 1); }
  let mi = 0;
  for (const [k, c] of jx) { const [x, y] = k.split("|"); mi += c / n * Math.log2(c * n / (cx.get(+x) * cy.get(+y))); }
  return Math.max(0, mi - (jx.size - cx.size - cy.size + 1) / (2 * n * Math.LN2));
}
const median = xs => { if (!xs.length) return null; const s = xs.slice().sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const mean = xs => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
const share = (xs, f) => xs.length ? xs.filter(f).length / xs.length : null;
const valid = d => d && Number.isFinite(d.strength);

function sizeTell(ds) {
  const xs = ds.map(d => d.sizePct), ys = ds.map(d => d.strength), n = ds.length, m = { n, min: TH.size.min, enough: n >= TH.size.min };
  if (!n) return m;
  const t = terciles(ys), by = k => xs.filter((x, i) => t[i] === k);
  Object.assign(m, { rho: spearman(xs, ys), mi: mutualInfo(xs.map(sizeBucket), t), strongPct: mean(by(2)), weakPct: mean(by(0)) });
  m.leak = m.enough && Math.abs(m.rho) >= TH.size.rho && m.mi >= TH.size.mi;
  return m;
}
function timingTell(ds) {
  const e = ds.filter(d => !d.forced && d.timed !== false && Number.isFinite(d.ms) && d.ms >= TH.timing.instantMs);
  const n = e.length, t = terciles(e.map(d => d.strength)), med = [0, 1, 2].map(k => median(e.filter((d, i) => t[i] === k).map(d => d.ms)));
  const per = [0, 1, 2].map(k => t.filter(x => x === k).length);
  const m = { n, min: TH.timing.min, excluded: ds.length - n, enough: n >= TH.timing.min && per.every(c => c >= TH.timing.perTercile), medians: med };
  if (!n) return m;
  m.rho = spearman(e.map(d => d.ms), e.map(d => d.strength));
  const lo = Math.min(...med.filter(x => x != null)), hi = Math.max(...med.filter(x => x != null));
  m.ratio = lo > 0 ? hi / lo : null;
  m.leak = m.enough && Math.abs(m.rho) >= TH.timing.rho && m.ratio >= TH.timing.ratio;
  return m;
}
const valueShare = (ds, min) => { const n = ds.length, m = { n, min, enough: n >= min }; if (n) m.valueShare = share(ds, d => d.strength >= TH.value); return m; };

export function tellMetrics(decisions = [], showdowns = []) {
  const ds = decisions.filter(valid);
  const size = [0, 1, 2, 3].map(st => sizeTell(ds.filter(d => d.street === st && AGG.has(d.action) && Number.isFinite(d.sizePct))));
  const timing = timingTell(ds);
  // c-bet: frequency, the strength gap between betting and checking, and the policy's frequency.
  const cs = ds.filter(d => d.spot === "cbet" && (AGG.has(d.action) || d.action === "check"));
  const cb = cs.filter(d => AGG.has(d.action)), ck = cs.filter(d => d.action === "check");
  const cbet = { n: cs.length, min: TH.cbet.min, enough: cs.length >= TH.cbet.min, rate: share(cs, d => AGG.has(d.action)),
    betEq: mean(cb.map(d => d.strength)), checkEq: mean(ck.map(d => d.strength)), nBet: cb.length, nCheck: ck.length };
  cbet.gapEnough = cb.length >= TH.cbet.gapMin && ck.length >= TH.cbet.gapMin;
  cbet.gap = cbet.gapEnough ? cbet.betEq - cbet.checkEq : null;
  cbet.leakFreq = cbet.enough && (cbet.rate >= TH.cbet.high || cbet.rate <= TH.cbet.low);
  cbet.leakGap = cbet.gapEnough && cbet.gap >= TH.cbet.gap;
  const cg = cs.filter(d => Number.isFinite(d.gtoAgg));
  const gto = { n: cg.length, min: TH.gto.min, enough: cg.length >= TH.gto.min, rate: share(cg, d => AGG.has(d.action)), policy: mean(cg.map(d => d.gtoAgg)) };
  gto.leak = gto.enough && Math.abs(gto.rate - gto.policy) >= TH.gto.diff;
  const xr = valueShare(ds.filter(d => d.spot === "xr" && d.action === "raise"), TH.xr.min); xr.leak = xr.enough && xr.valueShare >= TH.xr.valueShare;
  const donk = valueShare(ds.filter(d => d.spot === "donk" && AGG.has(d.action)), TH.donk.min); donk.leak = donk.enough && donk.valueShare >= TH.donk.valueShare;
  const rb = ds.filter(d => d.street === 3 && AGG.has(d.action));
  const river = { n: rb.length, min: TH.river.min, enough: rb.length >= TH.river.min, value: rb.filter(d => d.strength >= TH.value).length, bluff: rb.filter(d => d.strength < TH.bluff).length };
  river.bluffShare = rb.length ? river.bluff / rb.length : null;
  river.leakLow = river.enough && river.bluffShare < TH.river.bluffLow;
  river.leakHigh = river.enough && river.bluffShare > TH.river.bluffHigh;
  const cc = ds.filter(d => d.spot === "xr" && d.action === "call");
  const checkCall = { n: cc.length, min: TH.checkCall.min, enough: cc.length >= TH.checkCall.min, meanEq: mean(cc.map(d => d.strength)), strongShare: share(cc, d => d.strength >= TH.value) };
  checkCall.leak = checkCall.enough && checkCall.strongShare < TH.checkCall.strongLow;
  // Showdown evidence: what the opponents saw, keyed by the line that led there.
  const byHand = new Map();
  for (const d of ds) { if (!byHand.has(d.hand)) byHand.set(d.hand, []); byHand.get(d.hand).push(d); }
  const lines = new Map();
  for (const s of showdowns) {
    const line = lineOf(byHand.get(s.hand) || []);
    if (!lines.has(line)) lines.set(line, []);
    lines.get(line).push(s.madeClass);
  }
  const showdown = { n: showdowns.length, lines: [...lines].map(([line, made]) => ({ line, n: made.length, made })).sort((a, b) => b.n - a.n) };
  return { size, timing, cbet, gto, xr, donk, river, checkCall, showdown, decisions: ds.length };
}
const LETTER = { fold: "F", check: "X", call: "C", bet: "B", raise: "R" };
export function lineOf(ds) {
  const parts = [];
  for (let st = 0; st < 4; st++) { const a = ds.filter(d => d.street === st).map(d => LETTER[d.action] || "?").join(""); if (a) parts.push(`${STREETS[st]} ${a}`); }
  return parts.join(" · ") || "—";
}

const pc = x => Math.round(x * 100);
const f2 = x => x.toFixed(2);
const lack = m => `데이터 부족 (n=${m.n}/최소 ${m.min})`;
// Korean report: each leak with numbers and one fix; below the minimum it says so instead of judging.
export function tellReport(decisions = [], showdowns = []) {
  const m = tellMetrics(decisions, showdowns), leaks = [], rows = [];
  m.size.forEach((s, st) => {
    const name = `${STREETS[st]} 벳 크기`;
    if (!s.enough) { rows.push({ id: `size${st}`, name, text: lack(s) }); return; }
    const text = `강할 때 평균 팟 ${Math.round(s.strongPct)}%, 약할 때 ${Math.round(s.weakPct)}% · 순위상관 ${f2(s.rho)} · 정보량 ${f2(s.mi)}비트 (n=${s.n})`;
    rows.push({ id: `size${st}`, name, text, leak: s.leak });
    if (s.leak) leaks.push({ id: `size${st}`, text: `${STREETS[st]}에서 벳 크기로 핸드 강도가 드러납니다: ${text}`, fix: `${STREETS[st]}에서는 밸류와 블러프에 같은 크기를 쓰세요. 크기를 바꾸려면 강도가 아니라 보드에 따라 바꾸세요.` });
  });
  const t = m.timing;
  if (!t.enough) rows.push({ id: "timing", name: "결정 시간", text: lack(t) + (t.n ? " · 강도 3구간마다 최소 " + TH.timing.perTercile + "회" : "") });
  else {
    const s = x => x == null ? "—" : (x / 1000).toFixed(1) + "초";
    const text = `약한 핸드 ${s(t.medians[0])}, 중간 ${s(t.medians[1])}, 강한 핸드 ${s(t.medians[2])} (중앙값) · 순위상관 ${f2(t.rho)} (n=${t.n}, 강제·0.3초 미만·Guided 제외 ${t.excluded})`;
    rows.push({ id: "timing", name: "결정 시간", text, leak: t.leak });
    if (t.leak) leaks.push({ id: "timing", text: `결정 시간으로 핸드 강도가 드러납니다: ${text}`, fix: "강하든 약하든 비슷한 시간(예: 매번 2~3초)을 두고 행동하세요." });
  }
  const c = m.cbet;
  if (!c.enough && !c.gapEnough) rows.push({ id: "cbet", name: "c-벳", text: lack(c) });
  else {
    const text = `c-벳 ${c.rate == null ? "—" : pc(c.rate) + "%"} (n=${c.n})` + (c.gapEnough ? ` · 벳할 때 평균 에퀴티 ${pc(c.betEq)}%, 체크할 때 ${pc(c.checkEq)}%` : "");
    rows.push({ id: "cbet", name: "c-벳", text, leak: c.leakFreq || c.leakGap });
    if (c.leakGap) leaks.push({ id: "cbet-gap", text: `c-벳 여부로 강도가 드러납니다: ${text}`, fix: "강한 핸드도 일부 체크하고, 약한 핸드도 일부 벳해서 체크 레인지와 벳 레인지가 둘 다 섞이게 하세요." });
    if (c.leakFreq) leaks.push({ id: "cbet-freq", text: `c-벳 빈도가 한쪽으로 치우쳤습니다: ${pc(c.rate)}% (n=${c.n})`, fix: c.rate >= TH.cbet.high ? "보드가 상대 레인지에 유리할 때는 체크도 섞으세요." : "내 레인지에 유리한 보드에서는 더 자주 c-벳하세요." });
  }
  const g = m.gto;
  if (g.n) {
    const text = `같은 스팟 c-벳: 나 ${pc(g.rate)}%, TP-GTO 정책 ${pc(g.policy)}% (n=${g.n})`;
    rows.push({ id: "gto", name: "TP-GTO와 비교", text: g.enough ? text : `${text} · ${lack(g)}`, leak: g.leak });
    if (g.leak) leaks.push({ id: "gto", text: `c-벳 빈도가 TP-GTO와 크게 다릅니다: ${text}`, fix: `c-벳 빈도를 정책의 ${pc(g.policy)}% 쪽으로 옮기세요.` });
  }
  for (const [id, name, subj, fix] of [["xr", "체크레이즈", "체크레이즈가", "체크레이즈에 드로·블러프도 섞으세요. 아니면 상대는 체크레이즈를 만나면 바로 접습니다."], ["donk", "돈크 벳", "돈크 벳이", "돈크 벳에 드로·블러프도 섞거나, 강한 핸드를 체크로도 두세요."]]) {
    const x = m[id];
    if (!x.enough) { rows.push({ id, name, text: lack(x) }); continue; }
    const text = `밸류(에퀴티 ${pc(TH.value)}% 이상) 비중 ${pc(x.valueShare)}% (n=${x.n})`;
    rows.push({ id, name, text, leak: x.leak });
    if (x.leak) leaks.push({ id, text: `${subj} 거의 항상 밸류입니다: ${text}`, fix });
  }
  const r = m.river;
  if (!r.enough) rows.push({ id: "river", name: "리버 벳 밸류:블러프", text: lack(r) });
  else {
    const text = `밸류 ${r.value} : 블러프 ${r.bluff} (블러프 ${pc(r.bluffShare)}%, n=${r.n})`;
    rows.push({ id: "river", name: "리버 벳 밸류:블러프", text, leak: r.leakLow || r.leakHigh });
    if (r.leakLow) leaks.push({ id: "river", text: `리버 벳이 곧 밸류입니다: ${text}`, fix: "리버에서 놓친 드로 같은 블러프를 밸류 2개당 1개 정도 섞으세요." });
    if (r.leakHigh) leaks.push({ id: "river", text: `리버 벳에 블러프가 너무 많습니다: ${text}`, fix: "리버 블러프를 줄이고 밸류 벳 쪽으로 옮기세요." });
  }
  const k = m.checkCall;
  if (!k.enough) rows.push({ id: "checkcall", name: "체크-콜 강도", text: lack(k) });
  else {
    const text = `평균 에퀴티 ${pc(k.meanEq)}%, 강한 핸드(${pc(TH.value)}% 이상) ${pc(k.strongShare)}% (n=${k.n})`;
    rows.push({ id: "checkcall", name: "체크-콜 강도", text, leak: k.leak });
    if (k.leak) leaks.push({ id: "checkcall", text: `체크-콜 레인지에 강한 핸드가 없습니다: ${text}`, fix: "강한 핸드도 가끔 체크-콜해서 체크-콜 레인지가 약하다고 읽히지 않게 하세요." });
  }
  const sd = m.showdown;
  rows.push({ id: "showdown", name: "쇼다운 증거", text: sd.n ? `상대가 쇼다운에서 본 핸드 ${sd.n}개 · ` + sd.lines.slice(0, 3).map(l => `${l.line}: ${l.made.map(x => HAND_NAMES[x] ?? "?").join(", ")}`).join(" / ") : "아직 쇼다운이 없어요." });
  return { metrics: m, rows, leaks };
}
