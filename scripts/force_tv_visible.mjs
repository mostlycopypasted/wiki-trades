#!/usr/bin/env node
// Forces TradingView Desktop's Electron/Chromium page out of the "hidden"
// page-visibility state so canvas chart rendering actually happens.
//
// Root cause (found 2026-08-05): capture_tv_chart.sh screenshots were
// silently blank/stale-legend even though every symbol-set/state check
// reported success. Turned out document.hidden was true — the TradingView
// window was occluded/backgrounded on screen, and Chromium throttles canvas
// rendering for hidden pages. Legend text and the live order-ticket price
// box kept updating (they don't depend on the render loop), which made the
// bug easy to miss without actually looking at a captured screenshot.
// `Page.setWebLifecycleState({state:'active'})` forces rendering to resume
// without needing real OS-level window focus (which isn't reliably
// scriptable — AppleScript System Events access needs Accessibility
// permissions this environment doesn't have).

// This script doesn't go through the CLI router (src/cli/router.js), so it
// doesn't inherit that file's --timeout-ms safety net — these CDP calls are
// guarded locally instead. Without this, a stuck compositor here would hang
// forever just like the router-covered commands did before that fix.
const TIMEOUT_MS = 15000;

const MCP_DIR = `${process.env.HOME}/tradingview-mcp`;

async function forceVisible() {
  const conn = await import(`${MCP_DIR}/src/connection.js`);
  const client = await conn.getClient();
  await client.Emulation.setFocusEmulationEnabled({ enabled: true });
  await client.Page.setWebLifecycleState({ state: 'active' });
  // Dismiss any promotional / marketing modals or overlays (e.g. End of Summer sale)
  await conn.evaluate(`(() => {
    try {
      const closeButtons = document.querySelectorAll('[data-name="close"], [aria-label*="close" i], [aria-label*="Close" i], [class*="closeButton"], [class*="close-button"]');
      for (const btn of closeButtons) {
        if (btn.offsetParent !== null || btn.getBoundingClientRect().width > 0) {
          btn.click();
        }
      }
      // Remove any marketing modal containers directly if present
      const overlays = document.querySelectorAll('[data-dialog-name], [data-role="dialog"], [class*="modal-"], [class*="dialog-"], [class*="overlap-manager"] > div');
      for (const el of overlays) {
        const text = el.innerText || '';
        if (text.includes('End of Summer') || text.includes('sale') || text.includes('Up to 80%') || text.includes('Explore offers')) {
          el.remove();
        }
      }
    } catch (e) {}
    return document.hidden;
  })()`);
  return conn.evaluate('document.hidden');
}

let hidden;
try {
  hidden = await Promise.race([
    forceVisible(),
    new Promise((_, reject) => setTimeout(() => reject(new Error(`timed out after ${TIMEOUT_MS}ms`)), TIMEOUT_MS)),
  ]);
} catch (err) {
  console.error(`⚠️ force_tv_visible failed: ${err.message}`);
  process.exit(1);
}

if (hidden) {
  console.error('⚠️ TradingView page still reports hidden after forcing visible state');
  process.exit(1);
} else {
  console.log('✅ TradingView page visibility forced active');
  process.exit(0);
}
