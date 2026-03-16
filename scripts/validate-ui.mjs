import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const VIEWPORT = { width: 1440, height: 900 };

function usage() {
  console.error(
    [
      'Usage: node scripts/validate-ui.mjs',
      '  --base-url <frontend-url>',
      '  --health-url <health-url>',
      '  [--provider-name <label>]',
      '  [--record-video <output-path>]',
      '  [--screenshot-dir <output-dir>]',
    ].join(' '),
  );
}

function parseArgs(argv) {
  const options = {
    providerName: 'deployment',
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];

    switch (arg) {
      case '--base-url':
        options.baseUrl = value;
        index += 1;
        break;
      case '--health-url':
        options.healthUrl = value;
        index += 1;
        break;
      case '--provider-name':
        options.providerName = value;
        index += 1;
        break;
      case '--commit-sha':
        options.commitSha = value;
        index += 1;
        break;
      case '--record-video':
        options.recordVideoPath = value;
        index += 1;
        break;
      case '--screenshot-dir':
        options.screenshotDir = value;
        index += 1;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!options.baseUrl || !options.healthUrl) {
    usage();
    throw new Error('Both --base-url and --health-url are required');
  }

  options.baseUrl = options.baseUrl.replace(/\/$/, '');
  options.healthUrl = options.healthUrl.replace(/\/$/, '');

  return options;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function logStep(message) {
  const stamp = new Date().toISOString();
  console.log(`[${stamp}] ${message}`);
}

async function humanType(page, selector, value, delayMs = 85) {
  await page.locator(selector).click();
  await page.locator(selector).fill('');
  await page.keyboard.type(value, { delay: delayMs });
}

async function slowScroll(page, distance) {
  const steps = 8;
  for (let index = 0; index < steps; index += 1) {
    await page.mouse.wheel(0, distance / steps);
    await delay(180);
  }
}

async function pickFirstNonEmptyOption(page, selector) {
  const locator = page.locator(selector);
  const value = await locator.evaluate((element) => {
    const select = element;
    const option = Array.from(select.options).find((item) => item.value);
    return option ? option.value : '';
  });

  if (!value) {
    throw new Error(`No selectable option found for ${selector}`);
  }

  await locator.selectOption(value);
}

async function waitForQuietUi(page) {
  await page.waitForLoadState('domcontentloaded');
  await delay(1200);
}

async function waitForDashboard(page) {
  const dashboardHeading = page.getByRole('heading', { name: /Financial Dashboard/i });
  const fetchFailure = page.getByText('Failed to fetch');

  await Promise.race([
    page.waitForURL(/\/dashboard(?:\/)?(?:[?#].*)?$/, { timeout: 35000 }),
    dashboardHeading.waitFor({ timeout: 35000 }),
    fetchFailure.waitFor({ timeout: 35000 }).then(() => {
      throw new Error('Registration flow failed because the frontend could not reach the API');
    }),
  ]);

  await dashboardHeading.waitFor({ timeout: 15000 });
  await delay(1500);
}

function primaryNavLink(page, name) {
  return page.getByRole('navigation').getByRole('link', { name, exact: true }).first();
}

function buildHealthCheckPage(healthUrl, providerName) {
  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>FinMind readiness check</title>
    <style>
      :root {
        color-scheme: light;
        font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: linear-gradient(135deg, #0f172a 0%, #111827 45%, #164e63 100%);
        color: #e5f3ff;
      }
      .card {
        width: min(920px, calc(100vw - 96px));
        border-radius: 28px;
        padding: 32px 36px;
        background: rgba(15, 23, 42, 0.78);
        border: 1px solid rgba(148, 163, 184, 0.24);
        box-shadow: 0 24px 80px rgba(15, 23, 42, 0.35);
        backdrop-filter: blur(16px);
      }
      .eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        padding: 8px 14px;
        border-radius: 999px;
        background: rgba(16, 185, 129, 0.14);
        color: #a7f3d0;
        font-size: 14px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }
      .dot {
        width: 10px;
        height: 10px;
        border-radius: 999px;
        background: #34d399;
        box-shadow: 0 0 18px rgba(52, 211, 153, 0.9);
      }
      h1 {
        margin: 22px 0 10px;
        font-size: 44px;
        line-height: 1.02;
      }
      p {
        margin: 0;
        color: #cbd5e1;
        font-size: 18px;
      }
      pre {
        margin: 26px 0 0;
        padding: 20px 22px;
        border-radius: 20px;
        background: rgba(15, 23, 42, 0.85);
        border: 1px solid rgba(148, 163, 184, 0.2);
        color: #bfdbfe;
        font-size: 18px;
        line-height: 1.6;
        white-space: pre-wrap;
        word-break: break-word;
      }
    </style>
  </head>
  <body>
    <main class="card">
      <div class="eyebrow"><span class="dot"></span>FinMind deployment verification</div>
      <h1 id="status">Checking backend readiness…</h1>
      <p>Validating database and Redis connectivity before the ${providerName} walkthrough starts.</p>
      <pre id="details">Waiting for /health/ready…</pre>
    </main>
    <script>
      const details = document.getElementById('details');
      const status = document.getElementById('status');
      fetch(${JSON.stringify(healthUrl)})
        .then(async (response) => {
          const payload = await response.json();
          document.body.dataset.ready = response.ok ? 'true' : 'false';
          status.textContent = response.ok ? 'Deployment ready' : 'Deployment not ready';
          details.textContent = JSON.stringify(payload, null, 2);
        })
        .catch((error) => {
          document.body.dataset.ready = 'error';
          status.textContent = 'Health check failed';
          details.textContent = String(error);
        });
    </script>
  </body>
</html>`;
}

async function maybeScreenshot(page, screenshotDir, name) {
  if (!screenshotDir) {
    return;
  }

  await fs.mkdir(screenshotDir, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDir, name),
    fullPage: false,
  });
}

export async function runUiValidation({
  baseUrl,
  healthUrl,
  providerName = 'deployment',
  commitSha,
  recordVideoPath,
  screenshotDir,
}) {
  let resolvedVideoPath = null;
  let videoOutputDir = null;

  if (recordVideoPath) {
    resolvedVideoPath = path.resolve(recordVideoPath);
    videoOutputDir = path.dirname(resolvedVideoPath);
    await fs.mkdir(videoOutputDir, { recursive: true });
  }

  if (screenshotDir) {
    await fs.mkdir(path.resolve(screenshotDir), { recursive: true });
  }

  const browser = await chromium.launch({
    headless: true,
    channel: process.env.FINMIND_PLAYWRIGHT_CHANNEL,
    args: ['--disable-dev-shm-usage'],
  });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    ...(videoOutputDir
      ? {
          recordVideo: {
            dir: videoOutputDir,
            size: VIEWPORT,
          },
        }
      : {}),
  });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);

  const video = recordVideoPath ? page.video() : null;
  const email = `review+${Date.now()}@finmind.local`;
  const password = 'DemoPass123!';
  const billName = 'Studio Internet';
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 10);

  logStep(`provider=${providerName}`);
  if (commitSha) {
    logStep(`commit_sha=${commitSha}`);
  }
  logStep(`validated_at_utc=${new Date().toISOString()}`);
  logStep(`frontend_url=${baseUrl}`);
  logStep(`health_url=${healthUrl}`);

  try {
    logStep('step=readiness');
    await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
    await page.setContent(buildHealthCheckPage(healthUrl, providerName), {
      waitUntil: 'domcontentloaded',
    });
    await page.waitForFunction(() => document.body.dataset.ready === 'true', {
      timeout: 20000,
    });
    await delay(2200);
    await maybeScreenshot(page, screenshotDir, 'readiness.png');
    logStep('step=readiness ok');

    logStep('step=signup');
    await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
    await waitForQuietUi(page);

    await page.getByRole('link', { name: /Get Started for Free/i }).click();
    await page.waitForURL(/\/register$/);
    await waitForQuietUi(page);

    await humanType(page, '#email', email);
    await delay(250);
    await humanType(page, '#password', password);
    await delay(250);
    await humanType(page, '#confirmPassword', password);
    await delay(400);
    await page.getByRole('button', { name: /Create account/i }).click();
    await waitForDashboard(page);
    await maybeScreenshot(page, screenshotDir, 'signup.png');
    logStep('step=signup ok');
    await slowScroll(page, 700);
    await delay(500);
    await slowScroll(page, -700);

    logStep('step=bills');
    await primaryNavLink(page, 'Bills').click();
    await page.getByRole('heading', { name: /Bill Management/i }).waitFor();
    await delay(1200);
    await page.getByRole('button', { name: 'Add Bill' }).first().click();
    await waitForQuietUi(page);
    await humanType(page, 'input[placeholder="Internet"]', billName);
    await delay(200);
    await humanType(page, 'input[type="number"]', '89.99', 70);
    await delay(200);
    await page.locator('input[type="date"]').last().fill(tomorrow);
    await delay(400);
    await page.getByRole('button', { name: 'Create' }).click();
    await page.getByText(billName).waitFor();
    await delay(1500);
    await maybeScreenshot(page, screenshotDir, 'bills.png');
    logStep('step=bills ok');

    logStep('step=reminders');
    await primaryNavLink(page, 'Reminders').click();
    await page.getByRole('heading', { name: /^Reminders$/i }).waitFor();
    await delay(1200);
    await pickFirstNonEmptyOption(page, 'select[aria-label="bill picker"]');
    await delay(250);
    await page.locator('input[aria-label="reminder offsets"]').fill('7,3,1');
    await delay(350);
    await page.getByRole('button', { name: /Schedule Bill Reminders/i }).click();
    await delay(1800);
    logStep('step=reminders ok');

    logStep('step=expenses');
    await primaryNavLink(page, 'Expenses').click();
    await page.getByRole('heading', { name: /^Expenses$/i }).waitFor();
    await delay(1200);
    await humanType(page, '#q-amount', '42.50', 70);
    await delay(200);
    await humanType(page, '#q-description', 'Team lunch', 65);
    await delay(350);
    await page.getByRole('button', { name: /Save Expense/i }).click();
    await delay(1800);
    await maybeScreenshot(page, screenshotDir, 'expenses.png');
    logStep('step=expenses ok');
    await slowScroll(page, 420);
    await delay(400);
    await slowScroll(page, -420);

    logStep('step=insights');
    await primaryNavLink(page, 'Analytics').click();
    await page.getByRole('heading', { name: /Financial Analytics/i }).waitFor();
    await delay(1600);
    await page.locator('select[aria-label="analytics persona"]').selectOption({
      label: 'Debt-focused planner',
    });
    await delay(300);
    await page.getByRole('button', { name: /Refresh Insights/i }).click();
    await delay(2500);
    await slowScroll(page, 500);
    await delay(1000);
    await maybeScreenshot(page, screenshotDir, 'analytics.png');
    logStep('step=insights ok');
  } finally {
    await context.close();
    await browser.close();
  }

  if (!video || !resolvedVideoPath) {
    return null;
  }

  const recordedPath = await video.path();
  await fs.rename(recordedPath, resolvedVideoPath);
  return resolvedVideoPath;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const recordedPath = await runUiValidation(options);

  if (recordedPath) {
    console.log(recordedPath);
  }

  console.log(`FinMind UI validation passed for ${options.providerName}`);
  console.log('ui_path=readiness -> signup -> dashboard -> bills -> reminders -> expenses -> insights');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
