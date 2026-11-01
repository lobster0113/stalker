// 내 게임 저장·리플레이 (#465): pure helpers, no DOM. The page keeps `stalker.games` in localStorage.
// Shape: {schema:"stalker.games", schema_version:1, games:[{id, ts, tier, mode, n, hands:[hand]}]}
// hand: {no, cards, net, folded, board:[text], seats:[{i,name,pos,hero,stack}], acts:[act]}
// act:  {st, seat, hero, type, txt, to, pot, board, bets:[], stacks:[], folded:[], an?}
// an (hero decision on a TP-GTO table): {name, p, approx, top, topP, mix:[{name,p}], leak, eq, need, beats,
//       opps, reply:{canFold, weakFold, strongFold, strongOfContinuing, fold, weakShare}|null, tp:{total, worst:[{k,score}]}|null}
export const GAMES_SCHEMA = "stalker.games";
export const GAMES_VERSION = 1;
export const LIMITS = { games: 30, hands: 300, bytes: 1_500_000 };
export const GOOD_P = 0.25, WARN_P = 0.10;

const isObj = (x) => x && typeof x === "object" && !Array.isArray(x);
const finite = (x) => typeof x === "number" && Number.isFinite(x);

/** A hand that cannot be replayed (missing fields) is dropped on load instead of breaking the page. */
export function validHand(h) {
  return isObj(h) && finite(h.no) && typeof h.cards === "string" && Array.isArray(h.acts) && Array.isArray(h.seats) && h.seats.every(isObj)
    && h.acts.every((a) => isObj(a) && finite(a.st) && finite(a.seat) && typeof a.txt === "string" && Array.isArray(a.bets) && Array.isArray(a.stacks) && Array.isArray(a.folded) && finite(a.pot))
    && Array.isArray(h.board);
}

/** Parse the stored text; anything unreadable gives an empty list. */
export function loadGames(raw) {
  let d = raw;
  if (typeof raw === "string") { try { d = JSON.parse(raw); } catch { return []; } }
  if (!isObj(d) || d.schema !== GAMES_SCHEMA || d.schema_version !== GAMES_VERSION || !Array.isArray(d.games)) return [];
  return d.games.filter((g) => isObj(g) && typeof g.id === "string" && Array.isArray(g.hands))
    .map((g) => ({ ...g, hands: g.hands.filter(validHand) })).filter((g) => g.hands.length);
}

/** Add `hand` to game `meta.id` (created when new), then drop the oldest hands/games past LIMITS. */
export function addHand(games, meta, hand) {
  const out = games.map((g) => ({ ...g, hands: g.hands.slice() }));
  let g = out.find((x) => x.id === meta.id);
  if (!g) { g = { ...meta, hands: [] }; out.push(g); }
  g.hands.push(hand);
  return bound(out);
}

function size(games) { return serialize(games).length; }

export function bound(games, lim = LIMITS) {
  let out = games.slice(-lim.games);
  const count = () => out.reduce((a, g) => a + g.hands.length, 0);
  while (out.length && (count() > lim.hands || size(out) > lim.bytes)) {
    out[0] = { ...out[0], hands: out[0].hands.slice(1) };
    if (!out[0].hands.length) out.shift();
  }
  return out;
}

export function wrap(games) { return { schema: GAMES_SCHEMA, schema_version: GAMES_VERSION, games }; }
export function serialize(games) { return JSON.stringify(wrap(games)); }

/** 잘함 / 아쉬움 / 실수 by how often the policy takes my action; null when there is nothing to compare. */
export function verdict(an) {
  if (!an || an.p == null) return null;
  if (an.leak) return { key: "skip", text: "채점 안 함" };
  if (an.p >= GOOD_P) return { key: "good", text: "잘함" };
  if (an.p >= WARN_P) return { key: "warn", text: "아쉬움" };
  return { key: "bad", text: "실수" };
}

const pc = (x) => Math.round(x * 100) + "%";

/** Reason lines computed from the stored numbers (never canned): [{kind, text}]. */
export function reasons(an, act, names = {}) {
  if (!an) return [{ kind: "note", text: "이 테이블은 학습된 TP-GTO 정책이 없어 모의 상대였어요. 계산할 수 있는 것(액션 기록)만 보여요." }];
  const out = [];
  const aggressive = act.type === "raise";
  if (an.p != null) {
    const top = an.top && an.top !== an.name ? ` 정책이 가장 자주 고르는 건 ${an.top}(${pc(an.topP)})이에요.` : "";
    out.push({ kind: "freq", text: `내 선택 ${an.name}은 정책이 ${an.approx ? "대략 " : ""}${pc(an.p)} 쓰는 액션이에요.${top}` });
  }
  const r = an.reply;
  if (aggressive && r) {
    if (r.canFold && r.weakFold != null) {
      const strongLeft = r.strongOfContinuing != null ? ` 남는 핸드 중 나보다 강한 비중은 ${pc(r.strongOfContinuing)}예요.` : "";
      out.push({ kind: "range", text: `이 ${names.verb || "벳"}에 상대 레인지 중 나보다 약한 핸드의 ${pc(r.weakFold)}가 폴드하고, 나보다 강한 핸드는 ${pc(r.strongFold ?? 0)}만 폴드해요.${strongLeft}` });
      if (r.weakFold >= 0.6 && r.strongOfContinuing != null && r.strongOfContinuing >= 0.6) {
        out.push({ kind: "bad", text: "약한 핸드가 거의 다 죽고 남는 건 대부분 나보다 강해서 팟을 키워도 밸류를 못 받아요. 체크로 약한 핸드의 블러프·콜을 남기는 쪽이 나아요." });
      } else if (r.weakFold <= 0.3) {
        out.push({ kind: "good", text: "나보다 약한 핸드가 대부분 계속 남아 밸류를 받을 수 있어요." });
      }
    } else if (r.weakRaise != null) {
      out.push({ kind: "range", text: `상대가 나보다 약한 핸드의 ${pc(r.weakRaise)}로 다시 레이즈해요.` });
    }
    if (an.beats != null && an.beats < 0.35 && r.fold != null) out.push({ kind: "range", text: `내 핸드는 상대 레인지의 ${pc(an.beats)}만 이겨요(블러프에 가까움). 이 벳에 상대 레인지의 ${pc(r.fold)}가 폴드해요.` });
  } else if (!aggressive && an.beats != null) {
    out.push({ kind: "range", text: `내 핸드는 상대 공개 레인지의 ${pc(an.beats)}를 이기고 있어요${an.opps > 1 ? "(상대 한 명씩 따로 본 평균)" : ""}.` });
    if (act.type === "fold" && an.eq != null && an.need != null) {
      out.push({ kind: an.eq > an.need + 0.05 ? "bad" : "good", text: `콜에 필요한 에퀴티는 ${pc(an.need)}인데 내 에퀴티는 공개 레인지 대비 ${pc(an.eq)}였어요.${an.eq > an.need + 0.05 ? " 폴드한 핸드가 이길 만한 값이었어요." : ""}` });
    } else if (act.type === "call" && an.eq != null && an.need != null) {
      out.push({ kind: an.eq + 0.05 < an.need ? "bad" : "good", text: `콜에 필요한 에퀴티 ${pc(an.need)}, 내 에퀴티 ${pc(an.eq)}.` });
    }
  }
  if (an.tp && an.tp.worst && an.tp.worst.length) {
    const w = an.tp.worst.map((x) => `${names.items?.[x.k] || x.k} ${x.score}점`).join(", ");
    out.push({ kind: "tp", text: `이 결정에서 정답과 가장 멀었던 판단: ${w} (TP 점수 ${an.tp.total}).` });
  }
  return out;
}

/** Counts shown in the 내 게임 list. */
export function handStats(h) {
  const d = h.acts.filter((a) => a.hero);
  return { decisions: d.length, compared: d.filter((a) => a.an && a.an.p != null).length };
}
