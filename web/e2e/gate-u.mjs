// Gate U 센서: 데모 E2E 흐름 + 3종 화면 스크린샷 + 가로 스크롤/axe 검사. 사용법은 web/README.md.
import { chromium } from "playwright";
import { createRequire } from "node:module";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const url = pathToFileURL(resolve(here, "../demo/index.html")).href + "?speed=30";
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

async function inspect(tag) {
  for (const [name, width, height] of VIEWPORTS) {
    await page.setViewportSize({ width, height });
    await page.screenshot({ path: `${shots}/${tag}-${name}.png` });
    const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
    must(sw <= iw, `${tag} ${width}x${height}: 가로 스크롤 (scrollWidth ${sw} > ${iw}). 넘치는 요소를 줄이세요`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.evaluate(src => { if (!window.axe) (0, eval)(src); }, axeSource);
  const res = await page.evaluate(() => axe.run(document, { resultTypes: ["violations"] }));
  const critical = res.violations.filter(v => v.impact === "critical");
  must(critical.length === 0, `${tag}: axe critical ${critical.map(v => v.id + "×" + v.nodes.length).join(", ")}`);
}

// 1. 시작 → 테이블 → 내 차례 → TP 입력 → 제출 → 채점
await page.goto(url);
await inspect("home");
await page.click("#start-btn");
await page.waitForSelector("#tp-submit");
await inspect("train-input");
await page.evaluate(() => {
  for (const el of document.querySelectorAll("[data-slider], [data-range]")) {
    el.value = Math.round((+el.min + +el.max) / 2);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
});
await page.click("[data-act]:not([disabled]):not([data-act='fold'])");
if (await page.locator("[data-sizes]:not([hidden])").count()) await page.click("[data-size]");
must(!(await page.locator("#tp-submit").isDisabled()), "TP 입력을 채웠는데 제출 버튼이 비활성");
await page.click("#tp-submit");
await page.waitForSelector("#tp-body .result-top");
must((await page.textContent("#tp-body .result-top .ring")).trim() !== "", "채점 점수가 비어 있음");
await inspect("train-result");

// 2. 학습 섹션 1문제
await page.click(".tab[data-view='learn']");
await page.waitForSelector("#dr-go");
await page.click("#dr-go");
must((await page.locator("#dr-res").innerHTML()).trim() !== "", "학습 섹션: 정답 확인 후 결과가 비어 있음");
await inspect("learn");

// 3. 복기: 핸드 입력 → 비교
await page.click(".tab[data-view='review']");
await page.waitForSelector("#rv-deck");
for (let i = 0; i < 2; i++) await page.click("#rv-deck button:not([disabled])");
await page.click("#rv-go");
await page.waitForSelector("#rv-out .rrow");
must((await page.textContent("#rv-out h2")).includes("비교 결과"), "복기: 비교 결과가 표시되지 않음");
await inspect("review");

await browser.close();
if (failures.length) { console.error(`Gate U: ${failures.length}건 실패`); process.exit(1); }
console.log("Gate U ok");
