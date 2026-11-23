"""Fetch a table from the web: Kaggle datasets, OpenML datasets, or any CSV/TSV link.

Standard library only, so the hosted site server can use this same file (it is copied
into the site as importer.py by `scout site`).

Safety, because the hosted site fetches URLs that visitors type:
- only http and https, on ports 80 and 443;
- every hostname is resolved and must be a public address; the connection is pinned to
  the checked address (no DNS-rebinding window), and each redirect is checked again;
- downloads are capped in bytes and time, and HTML pages are refused.
"""

from __future__ import annotations

import csv
import gzip
import http.client
import io
import ipaddress
import json
import re
import socket
import ssl
import time
import zipfile
from urllib.parse import quote, urljoin, urlparse

UA = "hill-scout-importer/1.0"
MAX_BYTES = 60 * 1024 * 1024  # compressed download cap
MAX_ROWS = 20000  # rows handed to the browser preview
MAX_SCAN_ROWS = 2_000_000  # rows counted for the total
TABLE_EXT = (".csv", ".tsv", ".txt", ".csv.gz", ".tsv.gz")

# Columns that are usually the thing to predict, most specific first.
TARGET_NAMES = [
    "target", "label", "labels",
    "churn", "exited", "attrition", "survived", "default", "is_fraud", "isfraud", "fraud", "diagnosis",
    "income", "saleprice", "price", "quality", "loan_status", "approved", "response", "converted",
    "purchased", "stroke", "heartdisease", "heart_disease",
    "class", "y", "outcome", "output", "result", "species", "category", "rating", "score",
]


# Licenses that allow redistribution of a derived split. Matched case-insensitively
# after normalising spaces, dashes and underscores away.
ALLOWED_LICENSES = (
    "public", "publicdomain", "cc0", "ccby", "ccby40", "ccby30", "ccby20",
    "ccbysa", "ccbysa40", "ccbysa30", "pddl", "odcby", "odbl", "mit", "apache20",
)


def normalise_license(text: str | None) -> str:
    if not text:
        return ""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def license_allows_redistribution(text: str | None) -> tuple[bool, str]:
    norm = normalise_license(text)
    if not norm:
        return False, "license missing"
    if norm.startswith("cc") and ("nc" in norm[2:] or "nd" in norm[2:]):
        return False, f"license '{text}' restricts commercial use or derivatives"
    if any(norm.startswith(ok) or norm == ok for ok in ALLOWED_LICENSES):
        return True, "ok"
    return False, f"license '{text}' not on the redistribution allow-list"


class ImportError_(Exception):
    """A normal, explainable failure (bad link, too big, not a table)."""


# ---------------------------------------------------------------- reference parsing

def resolve(ref: str) -> dict:
    """Turn what a person typed into {kind, ...}. Raises ImportError_ when unrecognised."""
    ref = (ref or "").strip()
    if not ref:
        raise ImportError_("paste a Kaggle dataset, an OpenML id, or a link to a CSV file")
    m = re.match(r"^(?:kaggle:)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", ref)
    if m and not ref.lower().startswith(("http", "openml")):
        return {"kind": "kaggle", "owner": m.group(1), "slug": m.group(2)}
    m = re.match(r"^https?://(?:www\.)?kaggle\.com/datasets/([^/?#]+)/([^/?#]+)", ref)
    if m:
        return {"kind": "kaggle", "owner": m.group(1), "slug": m.group(2)}
    if re.match(r"^https?://(?:www\.)?kaggle\.com/(?:c|competitions)/", ref):
        raise ImportError_("Kaggle competition data needs you to accept the rules on Kaggle first; "
                           "use a Kaggle dataset link or a direct CSV link instead")
    m = re.match(r"^(?:openml:)?(\d+)$", ref) or re.match(r"^https?://(?:www\.)?openml\.org/(?:d/|search\?.*id=|.*data/)(\d+)", ref)
    if m:
        return {"kind": "openml", "id": m.group(1)}
    if re.match(r"^https?://", ref):
        url = ref
        g = re.match(r"^https://github\.com/([^/]+)/([^/]+)/blob/(.+)$", url)
        if g:
            url = f"https://raw.githubusercontent.com/{g.group(1)}/{g.group(2)}/{g.group(3)}"
        url = re.sub(r"^(https://huggingface\.co/datasets/[^/]+/[^/]+)/blob/", r"\1/resolve/", url)
        return {"kind": "url", "url": url}
    raise ImportError_("not recognised: use owner/dataset for Kaggle, a number for OpenML, or an https link")


# ---------------------------------------------------------------- safe HTTP

def _public_ip(host: str, port: int) -> str:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ImportError_(f"could not find the host {host}") from exc
    ips = [i[4][0] for i in infos]
    for ip in ips:
        a = ipaddress.ip_address(ip)
        if not a.is_global or a.is_multicast:
            raise ImportError_(f"{host} points to a private or internal address; only public links can be imported")
    return ips[0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


def safe_get(url: str, max_bytes: int = MAX_BYTES, timeout: float = 30, deadline_s: float = 90) -> tuple[bytes, dict]:
    """GET a public URL with redirects checked hop by hop. Returns (body, info)."""
    start = time.monotonic()
    for _hop in range(6):
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ImportError_("only http and https links can be imported")
        port = u.port or (443 if u.scheme == "https" else 80)
        if port not in (80, 443):
            raise ImportError_("only links on the standard web ports (80 and 443) can be imported")
        ip = _public_ip(u.hostname, port)
        conn = (_PinnedHTTPS if u.scheme == "https" else _PinnedHTTP)(u.hostname, ip, port, timeout)
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        try:
            conn.request("GET", path, headers={"User-Agent": UA, "Accept": "*/*"})
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.getheader("Location")
                conn.close()
                if not loc:
                    raise ImportError_("the link redirected without saying where")
                url = urljoin(url, loc)
                continue
            if resp.status == 404:
                raise ImportError_("that link returned 404 (not found)")
            if resp.status in (401, 403):
                raise ImportError_("that link needs a login, so it can't be imported; it has to be public")
            if resp.status >= 400:
                raise ImportError_(f"that link returned HTTP {resp.status}")
            length = resp.getheader("Content-Length")
            if length and length.isdigit() and int(length) > max_bytes:
                raise ImportError_(f"the file is {int(length) / 1e6:.0f} MB; the limit is {max_bytes / 1e6:.0f} MB")
            chunks, total = [], 0
            while True:
                if time.monotonic() - start > deadline_s:
                    raise ImportError_("the download took too long")
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ImportError_(f"the file is over the {max_bytes / 1e6:.0f} MB limit")
                chunks.append(chunk)
            return b"".join(chunks), {"url": url, "content_type": resp.getheader("Content-Type") or ""}
        except (OSError, http.client.HTTPException) as exc:
            if isinstance(exc, ImportError_):
                raise
            raise ImportError_(f"download failed: {type(exc).__name__}") from exc
        finally:
            conn.close()
    raise ImportError_("too many redirects")


def get_json(url: str, max_bytes: int = 5_000_000) -> dict | list:
    body, _ = safe_get(url, max_bytes=max_bytes)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ImportError_("the service did not return JSON") from exc


# ---------------------------------------------------------------- tables

def _members(blob: bytes, name_hint: str) -> list[tuple[str, int, callable]]:
    """List table files in a download: [(name, size, opener)]."""
    if blob[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(blob))
        except zipfile.BadZipFile as exc:
            raise ImportError_("the zip file is damaged") from exc
        out = []
        for info in zf.infolist():
            low = info.filename.lower()
            if info.is_dir() or "__macosx" in low or not low.endswith(TABLE_EXT):
                continue
            out.append((info.filename, info.file_size, (lambda i=info: zf.open(i))))
        return out
    if blob[:2] == b"\x1f\x8b":
        name = re.sub(r"\.gz$", "", name_hint or "data.csv")
        return [(name, 0, lambda: gzip.GzipFile(fileobj=io.BytesIO(blob)))]
    head = blob[:512].lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html", b"<?xml", b"<head", b"<body")):
        raise ImportError_("that link is a web page, not a data file; use the direct download link to the CSV")
    if blob[:4] == b"PAR1":
        raise ImportError_("Parquet files aren't supported here yet; use a CSV link")
    return [(name_hint or "data.csv", len(blob), lambda: io.BytesIO(blob))]


def _read_table(opener, name: str) -> dict:
    raw = opener()
    text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
    sample = text.read(65536)
    sample += text.readline()  # finish the last line so no row is split
    if not sample.strip():
        raise ImportError_(f"{name} is empty")
    if "\x00" in sample[:4096]:
        raise ImportError_(f"{name} looks binary, not a text table")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if name.lower().endswith((".tsv", ".tsv.gz")) else ","
    rest = io.StringIO(sample)
    reader = csv.reader(_chain(rest, text), delimiter=delim)
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    header = None
    kept = total = 0
    widths = set()
    for row in reader:
        if not row or (len(row) == 1 and not row[0].strip()):
            continue
        if header is None:
            header = [h.strip() for h in row]
            if len(header) < 2:
                raise ImportError_(f"{name} has a single column; a table needs at least a feature and a target")
            w.writerow(header)
            continue
        total += 1
        if kept < MAX_ROWS:
            w.writerow(row)
            kept += 1
            widths.add(len(row))
        if total >= MAX_SCAN_ROWS:
            break
    if header is None or total == 0:
        raise ImportError_(f"{name} has a header but no rows")
    return {"header": header, "csv": out.getvalue(), "rows_sent": kept, "total_rows": total,
            "total_is_lower_bound": total >= MAX_SCAN_ROWS, "delimiter": delim,
            "ragged": len(widths) > 1}


def _chain(first: io.StringIO, second):
    yield from first
    yield from second


GENERIC_TARGETS = {"y", "output", "result", "score", "category", "rating", "class", "species"}


def guess_target(header: list[str], declared: str = "", strict: bool = False) -> tuple[str, str]:
    """Pick the likely target column: (name, reason). Name is '' when nothing fits.

    strict=True (unattended discovery) skips generic names such as y or score, which are
    too often a coordinate or a feature rather than the thing to predict."""
    if declared and declared in header:
        return declared, "the dataset declares it as the target"
    norm = {re.sub(r"[^a-z0-9_]", "", h.lower()): h for h in header}
    for n in TARGET_NAMES:
        if strict and n in GENERIC_TARGETS:
            continue
        if n in norm:
            return norm[n], f"the column is named '{norm[n]}'"
    return "", "no column has a usual target name"


def pick_table(blob: bytes, name_hint: str, want: str = "") -> tuple[dict, list[dict]]:
    members = _members(blob, name_hint)
    if not members:
        raise ImportError_("no CSV or TSV file found in the download")
    files = [{"name": n, "bytes": s} for n, s, _ in members]
    chosen = next((m for m in members if m[0] == want), None) if want else None
    if want and not chosen:
        raise ImportError_(f"{want} is not in this dataset")
    chosen = chosen or max(members, key=lambda m: m[1])
    table = _read_table(chosen[2], chosen[0])
    table["file"] = chosen[0]
    return table, files


# ---------------------------------------------------------------- sources

def kaggle_meta(owner: str, slug: str) -> dict:
    d = get_json(f"https://www.kaggle.com/api/v1/datasets/view/{quote(owner)}/{quote(slug)}")
    if not isinstance(d, dict) or not (d.get("titleNullable") or d.get("title")):
        raise ImportError_(f"Kaggle has no public dataset {owner}/{slug}")
    return {
        "title": d.get("titleNullable") or d.get("title") or slug,
        "license": d.get("licenseNameNullable") or d.get("licenseName") or "",
        "subtitle": d.get("subtitleNullable") or "",
        "bytes": d.get("totalBytesNullable") or d.get("totalBytes") or 0,
        "url": f"https://www.kaggle.com/datasets/{owner}/{slug}",
        "votes": d.get("voteCount") or 0,
        "usability": d.get("usabilityRatingNullable") or 0,
    }


def kaggle_download(owner: str, slug: str, max_bytes: int = MAX_BYTES) -> bytes:
    blob, _ = safe_get(f"https://www.kaggle.com/api/v1/datasets/download/{quote(owner)}/{quote(slug)}", max_bytes=max_bytes)
    return blob


def kaggle_license_canonical(name: str) -> str:
    """Map Kaggle's licence names to the short forms the scout's allow-list understands."""
    low = (name or "").lower()
    if "nc" in re.findall(r"[a-z]+", low.replace("-", " ")) or "noncommercial" in low.replace("-", ""):
        return name
    if "cc0" in low or "public domain" in low:
        return "CC0"
    if "by-sa" in low or "by sa" in low:
        return "CC-BY-SA"
    if "cc by" in low or "cc-by" in low or "attribution 4.0" in low or "attribution 3.0" in low:
        return "CC-BY"
    if "odbl" in low or "open database" in low:
        return "ODbL"
    if "apache" in low:
        return "Apache-2.0"
    if re.search(r"\bmit\b", low):
        return "MIT"
    if "cdla" in low and "permissive" in low:
        return "CDLA-Permissive"
    return name


def openml_meta(did: str) -> dict:
    d = get_json(f"https://www.openml.org/api/v1/json/data/{did}")
    desc = d.get("data_set_description") if isinstance(d, dict) else None
    if not desc:
        raise ImportError_(f"OpenML has no dataset {did}")
    return {"title": desc.get("name", f"openml-{did}"), "license": desc.get("licence", ""),
            "file_id": desc.get("file_id"), "target": desc.get("default_target_attribute") or "",
            "ignore": desc.get("ignore_attribute") or [], "row_id": desc.get("row_id_attribute") or "",
            "url": f"https://www.openml.org/d/{did}"}


def fetch(ref: str, file: str = "") -> dict:
    """Import a table for preview. Returns header, CSV text (first MAX_ROWS rows), totals, source info."""
    r = resolve(ref)
    if r["kind"] == "kaggle":
        meta = kaggle_meta(r["owner"], r["slug"])
        if meta["bytes"] and meta["bytes"] > MAX_BYTES:
            raise ImportError_(f"that Kaggle dataset is {meta['bytes'] / 1e6:.0f} MB; the limit is {MAX_BYTES / 1e6:.0f} MB")
        blob = kaggle_download(r["owner"], r["slug"])
        table, files = pick_table(blob, f"{r['slug']}.csv", file)
        source = {"kind": "kaggle", "ref": f"kaggle:{r['owner']}/{r['slug']}", "title": meta["title"],
                  "url": meta["url"], "license": meta["license"], "subtitle": meta["subtitle"]}
        declared = ""
    elif r["kind"] == "openml":
        meta = openml_meta(r["id"])
        if not meta["file_id"]:
            raise ImportError_("that OpenML dataset has no downloadable file")
        blob, _ = safe_get(f"https://www.openml.org/data/get_csv/{meta['file_id']}/")
        table, files = pick_table(blob, f"{meta['title']}.csv", "")
        source = {"kind": "openml", "ref": f"openml:{r['id']}", "title": meta["title"], "url": meta["url"],
                  "license": meta["license"], "subtitle": ""}
        declared = meta["target"] if "," not in meta["target"] else ""
    else:
        blob, info = safe_get(r["url"])
        name = urlparse(info["url"]).path.rsplit("/", 1)[-1] or "data.csv"
        table, files = pick_table(blob, name, file)
        source = {"kind": "url", "ref": r["url"], "title": table["file"], "url": r["url"],
                  "license": "", "subtitle": ""}
        declared = ""
    target, why = guess_target(table["header"], declared)
    lic = kaggle_license_canonical(source["license"]) if source["kind"] == "kaggle" else source["license"]
    ok, lic_why = license_allows_redistribution(lic)
    source["open_license"] = ok
    source["license_note"] = ("allows a public hill" if ok else
                              f"{lic_why}; fine for a private hill for your own team, not for the public catalogue")
    return {**table, "files": files, "source": source, "suggested_target": target, "target_reason": why}
