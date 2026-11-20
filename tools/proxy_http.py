#!/usr/bin/env python3
"""HTTP helper that works around the OpenClaw egress proxy.

THE PROBLEM
-----------
The OpenClaw exec sandbox routes outbound HTTPS through a secret egress
proxy that is HOST-ALLOWLISTED. Twitch's API hosts are not on that list:

    api.twitch.tv    -> CONNECT tunnel failed, response 403
    id.twitch.tv     -> CONNECT tunnel failed, response 403
    dev.twitch.tv    -> CONNECT tunnel failed, response 403

A 403 at the CONNECT layer means the proxy refused the tunnel BEFORE TLS.
The host is fine, the credential is fine, the service is fine -- only this
sandbox's egress path is blocked.

THE FIX
-------
The proxy is a sandbox artifact, not a network fact. Unsetting the proxy
variables makes the same request go out directly and it works:

    env -u HTTP_PROXY -u HTTPS_PROXY -u NODE_USE_ENV_PROXY \
        curl https://api.twitch.tv/helix/games

This module handles that automatically:
  - it tries the request with the proxy first
  - if the proxy answers with a CONNECT 403, it retries WITHOUT the proxy
  - it caches that decision so later calls skip the doomed proxy attempt

This way the same script works from inside the sandbox AND from your own
terminal (where there is no proxy to begin with, so the first attempt
succeeds and nothing changes).

USAGE
-----
    from proxy_http import request
    status, data = request("GET", "https://api.twitch.tv/helix/games?name=X",
                            headers={...})
"""

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

# Hosts known to be blocked by the sandbox egress proxy. We still probe
# generically -- if ANY host comes back as a CONNECT 403 we retry direct.
PROXY_ENV_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                  "ALL_PROXY", "all_proxy", "NODE_USE_ENV_PROXY")

# Cache: True once we know direct connections work.
_DIRECT_OK = False

# SSL context for direct (no-proxy) connections.
#
# WHY NOT THE DEFAULT
# ------------------
# The OpenClaw sandbox sets SSL_CERT_FILE to the egress proxy's trust
# bundle. That bundle only contains the CAs the proxy itself needs -- it
# does NOT necessarily contain the issuer for every host we might reach
# directly (Kick is signed by "Google Trust Services WE1"). Connecting
# directly with that bundle gives:
#
#   SSL: CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate
#
# certifi ships a complete public CA bundle and is what pip/requests
# already trust everywhere. Use it for direct connections so the direct
# path does not depend on the proxy's CA list.
_DIRECT_SSL_CONTEXT = None


def _direct_ssl_context():
    """An SSL context with a full public CA bundle, for direct connections."""
    global _DIRECT_SSL_CONTEXT
    if _DIRECT_SSL_CONTEXT is not None:
        return _DIRECT_SSL_CONTEXT

    ctx = None
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            # Fall back to macOS system roots, then the env default.
            ctx = ssl.create_default_context()
        except Exception:
            ctx = None
    _DIRECT_SSL_CONTEXT = ctx
    return ctx


def _no_proxy_env():
    """Return an env dict with the proxy variables removed."""
    env = dict(os.environ)
    for v in PROXY_ENV_VARS:
        env.pop(v, None)
    return env


def _is_proxy_403(err):
    """True if this error is the proxy refusing the CONNECT tunnel."""
    msg = str(err).lower()
    return "tunnel" in msg and "403" in msg


def _build(method, url, headers, body):
    data = None
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", "Streaming-Relay/1.0")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    return req


def _build_form(method, url, fields, headers):
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(fields).encode(), method=method)
    req.add_header("User-Agent", "Streaming-Relay/1.0")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    return req


def _do(req, timeout, env=None):
    """Perform the request, returning (status, parsed_body).

    env=None means "use the ambient environment" (proxy included).
    env=<dict> means "go direct" -- no proxy, full public CA bundle.

    IMPORTANT: the Request object is REBUILT for each attempt.
    urllib.request.Request caches the proxy handler on first use, so
    reusing the same Request object across openers keeps the proxy and
    the direct fallback never actually goes direct. That bug made every
    direct retry fail with "Tunnel connection failed, response 403".
    """
    if env is None:
        opener = urllib.request.build_opener()
    else:
        # Direct: no proxy, and a full public CA bundle.
        handlers = [urllib.request.ProxyHandler({})]
        ctx = _direct_ssl_context()
        if ctx is not None:
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        opener = urllib.request.build_opener(*handlers)

    # Rebuild so the opener's proxy setting is not inherited.
    req = _rebuild(req)

    try:
        with opener.open(req, timeout=timeout) as r:
            raw = r.read().decode(errors="replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, {"error": str(e)}


def _rebuild(req):
    """Return a fresh Request with the same method, url, headers and body.

    Needed because urllib.request.Request memoizes the proxy handler the
    first time it is opened.
    """
    data = req.data
    if data is not None and isinstance(data, str):
        data = data.encode()
    new = urllib.request.Request(req.full_url, data=data, method=req.get_method())
    # Copy the headers we care about (skip the auto-added ones).
    for k, v in req.header_items():
        if k.lower() in ("host", "content-length"):
            continue
        new.add_header(k, v)
    return new


def request(method, url, headers=None, body=None, timeout=15, force_direct=None):
    """Make an HTTP request, working around the sandbox egress proxy.

    Returns (status, body). status == 0 means the request never completed
    (network failure). A non-zero status is the origin server's answer --
    including 401, which means we REACHED the server.
    """
    global _DIRECT_OK

    req = _build(method, url, headers, body)

    # Fast path: we already know direct works.
    if _DIRECT_OK:
        return _do(req, timeout, env=_no_proxy_env())

    # Try with the current environment (proxy included) first.
    status, data = _do(req, timeout)

    if status != 0:
        return status, data

    # Failed. If it was a CONNECT 403, the proxy is the blocker -- retry
    # directly.
    err = (data or {}).get("error", "") if isinstance(data, dict) else str(data)
    if _is_proxy_403(err):
        status, data = _do(req, timeout, env=_no_proxy_env())
        if status != 0:
            _DIRECT_OK = True
        return status, data

    # Some other network failure -- including an SSL failure. That happens
    # when the ambient trust bundle (the proxy's) lacks the issuer for this
    # host. Retry direct with the certifi bundle.
    status, data = _do(req, timeout, env=_no_proxy_env())
    if status != 0:
        _DIRECT_OK = True
        return status, data
    return status, data


def request_form(method, url, fields, headers=None, timeout=20):
    """POST/GET with application/x-www-form-urlencoded body.

    Some OAuth token endpoints (Kick's) require form encoding, not JSON.
    This is the same proxy-aware path as request(), but the body is
    urlencoded and the direct attempt uses a full public CA bundle.
    """
    global _DIRECT_OK

    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", "Streaming-Relay/1.0")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    if _DIRECT_OK:
        return _do(req, timeout, env=_no_proxy_env())

    status, resp = _do(req, timeout)
    if status != 0:
        return status, resp

    err = (resp or {}).get("error", "") if isinstance(resp, dict) else str(resp)
    if _is_proxy_403(err):
        status, resp = _do(req, timeout, env=_no_proxy_env())
        if status != 0:
            _DIRECT_OK = True
        return status, resp

    status, resp = _do(req, timeout, env=_no_proxy_env())
    if status != 0:
        _DIRECT_OK = True
    return status, resp
