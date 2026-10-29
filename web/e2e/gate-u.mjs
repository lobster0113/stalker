// Gate U 센서: 데모 E2E 흐름 + 3종 화면 스크린샷 + 가로 스크롤/axe 검사. 사용법은 web/README.md.
import { chromium } from "playwright";
import { createRequire } from "node:module";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// abseed=1 pins the #262 question-form draws to B, A, B so both forms run on every CI pass.
const url = pathToFileURL(resolve(here, "../demo/index.html")).href + "?speed=30&abseed=1";
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
await inspect("home");
await page.click("#start-btn");
const QUICK = "#tp-body [data-card='quick-act']";
await page.waitForSelector(QUICK);
await inspect("train-input", QUICK);
// #163: the level clock is frozen while it is my turn (the TP panel is open).
must((await page.locator("#lv-left").count()) > 0, "토너먼트 레벨 시계(#lv-left)가 없음");
{
  const before = (await page.textContent("#lv-left")).trim();
  await page.waitForTimeout(2500);
  must((await page.textContent("#lv-left")).trim() === before, `내 차례인데 레벨 시계가 흐름: ${before} → ${(await page.textContent("#lv-left")).trim()}`);
}
// #116 Quick: one decision ends in at most 3 inputs — action, size (only for a bet/raise), 진행. No judgment is required.
{
  let inputs = 0;
  const raise = page.locator(`${QUICK} [data-act='raise']:not([disabled])`);
  if (await raise.count()) {
    await raise.click(); inputs++;
    await page.locator("[data-sizes]:not([hidden]) [data-size]").first().click(); inputs++;
  } else { await page.locator(`${QUICK} [data-act]:not([disabled])`).last().click(); inputs++; }
  must(await page.locator("#tp-go").isEnabled(), "Quick: 액션을 골랐는데 진행 버튼이 비활성");
  await page.click("#tp-go"); inputs++;
  await page.waitForSelector("#tp-body .waiting");
  must(inputs <= 3, `Quick: 한 결정에 입력 ${inputs}개 (3개 이하여야 함)`);
}
// #116 Quick analysis: action first, then "분석 보기" asks 1–3 core judgments and shows the TP comparison.
await page.waitForSelector(QUICK);
await page.locator(`${QUICK} [data-act='check']:not([disabled]), ${QUICK} [data-act='call']:not([disabled])`).first().click();
await page.click("#tp-analyze");
await page.waitForSelector("#tp-body [data-card='quick-ask']");
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
must((await page.locator("#tp-body .rrow.ref").count()) >= 1, "Quick 분석: 액션 비교(TP-GTO 모의 혼합 전략)가 없음");
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

await browser.close();
if (failures.length) { console.error(`Gate U: ${failures.length}건 실패`); process.exit(1); }
console.log("Gate U ok");
