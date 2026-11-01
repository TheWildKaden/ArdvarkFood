import fs from "node:fs";
import puppeteer from "puppeteer";
import { run } from "@mermaid-js/mermaid-cli";

const diagrams = JSON.parse(fs.readFileSync(0, "utf8"));
let browser;

try {
  browser = await puppeteer.launch({ headless: "shell" });
  for (const { input, output } of diagrams) {
    await run(input, output, {
      browser,
      quiet: true,
      outputFormat: "svg",
      parseMMDOptions: {
        mermaidConfig: { theme: "neutral" },
        backgroundColor: "transparent",
        fontEmbed: true,
        viewport: { width: 0, height: 0, deviceScaleFactor: 1 },
      },
    });
  }
} finally {
  await browser?.close();
}
