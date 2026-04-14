#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

const [, , htmlPathArg, pdfPathArg] = process.argv;

if (!htmlPathArg || !pdfPathArg) {
  console.error("Usage: node scripts/render_html_to_pdf.js <htmlPath> <pdfPath>");
  process.exit(1);
}

const repoRoot = process.cwd();
const playwrightPath = path.resolve(repoRoot, "apps/dsa-web/node_modules/playwright");

if (!fs.existsSync(playwrightPath)) {
  console.error(`Playwright not found at ${playwrightPath}`);
  process.exit(1);
}

const { chromium } = require(playwrightPath);

async function main() {
  const htmlPath = path.resolve(htmlPathArg);
  const pdfPath = path.resolve(pdfPathArg);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    await page.goto(pathToFileURL(htmlPath).href, {
      waitUntil: "networkidle",
      timeout: 120000,
    });
    await page.waitForFunction(() => window.__MERMAID_READY === true, {
      timeout: 120000,
    });
    await page.waitForTimeout(800);
    await page.emulateMedia({ media: "screen" });
    await page.pdf({
      path: pdfPath,
      format: "A4",
      printBackground: true,
      margin: {
        top: "10mm",
        right: "10mm",
        bottom: "12mm",
        left: "10mm",
      },
      preferCSSPageSize: true,
    });
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
