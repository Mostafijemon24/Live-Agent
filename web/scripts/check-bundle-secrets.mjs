// Fails if the built client bundle contains secret-looking material or server-only config names.
// Usage (after `npm run build`): node scripts/check-bundle-secrets.mjs
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(".next/static");
const patterns = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /\bsk-(?:proj-|live-)?[A-Za-z0-9]{20,}/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /postgres(?:ql)?(?:\+psycopg)?:\/\/[^\s"']+/,
  /APPROVAL_SIGNING_KEY|MODEL_API_KEY|SMTP_PASSWORD|DATABASE_URL|STEWARD_[A-Z]+_PASSWORD/,
];
let files = 0;
const hits = [];
function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(js|css|json|html|txt)$/.test(e.name)) {
      files++;
      const s = fs.readFileSync(p, "utf8");
      for (const re of patterns) if (re.test(s)) hits.push(`${path.relative(root, p)}: ${re}`);
    }
  }
}
if (!fs.existsSync(root)) {
  console.error("no .next/static — run `npm run build` first");
  process.exit(2);
}
walk(root);
if (hits.length) {
  console.error("Secret-like content in the client bundle:\n" + hits.join("\n"));
  process.exit(1);
}
console.log(`bundle secret check: ${files} files scanned, no secret-like content`);
