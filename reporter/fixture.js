/**
 * Clawsome Playwright fixture — streams live screenshots and test progress
 * to the Clawsome dashboard.
 *
 * Usage:
 *
 *   // In your test files, import from this fixture instead of @playwright/test:
 *   import { test, expect } from '../path/to/clawsome/reporter/fixture.js';
 *
 *   test('my test', async ({ page, clawsome }) => {
 *     await page.goto('https://example.com');
 *     await clawsome.log('Navigated to example.com');
 *     // ...
 *   });
 *
 *   // Or without using the clawsome helper (screenshots still stream automatically):
 *   test('another test', async ({ page }) => {
 *     await page.goto('https://example.com');
 *   });
 *
 * Set CLAWSOME_URL to point at your Clawsome instance (default: http://localhost:3000).
 * If Clawsome is unreachable, tests run normally with no side effects.
 */

import { createHash } from 'node:crypto';
import { test as base } from '@playwright/test';

const CLAWSOME_URL = process.env.CLAWSOME_URL || 'http://localhost:3000';
const SCREENSHOT_INTERVAL_MS = Number(process.env.CLAWSOME_SCREENSHOT_INTERVAL_MS) || 1000;

const hash = (buf) => createHash('sha256').update(buf).digest('hex');

export const test = base.extend({
  clawsome: [async ({ page }, use, testInfo) => {
    let id = null;

    // Create an external context in Clawsome
    try {
      const res = await fetch(`${CLAWSOME_URL}/api/contexts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: testInfo.title, external: true }),
      });
      if (res.ok) {
        const meta = await res.json();
        id = meta.id;
      }
    } catch {
      // Clawsome not available — tests run normally
    }

    if (!id) {
      await use({ id: null, log: async () => {} });
      return;
    }

    const post = (path, body) =>
      fetch(`${CLAWSOME_URL}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).catch(() => {});

    const log = (message, level = 'info') =>
      post(`/api/contexts/${id}/logs`, { level, message });

    // Stream screenshots in the background, skipping frames identical to the last one sent
    let running = true;
    let lastHash = null;
    const loop = (async () => {
      while (running) {
        try {
          const png = await page.screenshot({ type: 'png' });
          const digest = hash(png);
          if (digest !== lastHash) {
            lastHash = digest;
            await fetch(`${CLAWSOME_URL}/api/contexts/${id}/screenshot`, {
              method: 'POST',
              headers: { 'Content-Type': 'image/png' },
              body: png,
            });
          }
        } catch {
          // page may be navigating or closed
        }
        await new Promise((r) => setTimeout(r, SCREENSHOT_INTERVAL_MS));
      }
    })();

    await log(`Test started: ${testInfo.title}`);

    await use({ id, log });

    // Teardown
    running = false;
    await loop;

    // Final screenshot
    try {
      const png = await page.screenshot({ type: 'png' });
      await fetch(`${CLAWSOME_URL}/api/contexts/${id}/screenshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'image/png' },
        body: png,
      });
    } catch {}

    const passed = testInfo.status === testInfo.expectedStatus;
    await log(
      `Test ${testInfo.status}: ${testInfo.title}`,
      passed ? 'info' : 'error',
    );

    // Destroy context
    await fetch(`${CLAWSOME_URL}/api/contexts/${id}`, {
      method: 'DELETE',
    }).catch(() => {});
  }, { auto: true }],
});

export { expect } from '@playwright/test';
