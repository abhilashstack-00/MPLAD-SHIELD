/**
 * Copies engine output into the frontend's public folder.
 *
 * Two files: `scored.json` (index plus every report block, loaded at startup)
 * and `work_details.json` (full records, fetched only when a work is opened).
 */
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dest = resolve(here, "../public");
mkdirSync(dest, { recursive: true });

let copied = 0;
for (const name of ["scored.json", "work_details.json"]) {
  const src = resolve(here, "../../outputs", name);
  if (!existsSync(src)) {
    console.error(`Missing ${src}\nRun \`python build_data.py\` then \`python score_works.py\` first.`);
    process.exit(1);
  }
  copyFileSync(src, resolve(dest, name));
  console.log(`Copied ${name}`);
  copied += 1;
}
console.log(`${copied} file(s) synced to web/public/`);
