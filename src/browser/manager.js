import { chromium } from 'playwright';

let browser = null;

export async function launchBrowser() {
  if (browser) return browser;

  browser = await chromium.launch({
    headless: true,
    args: [
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--no-sandbox',
    ],
  });

  browser.on('disconnected', () => {
    browser = null;
  });

  return browser;
}

export function getBrowser() {
  if (!browser) throw new Error('Browser not launched — call launchBrowser() first');
  return browser;
}

export async function closeBrowser() {
  if (browser) {
    await browser.close();
    browser = null;
  }
}
