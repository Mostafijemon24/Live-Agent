/**
 * Returns a same-origin app path ("/tasks?x=1#y") or null.
 *
 * Browsers strip tab/CR/LF and treat "\" like "/" while parsing URLs, so
 * "/%09/evil.example" or "/\evil.example" become protocol-relative links.
 * We therefore reject control characters and backslashes outright, then parse
 * the value as a URL and require it to stay on our own origin.
 */
const BASE = "https://steward.invalid";

export function sameOriginPath(input: string | null | undefined): string | null {
  if (!input || input.length > 2048) return null;
  if (/[\u0000-\u001f\u007f\\]/.test(input)) return null;
  let decoded = input;
  try {
    decoded = decodeURIComponent(input);
  } catch {
    return null;
  }
  if (/[\u0000-\u001f\u007f\\]/.test(decoded)) return null;
  if (!input.startsWith("/") || input.startsWith("//")) return null;
  let url: URL;
  try {
    url = new URL(input, BASE);
  } catch {
    return null;
  }
  if (url.origin !== BASE) return null;
  return url.pathname + url.search + url.hash;
}
