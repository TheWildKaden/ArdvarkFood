import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const environment = { ...process.env, NODE_ENV: "development" };
const viteCli = path.join(root, "node_modules", "vite", "bin", "vite.js");
const children = [
  spawn(process.execPath, [path.join(root, "app.js")], { cwd: root, env: environment, stdio: "inherit" }),
  spawn(process.execPath, [viteCli], { cwd: root, env: environment, stdio: "inherit" }),
];
let stopping = false;

function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) child.kill();
  }
  process.exitCode = code;
}

for (const child of children) {
  child.once("error", (error) => {
    console.error("Unable to start a development process:", error.message);
    stop(1);
  });
  child.once("exit", (code, signal) => {
    if (!stopping) {
      console.error(`Development process exited (${signal ?? code ?? "unknown"}); stopping the other process.`);
      stop(code ?? 1);
    }
  });
}

process.once("SIGINT", () => stop(0));
process.once("SIGTERM", () => stop(0));
