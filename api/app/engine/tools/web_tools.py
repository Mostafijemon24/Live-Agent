"""Read-only web tools: page inspection, an SEO audit and the public WordPress REST API.

Every request goes through the egress client (allowlist, private-address block, size and time
limits). Page content is untrusted data: it is parsed into a few fields, truncated and redacted;
it is never fed back to the planner as instructions.
"""

from __future__ import annotations

import contextlib
import json
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

from pydantic import Field, HttpUrl, field_validator

from app.domain.enums import StepRisk
from app.engine.egress import EgressBlocked, EgressClient, EgressFailed, normalize_host, workspace_policy
from app.engine.redaction import redact
from app.engine.tools.base import (
    PlanEnv,
    ToolArgs,
    ToolContext,
    ToolDefinition,
    ToolError,
    ToolResult,
    const,
    public_only,
)


class UrlArgs(ToolArgs):
    url: HttpUrl

    @field_validator("url")
    @classmethod
    def _len(cls, v: HttpUrl) -> HttpUrl:
        if len(str(v)) > 2048:
            raise ValueError("URL too long")
        return v


def _url_dest(a: ToolArgs, _e: PlanEnv) -> list[str]:
    assert isinstance(a, UrlArgs)
    return [normalize_host(a.url.host or "")]


class _PageParser(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.title = ""
        self._in: str | None = None
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None
        self.lang: str | None = None
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.links_internal = 0
        self.links_external = 0
        self.images = 0
        self.images_no_alt = 0
        self._buf = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"][:20]
        elif tag in ("title", "h1", "h2"):
            self._in, self._buf = tag, ""
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in ("description", "robots", "viewport", "og:title", "og:description"):
                self.meta[name] = a.get("content", "")[:500]
        elif tag == "link" and "canonical" in a.get("rel", "").lower():
            self.canonical = a.get("href", "")[:500]
        elif tag == "a" and a.get("href"):
            host = urlsplit(urljoin(self.base, a["href"])).hostname or ""
            if normalize_host(host) == normalize_host(urlsplit(self.base).hostname or ""):
                self.links_internal += 1
            elif host:
                self.links_external += 1
        elif tag == "img":
            self.images += 1
            if not a.get("alt", "").strip():
                self.images_no_alt += 1

    def handle_data(self, data: str) -> None:
        if self._in:
            self._buf += data

    def handle_endtag(self, tag: str) -> None:
        if tag == self._in:
            text = " ".join(self._buf.split())[:300]
            if tag == "title":
                self.title = text
            elif tag == "h1" and len(self.h1) < 10:
                self.h1.append(text)
            elif tag == "h2" and len(self.h2) < 20:
                self.h2.append(text)
            self._in = None


def _clean(s: str | None, n: int = 300) -> str | None:
    if s is None:
        return None
    return redact(s[:n]).text


def _fetch(ctx: ToolContext, url: str) -> tuple[Any, _PageParser]:
    client = EgressClient(workspace_policy(ctx.env.allowed_domains, ctx.settings), ctx.settings)
    try:
        resp = client.get(url, headers={"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"})
    except EgressBlocked as e:
        raise ToolError(e.code, e.message) from None
    except EgressFailed as e:
        raise ToolError(e.code, e.message, retryable=e.retryable) from None
    if ctx.is_cancelled():
        raise ToolError("cancelled", "The task was cancelled.")
    parser = _PageParser(resp.url)
    ctype = resp.headers.get("content-type", "")
    if "html" in ctype or resp.body[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):
        with contextlib.suppress(Exception):  # malformed HTML still yields partial results
            parser.feed(resp.text())
    return resp, parser


def _page_output(resp: Any, p: _PageParser) -> dict[str, Any]:
    return {
        "url": resp.url,
        "status": resp.status,
        "response_ms": resp.elapsed_ms,
        "bytes": len(resp.body),
        "truncated": resp.truncated,
        "content_type": resp.headers.get("content-type", "")[:100],
        "title": _clean(p.title),
        "description": _clean(p.meta.get("description")),
        "robots": _clean(p.meta.get("robots"), 100),
        "canonical": _clean(p.canonical),
        "lang": p.lang,
        "h1": [_clean(h) for h in p.h1],
        "h2_count": len(p.h2),
        "links_internal": p.links_internal,
        "links_external": p.links_external,
        "images": p.images,
        "images_missing_alt": p.images_no_alt,
    }


def run_inspect(ctx: ToolContext, args: ToolArgs) -> ToolResult:
    assert isinstance(args, UrlArgs)
    resp, p = _fetch(ctx, str(args.url))
    out = _page_output(resp, p)
    return ToolResult(
        summary=f"Inspected {urlsplit(resp.url).hostname}: HTTP {resp.status}, “{(out['title'] or 'no title')[:60]}”",
        output=out,
        classification="public",
    )


def run_seo(ctx: ToolContext, args: ToolArgs) -> ToolResult:
    assert isinstance(args, UrlArgs)
    resp, p = _fetch(ctx, str(args.url))
    out = _page_output(resp, p)
    findings: list[dict[str, str]] = []

    def add(sev: str, msg: str) -> None:
        findings.append({"severity": sev, "issue": msg})

    if resp.status >= 400:
        add("high", f"The page returns HTTP {resp.status}.")
    if not p.title:
        add("high", "Missing <title>.")
    elif not 15 <= len(p.title) <= 65:
        add("medium", f"Title is {len(p.title)} characters (aim for 15-65).")
    desc = p.meta.get("description", "")
    if not desc:
        add("high", "Missing meta description.")
    elif not 50 <= len(desc) <= 160:
        add("medium", f"Meta description is {len(desc)} characters (aim for 50-160).")
    if not p.h1:
        add("high", "No <h1> heading.")
    elif len(p.h1) > 1:
        add("low", f"{len(p.h1)} <h1> headings (one is typical).")
    if "noindex" in p.meta.get("robots", "").lower():
        add("high", "The page asks search engines not to index it (noindex).")
    if not p.canonical:
        add("low", "No canonical link.")
    if p.images_no_alt:
        add("medium", f"{p.images_no_alt} of {p.images} images have no alt text.")
    if "viewport" not in p.meta:
        add("medium", "No mobile viewport meta tag.")
    if resp.elapsed_ms > 2500:
        add("medium", f"Slow response: {resp.elapsed_ms} ms.")
    if not p.lang:
        add("low", "No language attribute on <html>.")
    out["findings"] = findings
    high = sum(1 for f in findings if f["severity"] == "high")
    return ToolResult(
        summary=f"SEO audit of {urlsplit(resp.url).hostname}: {len(findings)} issues ({high} high)",
        output=out,
        classification="public",
    )


WEB_INSPECT = ToolDefinition(
    id="web.inspect",
    label="Inspect a web page (read-only)",
    description="Opens one page on an allowed domain and reads its title, description, headings and links.",
    args_model=UrlArgs,
    risk=StepRisk.read_only,
    permissions=("network.read",),
    impact=const("external_read"),
    classifications=public_only,
    destinations=_url_dest,
    run=run_inspect,
    setting_key="browser",
    timeout_seconds=30,
    max_attempts=3,
    network=True,
    args_hint={"url": "https URL on an allowed domain"},
)

SEO_AUDIT = ToolDefinition(
    id="seo.audit",
    label="SEO audit of a page (read-only)",
    description="Checks one page on an allowed domain for common SEO problems (title, description, headings, alt text, indexing).",
    args_model=UrlArgs,
    risk=StepRisk.read_only,
    permissions=("network.read",),
    impact=const("external_read"),
    classifications=public_only,
    destinations=_url_dest,
    run=run_seo,
    setting_key="browser",
    timeout_seconds=30,
    max_attempts=3,
    network=True,
    args_hint={"url": "https URL on an allowed domain"},
)


# ---------------------------------------------------------------- WordPress (public REST API, read-only)
class WordPressArgs(ToolArgs):
    content: Literal["pages", "posts"] = "pages"
    limit: int = Field(default=20, ge=1, le=50)


def _wp_dest(_a: ToolArgs, e: PlanEnv) -> list[str]:
    return [normalize_host(urlsplit(e.wordpress_site).hostname or "")] if e.wordpress_site else ["(not connected)"]


def run_wordpress(ctx: ToolContext, args: ToolArgs) -> ToolResult:
    assert isinstance(args, WordPressArgs)
    site = ctx.env.wordpress_site
    if not site:
        raise ToolError("integration_not_connected", "WordPress is not connected for this workspace.")
    url = f"{site.rstrip('/')}/wp-json/wp/v2/{args.content}?per_page={args.limit}&_fields=id,title,link,modified,status"
    client = EgressClient(workspace_policy(ctx.env.allowed_domains, ctx.settings), ctx.settings)
    try:
        resp = client.get(url, headers={"Accept": "application/json"})
    except EgressBlocked as e:
        raise ToolError(e.code, e.message) from None
    except EgressFailed as e:
        raise ToolError(e.code, e.message, retryable=e.retryable) from None
    if resp.status in (401, 403):
        raise ToolError("wordpress_forbidden", "The site's REST API refused public read access.")
    if resp.status >= 400:
        raise ToolError("wordpress_error", f"The site returned HTTP {resp.status}.", retryable=resp.status >= 500)
    try:
        items = json.loads(resp.body)
        assert isinstance(items, list)
    except (ValueError, AssertionError):
        raise ToolError("wordpress_invalid", "The site did not return a WordPress content list.") from None
    rows = []
    for it in items[: args.limit]:
        if not isinstance(it, dict):
            continue
        title = it.get("title", {})
        rows.append(
            {
                "id": it.get("id"),
                "title": _clean(str(title.get("rendered", "") if isinstance(title, dict) else title), 200),
                "link": _clean(str(it.get("link", "")), 300),
                "modified": str(it.get("modified", ""))[:30],
            }
        )
    return ToolResult(
        summary=f"Read {len(rows)} {args.content} from {urlsplit(site).hostname} (read-only)",
        output={"site": site, "content": args.content, "items": rows},
        classification="public",
    )


def _wp_available(_s: Any) -> tuple[bool, str]:
    return True, ""


WORDPRESS_READ = ToolDefinition(
    id="wordpress.read",
    label="WordPress: read pages or posts",
    description="Reads published pages or posts from the connected WordPress site through its public REST API. No credentials, no changes.",
    args_model=WordPressArgs,
    risk=StepRisk.read_only,
    permissions=("integration.wordpress.read",),
    impact=const("external_read"),
    classifications=public_only,
    destinations=_wp_dest,
    run=run_wordpress,
    setting_key="wp_read",
    timeout_seconds=30,
    max_attempts=3,
    network=True,
    available=_wp_available,
    args_hint={"content": "pages | posts", "limit": "1-50"},
)
