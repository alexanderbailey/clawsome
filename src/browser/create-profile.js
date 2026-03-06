#!/usr/bin/env node

import { chromium } from 'playwright';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { mkdirSync } from 'fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', '..');
const PROFILES_DIR = join(ROOT, 'profiles');

const name = process.argv[2];

if (!name) {
  console.error('Usage: npm run profile:create <name>');
  console.error('Example: npm run profile:create amazon');
  process.exit(1);
}

const profilePath = join(PROFILES_DIR, name);
mkdirSync(profilePath, { recursive: true });

console.log(`Opening browser with profile "${name}" at ${profilePath}`);
console.log('Log in to the site, then close the browser window to save the profile.\n');

const context = await chromium.launchPersistentContext(profilePath, {
  headless: false,
  viewport: { width: 1280, height: 720 },
  args: ['--disable-gpu'],
});

const page = context.pages()[0] || await context.newPage();
await page.goto('about:blank');

// Wait for the user to close the browser
await new Promise((resolve) => {
  context.on('close', resolve);
});

console.log(`\nProfile "${name}" saved to ${profilePath}`);
