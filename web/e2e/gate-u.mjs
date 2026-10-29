// Gate U 센서: 서비스 E2E 흐름 + 3종 화면 스크린샷 + 가로 스크롤/axe 검사. 사용법은 web/README.md.
import { chromium } from "playwright";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// The page loads the TP-GTO engine and policies with import()/fetch, which file:// blocks: serve web/.
const webRoot = resolve(here, "..");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json" };
const server = createServer((req, res) => {
  const path = resolve(webRoot, "." + decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!path.startsWith(webRoot + sep) || !existsSync(path) || !statSync(path).isFile()) { res.writeHead(404); res.end(); return; }
  const body = readFileSync(path);
  res.writeHead(200, { "content-type": TYPES[extname(path)] || "application/octet-stream", "content-length": body.length });
  res.end(body);
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
// abseed=1 pins the #262 question-form draws to B, A, B so both forms run on every CI pass.
const url = `http://127.0.0.1:${server.address().port}/demo/index.html?speed=30&abseed=1`;
const shots = resolve(process.env.SCREENSHOT_DIR || resolve(here, "screenshots"));
const axeSource = readFileSync(createRequire(import.meta.url).resolve("axe-core/axe.min.js"), "utf8");
const VIEWPORTS = [["phone", 390, 844], ["tablet", 820, 1180], ["laptop", 1440, 900]];
mkdirSync(shots, { recursive: true });

const failures = [];
const must = (ok, msg) => { if (!ok) { failures.push(msg); console.error("FAIL: " + msg); } };

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.setDefaultTimeout(60_000);
page.on("pageerror", e => must(false, `page error: ${e.message}`));
// 스크린샷 3장이 같은 화면을 찍도록, window.__hold가 참인 동안 데모 타이머(다른 플레이어 진행)를 미룬다.
await page.addInitScript(() => {
  const st = window.setTimeout.bind(window);
  window.setTimeout = (fn, ms, ...args) => st(function tick() {
    if (window.__hold) st(tick, 25); else fn(...args);
  }, ms);
});

// focus: 화면에 들여 놓고 보이는지 검사할 요소. 찍는 동안 데모 진행을 멈춘다.
async function inspect(tag, focus) {
  await page.evaluate(() => { window.__hold = true; });
  for (const [name, width, height] of VIEWPORTS) {
    await page.setViewportSize({ width, height });
    if (focus) {
      // A re-render (e.g. 복기 비교 결과) can detach the element between lookup and scroll: look it up
      // again and retry instead of failing on a timing race.
      let visible = false;
      for (let attempt = 0; attempt < 3 && !visible; attempt++) {
        try {
          const el = page.locator(focus).first();
          await el.waitFor({ state: "visible", timeout: 5000 });
          await el.scrollIntoViewIfNeeded({ timeout: 5000 });
          visible = await el.isVisible();
        } catch (e) {
          if (attempt === 2) console.error(`${tag} ${width}x${height}: ${focus} 재시도 실패 — ${e.message.split("\n")[0]}`);
          await page.waitForTimeout(200);
        }
      }
      must(visible, `${tag} ${width}x${height}: ${focus}가 화면에 없음`);
    }
    await page.screenshot({ path: `${shots}/${tag}-${name}.png` });
    const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
    must(sw <= iw, `${tag} ${width}x${height}: 가로 스크롤 (scrollWidth ${sw} > ${iw}). 넘치는 요소를 줄이세요`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  // axe-core도 setTimeout을 쓰므로 hold를 먼저 풀어야 교착하지 않는다.
  await page.evaluate(() => { window.__hold = false; });
  await page.evaluate(src => { if (!window.axe) (0, eval)(src); }, axeSource);
  const res = await page.evaluate(() => axe.run(document, { resultTypes: ["violations"] }));
  const critical = res.violations.filter(v => v.impact === "critical");
  must(critical.length === 0, `${tag}: axe critical ${critical.map(v => v.id + "×" + v.nodes.length).join(", ")}`);
}

// 1. 시작 → 테이블 → 내 차례(Quick: 액션 먼저 → 진행 / 분석 보기 → 비교) → Guided TP 입력 → 제출 → 채점
await page.goto(url);
must(await page.locator("#set-play [data-v='quick'][aria-pressed='true']").count() === 1, "시작 화면: 플레이 모드 기본값이 Quick이 아님");
must(await page.locator("#set-mode [data-v='cash'][aria-pressed='true']").count() === 1, "시작 화면: 기본 게임이 캐시게임(TP-GTO)이 아님");
// #337: the trained policy index loads and the header names the model, not a mock.
await page.waitForFunction(() => /학습 중간본/.test(document.querySelector("#svc-pill")?.textContent || ""), null, { timeout: 30_000 });
must(!(await page.evaluate(() => document.body.innerText)).includes("데모"), "서비스 화면에 '데모' 문구가 남아 있음");
must(await page.locator("#model-status .ms.on").count() >= 1, "시작 화면: 학습된 TP-GTO 모델 표시가 없음");
await inspect("home");
await page.click("#start-btn");
const QUICK = "#tp-body [data-card='quick-act']";
await page.waitForSelector(QUICK);
must((await page.textContent("#infobar")).includes("상대 TP-GTO"), "훈련 게임: 상대가 TP-GTO 정책이 아님(정책 연결 실패)");
await inspect("train-input", QUICK);
// #116 Quick: one decision ends in at most 3 inputs — action, size (only for a bet/raise), 진행. No judgment is required.
// #337/#341: the size is free no-limit — the amount box takes any size from the minimum raise to all in.
let freeSized = false;
for (let d = 0; d < 6 && !freeSized; d++) {
  if (d) await page.waitForSelector(QUICK);
  let inputs = 0;
  const raise = page.locator(`${QUICK} [data-act='raise']:not([disabled])`);
  if (await raise.count()) {
    await raise.click(); inputs++;
    const num = page.locator("[data-sizes]:not([hidden]) [data-size-num]"), msg = page.locator("[data-size-msg]");
    const lo = +(await num.getAttribute("min")), hi = +(await num.getAttribute("max"));
    // Below the minimum raise and above the stack are refused with the reason on screen, not clamped.
    for (const [bad, word] of [[Math.max(0.1, Math.round((lo - 0.5) * 10) / 10), "최소 레이즈"], [hi + 5, "올인"]]) {
      await num.fill(String(bad)); await num.press("Enter");
      must(await msg.isVisible() && (await msg.textContent()).includes(word), `노리밋 입력: ${bad}BB가 거부 이유(${word}) 없이 받아들여짐 (${await msg.textContent()})`);
      must(!(await page.locator("#tp-go").isEnabled()), `노리밋 입력: 범위 밖 금액 ${bad}BB인데 진행 버튼이 켜짐`);
    }
    await inspect("train-size-refused", "[data-size-msg]");
    // An amount that is neither a preset nor a menu size of the trained policy.
    const menu = await page.evaluate(() => { const tg = TPG.mod, s = G.eng.s; return tg.legal(s).filter(a => !["f", "k", "c"].includes(a)).map(a => tg.amountTo(s, a)); });
    let want = Math.round(((lo + hi) / 2.7) * 10) / 10;
    while (menu.includes(Math.round(want * 100))) want = Math.round((want + 0.3) * 10) / 10;
    await num.fill(String(want)); await num.press("Enter"); inputs++;
    const to = await page.evaluate(() => CUR.to);
    must(!(await msg.isVisible()), "노리밋 입력: 범위 안 금액인데 거부 메시지가 남아 있음");
    must(Math.abs(to - Math.round(want * 100)) <= 10 && to >= lo * 100 && to <= hi * 100, `노리밋 입력: ${want}BB를 넣었는데 금액이 ${to / 100}BB`);
    must(!menu.includes(to), `노리밋 입력: 메뉴 밖 금액을 고르려 했는데 ${to / 100}BB가 메뉴 금액`);
    freeSized = await page.evaluate(() => G.handNo);
  } else { await page.locator(`${QUICK} [data-act]:not([disabled])`).last().click(); inputs++; }
  must(await page.locator("#tp-go").isEnabled(), "Quick: 액션을 골랐는데 진행 버튼이 비활성");
  await page.evaluate(() => { window.__hold = true; });   // keep the waiting panel on screen while checking it
  await page.click("#tp-go"); inputs++;
  await page.waitForSelector("#tp-body .waiting");
  must(inputs <= 3, `Quick: 한 결정에 입력 ${inputs}개 (3개 이하여야 함)`);
  // Quick without analysis still compares the action with the trained policy's mixed strategy.
  must(await page.locator("#tp-body [data-model-action]").count() === 1 || !(await page.evaluate(() => G.eng?.ok)), "Quick: 진행 뒤 TP-GTO 혼합 전략 비교가 없음");
  if (!freeSized) await page.evaluate(() => { window.__hold = false; });
}
must(freeSized, "노리밋 입력: 6번의 결정 동안 벳·레이즈 기회가 없었음");
must((await page.textContent("#tp-body [data-model-action]")).includes("학습 중간본"), "액션 비교: 모델 라벨(학습 중간본·반복·LBR·run)이 없음");
await inspect("train-quick-model", "#tp-body [data-model-action]");
// The off-menu hand plays to its end with the engine mirror on (check/call/fold on my later turns).
if (freeSized) {
  for (let guard = 0; guard < 12; guard++) {
    await page.waitForFunction(h => G.eng?.lastHand?.hand === h || (CUR && G.handNo === h), freeSized, { timeout: 60_000 });
    if (await page.evaluate(h => G.eng?.lastHand?.hand === h, freeSized)) break;
    await page.locator(`${QUICK} [data-act='check']:not([disabled]), ${QUICK} [data-act='call']:not([disabled]), ${QUICK} [data-act='fold']:not([disabled])`).first().click();
    await page.click("#tp-go");
  }
  const end = await page.evaluate(() => G.eng?.lastHand);
  must(end?.hand === freeSized && end.ok && end.done, `노리밋 입력: 메뉴 밖 금액 핸드가 엔진과 함께 끝나지 않음 (${JSON.stringify(end)})`);
}
// #337: AI seats play the trained policy. Every logged AI decision must be an action the policy file gives
// weight to (read straight from web/app/policy/mid-6.json), with the same row, and at least one is the argmax.
{
  for (let guard = 0; guard < 20 && (await page.evaluate(() => TPG.botLog.length)) < 12; guard++) {
    await page.waitForSelector(QUICK);
    await page.locator(`${QUICK} [data-act='check']:not([disabled]), ${QUICK} [data-act='call']:not([disabled])`).first().click();
    await page.click("#tp-go");
  }
  const file = JSON.parse(readFileSync(resolve(webRoot, "app/policy/mid-6.json"), "utf8"));
  const log = await page.evaluate(() => TPG.botLog.filter(x => x.tier === "mid"));
  let inTable = 0, argmax = 0;
  for (const d of log) {
    const row = file.policy[d.key], i = d.acts.indexOf(d.chosen);
    must(i >= 0, `정책 상대: AI가 합법 메뉴 밖 액션 ${d.chosen}을 고름 (${d.key})`);
    if (!row) { must(!d.fromTable, `정책 상대: 파일에 없는 키인데 표에서 읽었다고 함 (${d.key})`); continue; }
    inTable++;
    must(row.length === d.acts.length && row.every((v, j) => Math.abs(v / file.q - d.probs[j]) < 1e-9), `정책 상대: 페이지가 쓴 확률이 정책 파일과 다름 (${d.key})`);
    must(row[i] > 0, `정책 상대: 정책 확률 0인 액션 ${d.chosen}을 고름 (${d.key})`);
    if (row[i] === Math.max(...row)) argmax++;
  }
  must(log.length >= 12 && inTable >= 6, `정책 상대: 검사할 AI 결정이 모자람 (전체 ${log.length}, 표에 있는 키 ${inTable})`);
  must(argmax >= 1, `정책 상대: 고정 시드에서 정책 최대 확률 액션과 같은 AI 결정이 하나도 없음 (${inTable}개 중)`);
  console.log(`정책 상대: AI 결정 ${log.length}개(표 ${inTable}) 모두 정책 지지 액션, 최대 확률 일치 ${argmax}개`);
}
// #116 Quick analysis: action first, then "분석 보기" asks 1–3 core judgments and shows the TP comparison.
await page.waitForSelector(QUICK);
await page.locator(`${QUICK} [data-act='check']:not([disabled]), ${QUICK} [data-act='call']:not([disabled])`).first().click();
await page.click("#tp-analyze");
await page.waitForSelector("#tp-body [data-card='quick-ask']");
const eqTruth = await page.evaluate(() => {
  const tg = TPG.mod, E = G.eng;
  if (!E?.ok || !CUR.g.model) return null;
  const seat = E.s.toAct, eq = tg.multiEquity(E.s, seat, E.ranges)[tg.comboIndex(E.s.hole[seat])];
  return { want: Math.round(eq * 100), got: CUR.g.v["hand.equity"], src: CUR.g.src?.["hand.equity"],
           step: CUR.g.model.step, step2: tg.equityStepOf(E.s, seat, E.ranges, E.tier), key: CUR.g.model.d.key, key2: tg.decisionKey(E.s, E.ranges, E.tier).key };
});
must(eqTruth && eqTruth.src === "model" && eqTruth.got === eqTruth.want, `hand.equity 정답: 엔진 공개 레인지 에퀴티와 다름 (${JSON.stringify(eqTruth)})`);
must(eqTruth && eqTruth.step === eqTruth.step2 && eqTruth.key === eqTruth.key2, `hand.equity 정답: 정책 키·단계가 엔진과 다름 (${JSON.stringify(eqTruth)})`);
{
  const qs = await page.locator("#tp-body [data-card='quick-ask'] .q").all();
  must(qs.length >= 1 && qs.length <= 3, `Quick 분석: 핵심 판단 ${qs.length}개 (1~3개여야 함)`);
  must((await page.locator("#tp-body [data-act]").count()) === 0, "Quick 분석: 액션을 다시 묻고 있음(액션이 먼저여야 함)");
  for (const q of qs) await q.locator("[data-chip]").first().click();
}
await inspect("train-quick-ask", "#tp-submit");
await page.click("#tp-submit");
await page.waitForSelector("#tp-body .result-top");
must((await page.textContent("#tp-body .result-top")).includes("Quick 분석"), "Quick 분석: 채점 화면에 Quick 표시 없음");
must((await page.locator("#tp-body .rrow.ref").count()) >= 1, "Quick 분석: 액션 비교(TP-GTO 혼합 전략)가 없음");
must((await page.locator("#tp-body .result-top .conf.model").count()) === 1, "Quick 분석: 채점 화면에 TP-GTO 학습 중간본 라벨이 없음");
{
  const row = await page.evaluate(() => G.lastGrade.rows.find(r => r.k === "hand.equity"));
  must(row && row.src === "model" && row.gto === eqTruth?.want, `hand.equity 채점: 정답이 엔진 값(${eqTruth?.want})이 아님 (${JSON.stringify(row && { gto: row.gto, src: row.src })})`);
  if (row) must((await page.locator("#tp-body .rrow:not(.ref)", { hasText: "에퀴티 감각" }).textContent()).includes(`TP-GTO ${eqTruth.want}`), "hand.equity 채점: 결과 줄에 TP-GTO 정답 값이 없음");
}
await inspect("train-quick-result", "#tp-body .result-top");
// Switch to Guided between decisions (hold the demo so the next turn waits), then do the full card deck.
await page.evaluate(() => { window.__hold = true; });
await page.click(".tab[data-view='home']");
await page.click("#set-play [data-v='guided']");
await page.click(".tab[data-view='train']");
await page.evaluate(() => { window.__hold = false; });
for (let guard = 0; guard < 6; guard++) {
  await page.waitForSelector(`${QUICK}, #tp-body .tpc[data-card='0']:not([hidden])`);
  if (!(await page.locator(QUICK).count())) break;
  await page.locator(`${QUICK} [data-act]:not([disabled])`).first().click(); // a turn that began before the switch
  await page.click("#tp-go");
  await page.waitForSelector("#tp-body .waiting");
}
await inspect("train-guided", "#tp-body .tpc[data-card='0']");
// #164: answer card 1, go next, come back with "이전": same card and the answer is kept.
{
  const first = page.locator("#tp-body .tpc:not([hidden])");
  const stage = await first.getAttribute("data-card");
  const chip = first.locator(".q:not(.na) [data-chip]").first();
  if (await chip.count()) {
    await chip.click();
    for (const q of await first.locator(".q:not(.na)").all()) if (await q.locator("[data-chip]").count()) await q.locator("[data-chip]").first().click();
    if (await page.locator("#tp-next").isEnabled()) {
      await page.click("#tp-next");
      must((await page.locator("#tp-body .tpc:not([hidden])").getAttribute("data-card")) !== stage, "다음: 카드가 바뀌지 않음");
      await page.click("#tp-prev");
      const back = page.locator("#tp-body .tpc:not([hidden])");
      must((await back.getAttribute("data-card")) === stage, "이전: 처음 카드로 돌아오지 않음");
      must((await back.locator(".q:not(.na) [data-chip][aria-pressed='true']").count()) > 0, "이전: 입력했던 답이 사라짐");
      must((await page.locator("#tp-dots .dot.cur").count()) === 1, "이전: 진행 점 표시 없음");
    }
  }
}
// TP input is a card deck (B board → C opponent → D hand → E plan → F action → G checks): answer every
// question on the visible card with its first chip (or a non-fold action and a size), then go next.
async function answerDeck() {
  for (let guard = 0; guard < 12; guard++) {
    const card = page.locator("#tp-body .tpc:not([hidden])");
    for (const q of await card.locator(".q:not(.na)").all()) {
      if (await q.locator("[data-act]").count()) {
        await q.locator("[data-act]:not([disabled]):not([data-act='fold'])").first().click();
        if (await page.locator("[data-sizes]:not([hidden]) [data-size]").count()) await page.locator("[data-sizes]:not([hidden]) [data-size]").first().click();
      } else if (await q.locator("[data-chip]").count()) {
        await q.locator("[data-chip]").first().click();
      }
    }
    const next = page.locator("#tp-next");
    if (await next.isVisible() && await next.isEnabled()) { await next.click(); continue; }
    break;
  }
}
await answerDeck();
must(await page.locator("#tp-submit").isVisible() && await page.locator("#tp-submit").isEnabled(), "TP 카드를 다 채웠는데 제출 버튼이 비활성");
await page.click("#tp-submit");
await page.waitForSelector("#tp-body .result-top");
must((await page.textContent("#tp-body .result-top .ring")).trim() !== "", "채점 점수가 비어 있음");
await inspect("train-result", "#tp-body .result-top");
must(await page.locator("#tp-body [data-drivers]").count() > 0 || !(await page.locator("#tp-body .rrow:not(.ref)").count()),
     "결과 화면: 판단 Top 3(모의) 블록이 없음");
if (await page.locator("#tp-body [data-drivers]").count()) await inspect("train-drivers", "#tp-body [data-drivers]");
must(!(await page.locator("#tp-body [data-ab]").count()), "질문 형태 실험이 꺼져 있는데 A/B 기록이 보임");

// #262 질문 형태 실험: 토글 켬 → Guided 결정 3회(에퀴티 질문이 A 또는 B, 패널 제목에 형태) → 학습 섹션 표
await page.evaluate(() => { window.__hold = true; });
await page.click(".tab[data-view='home']");
must(await page.locator("#set-eqab [data-v='off'][aria-pressed='true']").count() === 1, "질문 형태 실험: 기본값이 끔이 아님");
await page.click("#set-eqab [data-v='on']");
await page.click(".tab[data-view='train']");
await page.evaluate(() => { window.__hold = false; });
{
  const forms = [];
  for (let guard = 0; guard < 6; guard++) {   // a turn that began before the switch has no form drawn
    await page.waitForSelector("#tp-body .tpc[data-card='0']:not([hidden])");
    if (await page.evaluate(() => !!(CUR && CUR.ab))) break;
    await answerDeck();
    await page.click("#tp-submit");
    await page.waitForSelector("#tp-body .waiting");
  }
  for (let d = 0; d < 3; d++) {
    await page.waitForSelector("#tp-body .tpc[data-card='0']:not([hidden])");
    const title = (await page.textContent("#tp-form")).trim();
    must(await page.locator("#tp-form").isVisible() && /^형태 [AB] · (이길 확률|상위 %)$/.test(title), `질문 형태 실험: 패널 제목에 형태가 없음 (${title})`);
    forms.push(title[3]);
    const q = page.locator("#tp-body .q[data-k='hand.equity'] [data-chip]");
    must(await q.count() === 5, `질문 형태 실험: 에퀴티 질문 칩이 5개가 아님 (${await q.count()})`);
    if (title[3] === "B") {
      // B's truth chip samples with its own random state; the game's deal stream must come back untouched.
      const r = await page.evaluate(() => { const s = rngState, t = eqabTruth("B", CUR.g); return { same: s === rngState, t }; });
      must(r.same, "질문 형태 실험: eqabTruth(\"B\")가 게임 난수 상태(rngState)를 되돌리지 않음 — 켬/끔 사이에 딜이 달라진다");
      must(Number.isInteger(r.t) && r.t >= 0 && r.t <= 4, `질문 형태 실험: B 정답 칩이 0–4 정수가 아님 (${r.t})`);
    }
    if (d === 0) await inspect("train-eqab", "#tp-form");
    await answerDeck();
    await page.click("#tp-submit");
    await page.waitForSelector("#tp-body .result-top");
    must(await page.locator("#tp-body [data-ab]").count() === 1, "질문 형태 실험: 결과에 A/B 기록 줄이 없음");
  }
  const n = await page.evaluate(() => JSON.parse(localStorage.getItem("stalker.eqab") || "[]").length);
  must(n === 3, `질문 형태 실험: 결정 3회에 기록 ${n}건`);
  must(forms.includes("A") && forms.includes("B"), `질문 형태 실험: abseed=1인데 A·B가 모두 나오지 않음 (${forms.join("")}) — abNext나 시드 처리가 바뀌었으면 두 형태가 다 나오는 시드로 url을 고친다`);
  const bRecs = await page.evaluate(() => JSON.parse(localStorage.getItem("stalker.eqab") || "[]").filter(r => r.f === "B"));
  must(bRecs.length > 0 && bRecs.every(r => Number.isInteger(r.t) && r.t >= 0 && r.t <= 4), `질문 형태 실험: B 기록이 없거나 정답 칩 t가 0–4 정수가 아님 (${JSON.stringify(bRecs)})`);
  console.log(`질문 형태 실험: 배정 ${forms.join("")}`);
}

// #315 TP v0.2: with the experiment off, beginners get hand.equity as the rank question (form B chips),
// graded against the B truth chip, and no A/B record is written. Then back to mid for the rest.
await page.evaluate(() => { window.__hold = true; });
await page.click(".tab[data-view='home']");
await page.click("#set-eqab [data-v='off']");
await page.click("#set-tier [data-v='beginner']");
await page.click(".tab[data-view='train']");
await page.evaluate(() => { window.__hold = false; });
{
  for (let guard = 0; guard < 6; guard++) {   // a turn that began before the switch is still mid
    await page.waitForSelector("#tp-body .tpc[data-card='0']:not([hidden])");
    if (await page.evaluate(() => CUR && CUR.rank === true)) break;
    await answerDeck();
    await page.click("#tp-submit");
    await page.waitForSelector("#tp-body .waiting");
  }
  must(await page.evaluate(() => CUR && CUR.rank === true), "초보 순위형: 초보로 바꿨는데 hand.equity가 순위형으로 묻지 않음");
  must(!(await page.locator("#tp-form").isVisible()), "초보 순위형: 실험이 꺼져 있는데 패널 제목에 형태가 보임");
  const eq = page.locator("#tp-body .q[data-k='hand.equity']");
  must((await eq.textContent()).includes("내 레인지의 상위 몇 %"), `초보 순위형: 에퀴티 질문 문구가 순위형이 아님 (${(await eq.textContent()).slice(0, 60)})`);
  const chips = (await eq.locator("[data-chip]").allTextContents()).map(t => t.trim());
  must(chips.length === 5 && chips[0] === "상위 20%" && chips[4] === "하위 20%", `초보 순위형: 순위 칩 5개가 아님 (${chips.join(", ")})`);
  const before = await page.evaluate(() => JSON.parse(localStorage.getItem("stalker.eqab") || "[]").length);
  // Walk the deck up to the card that asks hand.equity so the screenshot shows the rank question.
  for (let guard = 0; guard < 6 && !(await eq.isVisible()); guard++) {
    for (const q of await page.locator("#tp-body .tpc:not([hidden]) .q:not(.na)").all())
      if (await q.locator("[data-chip]").count()) await q.locator("[data-chip]").first().click();
    if (!(await page.locator("#tp-next").isEnabled())) break;
    await page.click("#tp-next");
  }
  await eq.locator("[data-chip]").first().click();
  await inspect("train-beginner-rank", "#tp-body .q[data-k='hand.equity']");
  await answerDeck();
  await page.click("#tp-submit");
  await page.waitForSelector("#tp-body .result-top");
  const row = page.locator("#tp-body .rrow:not(.ref)", { hasText: "참값" });
  must(await row.count() === 1, "초보 순위형: 채점 결과에 순위형 에퀴티 줄(참값 칸)이 없음");
  if (await row.count()) must(/상위 20%|20–40%|40–60%|60–80%|하위 20%/.test(await row.textContent()), "초보 순위형: 채점 줄에 순위 칩 라벨이 없음");
  if (await row.count()) must((await row.textContent()).includes("내 레인지"), "초보 순위형: 채점 노트가 정답 기준(내 레인지 안 순위, TP §4.1 share_better)을 밝히지 않음");
  must(!(await page.locator("#tp-body [data-ab]").count()), "초보 순위형: 실험이 꺼져 있는데 A/B 기록 줄이 보임");
  const after = await page.evaluate(() => JSON.parse(localStorage.getItem("stalker.eqab") || "[]").length);
  must(after === before, `초보 순위형: 실험 기록(eqab)이 늘어남 (${before} → ${after}) — 순위형 채점은 eqab에 넣지 않는다`);
  await inspect("train-beginner-result", "#tp-body .result-top");
}
await page.evaluate(() => { window.__hold = true; });
await page.click(".tab[data-view='home']");
await page.click("#set-tier [data-v='mid']");
await page.click(".tab[data-view='train']");
await page.evaluate(() => { window.__hold = false; });

// #163 토너먼트(모의): 내 차례에는 레벨 시계가 멈춘다.
await page.evaluate(() => { window.__hold = true; });
await page.click(".tab[data-view='home']");
await page.click("#set-mode [data-v='tournament']");
await page.click("#set-play [data-v='quick']");
await page.evaluate(() => { window.__hold = false; });
await page.click("#start-btn");
await page.waitForSelector(QUICK);
must((await page.locator("#lv-left").count()) > 0, "토너먼트 레벨 시계(#lv-left)가 없음");
{
  const before = (await page.textContent("#lv-left")).trim();
  await page.waitForTimeout(2500);
  must((await page.textContent("#lv-left")).trim() === before, `내 차례인데 레벨 시계가 흐름: ${before} → ${(await page.textContent("#lv-left")).trim()}`);
}
must((await page.textContent("#svc-pill")).includes("모의"), "토너먼트: 학습 정책이 없는데 모의 표시가 없음");

// 2. 학습 섹션: 갤러리 → 모듈 하나 열기 → 1문제
await page.click(".tab[data-view='learn']");
await page.waitForSelector("#mods .mod:not(.locked)");
await inspect("learn-gallery");
{
  const cells = async f => (await page.locator(`#ab-box tr[data-form='${f}'] td`).allTextContents()).map(t => t.trim());
  const a = await cells("A"), b = await cells("B");
  must(a.length === 5 && b.length === 5, "학습 섹션: 질문 형태 실험 표(A·B 행)가 없음");
  must(+a[1] + +b[1] === 3, `학습 섹션: 형태별 기록 합이 3이 아님 (${a[1]}+${b[1]})`);
  must(+b[1] > 0, `학습 섹션: 질문 형태 표 B 행 기록 수가 0 (${b.join(" | ")})`);
  for (const r of [a, b]) if (+r[1] > 0) must(/초$/.test(r[2]) && /초$/.test(r[3]) && /%$/.test(r[4]), `학습 섹션: P50·P95·정답률 칸이 비어 있음 (${r.join(" | ")})`);
  await inspect("learn-eqab", "#ab-box");
}
// #165: opening a module turns the gallery into a side list; "← 전체" brings the gallery back.
await page.locator("#mods .mod[data-k='hand.rank']").click();
await page.waitForSelector("#learn.open #drill:not([hidden])");
must(!(await page.locator("#learn").getAttribute("class")).includes("gallery"), "모듈을 열었는데 갤러리 레이아웃 그대로");
// Rank quiz: pick a hand rank for both hands, grade, and see the result.
for (const who of [0, 1]) await page.locator(`.rk-opts[data-who='${who}'] button`).first().click();
must(await page.locator("#dr-go").isEnabled(), "족보 맞히기: 둘 다 골랐는데 정답 확인 비활성");
await page.click("#dr-go");
must((await page.locator("#dr-res").innerHTML()).trim() !== "", "족보 맞히기: 채점 결과가 비어 있음");
await inspect("learn-rank", "#dr-res");
await page.click("#dr-back");
await page.waitForSelector("#learn.gallery");
await page.locator("#mods .mod:not(.locked)").nth(1).click();
await page.waitForSelector("#dr-go");
if (await page.locator("#drill [data-chip]").count()) await page.locator("#drill [data-chip]").first().click();
await page.click("#dr-go");
must((await page.locator("#dr-res").innerHTML()).trim() !== "", "학습 섹션: 정답 확인 후 결과가 비어 있음");
await inspect("learn", "#dr-res");

// 3. 복기: 단계(포지션 → 핸드 → 프리플랍 …) → 비교
await page.click(".tab[data-view='review']");
await page.waitForSelector("#rv-next");
await page.click("#rv-next");                                       // 포지션: 기본 자리
for (let i = 0; i < 2; i++) await page.click("#rv-deck button:not([disabled])");
await page.click("#rv-next");                                       // 핸드 → 프리플랍
for (let guard = 0; guard < 12 && await page.locator("#rv-bar [data-rv]").count(); guard++) {
  const fold = page.locator("#rv-bar [data-rv='fold']:not([disabled])");
  if (await fold.count()) await fold.click(); else await page.locator("#rv-bar [data-rv='check'], #rv-bar [data-rv='call']").first().click();
}
for (let guard = 0; guard < 8 && await page.locator("#rv-next:not([disabled])").count(); guard++) await page.click("#rv-next");
await page.waitForSelector("#rv-out .rrow");
must((await page.textContent("#rv-body h2")).includes("비교 결과"), "복기: 비교 결과가 표시되지 않음");
must(await page.locator("#rv-out [data-model-action]").count() === 1, "복기: 캐시 6인 100BB 핸드인데 TP-GTO 정책 비교가 없음");
await inspect("review", "#rv-body h2");

// 4. #117 기록 옮기기: 내보내기 → 초기화 → 가져오기 → 같은 통계
await page.click(".tab[data-view='home']");
await page.click("#move summary");
await page.waitForFunction(() => document.querySelector("#move-out").value.length > 0);
const exported = await page.inputValue("#move-out");
const weakBefore = await page.textContent("#weak-home");
must(JSON.parse(exported).schema_version === 2 && Object.keys(JSON.parse(exported).weak).length > 0, "기록 옮기기: 내보낸 JSON에 schema_version 2·weak가 없음");
must(JSON.parse(exported).eqab.length === 3, "기록 옮기기: 내보낸 JSON에 질문 형태 실험 기록(eqab) 3건이 없음");
const abBefore = await page.evaluate(() => { renderEqab(); return document.querySelector("#ab-box").innerHTML; });
await page.evaluate(() => localStorage.clear());
await page.reload();
must((await page.textContent("#weak-home")).includes("아직 기록이 없어요"), "기록 옮기기: 초기화 뒤에도 기록이 남음");
await page.click("#move summary");
await page.waitForFunction(() => document.querySelector("#move-out").value.length > 0);
await page.fill("#move-in", "{not json");
await page.click("#move-import");
must((await page.textContent("#move-msg")).includes("JSON으로 읽을 수 없어요"), "기록 옮기기: 잘못된 입력에 고치는 법이 없음");
await page.fill("#move-in", exported);
await page.click("#move-import");                                    // 첫 클릭: 덮어쓰기 확인
await page.click("#move-import");                                    // 두 번째: 가져오기
must(await page.textContent("#weak-home") === weakBefore, "기록 옮기기: 가져온 뒤 통계가 내보내기 전과 다름");
must(await page.evaluate(() => window.STALKER_RECORDS.exportRecords()) === exported, "기록 옮기기: 왕복 뒤 내보내기 텍스트가 다름");
must(await page.evaluate(() => { renderEqab(); return document.querySelector("#ab-box").innerHTML; }) === abBefore, "기록 옮기기: 왕복 뒤 질문 형태 실험 표가 다름");
await inspect("home-move", "#move");

// 5. #337 정책을 못 불러올 때: 오류 화면(이유·다시 시도·모의로 계속) → 다시 시도 성공 / 모의로 계속
{
  const p2 = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  p2.setDefaultTimeout(60_000);
  p2.on("pageerror", e => must(false, `page error (정책 오류 경로): ${e.message}`));
  const block = r => r.abort();
  await p2.route("**/policy/mid-6.json", block);
  await p2.goto(url);
  await p2.waitForFunction(() => /연결 실패/.test(document.querySelector("#svc-pill")?.textContent || ""));
  await p2.click("#start-btn");
  await p2.waitForSelector("#tp-body [role='alert'] #tpg-again");
  const alertText = await p2.textContent("#tp-body [role='alert']");
  must(alertText.includes("정책을 불러오지 못했어요") && (await p2.locator("#tpg-mock").count()) === 1, `정책 오류: 이유·모의로 계속 버튼이 없음 (${alertText})`);
  for (const [name, width, height] of VIEWPORTS) {
    await p2.setViewportSize({ width, height });
    await p2.locator("#tp-body [role='alert']").scrollIntoViewIfNeeded();
    await p2.screenshot({ path: `${shots}/policy-error-${name}.png` });
    const { sw, iw } = await p2.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
    must(sw <= iw, `정책 오류 ${width}x${height}: 가로 스크롤 (scrollWidth ${sw} > ${iw})`);
  }
  await p2.setViewportSize({ width: 1440, height: 900 });
  await p2.click("#tpg-again");                       // still blocked: the same screen comes back
  await p2.waitForSelector("#tp-body [role='alert'] #tpg-mock");
  await p2.click("#tpg-mock");
  await p2.waitForSelector(QUICK);
  must((await p2.textContent("#infobar")).includes("규칙 봇"), "정책 오류: 모의로 계속했는데 규칙 봇·모의 표시가 없음");
  await p2.unroute("**/policy/mid-6.json", block);
  await p2.click("#new-game");
  await p2.waitForSelector(QUICK);
  must((await p2.textContent("#infobar")).includes("상대 TP-GTO"), "정책 오류: 연결이 돌아온 뒤 새 게임에서 TP-GTO 정책을 불러오지 못함");
  await p2.close();
}

// 6. #360 고수 등급: 상대 5명이 pro-6.json 정책(board.nut 키 포함)을 두고, 한 핸드를 끝까지 치며 모델 비교가 보인다.
{
  const p3 = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  p3.setDefaultTimeout(90_000);
  p3.on("pageerror", e => must(false, `page error (고수 정책): ${e.message}`));
  await p3.goto(url);
  await p3.click("#set-tier [data-v='pro']");
  await p3.waitForFunction(() => /학습 중간본/.test(document.querySelector("#svc-pill")?.textContent || "") && TPG.pol.pro, null, { timeout: 120_000 });
  await p3.click("#start-btn");
  await p3.waitForSelector(QUICK);
  must((await p3.textContent("#infobar")).includes("상대 TP-GTO 고수"), "고수: 상대가 TP-GTO 고수 정책이 아님");
  const first = await p3.evaluate(() => G.handNo);
  let compared = false, fin = false;
  for (let guard = 0; guard < 40; guard++) {
    fin = await p3.evaluate(h => G.handNo > h + 1 && TPG.botLog.filter(x => x.tier === "pro" && x.key.startsWith("p|")).length > 0, first);
    if (fin) break;
    await p3.waitForSelector(QUICK);
    await p3.locator(`${QUICK} [data-act='check']:not([disabled]), ${QUICK} [data-act='call']:not([disabled])`).first().click();
    await p3.click("#tp-go");
    if (await p3.locator("#tp-body [data-model-action]").count()) compared = true;
  }
  must(fin, "고수: 40번의 내 차례 안에 첫 핸드가 끝나고 포스트플랍 고수 키가 기록되지 않음");
  must(compared, "고수: 진행 뒤 TP-GTO 고수 혼합 전략 비교([data-model-action])가 한 번도 보이지 않음");
  const done = await p3.evaluate(h => G.eng?.lastHand?.hand >= h && G.eng.lastHand.ok && G.eng.lastHand.done, first);
  must(done, `고수: 첫 핸드가 엔진과 함께 끝나지 않음 (${JSON.stringify(await p3.evaluate(() => G.eng?.lastHand))})`);
  const file = JSON.parse(readFileSync(resolve(webRoot, "app/policy/pro-6.json"), "utf8"));
  must(file.nut_k === await p3.evaluate(() => TPG.mod.NUT_K), "고수: 정책 파일 nut_k가 tpgto.js NUT_K와 다름");
  const log = await p3.evaluate(() => TPG.botLog.filter(x => x.tier === "pro"));
  let inTable = 0, post = 0;
  for (const d of log) {
    const row = file.policy[d.key], i = d.acts.indexOf(d.chosen);
    must(i >= 0, `고수 정책 상대: 합법 메뉴 밖 액션 ${d.chosen} (${d.key})`);
    if (!row) { must(!d.fromTable, `고수 정책 상대: 파일에 없는 키인데 표에서 읽었다고 함 (${d.key})`); continue; }
    inTable++; if (d.key.startsWith("p|")) post++;
    must(row.length === d.acts.length && row.every((v, j) => Math.abs(v / file.q - d.probs[j]) < 1e-9), `고수 정책 상대: 페이지 확률이 파일과 다름 (${d.key})`);
    must(row[i] > 0, `고수 정책 상대: 확률 0인 액션 ${d.chosen} (${d.key})`);
  }
  must(inTable >= 6 && post >= 1, `고수 정책 상대: 표에 있는 키 ${inTable}개, 포스트플랍 ${post}개 (6개·1개 이상이어야 함, 전체 ${log.length})`);
  console.log(`고수 정책 상대: AI 결정 ${log.length}개(표 ${inTable}, 포스트플랍 ${post}) 모두 정책 지지 액션`);
  await p3.screenshot({ path: `${shots}/train-pro-laptop.png` });
  await p3.close();
}

await browser.close();
server.close();
if (failures.length) { console.error(`Gate U: ${failures.length}건 실패`); process.exit(1); }
console.log("Gate U ok");
