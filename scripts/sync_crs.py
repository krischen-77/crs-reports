#!/usr/bin/env python3
"""Archive public CRS originals, with explicit source coverage and persistent retries."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import fitz
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify

MIRROR = "https://www.everycrsreport.com/"
API = "https://api.congress.gov/v3/crsreport"
RSS = MIRROR + "rss.xml"
HOSTS = {"www.everycrsreport.com", "everycrsreport.com", "www.congress.gov", "congress.gov", "crsreports.congress.gov", "api.congress.gov"}
MAX_BYTES = 80 * 1024 * 1024
SCHEMA_VERSION = 2
ROOT = Path(__file__).resolve().parents[1]


def digest(data: bytes, algorithm: str = "sha256") -> str:
    return hashlib.new(algorithm, data).hexdigest()


def report_id(value: str) -> str:
    value = str(value).upper().strip()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,29}", value):
        raise ValueError("Invalid report identifier")
    return value


def day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def within(value: str | None, start: date, end: date) -> bool:
    d = day(value)
    return d is not None and start <= d <= end


def category(identifier: str) -> str:
    for prefix, folder in [("LSB", "sidebars"), ("IF", "in-focus"), ("IN", "insights"), ("IG", "infographics"), ("TE", "testimony")]:
        if identifier.startswith(prefix):
            return folder
    return "reports"


def safe_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme != "https" or p.hostname not in HOSTS or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Disallowed upstream URL")
    query = [(k, v) for k, v in parse_qsl(p.query) if k.lower() != "api_key"]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(query), ""))


def access_scope(url: str) -> str:
    """An HTML access denial must not disable independently public PDF routes."""
    p = urlsplit(url)
    if p.hostname == "api.congress.gov":
        return p.hostname
    if p.hostname in ("www.congress.gov", "congress.gov"):
        for kind in ("HTML", "PDF"):
            if f"/{kind}/" in p.path:
                return f"{p.hostname}:{kind}"
    return p.hostname or ""


def source_version(url: str, source_record: str = "") -> str:
    for pattern in (r"\.(\d+)\.pdf(?:$|\?)", r"/product/pdf/[^/]+/[^/]+/(\d+)(?:$|\?)"):
        m = re.search(pattern, url)
        if m:
            return m[1]
    m = re.search(r"_A?(\d+)_\d{4}-", source_record)
    return m[1] if m else "unknown"


def mirror_covers_publication(tasks: list[dict], row: dict) -> bool:
    """API metadata version numbers can lag/differ from actual PDF revisions.

    This compares publication coverage, NOT byte-equivalence across sources.
    Preserve both version namespaces rather than request an older PDF solely
    because its API metadata version differs from the PDF filename.
    """
    published = day(row.get("publishDate") or row.get("date"))
    return published is not None and any(day(t.get("date")) and day(t["date"]) >= published for t in tasks)


def write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if path.exists() and path.read_bytes() == raw:
        return
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(raw)
    temp.replace(path)


def write_json(path: Path, obj: object) -> None:
    write(path, json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def read_json(path: Path, default):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


class HTTP:
    """Bounded downloads, host allow-list, scoped credentials and polite retries."""
    def __init__(self, api_key: str = ""):
        self.key = api_key or "DEMO_KEY"
        self.has_key = bool(api_key)
        self.api_calls = 0
        self.session = requests.Session()
        self.last: dict[str, float] = {}
        self.blocked: set[str] = set()

    def get(self, url: str) -> tuple[bytes, str]:
        url = safe_url(url)
        for redirect in range(5):
            host = urlsplit(url).hostname
            scope = access_scope(url)
            if host in self.blocked or scope in self.blocked:
                raise RuntimeError(f"{host}: unavailable for this run after access/rate-limit response")
            headers = {"User-Agent": "crs-reports-archive/1.0 (+https://github.com/krischen-77/crs-reports)"}
            if host == "api.congress.gov":
                if not self.has_key and self.api_calls >= 20:
                    raise RuntimeError("DEMO_KEY request budget reached; configure CONGRESS_API_KEY")
                headers["X-Api-Key"] = self.key
                self.api_calls += 1
            wait = 2.1 if host and host.endswith("congress.gov") else 0.3
            for attempt in range(4):
                time.sleep(max(0, wait - (time.monotonic() - self.last.get(host, 0))))
                self.last[host] = time.monotonic()
                try:
                    with self.session.get(url, headers=headers, timeout=(20, 90), stream=True, allow_redirects=False) as response:
                        status = response.status_code
                        if status in (301, 302, 303, 307, 308):
                            url = safe_url(urljoin(url, response.headers["Location"]))
                            break
                        if status in (401, 403):
                            self.blocked.add(scope)
                            raise RuntimeError(f"{scope}: HTTP {status}; not bypassing access restrictions")
                        if status == 429:
                            self.blocked.add(host)
                            raise RuntimeError(f"{host}: HTTP 429; defer to next run")
                        if status >= 500:
                            raise requests.ConnectionError(f"HTTP {status}")
                        if status != 200:
                            raise RuntimeError(f"{host}: HTTP {status}")
                        body = bytearray()
                        for chunk in response.iter_content(131072):
                            body.extend(chunk)
                            if len(body) > MAX_BYTES:
                                raise RuntimeError("Upstream file exceeds the 80 MiB safety limit")
                        return bytes(body), url
                except requests.RequestException:
                    if attempt == 3:
                        raise RuntimeError(f"{host}: network failure after four attempts") from None
                    time.sleep(2 ** (attempt + 1))
            else:
                raise RuntimeError("Retry limit exhausted")
        raise RuntimeError("Redirect limit exhausted")

    def json(self, url: str):
        body, _ = self.get(url)
        return json.loads(body)


def parse_catalog(raw: bytes) -> dict[str, dict]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    required = {"number", "url", "latestPubDate", "title", "latestPDF", "latestHTML"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("Unexpected EveryCRSReport CSV schema")
    rows = {}
    for row in reader:
        ident = report_id(row["number"])
        rows[ident] = {"id": ident, "title": row["title"], "published": row["latestPubDate"],
                       "official_page": f"https://www.congress.gov/crs-product/{ident}",
                       "mirror_metadata": safe_url(urljoin(MIRROR, row["url"])),
                       "mirror_pdf": safe_url(urljoin(MIRROR, row["latestPDF"])) if row["latestPDF"] else "",
                       "mirror_html": safe_url(urljoin(MIRROR, row["latestHTML"])) if row["latestHTML"] else "",
                       "mirror_metadata_sha1": row.get("sha1", "")}
    return rows


def api_scan(http: HTTP, start: date, end: date, full: bool = False) -> tuple[list[dict], int]:
    rows, offset, expected = [], 0, None
    while True:
        params = {"format": "json", "limit": 250, "offset": offset}
        if not full:
            params.update(fromDateTime=f"{start}T00:00:00Z", toDateTime=f"{end}T23:59:59Z")
        obj = http.json(API + "?" + urlencode(params))
        page = next((v for k, v in obj.items() if k.lower() == "crsreports"), None)
        if not isinstance(page, list):
            raise ValueError("Unexpected Congress.gov list schema")
        expected = int(obj.get("pagination", {}).get("count", len(page)))
        rows.extend(page)
        offset += len(page)
        if not obj.get("pagination", {}).get("next"):
            if offset < expected:
                raise ValueError("Congress.gov pagination ended before its reported count")
            return rows, expected
        if not page or offset > 200000:
            raise ValueError("Congress.gov pagination made no progress")


def feed_records(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    records = []
    for item in root.findall("./channel/item"):
        link = item.findtext("link", "")
        m = re.search(r"/reports/([A-Za-z0-9-]+)\.html", link)
        if not m:
            continue
        published = parsedate_to_datetime(item.findtext("pubDate", "")).date().isoformat()
        records.append({"id": report_id(m[1]), "title": item.findtext("title", ""), "published": published})
    return records


def mirror_tasks(obj: dict, start: date, end: date, include_latest: bool = False) -> list[dict]:
    ident = report_id(obj.get("id") or obj.get("number"))
    tasks = []
    for i, version in enumerate(obj.get("versions", [])):
        if not within(version.get("date"), start, end) and not (include_latest and i == 0 and day(version.get("date")) and day(version["date"]) <= end):
            continue
        formats, ignored = {}, []
        number = "unknown"
        for fmt in version.get("formats", []):
            kind = str(fmt.get("format", "")).upper()
            if kind not in ("PDF", "HTML"):
                continue
            original = fmt.get("url", "")
            mirror = urljoin(MIRROR, fmt["filename"]) if fmt.get("filename") else ""
            urls = []
            for url in [original, mirror]:
                if not url:
                    continue
                try:
                    checked = safe_url(url)
                except ValueError:
                    # Older source records refer to the non-public crs.gov site.
                    # Do not request it; the public immutable mirror is separate.
                    ignored.append(url)
                    continue
                if checked not in urls:
                    urls.append(checked)
            if urls:
                formats[kind] = {"urls": urls, "sha1": fmt.get("sha1", ""),
                                 "report_id": ident, "source_format": fmt.get("source", "source HTML" if kind == "HTML" else "original PDF"),
                                 "allow_transformed_html": kind == "HTML" and bool(mirror)}
            if kind == "PDF":
                number = source_version(original, str(version.get("id", "")))
        if "PDF" not in formats:
            continue
        tasks.append({"id": ident, "title": version.get("title", ident), "date": str(version.get("date", ""))[:10],
                      "version": number, "formats": formats, "metadata_source": "EveryCRSReport.com",
                      "source_record": str(version.get("id", "")), "ignored_nonpublic_source_urls": ignored})
    return tasks


def official_task(http: HTTP, row: dict) -> dict:
    ident = report_id(row["id"])
    obj = http.json(API + "/" + ident + "?format=json")
    item = next((v for k, v in obj.items() if k.lower() == "crsreport"), None)
    if not isinstance(item, dict):
        raise ValueError("Unexpected Congress.gov item schema")
    formats = {}
    for fmt in item.get("formats", []):
        kind = str(fmt.get("format", "")).upper()
        url = fmt.get("url") or fmt.get("URL")
        if kind in ("PDF", "HTML") and url:
            formats[kind] = {"urls": [safe_url(url)], "sha1": ""}
    if "PDF" not in formats:
        raise ValueError(f"{ident}: API did not provide a PDF URL")
    return {"id": ident, "title": item.get("title", row["title"]), "date": str(item.get("publishDate", row.get("publishDate", "")))[:10],
            "version": source_version(formats["PDF"]["urls"][0]) if source_version(formats["PDF"]["urls"][0]) != "unknown" else str(item.get("version", row.get("version", "unknown"))),
            "api_version": str(item.get("version", row.get("version", "unknown"))), "formats": formats,
            "metadata_source": "Congress.gov API", "source_record": ident}


def task_key(task: dict) -> str:
    return task["id"] + ":" + digest(json.dumps(task, sort_keys=True).encode())[:20]


def download_format(http: HTTP, spec: dict, kind: str) -> tuple[bytes, str, list[str]]:
    errors = []
    for url in spec["urls"]:
        try:
            body, actual = http.get(url)
            if spec.get("sha1") and digest(body, "sha1") != spec["sha1"]:
                if kind == "HTML" and spec.get("allow_transformed_html") and urlsplit(actual).hostname in ("www.everycrsreport.com", "everycrsreport.com"):
                    # EveryCRSReport serves cleaned HTML fragments; their name may
                    # retain the hash of the pre-transformation official HTML.
                    # Keep this as a DERIVATIVE with its own hash, never as verified
                    # original bytes. PDF checksum requirements remain unchanged.
                    text = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
                    if not spec.get("report_id") or spec["report_id"] not in text:
                        raise ValueError("Mirror HTML identity check failed")
                    errors.append("Saved provider HTML derivative; bytes differ from upstream HTML SHA-1, original PDF remains authoritative")
                else:
                    raise ValueError("Source bytes differ from the catalogued version checksum")
            if kind == "PDF" and not body.lstrip().startswith(b"%PDF-"):
                raise ValueError("Response is not a PDF")
            if kind == "HTML":
                text = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
                if len(text) < 100 or "just a moment" in text[:300].lower() or "access denied" in text[:300].lower():
                    raise ValueError("HTML is empty or an access-denial page")
            return body, actual, errors
        except Exception as exc:
            errors.append(f"{urlsplit(url).hostname}: {exc}")
    raise RuntimeError("; ".join(errors))


def body_markdown(html: bytes | None, base_url: str, pdf: bytes) -> tuple[str, str, int]:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        if doc.needs_pass or len(doc) == 0:
            raise ValueError("Unreadable or encrypted PDF")
        pages = len(doc)
        fallback = None
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for el in soup.select("script, style, noscript"):
                el.decompose()
            for el in soup.find_all(["a", "img"]):
                attr = "href" if el.name == "a" else "src"
                if el.get(attr):
                    el[attr] = urljoin(base_url, el[attr])
            result = markdownify(str(soup.body or soup), heading_style="ATX").strip()
            if len(result) >= 100:
                return result, "html-to-markdown; external images not mirrored", pages
        fallback = "\n\n".join(f"## Page {i + 1}\n\n{page.get_text(sort=True).strip()}" for i, page in enumerate(doc))
        if sum(len(page.get_text().strip()) for page in doc) < 50:
            return "This PDF has no usable text layer. Consult the preserved original; OCR was not performed.", "pdf-no-text-layer", pages
        return fallback, "pdf-text-extraction; layout and tables may differ", pages


def archive_task(http: HTTP, root: Path, task: dict, known: list[dict]) -> tuple[dict, bool, list[str]]:
    expected = task["formats"]["PDF"].get("sha1")
    cached = None
    for old in known:
        if old["id"] != task["id"] or not expected or old.get("pdf_sha1") != expected:
            continue
        if (root / old["pdf"]).is_file() and digest((root / old["pdf"]).read_bytes()) == old["pdf_sha256"]:
            cached = old
            break
    if cached and cached.get("schema_version", 0) >= SCHEMA_VERSION and not cached.get("retry_html"):
        if all((root / cached[k]).is_file() for k in ("pdf", "markdown")) and (not cached.get("html") or (root / cached["html"]).is_file()):
            return cached, False, []
    if cached:
        pdf, pdf_url, warnings = (root / cached["pdf"]).read_bytes(), cached["pdf_source"], []
    else:
        pdf, pdf_url, warnings = download_format(http, task["formats"]["PDF"], "PDF")
    with fitz.open(stream=pdf, filetype="pdf") as document:
        if document.needs_pass or len(document) == 0:
            raise ValueError("Unreadable or encrypted PDF")
    sha = digest(pdf)
    # A PDF hash, not a publication date alone, prevents accidental overwriting.
    ident = report_id(task["id"])
    version = re.sub(r"[^A-Za-z0-9-]", "", task["version"]) or "unknown"
    publication = str(day(task["date"]) or "undated")
    stem = f"{ident}v{version}-{publication}-{sha[:16]}"
    folder = category(ident)
    pdf_path = f"pdf/{folder}/{stem}.pdf"
    write(root / pdf_path, pdf)
    html, html_url, html_path, retry_html = None, "", "", False
    if "HTML" in task["formats"]:
        try:
            html, html_url, other = download_format(http, task["formats"]["HTML"], "HTML")
            warnings.extend(other)
            html_path = f"html/{folder}/{stem}-{digest(html)[:12]}.html"
            write(root / html_path, html)
        except Exception as exc:
            warnings.append(f"HTML unavailable; preserve PDF and extract its text: {exc}")
            retry_html = True
    html_spec = task["formats"].get("HTML", {})
    if not html:
        html_kind = "unavailable"
    elif html_spec.get("source_format") == "pymupdf":
        html_kind = "provider PDF-to-HTML derivative; not official HTML"
    elif urlsplit(html_url).hostname in ("www.everycrsreport.com", "everycrsreport.com"):
        html_kind = "provider HTML snapshot; may be reformatted; not byte-identical official HTML"
    else:
        html_kind = "official HTML response"
    text, method, pages = body_markdown(html, html_url, pdf)
    md_path = f"markdown/{folder}/{stem}.md"
    header = {"report_number": ident, "title": task["title"], "publication_date": task["date"], "crs_version": task["version"],
              "official_page": f"https://www.congress.gov/crs-product/{ident}", "downloaded_pdf_from": pdf_url,
              "downloaded_html_from": html_url, "html_provenance": html_kind, "api_metadata_version": task.get("api_version", ""), "pdf_sha256": sha, "conversion": method}
    front = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in header.items()) + "\n---\n\n"
    write(root / md_path, front + text + "\n")
    entry = {"schema_version": SCHEMA_VERSION, "id": ident, "title": task["title"], "date": task["date"], "version": task["version"], "pdf": pdf_path,
             "pdf_sha256": sha, "pdf_sha1": digest(pdf, "sha1"), "pdf_source": pdf_url, "html": html_path,
             "html_source": html_url, "html_provenance": html_kind, "html_sha256": digest(html) if html else "",
             "api_metadata_version": task.get("api_version", ""), "markdown": md_path, "pages": pages, "conversion": method,
             "metadata_source": task["metadata_source"], "retry_html": retry_html,
             "archived_at": datetime.now(timezone.utc).isoformat()}
    old = next((v for v in known if v["id"] == ident and v.get("pdf_sha256") == sha), None)
    if old:
        entry["archived_at"] = old["archived_at"]
    return entry, old is None, warnings


def export_indexes(root: Path, catalog: dict, archives: list[dict], start: date, end: date) -> None:
    fields = ["report_id", "title", "published_date", "api_update_date", "official_page", "official_page_verified_by_api", "mirror_pdf", "mirror_html", "metadata_source", "archived_versions"]
    counts = {}
    for v in archives:
        counts[v["id"]] = counts.get(v["id"], 0) + 1
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fields, lineterminator="\n")
    writer.writeheader()
    links = set()
    for ident, row in sorted(catalog.items()):
        api = row.get("api", {})
        page = f"https://www.congress.gov/crs-product/{ident}"
        writer.writerow({"report_id": ident, "title": api.get("title") or row.get("title", ident),
                         "published_date": api.get("publishDate") or row.get("published", ""), "api_update_date": api.get("updateDate", ""),
                         "official_page": page, "official_page_verified_by_api": bool(api), "mirror_pdf": row.get("mirror_pdf", ""),
                         "mirror_html": row.get("mirror_html", ""), "metadata_source": ";".join(s for s, exists in [("EveryCRSReport.com", row.get("mirror_metadata")), ("Congress.gov API", api)] if exists),
                         "archived_versions": counts.get(ident, 0)})
        links.update(u for u in [page, row.get("mirror_pdf"), row.get("mirror_html")] if u)
    write(root / "data/all-report-links.csv", "\ufeff" + buffer.getvalue())
    write(root / "data/all-report-links.txt", "\n".join(sorted(links)) + "\n")
    selected = sorted((v for v in archives if within(v["date"], start, end)), key=lambda v: (v["date"], v["id"]), reverse=True)
    lines = ["# Recently archived CRS reports", "", f"Publication-date window (inclusive): **{start} to {end}**. Older archived files are retained.", "", "| Date | Report | Title | Original | Text |", "|---|---|---|---|---|"]
    for v in selected:
        title = v["title"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {v['date']} | {v['id']} v{v['version']} | {title} | [PDF]({v['pdf']}) | [Markdown]({v['markdown']}) |")
    write(root / "LATEST.md", "\n".join(lines) + "\n")
    buf = io.StringIO(newline="")
    fs = ["id", "title", "date", "version", "pdf", "html", "markdown", "pdf_sha256", "pdf_source", "metadata_source"]
    w = csv.DictWriter(buf, fs, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(sorted(archives, key=lambda v: (v["id"], v["date"], v["pdf_sha256"])))
    write(root / "data/archived-reports.csv", "\ufeff" + buf.getvalue())


def sync(args) -> int:
    root = Path(args.root)
    now = datetime.now(timezone.utc)
    end = date.fromisoformat(args.until) if args.until else now.date()
    start = end - timedelta(days=args.days)
    http = HTTP(os.getenv("CONGRESS_API_KEY", "").strip())
    status = {"run_at": now.isoformat(), "window_start_inclusive": str(start), "window_end_inclusive": str(end),
              "lookback_days": args.days, "sources": {}, "warnings": [], "errors": []}
    errors, warnings = status["errors"], status["warnings"]
    catalog = read_json(root / "data/catalog.json", {})
    archives = read_json(root / "data/archive-manifest.json", [])
    pending = read_json(root / "data/pending.json", {"reports": [], "tasks": []})
    api_rows, fresh_mirror, tasks = [], {}, {}
    try:
        raw, _ = http.get(MIRROR + "reports.csv")
        fresh_mirror = parse_catalog(raw)
        previous_count = sum(bool(v.get("mirror_metadata")) for v in catalog.values())
        if len(fresh_mirror) < 1000 or (previous_count and len(fresh_mirror) < previous_count * 0.8):
            raise ValueError("Unexpectedly small catalog; preserve the previous index")
        for ident, row in fresh_mirror.items():
            catalog[ident] = {**catalog.get(ident, {}), **row}
        write(root / "data/sources/everycrsreport-catalog.csv", raw)
        status["sources"]["everycrsreport"] = {"ok": True, "reports": len(fresh_mirror), "coverage": "complete published CSV, not a claim of complete official CRS coverage"}
    except Exception as exc:
        fresh_mirror = {}
        status["sources"]["everycrsreport"] = {"ok": False, "error": str(exc)}
        warnings.append(f"Catalog refresh failed: {exc}")
    full = args.full_catalog
    if full and not http.has_key:
        errors.append("Full official catalog requested without CONGRESS_API_KEY")
        full = False
    try:
        api_rows, count = api_scan(http, start, end, full)
        for row in api_rows:
            ident = report_id(row["id"])
            catalog.setdefault(ident, {"id": ident, "title": row.get("title", ident)})["api"] = row
        status["sources"]["congress_api"] = {"ok": True, "reports": len(api_rows), "reported_count": count, "scope": "full" if full else "update-date window", "credential": "repository secret" if http.has_key else "public DEMO_KEY"}
    except Exception as exc:
        status["sources"]["congress_api"] = {"ok": False, "error": str(exc)}
        warnings.append(f"Official API unavailable: {exc}")
    rss_rows = []
    try:
        raw, _ = http.get(RSS)
        rss_rows = feed_records(raw)
        write(root / "data/sources/everycrsreport-rss.xml", raw)
        status["sources"]["rss"] = {"ok": True, "items": len(rss_rows), "scope": "supplement only; feed is not the complete catalog"}
    except Exception as exc:
        warnings.append(f"Supplemental RSS unavailable: {exc}")
    if not fresh_mirror and not status["sources"].get("congress_api", {}).get("ok"):
        errors.append("No current catalog source succeeded; cached entries are not proof of a successful refresh")
    recent_api = {report_id(r["id"]): r for r in api_rows if within(r.get("publishDate"), start, end) or within(r.get("updateDate"), start, end)}
    ids = {i for i, r in fresh_mirror.items() if within(r.get("published"), start, end)} | set(recent_api) | set(pending["reports"])
    ids |= {r["id"] for r in rss_rows if within(r["published"], start, end)}
    ids |= {t["id"] for t in pending["tasks"]}
    print(f"Sources collected: {len(catalog)} catalog IDs; {len(ids)} candidate reports", flush=True)
    failed_reports = []
    for position, ident in enumerate(sorted(ids), 1):
        print(f"Metadata [{position}/{len(ids)}] {ident}", flush=True)
        try:
            obj = http.json(MIRROR + f"reports/{report_id(ident)}.json")
            if report_id(obj.get("id") or obj.get("number")) != ident:
                raise ValueError("Report metadata ID mismatch")
            write_json(root / f"metadata/sources/{ident}.json", obj)
            found = mirror_tasks(obj, start, end, include_latest=ident in recent_api or ident in pending["reports"] or any(t["id"] == ident for t in pending["tasks"]))
            api_row = recent_api.get(ident) or catalog.get(ident, {}).get("api")
            for task in found:
                if api_row:
                    task["api_version"] = str(api_row.get("version", ""))
                tasks[task_key(task)] = task
            if api_row and found and any(t["version"] != str(api_row.get("version")) for t in found):
                warnings.append({"id": ident, "api_version": api_row.get("version"), "pdf_revisions": [t["version"] for t in found],
                                 "note": "Version namespaces differ; publication coverage checked separately, not claimed byte-equivalent"})
            if api_row and not mirror_covers_publication(found, api_row):
                t = official_task(http, api_row)
                tasks[task_key(t)] = t
            if not found and not api_row:
                raise ValueError("No PDF version found in the requested window")
        except Exception as exc:
            if ident in recent_api:
                try:
                    t = official_task(http, recent_api[ident])
                    tasks[task_key(t)] = t
                    continue
                except Exception as api_exc:
                    exc = RuntimeError(f"{exc}; official fallback: {api_exc}")
            failed_reports.append(ident)
            errors.append(f"{ident}: metadata resolution failed: {exc}")
    reconciled = []
    for task in pending["tasks"]:
        fresh = [t for t in tasks.values() if t["id"] == task["id"]]
        old_hash = task["formats"]["PDF"].get("sha1")
        if old_hash and any(t["formats"]["PDF"].get("sha1") == old_hash for t in fresh):
            continue  # Fresh metadata is the authoritative retry specification.
        if task.get("metadata_source") == "Congress.gov API" and mirror_covers_publication(fresh, task):
            reconciled.append({"id": task["id"], "previous_api_version": task["version"],
                               "reason": "API/PDF version namespaces reconciled against same-or-newer publication metadata"})
            continue
        tasks.setdefault(task_key(task), task)
    status["reconciled_pending_discoveries"] = reconciled
    queued, new_count, ok_count = [], 0, 0
    for n, task in enumerate(tasks.values(), 1):
        print(f"[{n}/{len(tasks)}] {task['id']} v{task['version']} ({task['date']})", flush=True)
        try:
            entry, is_new, notices = archive_task(http, root, task, archives)
            archives = [v for v in archives if not (v["id"] == entry["id"] and v["pdf_sha256"] == entry["pdf_sha256"])] + [entry]
            new_count += int(is_new)
            ok_count += 1
            if notices:
                warnings.append({"id": task["id"], "messages": notices})
            if entry["retry_html"]:
                queued.append(task)
        except Exception as exc:
            queued.append(task)
            errors.append(f"{task['id']}: original archive failed: {exc}")
    archives.sort(key=lambda v: (v["id"], v["date"], v["pdf_sha256"]))
    write_json(root / "data/catalog.json", catalog)
    write_json(root / "data/archive-manifest.json", archives)
    write_json(root / "data/pending.json", {"reports": failed_reports, "tasks": queued})
    export_indexes(root, catalog, archives, start, end)
    status.update(catalog_reports=len(catalog), candidate_reports=len(ids), attempted_versions=len(tasks), successful_versions=ok_count,
                  new_pdf_versions=new_count, total_archived_pdf_versions=len(archives),
                  total_html_snapshots=sum(bool(v.get("html")) for v in archives),
                  total_pdf_bytes=sum((root / v["pdf"]).stat().st_size for v in archives),
                  pending_reports=len(failed_reports), pending_versions=len(queued))
    status["result"] = "failed" if errors else ("success_with_warnings" if warnings else "success")
    write_json(root / "data/status.json", status)
    run_id = os.getenv("GITHUB_RUN_ID", now.strftime("%Y%m%dT%H%M%S"))
    run_attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    write_json(root / f"data/runs/{now.date()}/{run_id}-{run_attempt}.json", status)
    summary = (f"## CRS archive: {status['result']}\n\nWindow: {start} to {end} (inclusive UTC dates).\n\n"
               f"Catalog: **{len(catalog)}** report IDs; attempted versions: **{len(tasks)}**; successfully preserved: **{ok_count}**; "
               f"new PDFs: **{new_count}**; cumulative PDF versions: **{len(archives)}**.\n\n"
               f"Pending reports: {len(failed_reports)}; pending versions: {len(queued)}. "
               "See `data/status.json` for source coverage, warnings and errors. A link in the catalog does not mean its PDF is archived.\n")
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary)
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--until", default="", help="Inclusive UTC end date, YYYY-MM-DD")
    parser.add_argument("--full-catalog", action="store_true", help="Refresh the complete official API catalog; requires a personal free API key")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    if not 1 <= args.days <= 3650:
        parser.error("--days must be between 1 and 3650")
    return sync(args)


if __name__ == "__main__":
    sys.exit(main())
