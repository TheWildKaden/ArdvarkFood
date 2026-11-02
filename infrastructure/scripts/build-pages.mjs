import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const source = path.join(root, "docs");
const output = path.join(root, "dist");

function repositoryUrl() {
  const configured = process.env.PAGES_REPOSITORY_URL;
  const actionsRepository = process.env.GITHUB_REPOSITORY;
  let remote = configured || (actionsRepository
    ? `https://github.com/${actionsRepository}`
    : "");

  if (!remote) {
    try {
      remote = execFileSync("git", ["remote", "get-url", "origin"], {
        cwd: root,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      }).trim();
    } catch {
      remote = "https://github.com/TheWildKaden/ArdvarkFood";
    }
  }

  const match = remote.match(
    /^(?:https:\/\/github\.com\/|git@github\.com:)([a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+?)(?:\.git)?\/?$/,
  );
  if (!match) {
    throw new Error(
      "Could not identify the GitHub repository. Set PAGES_REPOSITORY_URL to https://github.com/OWNER/REPOSITORY.",
    );
  }
  return `https://github.com/${match[1]}`;
}

function repositoryBranch() {
  const configured = process.env.PAGES_REPOSITORY_BRANCH;
  const actionsBranch = process.env.GITHUB_REF_NAME;
  const pagesBranch = process.env.CF_PAGES_BRANCH;
  if (configured || actionsBranch || pagesBranch) {
    return configured || actionsBranch || pagesBranch;
  }
  try {
    return execFileSync("git", ["branch", "--show-current"], {
      cwd: root,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim() || "main";
  } catch {
    return "main";
  }
}

const repo = repositoryUrl();
const branch = repositoryBranch();
if (!/^[a-zA-Z0-9_.\/-]+$/.test(branch)) {
  throw new Error("The repository branch contains unsupported characters.");
}

rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });
cpSync(source, output, { recursive: true });

const indexPath = path.join(output, "index.html");
const html = readFileSync(indexPath, "utf8")
  .replaceAll("https://github.com/TheWildKaden/ArdvarkFood", repo)
  .replaceAll("/blob/main/", `/blob/${branch}/`)
  .replaceAll("/tree/main/", `/tree/${branch}/`);
writeFileSync(indexPath, html);

console.log(`Built Pages site for ${repo} (${branch}) at ${path.relative(root, output)}/`);
