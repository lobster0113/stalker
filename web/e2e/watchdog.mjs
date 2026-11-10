// Gate U stall watchdog (#724). A hung Playwright wait used to sit silently until the CI job's 15-minute timeout
// cancelled it, leaving no clue where it stopped. This ends the run first, naming the section and last step.
export const DEFAULT_STALL_MS = 240_000;

// GATE_U_STALL_MS: a positive integer in ms; anything else falls back to the default.
export function stallMsFrom(env = process.env) {
  const v = Number(env.GATE_U_STALL_MS);
  return Number.isInteger(v) && v > 0 ? v : DEFAULT_STALL_MS;
}

// probe(): async, returns extra lines (page state). It may itself hang on a stuck page, so it gets probeMs.
export function createWatchdog({ stallMs = DEFAULT_STALL_MS, now = Date.now, every, probe = async () => [], probeMs = 5_000,
  log = line => console.error(line), exit = code => process.exit(code) } = {}) {
  let section = "(start)", last = "(none)", at = now(), timer = null, fired = false;
  const wd = {
    section(name) { section = name; at = now(); },
    step(line) { last = String(line).split("\n")[0].slice(0, 300); at = now(); },
    stalled() { return now() - at >= stallMs; },
    async check() {
      if (fired || !wd.stalled()) return false;
      fired = true;
      wd.stop();
      log(`Gate U stalled in ${section} after ${((now() - at) / 1000).toFixed(1)}s; last step: ${last}`);
      let extra;
      try {
        extra = await Promise.race([probe(), new Promise(r => setTimeout(() => r([`(page probe timed out after ${probeMs}ms)`]), probeMs))]);
      } catch (e) { extra = [`(page probe failed: ${e.message})`]; }
      for (const l of extra || []) log(l);
      exit(1);
      return true;
    },
    start() {
      wd.stop();
      timer = setInterval(() => { wd.check(); }, every ?? Math.max(1, Math.min(1_000, stallMs)));
      timer.unref?.();   // never keeps a finished run alive
      return wd;
    },
    stop() { if (timer) clearInterval(timer); timer = null; },
  };
  return wd;
}

// One line per open page: G.handNo / G.paused / G.log.length when the page has a game, else its URL only.
export async function probePages(browser, evalMs = 2_000) {
  const out = [];
  const pages = browser.contexts().flatMap(c => c.pages());
  for (const [i, p] of pages.entries()) {
    const st = await Promise.race([
      p.evaluate(() => typeof G === "undefined" ? null : { handNo: G.handNo ?? null, paused: G.paused ?? null, log: Array.isArray(G.log) ? G.log.length : null }).catch(e => ({ error: e.message.split("\n")[0] })),
      new Promise(r => setTimeout(() => r({ error: `evaluate timed out after ${evalMs}ms` }), evalMs)),
    ]);
    out.push(`  page ${i} ${p.url()}: ${JSON.stringify(st)}`);
  }
  return out;
}
