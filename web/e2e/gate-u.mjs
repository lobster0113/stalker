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

// #464: the game now pauses after each Guided decision and after every hand the hero played. The flows below
// are about other things, so they press 계속 플레이 / 다음 핸드 automatically; §10 turns this off (__noAuto).
const autoContinue = p => p.addInitScript(() => setInterval(() => {
  if (window.__noAuto || window.__hold) return;
  document.querySelector("#tp-resume, #tp-next-hand, #sd-muck, #fold-close")?.click();
}, 150));
await autoContinue(page);

// Answer one TP question at its low end: the first chip, or a judgment slider (#464) pulled to 0.
async function answerQ(q) {
  if (await q.locator("[data-chip]").count()) await q.locator("[data-chip]").first().click();
  else if (await q.locator("[data-dial]").count()) await q.locator("[data-dial]").fill("0");
}

// #445: on every visible table, card faces/backs must not cover a seat's name or stack, a bet must not sit
// on the dealer button, and the pot's chip pile must not cover the pot amount. Returns the colliding pairs.
function tableOverlaps() {
  const vis = e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && +cs.opacity > 0 && e.offsetParent !== null ? r : null; };
  const hit = (a, b) => a && b && a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
  const out = [];
  for (const seat of document.querySelectorAll(".view.active .seat")) {
    const who = seat.querySelector(".who"), w = who && vis(who);
    for (const c of seat.querySelectorAll(".hole .card")) if (hit(vis(c), w)) out.push(`카드/${seat.querySelector(".nm")?.textContent || seat.dataset.pos || "좌석"}`);
  }
  for (const d of document.querySelectorAll(".view.active .dealer")) for (const b of d.parentElement.querySelectorAll(".bet")) if (b.childElementCount && hit(vis(d), vis(b))) out.push(`딜러/벳 ${b.textContent.trim()}`);
  for (const p of document.querySelectorAll(".view.active .pot")) { const c = p.querySelector(".chips"), a = p.querySelector(".amt"); if (c && a && hit(vis(c), vis(a))) out.push("팟 칩/팟 금액"); }
  return out;
}

// focus: 화면에 들여 놓고 보이는지 검사할 요소. 찍는 동안 데모 진행을 멈춘다.
async function inspect(tag, focus, pg = page) {
  await pg.evaluate(() => { window.__hold = true; });
  for (const [name, width, height] of VIEWPORTS) {
    await pg.setViewportSize({ width, height });
    if (focus) {
      // A re-render (e.g. 복기 비교 결과) can detach the element between lookup and scroll: look it up
      // again and retry instead of failing on a timing race.
      let visible = false;
      for (let attempt = 0; attempt < 3 && !visible; attempt++) {
        try {
          const el = pg.locator(focus).first();
          await el.waitFor({ state: "visible", timeout: 5000 });
          await el.scrollIntoViewIfNeeded({ timeout: 5000 });
          visible = await el.isVisible();
        } catch (e) {
          if (attempt === 2) console.error(`${tag} ${width}x${height}: ${focus} 재시도 실패 — ${e.message.split("\n")[0]}`);
          await pg.waitForTimeout(200);
        }
      }
      must(visible, `${tag} ${width}x${height}: ${focus}가 화면에 없음`);
    }
    await pg.screenshot({ path: `${shots}/${tag}-${name}.png` });
    const ov = await pg.evaluate(tableOverlaps);
    must(!ov.length, `${tag} ${width}x${height}: 테이블 요소 겹침 ${ov.slice(0, 4).join(", ")} — 카드·칩·딜러 버튼 위치를 고치세요 (#445)`);
    const { sw, iw } = await pg.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
    must(sw <= iw, `${tag} ${width}x${height}: 가로 스크롤 (scrollWidth ${sw} > ${iw}). 넘치는 요소를 줄이세요`);
  }
  await pg.setViewportSize({ width: 1440, height: 900 });
  // axe-core도 setTimeout을 쓰므로 hold를 먼저 풀어야 교착하지 않는다.
  await pg.evaluate(() => { window.__hold = false; });
  await pg.evaluate(src => { if (!window.axe) (0, eval)(src); }, axeSource);
  const res = await pg.evaluate(() => axe.run(document, { resultTypes: ["violations"] }));
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
// #440: on a phone the open sheet covers the hero's seat, so its head strip must show the hole cards, board,
// pot, to-call and last opponent action uncovered next to the action row; the grabber taps/drags the sheet.
async function phoneDecision(tag) {
  await page.evaluate(() => { window.__hold = true; });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(600);   // sheet transform transition
  const free = sel => page.evaluate(sel => [...document.querySelectorAll(sel)].map(el => {
    const b = el.getBoundingClientRect(), hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
    return b.width > 0 && b.top >= 0 && b.bottom <= innerHeight && !!hit && (hit === el || el.contains(hit));
  }), sel);
  const hole = await free("[data-strip-hole] .card");
  must(hole.length === 2 && hole.every(Boolean), `${tag} phone: 내 카드(${hole})가 화면 안에서 가려지지 않아야 함 (#440)`);
  const nb = await page.evaluate(() => G.board.length), board = await free("[data-strip-board] .card");
  must(board.length === nb && board.every(Boolean), `${tag} phone: 보드 ${nb}장이 시트 위에 보여야 함 (보이는 것 ${board})`);
  for (const sel of ["[data-strip-pot]", "[data-strip-call]", "[data-strip-last]"]) must((await free(sel)).every(Boolean) && (await free(sel)).length === 1, `${tag} phone: ${sel}가 보이지 않음 (#440)`);
  const acts = await free(`${QUICK} [data-act], #tp-go`);
  must(acts.length >= 3 && acts.every(Boolean), `${tag} phone: 액션 버튼이 카드와 함께 보여야 함 (${acts})`);
  await page.screenshot({ path: `${shots}/${tag}-phone.png` });
  return free;
}
let boardShot = false;
{
  const free = await phoneDecision("train-decision");
  const hd = await page.locator("#tp-handle").boundingBox(), cx = hd.x + hd.width / 2, cy = hd.y + hd.height / 2;
  await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.move(cx, cy - 120, { steps: 4 }); await page.mouse.up();
  must(await page.evaluate(() => document.querySelector("#tp").classList.contains("full")), "phone: 그래버를 위로 끌면 시트가 다 펼쳐져야 함 (#440)");
  const dragDown = async () => {
    await page.waitForTimeout(600);
    const b = await page.locator("#tp-handle").boundingBox(), x = b.x + b.width / 2, y = b.y + b.height / 2;
    await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x, y + 120, { steps: 4 }); await page.mouse.up();
  };
  await dragDown();
  must(await page.evaluate(() => { const c = document.querySelector("#tp").classList; return c.contains("open") && !c.contains("full"); }), "phone: 다 펼친 시트를 아래로 끌면 기본 높이로 돌아와야 함 (#440)");
  await dragDown(); await page.waitForTimeout(600);
  must(await page.evaluate(() => !document.querySelector("#tp").classList.contains("open")), "phone: 그래버를 아래로 끌면 시트가 접혀야 함 (#440)");
  const seat = await free("#table .seat.hero .hole .card");
  must(seat.length === 2 && seat.every(Boolean), `phone: 접힌 시트에서 테이블의 내 카드가 보여야 함 (${seat})`);
  await page.screenshot({ path: `${shots}/train-decision-collapsed-phone.png` });
  await page.click("#tp-handle"); await page.waitForTimeout(600);
  must(await page.evaluate(() => document.querySelector("#tp").classList.contains("open")), "phone: 그래버를 누르면 시트가 다시 열려야 함 (#440)");
  await page.setViewportSize({ width: 1440, height: 900 });
  must(await page.evaluate(() => getComputedStyle(document.querySelector("#tp-strip")).display === "none"), "laptop: 폰 전용 카드 줄이 보이면 안 됨 (#440)");
  await page.evaluate(() => { window.__hold = false; });
}
// #116 Quick: one decision ends in at most 3 inputs — action, size (only for a bet/raise), 진행. No judgment is required.
// #337/#341: the size is free no-limit — the amount box takes any size from the minimum raise to all in.
let freeSized = false;
for (let d = 0; d < 6 && !freeSized; d++) {
  if (d) await page.waitForSelector(QUICK);
  if (!boardShot && await page.evaluate(() => G.board.length >= 3)) {
    await phoneDecision("train-decision-board"); boardShot = true;
    await page.setViewportSize({ width: 1440, height: 900 }); await page.evaluate(() => { window.__hold = false; });
  }
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
  if (freeSized) {
    // #386: a size between two menu sizes is read with the seeded pseudo-harmonic split; the comparison
    // shows the split and grades the split-weighted frequency f x p(A) + (1 - f) x p(B).
    await page.waitForFunction(h => G.eng?.reads?.some(r => r.hand === h) || !G.eng?.ok, freeSized, { timeout: 10_000 });
    const rd = await page.evaluate(() => {
      const tg = TPG.mod, E = G.eng, r = E?.reads?.at(-1), you = G.lastGrade?.refs?.[0]?.you;
      if (!r) return null;
      const again = tg.translateBet(r.s, r.to, engReadRng(E.ent, r.s)).action;
      return { split: r.split, label: r.label, again, fresh: tg.splitBet(r.s, r.to), hist: E.s.history[r.at], seat: r.s.toAct, you,
        weighted: you && G.lastGrade.refs[0].model ? tg.splitScore(r.split, a => G.lastGrade.refs[0].model.mix.find(m => m.a === a)?.p || 0) : null,
        note: document.querySelector("#tp-body [data-model-action]")?.textContent || "",
        hte: tg.translationError(r.s, r.to), tag: !!document.querySelector("#tp-body [data-model-action] [data-approx]") };
    });
    must(!!rd, "번역: 메뉴 밖 금액의 AI 해석 기록(G.eng.reads)이 없음");
    if (rd) {
      must(rd.split.length === 2 && Math.abs(rd.split[0].p + rd.split[1].p - 1) < 1e-12 && rd.split.every(x => x.p > 0 && x.p < 1),
        `번역: 두 메뉴 크기 사이 금액인데 확률 분할이 아님 (${JSON.stringify(rd.split)})`);
      must(JSON.stringify(rd.fresh) === JSON.stringify(rd.split), "번역: 기록된 분할이 엔진 splitBet과 다름");
      must(rd.split.some(x => x.a === rd.label) && rd.again === rd.label, `번역: AI 해석 ${rd.label}이 분할 밖이거나 같은 시드로 다시 읽으면 ${rd.again}`);
      must(rd.hist === `${rd.seat}:${rd.label}`, `번역: 엔진 기록 ${rd.hist}가 AI 해석 ${rd.label}과 다름`);
      must(rd.you && Math.abs(rd.you.p - rd.weighted) < 1e-12, `번역: 내 선택 빈도 ${rd.you?.p}가 분할 가중 점수 ${rd.weighted}가 아님`);
      must(/AI 해석: .*% · .*%/.test(rd.note) && rd.note.includes("확률로 읽어요"), `번역: 비교 화면에 분할 해석 문구가 없음 (${rd.note.slice(0, 200)})`);
      // #417: a split the pre-registered rule flags is shown as approximate, never as a full score.
      must(!!rd.you?.approx === rd.hte && rd.tag === rd.hte, `번역 오차: translationError ${rd.hte}인데 근사 표시 ${rd.tag}·채점 ${rd.you?.approx}`);
      if (rd.hte) must(rd.note.includes("근사(번역)") && rd.note.includes("≈") && rd.note.includes("만점으로 채점하지 않아요")
        && rd.split.every(x => rd.note.includes(`${Math.round(x.p * 100)}%`)), `번역 오차: 근사(번역)·두 이웃 비중·만점 아님 문구가 없음 (${rd.note.slice(0, 300)})`);
      console.log(`번역: ${JSON.stringify(rd.split)} → ${rd.label}, 내 선택 빈도 ${rd.you.p.toFixed(3)}${rd.hte ? " · 근사(번역)" : ""}`);
    }
  }
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
// #386: the size shortcuts are the real-play sizes of TP.md section 6 (chips equal to tpgto.js sizeMenu(s,
// "real", null)), the served policies stay v1, and a real size the v1 menu lacks is read on v1 labels.
{
  let realBet = false;
  for (let d = 0; d < 16 && !realBet; d++) {
    await page.waitForSelector(QUICK);
    const raise = page.locator(`${QUICK} [data-act='raise']:not([disabled])`);
    if (await raise.count() && await page.evaluate(() => !!G.eng?.ok)) {
      await raise.click();
      const chk = await page.evaluate(() => {
        const tg = TPG.mod, s = G.eng.s;
        return { real: tg.sizeMenu(s, "real", null).map(m => m.to), mine: sizeOptions().map(o => o.to), v1: tg.sizeMenu(s).map(m => m.to),
          menu: s.menu, missing: tg.SIZE_LABELS.filter(a => !MENU_COL[a]), shown: document.querySelectorAll("[data-size]:not([hidden])").length };
      });
      must(chk.real.join() === chk.mine.join(), `실전 사이즈: 단축 버튼 금액 ${chk.mine}이 엔진 real 메뉴 ${chk.real}과 다름`);
      must(chk.missing.length === 0, `실전 사이즈: MENU_COL에 색이 없는 라벨 ${chk.missing}`);
      must(chk.menu === "v1", `실전 사이즈: 정책 메타에 메뉴가 없으면 v1이어야 하는데 ${chk.menu}`);
      const idx = chk.mine.findIndex(t => !chk.v1.includes(t));
      if (idx >= 0) {
        const more = page.locator("[data-size-more]");
        if (await more.count()) { must(chk.shown < chk.mine.length, "실전 사이즈: 더보기가 있는데 모든 사이즈가 이미 보임"); await more.click(); }
        must(await page.locator("[data-size]:not([hidden])").count() === chk.mine.length, "실전 사이즈: 더보기 뒤에도 숨은 사이즈가 있음");
        await inspect("train-sizes-real", "[data-size-list]");
        await page.locator(`[data-size="${idx}"]`).click();
        must(await page.evaluate(t => CUR.to === t, chk.mine[idx]), `실전 사이즈: 단축 버튼 ${chk.mine[idx]}을 눌렀는데 금액이 다름`);
        await page.click("#tp-go");
        await page.waitForFunction(t => G.eng?.reads?.at(-1)?.to === t || !G.eng?.ok, chk.mine[idx], { timeout: 10_000 });
        const r = await page.evaluate(() => {
          const tg = TPG.mod, E = G.eng, r = E.reads.at(-1);
          return { split: r.split, label: r.label, again: tg.translateBet(r.s, r.to, engReadRng(E.ent, r.s)).action, v1: tg.legal(r.s), hist: E.s.history[r.at], seat: r.s.toAct };
        });
        must(r.split.every(x => r.v1.includes(x.a)) && r.split.some(x => x.a === r.label) && r.again === r.label && r.hist === `${r.seat}:${r.label}`,
          `실전 사이즈: v1 정책이 실전 사이즈를 자기 라벨로 읽지 않음 (${JSON.stringify(r)})`);
        console.log(`실전 사이즈: 단축 ${chk.mine.length}개 = 엔진 real 메뉴, ${chk.mine[idx] / 100}BB → v1 ${JSON.stringify(r.split)} → ${r.label}`);
        realBet = true;
        continue;
      }
    }
    await page.locator(`${QUICK} [data-act='check']:not([disabled]), ${QUICK} [data-act='call']:not([disabled]), ${QUICK} [data-act='fold']:not([disabled])`).first().click();
    await page.click("#tp-go");
  }
  must(realBet, "실전 사이즈: 16번의 결정 동안 v1 메뉴에 없는 실전 사이즈를 고를 기회가 없었음");
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
  for (const q of qs) await answerQ(q);
}
{
  // #445: preflop with nobody in the pot yet, there is no single opponent range to read.
  const f = await page.evaluate(() => ({ want: fieldOnly(CUR.hero), got: CUR.g.field, range: itemsNow().includes("opp.range") }));
  must(f.got === f.want && !(f.got && f.range), `판단 대상: 아무도 팟에 안 들어왔는데 상대 레인지를 물음 (${JSON.stringify(f)})`);
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
  const chip = first.locator(".q:not(.na) [data-chip], .q:not(.na) [data-dial]").first();
  if (await chip.count()) {
    for (const q of await first.locator(".q:not(.na)").all()) await answerQ(q);
    if (await page.locator("#tp-next").isEnabled()) {
      await page.click("#tp-next");
      must((await page.locator("#tp-body .tpc:not([hidden])").getAttribute("data-card")) !== stage, "다음: 카드가 바뀌지 않음");
      await page.click("#tp-prev");
      const back = page.locator("#tp-body .tpc:not([hidden])");
      must((await back.getAttribute("data-card")) === stage, "이전: 처음 카드로 돌아오지 않음");
      must((await back.locator(".q:not(.na) [data-chip][aria-pressed='true'], .q:not(.na) [data-dial]:not([data-unset])").count()) > 0, "이전: 입력했던 답이 사라짐");
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
      } else await answerQ(q);
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
{
  // #445: engine-computable items are graded on engine values; every mock row says why it is mock.
  const r = await page.evaluate(() => ({ txt: $("#tp-body").innerText, eng: !!G.eng, rows: G.lastGrade.rows.map(x => ({ k: x.k, src: x.src, labels: !!x.labels })), whys: $$("#tp-body .rrow:not(.ref) [data-mock-why]").length }));
  must(!r.txt.includes("TP-GTO(모의)"), "결과 화면: 모의 값이 'TP-GTO(모의)'로 표시됨");
  const eng = r.rows.filter(x => ["hand.outs", "hand.vuln", "opp.range", "board.adv"].includes(x.k));
  must(!r.eng || eng.every(x => x.src === "model"), `결과 화면: 엔진으로 계산할 수 있는 항목이 모의로 채점됨 (${JSON.stringify(eng)})`);
  const mocks = r.rows.filter(x => x.src !== "model" && !x.labels).length;
  must(r.whys === mocks, `결과 화면: 모의 줄 ${mocks}개 중 이유가 붙은 줄 ${r.whys}개`);
  console.log(`엔진 채점 항목: ${eng.map(x => x.k).join(", ") || "(이번 결정엔 없음)"}, 모의 ${mocks}줄`);
}
{
  // #445: the session total opens into one row per finished hand.
  const n = await page.evaluate(() => { const d = $("#infobar [data-sess]"); if (d) d.open = true; return { hands: (G.hands || []).length, rows: $$("#infobar .sess-pop tr").length, has: !!d }; });
  must(n.has && n.rows === Math.min(n.hands, 30), `세션 손익: 핸드별 목록이 없음 (${JSON.stringify(n)})`);
  await inspect("train-session", "#infobar .sess-pop");
  await page.evaluate(() => { const d = $("#infobar [data-sess]"); if (d) d.open = false; });
}
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
  for (let guard = 0; guard < 10; guard++) {   // the hand that was running at the switch is still mid (#364)
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
      await answerQ(q);
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
  const g = await page.evaluate(() => ({ txt: $("#view-learn").innerText, pill: $("#svc-pill").textContent }));
  must(!g.txt.includes("D2에서"), "학습 갤러리: 옛 계획 문구 'D2에서'가 남아 있음");
  must(g.pill.includes("학습 문제"), `헤더 배지: 학습 섹션인데 '${g.pill}'`);
}
{
  const cells = async f => (await page.locator(`#ab-box tr[data-form='${f}'] td`).allTextContents()).map(t => t.trim());
  const a = await cells("A"), b = await cells("B");
  must(a.length === 5 && b.length === 5, "학습 섹션: 질문 형태 실험 표(A·B 행)가 없음");
  must(+a[1] + +b[1] === 3, `학습 섹션: 형태별 기록 합이 3이 아님 (${a[1]}+${b[1]})`);
  must(+b[1] > 0, `학습 섹션: 질문 형태 표 B 행 기록 수가 0 (${b.join(" | ")})`);
  for (const r of [a, b]) if (+r[1] > 0) must(/초$/.test(r[2]) && /초$/.test(r[3]) && /%$/.test(r[4]), `학습 섹션: P50·P95·정답률 칸이 비어 있음 (${r.join(" | ")})`);
  await inspect("learn-eqab", "#ab-box");
}
// #430: every hero decision so far is logged with a time and a strength; few decisions -> "데이터 부족".
{
  await page.waitForSelector("#tell-box [data-tell-progress]");
  const log = await page.evaluate(() => TELL.decisions);
  must(log.length > 0, "텔 리포트: 내 결정이 기록되지 않음");
  must(log.every(d => Number.isFinite(d.ms) && d.ms >= 0 && Number.isFinite(d.strength) && d.strength >= 0 && d.strength <= 1 && d.street >= 0 && d.street <= 3),
    `텔 리포트: 결정 기록에 시간·강도가 비었음 (${JSON.stringify(log.slice(0, 3))})`);
  // #445 compact form: the short-of-data rows sit folded under one progress line, not as table rows.
  const tl = await page.evaluate(() => ({ prog: $("#tell-box [data-tell-progress]")?.textContent || "", waitTiming: !!$("#tell-box [data-tell-wait] [data-tell='timing']"), lackRows: $$("#tell-box tr").filter(r => r.textContent.includes("데이터 부족 (n=")).length, rows: $$("#tell-box tr").length }));
  must(tl.waitTiming, `텔 리포트: 표본이 적은 결정 시간이 '표본이 모자란 항목'에 없음 (${JSON.stringify(tl)})`);
  must(/판정한 항목 \d+\/\d+/.test(tl.prog) && /회 더/.test(tl.prog), `텔 리포트: 진행 한 줄('판정한 항목 n/m · 다음 판정 … k회 더')이 없음 (${tl.prog})`);
  must(tl.lackRows === 0, `텔 리포트: '데이터 부족' 줄이 표에 남아 있음 (${tl.lackRows}줄)`);
  await inspect("learn-tells", "#tell-box");
  await page.setViewportSize({ width: 390, height: 844 });
  const h = await page.evaluate(() => $("#tell-box").getBoundingClientRect().height);
  must(h < 700, `텔 리포트: 폰에서 너무 김 (${Math.round(h)}px, 700 미만이어야 함)`);
  await page.setViewportSize({ width: 1440, height: 900 });
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
await answerQ(page.locator("#drill .dr-q"));
await page.click("#dr-go");
must((await page.locator("#dr-res").innerHTML()).trim() !== "", "학습 섹션: 정답 확인 후 결과가 비어 있음");
await inspect("learn", "#dr-res");
{
  // #445: the equity answer and its win/tie/loss explanation come from one sample; answering 0 scores low.
  await page.click("#dr-back");
  await page.waitForSelector("#learn.gallery");
  await page.locator("#mods .mod[data-k='hand.equity']").click();
  await page.waitForSelector("#dr-go");
  await page.evaluate(() => { LM.val = 0; $("#dr-go").disabled = false; $("#dr-go").click(); });
  const d = await page.evaluate(() => ({ ans: LM.prob.answer, sp: LM.prob.split, res: $("#dr-res").innerText }));
  const shown = +(/에퀴티 = 승 \+ 무\/2 ≈ (\d+)%/.exec(d.res) || [])[1];
  must(d.sp && shown === d.ans, `학습 에퀴티: 정답 ${d.ans}와 설명 ${shown}이 다름`);
  const want = Math.round(Math.max(0, Math.min(100, 100 - Math.max(0, d.ans - 5) * 4)));
  must(d.res.includes(`${want}점`) && (d.ans < 18 || want <= 48), `학습 에퀴티: 0 입력 점수가 ${want}점이 아님 (정답 ${d.ans})`);
}

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
{
  const r = await page.evaluate(() => ({ nums: $$("#rv-out > div > .rrow > .t > span:first-child").map(e => parseInt(e.textContent)), txt: $("#rv-out").innerText, pill: $("#svc-pill").textContent, hero: $$("#rv-table .seat.hero .hole .card").length }));
  must(r.nums.length >= 2 && r.nums.every((n, i) => n === i + 1), `복기: 비교 번호가 1부터 이어지지 않음 (${r.nums.join(",")})`);
  must(!r.txt.includes("TP-GTO(모의)"), "복기: 모의 값이 'TP-GTO(모의)'로 표시됨");
  must(/^복기 · TP-GTO .+ 비교$/.test(r.pill.trim()), `헤더 배지: 캐시 6인 100BB 복기인데 '${r.pill}'`);
  must(r.hero === 2, `복기: 테이블에 내 카드 2장이 없음 (${r.hero}장)`);
}

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
  await autoContinue(p2);
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
  await autoContinue(p3);
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

// 7. #364 핸드 도중 등급 변경: 그 핸드는 중수 키로 끝나고, 다음 핸드부터 상대·질문·비교가 모두 고수 정책이다.
{
  const p4 = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await autoContinue(p4);
  p4.setDefaultTimeout(90_000);
  p4.on("pageerror", e => must(false, `page error (등급 변경): ${e.message}`));
  await p4.goto(url);
  await p4.waitForFunction(() => /학습 중간본/.test(document.querySelector("#svc-pill")?.textContent || "") && TPG.pol.mid);
  await p4.click("#start-btn");
  await p4.waitForSelector(QUICK);
  const sw = await p4.evaluate(() => G.handNo);
  await p4.evaluate(() => { window.__hold = true; });
  await p4.click(".tab[data-view='home']");
  await p4.click("#set-tier [data-v='pro']");
  await p4.click(".tab[data-view='train']");
  const note = p4.locator("#infobar [data-tier-next]");
  must(await note.count() === 1 && (await note.textContent()).includes("다음 핸드부터 고수 정책으로 바뀝니다"), "등급 변경: 바꾼 직후 '다음 핸드부터 고수 정책으로 바뀝니다' 안내가 없음");
  must(await p4.evaluate(() => G.tier === "mid" && G.eng.tier === "mid" && $("#tp-tier").textContent === "중수"), "등급 변경: 핸드 도중에 테이블 등급이 바뀜");
  await p4.waitForTimeout(500);   // let the view fade in; __hold only pauses the demo's timers
  await p4.screenshot({ path: `${shots}/train-tier-next-laptop.png` });
  await p4.evaluate(() => { window.__hold = false; });
  let proTurn = null;
  for (let guard = 0; guard < 40 && !proTurn; guard++) {
    await p4.waitForSelector(QUICK);
    const st = await p4.evaluate(() => ({ hand: G.handNo, tier: G.tier, eng: G.eng?.tier, model: !!CUR?.g?.model, items: TIERS[tierNow()].items.length, proItems: TIERS.pro.items.length }));
    if (st.hand === sw) must(st.tier === "mid" && st.eng === "mid", `등급 변경: 바꾼 핸드 #${sw}의 내 차례가 중수가 아님 (${JSON.stringify(st)})`);
    else proTurn = st;
    await p4.locator(`${QUICK} [data-act='check']:not([disabled]), ${QUICK} [data-act='call']:not([disabled])`).first().click();
    await p4.click("#tp-go");
  }
  must(proTurn && proTurn.tier === "pro" && proTurn.eng === "pro" && proTurn.items === proTurn.proItems, `등급 변경: 다음 핸드의 내 차례가 고수 정책·질문이 아님 (${JSON.stringify(proTurn)})`);
  must(proTurn?.model, "등급 변경: 다음 핸드 내 차례의 TP-GTO 비교(모델)가 없음");
  // let the opponents act a few more turns in the pro hands
  for (let guard = 0; guard < 20 && (await p4.evaluate(h => TPG.botLog.filter(x => x.hand > h).length, sw)) < 6; guard++) {
    await p4.waitForSelector(QUICK);
    await p4.locator(`${QUICK} [data-act='check']:not([disabled]), ${QUICK} [data-act='call']:not([disabled])`).first().click();
    await p4.click("#tp-go");
  }
  const ui = await p4.evaluate(() => ({ info: $("#infobar").textContent, tag: [...document.querySelectorAll(".seat:not(.hero) .persona")].map(e => e.textContent), tp: $("#tp-tier").textContent, note: !!document.querySelector("#infobar [data-tier-next]") }));
  must(ui.info.includes("상대 TP-GTO 고수") && ui.tp === "고수" && !ui.note && ui.tag.every(t => t.includes("TP-GTO 고수")), `등급 변경: 다음 핸드 헤더·좌석 태그·TP 등급이 고수가 아님 (${JSON.stringify(ui)})`);
  const log = await p4.evaluate(() => TPG.botLog);
  const before = log.filter(x => x.hand <= sw), after = log.filter(x => x.hand > sw);
  must(before.length > 0 && before.every(x => x.tier === "mid"), `등급 변경: 바꾼 핸드의 AI 결정이 중수가 아님 (${[...new Set(before.map(x => x.tier))]})`);
  must(after.length >= 6 && after.every(x => x.tier === "pro"), `등급 변경: 다음 핸드부터 AI 결정이 고수가 아님 (${after.length}개, ${[...new Set(after.map(x => x.tier))]})`);
  const mid = JSON.parse(readFileSync(resolve(webRoot, "app/policy/mid-6.json"), "utf8"));
  const pro = JSON.parse(readFileSync(resolve(webRoot, "app/policy/pro-6.json"), "utf8"));
  const rowsMatch = (file, xs) => {
    let n = 0;
    for (const d of xs) {
      const row = file.policy[d.key];
      if (!row) { must(!d.fromTable, `등급 변경: 파일에 없는 키인데 표에서 읽었다고 함 (${d.tier} ${d.key})`); continue; }
      n++;
      must(row.length === d.acts.length && row.every((v, j) => Math.abs(v / file.q - d.probs[j]) < 1e-9), `등급 변경: 페이지 확률이 ${d.tier} 정책 파일과 다름 (${d.key})`);
    }
    return n;
  };
  const nMid = rowsMatch(mid, before), nPro = rowsMatch(pro, after);
  must(nPro >= 3, `등급 변경: 다음 핸드부터 pro-6.json 행과 대조한 AI 결정이 모자람 (${nPro}개, 전체 ${after.length})`);
  console.log(`등급 변경: 바꾼 핸드 AI 결정 ${before.length}개(mid 표 ${nMid}), 다음 핸드부터 ${after.length}개(pro 표 ${nPro})`);
  await p4.close();
}

// 8. #441 known leaks: a forced AA first-in decision in a cell the probe flagged (mid-6.leaks.json) shows the
// strong warning instead of a frequency grade, and the home model card names the known preflop leak.
{
  const leaks = JSON.parse(readFileSync(resolve(webRoot, "app/policy/mid-6.leaks.json"), "utf8"));
  const cell = leaks.leaks.filter(c => c.spot === "first_in" && c.group === "AA").sort((a, b) => a.seat - b.seat)[0];
  must(!!cell, "known leaks: mid-6.leaks.json has no first_in AA leak cell to force (re-run python -m stalker.tools.policy_leaks)");
  const p5 = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await autoContinue(p5);
  p5.setDefaultTimeout(90_000);
  p5.on("pageerror", e => must(false, `page error (known leaks): ${e.message}`));
  await p5.addInitScript(() => {
    const st = window.setTimeout.bind(window);
    window.setTimeout = (fn, ms, ...args) => st(function tick() { if (window.__hold) st(tick, 25); else fn(...args); }, ms);
  });
  await p5.goto(url);
  await p5.waitForFunction(() => TPG.pol.mid && "mid" in TPG.leaks);
  const card = p5.locator("#model-status [data-known-leak]");
  must(await card.count() === 1 && /학습 중간본/.test(await card.textContent()) && /프리플랍/.test(await card.textContent())
    && /issues\/391$/.test(await card.locator("a").getAttribute("href")), "known leaks: 시작 화면 모델 카드에 알려진 프리플랍 결함·#391 링크가 없음");
  if (cell) {
    await p5.evaluate(() => { window.__hold = true; });
    await p5.click("#start-btn");
    await p5.waitForFunction(() => G?.deck?.length > 0 && G.seats.some(s => s.cards.length));
    // Seat the hero at the cell's position with AA; the seats before it get hands every policy folds first in.
    await p5.evaluate(q => {
      G.button = ((-3 - q) % G.n + 2 * G.n) % G.n;
      const forced = new Map([[0, [51, 50]]]), junk = [[20, 1], [24, 5], [28, 9], [32, 13], [36, 17]];
      for (const s of G.seats) if (!s.isHero && engSeatOf(s.i) < q) forced.set(s.i, junk[engSeatOf(s.i)]);
      const used = new Set([...forced.values()].flat());
      for (let i = G.deck.length - 1; i >= 0; i--) if (used.has(G.deck[i])) G.deck.splice(i, 1);
      for (const s of G.seats) s.cards = forced.get(s.i)?.slice() ?? [G.deck.pop(), G.deck.pop()];
      window.__hold = false;
    }, cell.seat);
    await p5.waitForSelector(QUICK);
    const v = await p5.evaluate(() => ({ leak: CUR.g.model?.leak, seat: CUR.g.model?.d?.seat, hist: G.eng?.s?.history }));
    must(v.leak?.kind === "leak" && v.leak.spot === "first_in" && v.leak.cell.group === "AA" && v.seat === cell.seat,
      `known leaks: 강제한 AA 퍼스트 인(${cell.pos})이 결함 칸으로 잡히지 않음 (${JSON.stringify(v)})`);
    await p5.locator(`${QUICK} [data-act='fold']:not([disabled]), ${QUICK} [data-act]:not([disabled])`).first().click();
    await p5.evaluate(() => { window.__hold = true; });
    await p5.click("#tp-go");
    const warn = p5.locator("#tp-body [data-model-action] [data-leak-warn]");
    await warn.waitFor();
    const t = (await warn.textContent()).replace(/\s+/g, " ");
    must(t.includes("이 스팟의 정책 답은 검증에서 손해로 확인됨 (#391)") && t.includes(`+${cell.gain_bb} bb`), `known leaks: 경고 문구가 다름 (${t})`);
    must((await p5.locator("#tp-body [data-model-action] .t").first().textContent()).includes("채점 안 함"), "known leaks: 결함 칸인데 정책 행 대비 내 선택 빈도를 보여 줌");
    await p5.screenshot({ path: `${shots}/train-leak-warn-laptop.png` });
    console.log(`known leaks: ${cell.pos} AA 퍼스트 인 경고 (+${cell.gain_bb} bb)`);
  }
  await p5.close();
}

// 10. #464 Guided: the game waits on the grading after every decision; every hand the hero played ends with
// that hand's analysis and waits; plan.pot is a slider; 종료·분석 stops the game and the report counts match.
{
  const p6 = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  p6.setDefaultTimeout(90_000);
  p6.on("pageerror", e => must(false, `page error (session report): ${e.message}`));
  await p6.addInitScript(() => { window.__noAuto = true; window.__sfxLog = []; });
  await autoContinue(p6);
  await p6.addInitScript(() => {
    const st = window.setTimeout.bind(window);
    window.setTimeout = (fn, ms, ...args) => st(function tick() { if (window.__hold) st(tick, 25); else fn(...args); }, ms);
  });
  await p6.goto(url);
  await p6.click("#set-play [data-v='guided']");
  await p6.click("#start-btn");
  const still = () => p6.evaluate(async () => { const a = [G.handNo, G.log.length]; await new Promise(r => setTimeout(r, 2500)); return G.paused && G.handNo === a[0] && G.log.length === a[1]; });
  let decided = 0, hands = 0, slider = false, foldViews = 0, closedHand = -1, targetSeen = false;
  const dials = new Set();
  for (let guard = 0; guard < 80 && (decided < 4 || hands < 2 || foldViews < 2); guard++) {
    await p6.waitForSelector("#tp-body .tpc:not([hidden]), #tp-resume, #tp-next-hand, #sd-muck, #fold-close");
    if (await p6.locator("#sd-muck").count()) { await p6.click("#sd-muck"); continue; }
    if (await p6.locator("#fold-close").count()) {
      // Folded: the analysis is up and the hand runs on fast. Kept open, the table holds at the hand's end;
      // closed (second time), the next hand starts without the hand-end hold. Read and act under __hold:
      // a fast hand can end between the selector wait and a click.
      const f = await p6.evaluate(close => {
        window.__hold = true;
        const b = $("#fold-close");
        const r = { open: !!b, paused: !!G.paused, fast: !!G.fast, hr: !!$("#tp-body [data-hand-review][data-live]"), no: G.handNo };
        if (b && close) b.click();
        window.__hold = false;
        return r;
      }, foldViews >= 1);
      if (!f.open) continue;
      must(!f.paused && f.fast && f.hr, `폴드 뒤: 분석 화면이 뜨고 게임은 빠르게 계속돼야 함 (${JSON.stringify(f)})`);
      if (!foldViews++) { await p6.waitForSelector("#tp-next-hand"); continue; }
      closedHand = f.no;
      await p6.waitForFunction(no => G.handNo > no || !!$("#tp-next-hand"), f.no);
      continue;
    }
    if (await p6.locator("#tp-next-hand").count()) {
      const v = await p6.evaluate(() => ({ no: G.handNo, rows: $$("#tp-body [data-hr-dec]").length, want: G.decs.filter(d => d.hand === G.handNo).length }));
      must(v.rows === v.want && v.rows > 0, `핸드 분석: 핸드 #${v.no}의 내 결정 ${v.want}개인데 표 줄 ${v.rows}개`);
      must(v.no !== closedHand, `폴드 뒤 분석을 닫았는데 핸드 #${v.no} 끝에서 멈춤`);
      if (!hands) { must(await still(), "핸드 분석: 화면이 떠 있는 동안 다음 핸드가 시작됨"); await inspect("train-hand-review", "#tp-body [data-hand-review]", p6); }
      hands++; await p6.click("#tp-next-hand"); continue;
    }
    if (await p6.locator("#tp-resume").count()) {
      if (decided === 1) { must(await still(), "Guided: 채점 화면에서 게임이 멈추지 않음"); must(await p6.locator("#tp-body .result-top").count() === 1, "Guided 멈춤: 채점 결과가 없음"); }
      await p6.click("#tp-resume"); continue;
    }
    // The opponent the C-stage questions read is outlined on the table (one seat, the graded opponent).
    const tg = await p6.evaluate(() => ({ on: $$(".seat.target").map(e => e.id), want: fieldOnly(CUR.hero) ? null : "seat-" + CUR.g.opp.i, tag: $$(".seat.target .target-tag").length }));
    must(tg.want ? tg.on.length === 1 && tg.on[0] === tg.want && tg.tag === 1 : tg.on.length === 0, `읽기 대상 표시가 다름 (${JSON.stringify(tg)})`);
    if (tg.want && !targetSeen) { targetSeen = true; await inspect("train-target", "#table .seat.target", p6); }
    // Answer the deck: the first decision raises or calls (so plan.pot is asked), later ones fold to end hands.
    for (let c = 0; c < 12; c++) {
      const card = p6.locator("#tp-body .tpc:not([hidden])");
      for (const q of await card.locator(".q:not(.na)").all()) {
        if (await q.locator("[data-act]").count()) {
          const pick = decided ? "[data-act='fold']:not([disabled]), [data-act='check']:not([disabled])" : "[data-act]:not([disabled]):not([data-act='fold'])";
          await q.locator(pick).first().click();
          if (await p6.locator("[data-sizes]:not([hidden]) [data-size]").count()) await p6.locator("[data-sizes]:not([hidden]) [data-size]").first().click();
        } else if (await q.locator("[data-dial]").count()) {
          // Judgment items are sliders (#464); plan.pot is checked by name, the others by the ends.
          const k = await q.getAttribute("data-k"), step = +(await q.locator("[data-dial]").getAttribute("step"));
          const v = Math.round(70 / step) * step;
          await q.locator("[data-dial]").fill(String(v));
          must((await q.locator("[data-val]").textContent()).trim() === String(v) && !(await q.locator("[data-chip]").count()), `${k} 슬라이더: 값 ${v}이 표시되지 않거나 칩이 남아 있음`);
          if (k === "plan.pot") slider = true;
          dials.add(k);
        } else await answerQ(q);
      }
      const next = p6.locator("#tp-next");
      if (await next.isVisible() && await next.isEnabled()) { await next.click(); continue; }
      break;
    }
    await p6.click("#tp-submit");
    decided++;
  }
  must(decided >= 4 && hands >= 2 && foldViews >= 2, `Guided 흐름: 결정 ${decided}회·핸드 분석 ${hands}회·폴드 화면 ${foldViews}회 (4·2·2 이상 필요)`);
  must(targetSeen, "읽기 대상 하이라이트가 한 번도 나오지 않음");
  const snd = await p6.evaluate(() => [...new Set(window.__sfxLog)]);
  const files = await p6.evaluate(() => ({ ok: Object.values(SND.buf || {}).filter(Boolean).length, want: new Set(Object.values(SFX_FILES).flat()).size + 2 * VOICE_KINDS.length }));
  must(files.ok === files.want, `효과음 파일: ${files.want}개 중 ${files.ok}개만 디코드됨 (app/assets/sfx/*.ogg·voice-*.mp3 경로·형식 확인)`);
  must(["deal", "flip", "fold"].every(k => snd.includes(k)) && snd.some(k => ["check", "call", "bet", "raise", "allin"].includes(k)), `효과음: 딜·오픈·액션 소리가 다 나오지 않음 (${snd.join(",")})`);
  must(slider, "plan.pot 슬라이더가 한 번도 나오지 않음 (첫 결정은 폴드가 아닌 액션이어야 함)");
  const chipJudg = await p6.evaluate(() => Object.keys(TP).filter(k => isDial(k)).length);
  must(dials.size >= 2 && chipJudg >= 8, `판단 슬라이더: 슬라이더로 답한 항목 ${[...dials].join(",")} (2개 이상), 슬라이더 항목 정의 ${chipJudg}개`);
  // Showdown order (#464): a bet river starts with the last river aggressor, a checked river with the first
  // live seat after the button; a beaten hand that wins nothing may muck.
  const so = await p6.evaluate(() => {
    const keep = { street: G.street, agg: G.streetAgg }, cs = G.seats.slice(0, 3);
    G.street = 3; G.streetAgg = cs[2].i; const bet = showOrder(cs).map(s => s.i);
    G.streetAgg = null; const chk = showOrder(cs).map(s => s.i), fa = firstAfterButton();
    G.street = keep.street; G.streetAgg = keep.agg;
    return { bet, chk, first: cs[2].i, fa, inCs: cs.some(s => s.i === fa) };
  });
  must(so.bet[0] === so.first && so.bet.length === 3, `쇼다운 순서: 리버 벳이면 마지막 공격자가 먼저 (${JSON.stringify(so)})`);
  must(so.chk.length === 3 && (!so.inCs || so.chk[0] === so.fa), `쇼다운 순서: 체크로 돌면 버튼 다음 좌석부터 (${JSON.stringify(so)})`);
  await p6.waitForSelector("#end-game");
  await p6.click("#end-game");
  await p6.waitForSelector(".modal[data-report]");
  const r = await p6.evaluate(() => ({ dec: +$("[data-rp-decisions] b").textContent, hands: +$("[data-rp-hands] b").textContent, want: G.decs.length, wantH: G.hands.length, ended: G.ended, items: $$("[data-rp-items] tr").length, act: !!$("[data-rp-act]") }));
  must(r.ended && r.dec === r.want && r.dec >= decided && r.hands === r.wantH && r.hands >= 2, `세션 분석: 결정·핸드 수가 기록과 다름 (${JSON.stringify(r)})`);
  must(r.items > 0 && r.act, `세션 분석: 항목별 점수 표나 TP-GTO 액션 비교가 없음 (${JSON.stringify(r)})`);
  const h0 = await p6.evaluate(() => G.handNo);
  await p6.waitForTimeout(2500);
  must(await p6.evaluate(() => G.handNo) === h0, "종료·분석: 게임이 끝나지 않고 다음 핸드가 진행됨");
  await inspect("train-session-report", ".modal[data-report] .box", p6);
  console.log(`세션 분석: 결정 ${r.dec}회 · 핸드 ${r.hands}개 · 항목 ${r.items}개`);
  await p6.click("#rp-close");
  must((await p6.textContent("#end-game")).includes("분석 다시 보기"), "종료 뒤 헤더 버튼이 '분석 다시 보기'가 아님");
  // 11. #465 내 게임: every played hand is saved, survives a reload, and the replay steps through the saved
  // action list; a hero decision shows its label and the reasons; a broken record never breaks the page.
  const saved = await p6.evaluate(() => { const d = JSON.parse(localStorage.getItem("stalker.games") || "null"); return { n: d?.games?.reduce((a, g) => a + g.hands.length, 0) ?? 0, played: G.hands.length, an: d?.games?.flatMap(g => g.hands).flatMap(h => h.acts).filter(a => a.an && a.an.p != null).length ?? 0 }; });
  must(saved.n === saved.played && saved.n >= 2, `내 게임: 저장된 핸드 ${saved.n}개, 끝난 핸드 ${saved.played}개`);
  must(saved.an > 0, "내 게임: 정책 비교가 담긴 결정이 하나도 저장되지 않음");
  await p6.reload();
  await p6.click("[data-view='review']");
  await p6.waitForSelector("[data-mg-game]");
  await p6.click("[data-mg-game]");
  const listed = await p6.evaluate(() => ({ rows: $$("[data-mg-hand]").length, text: $$("[data-mg-hand]").map(b => b.textContent).join("|") }));
  must(listed.rows === saved.n && /결정 \d+/.test(listed.text), `내 게임: 목록에 핸드 ${listed.rows}개 (저장 ${saved.n}), 결정 수 표시: ${listed.text}`);
  const withAn = await p6.evaluate(() => { const g = JSON.parse(localStorage.getItem("stalker.games")).games[0]; return g.hands.filter(h => h.acts.some(a => a.an && a.an.p != null)).map(h => h.no); });
  must(withAn.length > 0, "내 게임: 첫 게임에 정책 비교가 있는 핸드가 없음");
  await p6.click(`[data-mg-hand='${withAn[0]}']`);
  const want = await p6.evaluate(no => JSON.parse(localStorage.getItem("stalker.games")).games[0].hands.find(h => h.no === no).acts.map(a => a.txt), withAn[0]);
  const got = await p6.evaluate(() => $$("[data-mg-act]").map(b => b.firstChild.textContent.trim()));
  must(JSON.stringify(got) === JSON.stringify(want), `내 게임 리플레이: 액션 목록이 저장과 다름 (${JSON.stringify(got)} vs ${JSON.stringify(want)})`);
  let stepped = 0;
  while (!(await p6.locator("[data-mg-next]").isDisabled())) { await p6.click("[data-mg-next]"); stepped++; }
  must(stepped === want.length && (await p6.textContent("[data-mg-pos]")) === `${want.length}/${want.length}`, `내 게임 리플레이: 다음 액션 ${stepped}번, 액션 ${want.length}개`);
  await p6.click("[data-mg-first]");
  const heroStep = await p6.evaluate(no => JSON.parse(localStorage.getItem("stalker.games")).games[0].hands.find(h => h.no === no).acts.findIndex(a => a.hero && a.an && a.an.p != null) + 1, withAn[0]);
  await p6.click(`[data-mg-step='${heroStep}']`);
  const an = await p6.evaluate(() => ({ v: $("[data-mg-verdict]")?.textContent, li: $$("[data-mg-analysis] li").length, text: $("[data-mg-analysis]")?.textContent }));
  must(["잘함", "아쉬움", "실수", "채점 안 함"].includes(an.v) && an.li >= 1 && /정책이/.test(an.text), `내 게임 리플레이: 결정 분석이 없음 (${JSON.stringify(an)})`);
  await inspect("games-replay", "[data-mg-table]", p6);
  await p6.evaluate(() => { localStorage.setItem("stalker.games", "{broken"); });
  await p6.reload();
  await p6.click("[data-view='review']");
  await p6.waitForSelector("[data-mg-empty]");
  console.log(`내 게임: 핸드 ${saved.n}개 저장·재로드·리플레이 ${want.length}액션 · 분석 "${an.v}"`);
  await p6.close();
}

await browser.close();
server.close();
if (failures.length) { console.error(`Gate U: ${failures.length}건 실패`); process.exit(1); }
console.log("Gate U ok");
