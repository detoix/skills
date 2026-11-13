#!/usr/bin/env python3
"""Read-only Instagram API client; credentials never accepted on the command line."""

import argparse
import datetime as dt
import getpass
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import urllib.error
import urllib.parse as url
import urllib.request as http

from private_files import PrivateFileError, atomic_write, locked, open_private

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
HOST = "https://graph.instagram.com"
PARAMS = {"fields", "metric", "period", "metric_type", "breakdown", "since",
          "until", "timeframe", "limit", "after", "before"}
KEYS = {"INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_API_VERSION",
        "INSTAGRAM_TOKEN_ISSUED_AT", "INSTAGRAM_TOKEN_EXPIRES_AT"}
SECRETS = set()


class Failure(Exception):
    pass


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_env():
    try:
        fd = open_private(ENV)
    except FileNotFoundError:
        return {"INSTAGRAM_API_VERSION": "v25.0"}
    except (OSError, PrivateFileError):
        raise Failure("Credential file unavailable or not private; configure it locally with set-token.") from None
    with os.fdopen(fd, encoding="utf-8") as stream:
        values = {}
        for line in stream:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not sep or key not in KEYS or key in values:
                raise Failure("Invalid or duplicate configuration key in .env.")
            if value[:1] in ("'", '"'):
                if len(value) < 2 or value[-1] != value[0]:
                    raise Failure("Unbalanced quoting in .env.")
                value = value[1:-1]
            values[key] = value
    token = values.get("INSTAGRAM_ACCESS_TOKEN", "")
    if token:
        SECRETS.add(token)
        if not re.fullmatch(r"[A-Za-z0-9._~-]{20,}", token):
            raise Failure("Token has an invalid format; enter it locally without whitespace.")
    version = values.get("INSTAGRAM_API_VERSION", "v25.0")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", version):
        raise Failure("API version must have the form v25.0.")
    for key in ("INSTAGRAM_TOKEN_ISSUED_AT", "INSTAGRAM_TOKEN_EXPIRES_AT"):
        value = values.get(key, "")
        if value and not re.fullmatch(r"[0-9]{1,12}", value):
            raise Failure("Token timestamps must be Unix seconds or empty.")
    values["INSTAGRAM_API_VERSION"] = version
    return values


def save_env(values):
    contents = "# Local Instagram credentials. Never display or commit.\n"
    contents += "".join(key + "=" + values.get(key, "") + "\n" for key in sorted(KEYS))
    try:
        atomic_write(ENV, contents)
    except (OSError, PrivateFileError):
        raise Failure("Cannot save private credentials; the previous credential file is unchanged.") from None


def scrub(value):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if re.search(r"token|secret|authorization", k, re.I)
                    else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        for secret in sorted(SECRETS, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
            value = value.replace(url.quote(secret, safe=""), "[REDACTED]")
        value = re.sub(r"(?i)(access_token|client_secret|authorization)([=:\s%22]+)[^&\s\"<>]+",
                       r"\1\2[REDACTED]", value)
    return value


def emit(value):
    print(json.dumps(scrub(value), ensure_ascii=False, indent=2))


def params_from(items):
    result = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or key not in PARAMS or key in result:
            raise Failure("Use unique --param key=value entries from the supported parameter set.")
        result[key] = value
    return result


class NoRedirect(http.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Failure("API redirect refused to protect credentials.")


def request(path, params, token, refresh=False, response_versions=None):
    # Disable environment proxies and redirects; credentials never reach another host.
    opener = http.build_opener(http.ProxyHandler({}), NoRedirect())
    query = dict(params)
    headers = {"Accept": "application/json", "User-Agent": "instagram-readonly/1"}
    if refresh:
        query["access_token"] = token  # Required by Meta's refresh endpoint; never logged.
    else:
        headers["Authorization"] = "Bearer " + token
    address = HOST + path + ("?" + url.urlencode(query) if query else "")
    for attempt in range(4):
        status_code, retry_after = 200, None
        try:
            with opener.open(http.Request(address, headers=headers, method="GET"), timeout=30) as response:
                version = response.headers.get("facebook-api-version", "")
                if response_versions is not None and re.fullmatch(r"v[0-9]+\.[0-9]+", version):
                    response_versions.add(version)
                raw = response.read(20_000_001)
        except urllib.error.HTTPError as error:
            status_code = error.code
            retry_after = error.headers.get("Retry-After")
            raw = error.read(20_000_001)
            error.close()
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 3:
                raise Failure("Network request failed; transport details suppressed to protect credentials.")
            time.sleep(min(2 ** attempt + random.random(), 60))
            continue
        if len(raw) > 20_000_000:
            raise Failure("Response too large; reduce the page limit or query size.")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            payload = {"error": {"message": "Non-JSON API response (body suppressed)."}}
        if not isinstance(payload, dict):
            raise Failure("Unexpected API response shape (body suppressed).")
        error = payload.get("error")
        if not error and status_code == 200:
            return payload
        if not isinstance(error, dict):
            error = {"message": "Unsuccessful API request."}
        code = error.get("code")
        transient = (status_code == 429 or status_code >= 500 or
                     code in (1, 2, 4, 17, 32, 613) or error.get("is_transient") is True)
        if code in (10, 100, 190, 200):
            transient = False
        if transient and attempt < 3:
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt + random.random()
            if delay > 60:
                raise Failure("API rate limit requires a wait longer than 60 seconds; retry later.")
            time.sleep(delay)
            continue
        hint = ("Token invalid or expired; valid long-lived tokens may be refreshed; otherwise reauthorize."
                if code == 190 else "Check permissions, API version, metric and parameter compatibility.")
        safe = {k: error.get(k) for k in ("message", "code", "error_subcode", "type", "fbtrace_id")}
        raise Failure(json.dumps(scrub({"http_status": status_code, "api_error": safe, "hint": hint})))


def next_params(next_url, expected_path):
    parsed = url.urlsplit(next_url)
    actual = re.fullmatch(r"/(v[0-9]+\.[0-9]+)(/.*)", parsed.path)
    expected = re.fullmatch(r"/(v[0-9]+\.[0-9]+)(/.*)", expected_path)
    if (parsed.scheme != "https" or parsed.netloc != "graph.instagram.com" or
            not actual or not expected or actual.group(2) != expected.group(2) or parsed.fragment):
        raise Failure("Unexpected pagination destination refused.")
    # Meta may advertise another version. Keep the configured path and same resource.
    # Rebuild from sanitized parameters; never follow the raw URL or change hosts.
    items = []
    for key, value in url.parse_qsl(parsed.query, keep_blank_values=True):
        if key == "access_token":
            if value:
                SECRETS.add(value)
            continue
        items.append(key + "=" + value)
    return params_from(items)


def get_data(args, config):
    endpoint = args.endpoint.strip("/")
    if not re.fullmatch(r"(?:me|[0-9]+)(?:/(?:media|stories|children|insights))?", endpoint):
        raise Failure("Allowed paths: me or numeric ID, optionally /media, /stories, /children, /insights.")
    params = params_from(args.param)
    path = "/" + config["INSTAGRAM_API_VERSION"] + "/" + endpoint
    seen, rows, last, pending = set(), [], {}, None
    response_versions, pagination_versions = set(), set()
    for page in range(1, args.max_pages + 1):
        signature = json.dumps(params, sort_keys=True)
        if signature in seen:
            raise Failure("Pagination cycle detected; query a narrower range.")
        seen.add(signature)
        last = request(path, params, config["INSTAGRAM_ACCESS_TOKEN"], response_versions=response_versions)
        if isinstance(last.get("data"), list):
            rows.extend(last["data"])
        pending = last.get("paging", {}).get("next")
        if pending:
            candidate = next_params(pending, path)
            pagination_versions.add(url.urlsplit(pending).path.split("/")[1])
            # Safe continuation contains no token, even when Meta puts one in paging URLs.
            pending = HOST + path + "?" + url.urlencode(candidate)
        if not args.all or not pending:
            break
        params = candidate
    result = dict(last)
    if "data" in last:
        result["data"] = rows
    result.pop("paging", None)
    if pending:
        result["paging"] = {"next": pending}
    emit({"api_version": config["INSTAGRAM_API_VERSION"],
          "response_api_versions": sorted(response_versions),
          "pagination_api_versions": sorted(pagination_versions), "fetched_at": utc(),
          "endpoint": endpoint, "pages": page, "has_more": bool(pending),
          "complete": not bool(pending), "result": result})


def main():
    parser = argparse.ArgumentParser(description="Read-only Instagram API; secrets never accepted as arguments.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("set-token", help="User-only interactive secret entry; never run via agent transcripts.")
    commands.add_parser("refresh")
    get = commands.add_parser("get")
    get.add_argument("endpoint")
    get.add_argument("--param", action="append", default=[])
    get.add_argument("--all", action="store_true")
    get.add_argument("--max-pages", type=int, default=100)
    args = parser.parse_args()
    if args.command == "get" and not 1 <= args.max_pages <= 1000:
        raise Failure("--max-pages must be between 1 and 1000.")
    with locked(ROOT / ".env.lock"):
        if args.command == "set-token" and (not sys.stdin.isatty() or not sys.stderr.isatty()):
            raise Failure("Token entry requires the user's interactive terminal.")
        try:
            config = load_env()
        except Failure:
            if args.command != "set-token":
                raise
            # The user can replace an unsafe or malformed file without reading its token.
            config = {"INSTAGRAM_API_VERSION": "v25.0"}
        if args.command == "status":
            expiry = config.get("INSTAGRAM_TOKEN_EXPIRES_AT")
            emit({"configured": bool(config.get("INSTAGRAM_ACCESS_TOKEN")),
                  "api_version": config["INSTAGRAM_API_VERSION"],
                  "expires_at_unix": int(expiry) if expiry else None,
                  "expired": int(expiry) <= time.time() if expiry else None,
                  "live_access_verified": False})
            return
        if args.command == "set-token":
            token = getpass.getpass("Instagram access token (hidden): ")
            SECRETS.add(token)
            if not re.fullmatch(r"[A-Za-z0-9._~-]{20,}", token):
                raise Failure("Invalid token format; nothing saved.")
            config.update(INSTAGRAM_ACCESS_TOKEN=token, INSTAGRAM_TOKEN_ISSUED_AT="",
                          INSTAGRAM_TOKEN_EXPIRES_AT="")
            save_env(config)
            emit({"saved": True, "expiry": "unknown; refresh a valid long-lived token to record expiry"})
            return
        token = config.get("INSTAGRAM_ACCESS_TOKEN")
        if not token:
            raise Failure("Token not configured. User must enter it locally; never paste it into chat.")
        if args.command == "get":
            get_data(args, config)
            return
        now = int(time.time())
        issued, expiry = config.get("INSTAGRAM_TOKEN_ISSUED_AT"), config.get("INSTAGRAM_TOKEN_EXPIRES_AT")
        if expiry and now >= int(expiry):
            raise Failure("Token expired; user reauthorization is required.")
        if issued and now - int(issued) < 86400:
            raise Failure("Token must be at least 24 hours old before refresh.")
        payload = request("/refresh_access_token", {"grant_type": "ig_refresh_token"}, token, refresh=True)
        replacement = payload.get("access_token")
        if isinstance(replacement, str) and replacement:
            SECRETS.add(replacement)
        lifetime = payload.get("expires_in")
        if (not isinstance(replacement, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{20,}", replacement)
                or type(lifetime) is not int or lifetime <= 0):
            raise Failure("Invalid refresh response (body suppressed); credential file unchanged.")
        now = int(time.time())
        config.update(INSTAGRAM_ACCESS_TOKEN=replacement, INSTAGRAM_TOKEN_ISSUED_AT=str(now),
                      INSTAGRAM_TOKEN_EXPIRES_AT=str(now + lifetime))
        save_env(config)
        emit({"refreshed": True, "expires_at_unix": now + lifetime, "expires_in": lifetime})


if __name__ == "__main__":
    try:
        main()
    except (Failure, PrivateFileError) as error:
        emit({"error": str(error)})
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        emit({"error": "Unexpected local failure; details suppressed to protect credentials."})
        sys.exit(1)
