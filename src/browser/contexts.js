import { randomUUID } from 'crypto';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { existsSync } from 'fs';
import { chromium } from 'playwright';
import { getBrowser } from './manager.js';
import { insertContext, updateContextStatus, deleteContext as dbDeleteContext } from '../db/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', '..');
const PROFILES_DIR = join(ROOT, 'profiles');

// In-memory map: id -> { context, page, meta }
const alive = new Map();

/**
 * Create a new isolated browser context.
 * If `profile` is given and exists in ./profiles/<profile>/, a persistent context is used.
 */
export async function createContext({ name, profile, visible }) {
  const id = randomUUID();
  let context;
  let page;

  const profilePath = profile ? join(PROFILES_DIR, profile) : null;
  const hasPersistent = profilePath && existsSync(profilePath);

  if (hasPersistent) {
    // Persistent context gets its own browser instance with stored state
    context = await chromium.launchPersistentContext(profilePath, {
      headless: true,
      args: ['--disable-gpu', '--disable-dev-shm-usage', '--no-sandbox'],
      viewport: { width: 1280, height: 720 },
    });
    page = context.pages()[0] || await context.newPage();
  } else {
    // Ephemeral context within the shared browser
    const browser = getBrowser();
    context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
    });
    page = await context.newPage();
  }

  const meta = { id, name, profile: profile || null, visible: !!visible, persistent: !!hasPersistent };
  alive.set(id, { context, page, meta });

  // Persist to DB
  insertContext({ id, name, profile, visible: !!visible });

  return meta;
}

/**
 * Get a living context entry by id.
 */
export function getAliveContext(id) {
  return alive.get(id) || null;
}

/**
 * List all alive context metadata.
 */
export function listAliveContexts() {
  return Array.from(alive.values()).map((c) => c.meta);
}

/**
 * Navigate the context's page to a URL.
 */
export async function navigateTo(id, url) {
  const entry = alive.get(id);
  if (!entry) throw new Error(`Context ${id} not found`);
  await entry.page.goto(url, { waitUntil: 'domcontentloaded' });
  return { url: entry.page.url() };
}

/**
 * Take a screenshot of the context's page.
 */
export async function takeScreenshot(id) {
  const entry = alive.get(id);
  if (!entry) throw new Error(`Context ${id} not found`);
  return entry.page.screenshot({ type: 'png' });
}

/**
 * Execute a Playwright action on the context's page.
 */
export async function execAction(id, { action, selector, value, script }) {
  const entry = alive.get(id);
  if (!entry) throw new Error(`Context ${id} not found`);
  const { page } = entry;

  switch (action) {
    case 'click':
      await page.click(selector);
      return { action: 'click', selector };

    case 'type':
      await page.fill(selector, value);
      return { action: 'type', selector, value };

    case 'select':
      await page.selectOption(selector, value);
      return { action: 'select', selector, value };

    case 'wait':
      await page.waitForSelector(selector);
      return { action: 'wait', selector };

    case 'evaluate':
      const result = await page.evaluate(script);
      return { action: 'evaluate', result };

    default:
      throw new Error(`Unknown action: ${action}`);
  }
}

/**
 * Destroy a context and clean up.
 */
export async function destroyContext(id) {
  const entry = alive.get(id);
  if (!entry) throw new Error(`Context ${id} not found`);

  await entry.context.close();
  alive.delete(id);

  // Update DB
  updateContextStatus(id, 'stopped');
}

/**
 * Close all alive contexts (for graceful shutdown).
 */
export async function destroyAllContexts() {
  for (const [id] of alive) {
    try {
      await destroyContext(id);
    } catch {
      // best-effort on shutdown
    }
  }
}
