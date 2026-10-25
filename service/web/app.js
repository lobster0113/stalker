"use strict";
const ACTIONS = ["fold", "call", "raise", "allin"];
const STORE_KEY = "stalker.quiz.v1";
let report = null, quiz = null, state = { answered: 0, agree: 0, lossSum: 0, lossN: 0, seen: [] }, current = null;

// localStorage may throw or be absent (private mode); the page works without it.
function load() { try { const s = JSON.parse(localStorage.getItem(STORE_KEY)); if (s && Array.isArray(s.seen)) state = s; } catch (e) {} }
function save() { try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) {} }
const $ = (id) => document.getElementById(id);
const pct = (x) => (100 * x).toFixed(0) + "%";
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fail(msg) { const e = $("error"); e.textContent = msg; e.hidden = false; }

function renderTypes() {
  const c = report.criteria;
  $("types-summary").textContent = `결정 ${report.decisions}건, 셀 ${report.summary.cells}개, 표본 충분(S1) ${report.summary.s1_pass_cells}개. ` +
    `충분 기준: 주요 행동의 95% 신뢰구간 반폭 ≤ ${pct(c.s1_half_width)}p, 게임 ≥ ${c.min_games}.`;
  $("types-table").querySelector("thead").innerHTML = "<tr><th>셀 (단계|스택BB|포지션|스트리트|팟|상대)</th><th>결정</th><th>게임</th>" +
    ACTIONS.map((a) => `<th>${a}</th>`).join("") + "<th>표본</th></tr>";
  const rows = [...report.cells].sort((a, b) => b.n_decisions - a.n_decisions);
  $("types-table").querySelector("tbody").innerHTML = rows.map((c) => {
    const lacking = c.status !== "ok";
    const badge = c.s1_pass ? '<span class="badge ok">충분</span>' : lacking ? '<span class="badge low">데이터 부족</span>' : '<span class="badge fail">미달</span>';
    return `<tr><td>${esc(c.label)}</td><td>${c.n_decisions}</td><td>${c.n_games}</td>` +
      ACTIONS.map((a) => `<td>${pct(c.actions[a].mean)}</td>`).join("") + `<td>${badge}</td></tr>`;
  }).join("");
}

function optionLabel(o, bb) { return o.kind === "raise" ? `raise ${o.amount} (${(o.amount / bb).toFixed(1)}bb)` : o.kind; }

function renderScore() {
  const loss = state.lossN ? `, 평균 EV 손실 ${(state.lossSum / state.lossN).toFixed(2)}` : ", EV 손실: 이 데이터엔 행동 가치가 없어 표시하지 않음";
  $("quiz-score").textContent = state.answered ? `풀이 ${state.answered}, AI와 같은 선택 ${pct(state.agree / state.answered)}${loss}` : "스팟을 보고 행동을 고르세요.";
}

function nextSpot() {
  const pool = quiz.spots.filter((s) => !state.seen.includes(s.id));
  if (!pool.length) { state.seen = []; save(); return nextSpot(); }
  current = pool[Math.floor(Math.random() * pool.length)];
  const s = current, cell = report.cells.find((c) => c.label === s.cell);
  const seats = s.seats.map((x) => `좌석${x.seat}${x.seat === s.hero ? "(나)" : ""}: ${x.stack}${x.bet ? ` +베팅 ${x.bet}` : ""}${x.in_hand ? "" : " 폴드"}`).join(" · ");
  $("quiz-spot").innerHTML = `<div class="card"><div>${esc(s.street)} · ${esc(s.position)} · 팟 ${s.pot} · BB ${s.bb}</div>` +
    `<div>내 카드: <b>${esc(s.hole_cards.join(" "))}</b> 보드: ${esc(s.board.join(" ") || "-")}</div><div class="muted">${esc(seats)}</div>` +
    `<div class="muted">셀 ${esc(s.cell)}${cell && cell.status !== "ok" ? ' <span class="badge low">데이터 부족</span>' : ""}</div></div>`;
  $("quiz-options").innerHTML = s.options.map((o, i) => `<button data-i="${i}">${esc(optionLabel(o, s.bb))}</button>`).join("");
  $("quiz-result").innerHTML = ""; $("quiz-next").hidden = true;
}

function answer(i) {
  const s = current, best = s.probs.indexOf(Math.max(...s.probs));
  $("quiz-options").innerHTML = "";
  $("quiz-result").innerHTML = s.options.map((o, j) =>
    `<div class="row ${j === i ? "chosen" : ""}"><span>${esc(optionLabel(o, s.bb))}${j === i ? " ← 내 선택" : ""}</span>` +
    `<span><div class="bar" style="width:${(100 * s.probs[j]).toFixed(1)}%"></div></span><span>${pct(s.probs[j])}</span></div>`).join("");
  state.answered++; if (i === best) state.agree++;
  if (s.values) { state.lossSum += Math.max(...s.values) - s.values[i]; state.lossN++; }
  state.seen.push(s.id); save(); renderScore(); $("quiz-next").hidden = false;
}

function show(tab) {
  $("view-types").hidden = tab !== "types"; $("view-quiz").hidden = tab !== "quiz";
  $("tab-types").setAttribute("aria-selected", tab === "types"); $("tab-quiz").setAttribute("aria-selected", tab === "quiz");
}

async function main() {
  load();
  $("tab-types").onclick = () => show("types"); $("tab-quiz").onclick = () => show("quiz");
  $("quiz-options").onclick = (e) => { const b = e.target.closest("button[data-i]"); if (b) answer(+b.dataset.i); };
  $("quiz-next").onclick = nextSpot;
  try {
    [report, quiz] = await Promise.all(["data/report.json", "data/quiz.json"].map((u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); })));
  } catch (e) { return fail("데이터를 불러오지 못했습니다: " + e.message + " (python -m stalker.service.build 로 data/를 만들고 http.server로 여세요)"); }
  renderTypes(); renderScore(); if (quiz.spots.length) nextSpot();
}
main();
