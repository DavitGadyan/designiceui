#!/usr/bin/env node
/**
 * `npx designiceui` - install the designiceui skills into Claude Code in one command.
 *
 * This package is deliberately tiny: it does not carry the engine. It clones (or
 * updates) the real repository into ~/.designiceui and runs its installer, which
 * symlinks the `designice` CLI, copies the skills and commands into ~/.claude,
 * and registers the MCP server. Cloning rather than bundling keeps the npm
 * package at one file and means `npx designiceui` again later is an update.
 *
 *   npx designiceui              install or update
 *   npx designiceui --uninstall  remove everything the installer added
 *
 * Env: DESIGNICEUI_HOME (where to clone; default ~/.designiceui)
 *      DESIGNICEUI_REPO (clone source; default the GitHub repo - a local path works)
 */
"use strict";

const { execFileSync, spawnSync } = require("node:child_process");
const { existsSync } = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const REPO = process.env.DESIGNICEUI_REPO || "https://github.com/DavitGadyan/designiceui.git";
const HOME = process.env.DESIGNICEUI_HOME || path.join(os.homedir(), ".designiceui");
const args = process.argv.slice(2);

function have(cmd) {
  const r = spawnSync(process.platform === "win32" ? "where" : "which", [cmd], { stdio: "ignore" });
  return r.status === 0;
}

function run(cmd, cmdArgs, opts = {}) {
  return execFileSync(cmd, cmdArgs, { stdio: "inherit", ...opts });
}

function fail(msg) {
  console.error(`\n${msg}\n`);
  process.exit(1);
}

if (!have("git")) fail("git is required. Install it, or clone the repo by hand and run scripts/install-skills.sh.");
if (!have("python3")) fail("python3 (3.10+) is required - the skills drive a Python CLI with no dependencies.");

const installer = path.join(HOME, "scripts", "install-skills.sh");

if (args.includes("--uninstall")) {
  if (!existsSync(installer)) fail(`Nothing to uninstall: ${HOME} does not exist.`);
  run("bash", [installer, "--uninstall"]);
  console.log(`\nSkills removed. The clone at ${HOME} was left in place; delete it if you want it gone.`);
  process.exit(0);
}

if (existsSync(path.join(HOME, ".git"))) {
  console.log(`designiceui  updating ${HOME}`);
  const pull = spawnSync("git", ["-C", HOME, "pull", "--ff-only"], { stdio: "inherit" });
  if (pull.status !== 0) {
    console.warn("  ! could not fast-forward (local changes?). Installing what is there.");
  }
} else {
  console.log(`designiceui  cloning ${REPO} -> ${HOME}`);
  run("git", ["clone", "--depth", "1", REPO, HOME]);
}

if (!existsSync(installer)) fail(`Clone looks incomplete: ${installer} is missing.`);

run("bash", [installer]);
