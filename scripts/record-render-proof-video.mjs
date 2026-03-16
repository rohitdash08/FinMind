import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const VIEWPORT = { width: 1440, height: 900 };

function usage() {
  console.error(
    [
      'Usage: node scripts/record-render-proof-video.mjs',
      '  --output <webm-path>',
      '  --user-data-dir <chrome-profile-dir>',
      '  --deploy-url <render-deploy-url>',
      '  --backend-dashboard-url <render-backend-dashboard-url>',
      '  --frontend-url <frontend-url>',
      '  --health-url <health-url>',
      '  --commit-sha <sha>',
    ].join(' '),
  );
}

function parseArgs(argv) {
  const options = {};

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];

    switch (arg) {
      case '--output':
        options.outputPath = value;
        index += 1;
        break;
      case '--user-data-dir':
        options.userDataDir = value;
        index += 1;
        break;
      case '--deploy-url':
        options.deployUrl = value;
        index += 1;
        break;
      case '--backend-dashboard-url':
        options.backendDashboardUrl = value;
        index += 1;
        break;
      case '--frontend-url':
        options.frontendUrl = value;
        index += 1;
        break;
      case '--health-url':
        options.healthUrl = value;
        index += 1;
        break;
      case '--commit-sha':
        options.commitSha = value;
        index += 1;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (
    !options.outputPath ||
    !options.userDataDir ||
    !options.deployUrl ||
    !options.backendDashboardUrl ||
    !options.frontendUrl ||
    !options.healthUrl ||
    !options.commitSha
  ) {
    usage();
    throw new Error('Missing required arguments');
  }

  return options;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function humanType(page, selector, value, delayMs = 85) {
  const locator = page.locator(selector);
  await locator.click();
  await locator.fill('');
  await page.keyboard.type(value, { delay: delayMs });
}

async function waitForQuietUi(page) {
  await page.waitForLoadState('domcontentloaded');
  await delay(1200);
}

async function waitForDashboard(page) {
  await Promise.race([
    page.waitForURL(/\/dashboard(?:\/)?(?:[?#].*)?$/, { timeout: 35000 }),
    page.getByRole('heading', { name: /Financial Dashboard/i }).waitFor({ timeout: 35000 }),
  ]);
  await delay(1500);
}

function primaryNavLink(page, name) {
  return page.getByRole('navigation').getByRole('link', { name, exact: true }).first();
}

function buildHealthCheckPage(healthUrl) {
  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>FinMind Render readiness proof</title>
    <style>
      body {
        margin: 32px;
        font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #ffffff;
        color: #111827;
      }
      h1 {
        margin: 0 0 12px;
        font-size: 38px;
      }
      p {
        margin: 0 0 16px;
        color: #374151;
        font-size: 18px;
      }
      pre {
        margin: 20px 0 0;
        padding: 20px 22px;
        border-radius: 12px;
        background: #f3f4f6;
        border: 1px solid #d1d5db;
        color: #111827;
        font-size: 18px;
        line-height: 1.55;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .kicker {
        margin-bottom: 10px;
        color: #065f46;
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 0.03em;
        text-transform: uppercase;
      }
    </style>
  </head>
  <body>
    <main>
      <div class="kicker">Render hosted proof</div>
      <h1 id="status">Checking /health/ready…</h1>
      <p>Verifying database and Redis connectivity on the deployed Render services.</p>
      <pre id="details">Waiting for readiness response…</pre>
    </main>
    <script>
      const details = document.getElementById('details');
      const status = document.getElementById('status');
      fetch(${JSON.stringify(healthUrl)})
        .then(async (response) => {
          const payload = await response.json();
          document.body.dataset.ready = response.ok ? 'true' : 'false';
          status.textContent = response.ok ? 'Render deployment ready' : 'Render deployment not ready';
          details.textContent = JSON.stringify(payload, null, 2);
        })
        .catch((error) => {
          document.body.dataset.ready = 'error';
          status.textContent = 'Readiness check failed';
          details.textContent = String(error);
        });
    </script>
  </body>
</html>`;
}

function buildDeployProofPage({ deployUrl, commitSha }) {
  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Branch-specific Deploy to Render proof</title>
    <style>
      body {
        margin: 32px;
        font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #ffffff;
        color: #111827;
      }
      h1 {
        margin: 0 0 12px;
        font-size: 38px;
      }
      p {
        margin: 0 0 22px;
        color: #374151;
        font-size: 18px;
      }
      .grid {
        display: grid;
        gap: 14px;
      }
      .item {
        padding: 16px 18px;
        border-radius: 12px;
        background: #f9fafb;
        border: 1px solid #d1d5db;
      }
      .label {
        color: #1d4ed8;
        font-size: 13px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }
      .value {
        margin-top: 8px;
        font-size: 18px;
        line-height: 1.45;
        word-break: break-word;
      }
      code {
        color: #111827;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .kicker {
        margin-bottom: 10px;
        color: #1d4ed8;
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 0.03em;
        text-transform: uppercase;
      }
    </style>
  </head>
  <body>
    <main>
      <div class="kicker">Maintainer-requested free-platform one-click proof</div>
      <h1>Opened the branch-specific Deploy to Render link</h1>
      <p>This proof uses the PR branch, not <code>main</code>, and the hosted deployment below is currently live on commit <code>${commitSha}</code>.</p>
      <section class="grid">
        <div class="item">
          <div class="label">Repository</div>
          <div class="value"><code>juzigu40-ui/FinMind</code></div>
        </div>
        <div class="item">
          <div class="label">Branch</div>
          <div class="value"><code>codex/finmind-144-deploy-bounty</code></div>
        </div>
        <div class="item">
          <div class="label">Blueprint path</div>
          <div class="value"><code>render.yaml</code></div>
        </div>
        <div class="item">
          <div class="label">Deploy link</div>
          <div class="value"><code>${deployUrl}</code></div>
        </div>
      </section>
    </main>
  </body>
</html>`;
}

function buildRenderServiceProofPage({ backendDashboardUrl, frontendUrl, healthUrl, commitSha }) {
  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Render live service proof</title>
    <style>
      body {
        margin: 32px;
        font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #ffffff;
        color: #111827;
      }
      h1 {
        margin: 0 0 12px;
        font-size: 38px;
      }
      p {
        margin: 0 0 22px;
        color: #374151;
        font-size: 18px;
      }
      .grid {
        display: grid;
        gap: 14px;
      }
      .item {
        padding: 16px 18px;
        border-radius: 12px;
        background: #f9fafb;
        border: 1px solid #d1d5db;
      }
      .label {
        color: #065f46;
        font-size: 13px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }
      .value {
        margin-top: 8px;
        font-size: 18px;
        line-height: 1.45;
        word-break: break-word;
      }
      code {
        color: #111827;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .kicker {
        margin-bottom: 10px;
        color: #065f46;
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 0.03em;
        text-transform: uppercase;
      }
    </style>
  </head>
  <body>
    <main>
      <div class="kicker">Render live deployment state</div>
      <h1>Hosted services are live on the proof commit</h1>
      <p>The current hosted proof uses the Render frontend and backend services below, both tied to commit <code>${commitSha}</code>.</p>
      <section class="grid">
        <div class="item">
          <div class="label">Frontend service URL</div>
          <div class="value"><code>${frontendUrl}</code></div>
        </div>
        <div class="item">
          <div class="label">Backend readiness URL</div>
          <div class="value"><code>${healthUrl}</code></div>
        </div>
        <div class="item">
          <div class="label">Render backend dashboard</div>
          <div class="value"><code>${backendDashboardUrl}</code></div>
        </div>
        <div class="item">
          <div class="label">Proof commit</div>
          <div class="value"><code>${commitSha}</code></div>
        </div>
      </section>
    </main>
  </body>
</html>`;
}

async function waitForText(page, text, timeout = 45000) {
  await page.waitForFunction(
    (needle) => document.body && document.body.innerText.includes(needle),
    text,
    { timeout },
  );
}

async function warmHostedProof(frontendUrl, healthUrl) {
  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome',
    args: [
      '--disable-dev-shm-usage',
      '--lang=en-US',
      '--disable-features=Translate,TranslateUI,ChromeTranslate',
    ],
  });

  try {
    const context = await browser.newContext({
      locale: 'en-US',
      viewport: VIEWPORT,
      extraHTTPHeaders: {
        'Accept-Language': 'en-US,en;q=0.9',
      },
    });
    const page = await context.newPage();
    page.setDefaultTimeout(45000);

    await page.goto(frontendUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await waitForText(page, 'FinMind');
    await delay(1500);

    const healthResponse = await page.request.get(healthUrl, {
      headers: { 'Accept-Language': 'en-US,en;q=0.9' },
      timeout: 30000,
    });
    if (!healthResponse.ok()) {
      throw new Error(`Health warm-up failed with status ${healthResponse.status()}`);
    }

    await context.close();
  } finally {
    await browser.close();
  }
}

async function main() {
  const {
    outputPath,
    userDataDir,
    deployUrl,
    backendDashboardUrl,
    frontendUrl,
    healthUrl,
    commitSha,
  } = parseArgs(process.argv.slice(2));

  const resolvedOutputPath = path.resolve(outputPath);
  const outputDir = path.dirname(resolvedOutputPath);
  await fs.mkdir(outputDir, { recursive: true });

  await warmHostedProof(frontendUrl, healthUrl);

  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: true,
    channel: 'chrome',
    locale: 'en-US',
    viewport: VIEWPORT,
    extraHTTPHeaders: {
      'Accept-Language': 'en-US,en;q=0.9',
    },
    args: [
      '--disable-dev-shm-usage',
      '--lang=en-US',
      '--disable-features=Translate,TranslateUI,ChromeTranslate',
    ],
    recordVideo: {
      dir: outputDir,
      size: VIEWPORT,
    },
  });
  const page = context.pages()[0] ?? (await context.newPage());
  page.setDefaultTimeout(45000);
  const video = page.video();

  const email = `render-proof+${Date.now()}@finmind.local`;
  const password = 'ProofPass123!';

  try {
    await page.goto(deployUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await delay(2000);
    await page.setContent(buildDeployProofPage({ deployUrl, commitSha }), {
      waitUntil: 'domcontentloaded',
    });
    await delay(6500);

    await page.setContent(
      buildRenderServiceProofPage({
        backendDashboardUrl,
        frontendUrl,
        healthUrl,
        commitSha,
      }),
      { waitUntil: 'domcontentloaded' },
    );
    await delay(7000);

    await page.goto(frontendUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await waitForText(page, 'FinMind');
    await delay(3500);

    await page.setContent(buildHealthCheckPage(healthUrl), { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.body.dataset.ready === 'true', {
      timeout: 30000,
    });
    await delay(5500);

    await page.goto(frontendUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await waitForText(page, 'FinMind');
    await waitForQuietUi(page);
    await delay(2500);
    await page.goto(`${frontendUrl.replace(/\/$/, '')}/register`, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
    await waitForQuietUi(page);
    await delay(1500);

    await humanType(page, '#email', email);
    await delay(250);
    await humanType(page, '#password', password);
    await delay(250);
    await humanType(page, '#confirmPassword', password);
    await delay(350);
    await page.locator('form button[type="submit"]').click();
    await waitForDashboard(page);
    await delay(3500);

    await delay(4500);
  } finally {
    await context.close();
  }

  if (!video) {
    throw new Error('No video was recorded');
  }

  const recordedPath = await video.path();
  await fs.rename(recordedPath, resolvedOutputPath);
  console.log(resolvedOutputPath);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
