import hmac
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from typing import Literal
from urllib.parse import urlencode, urlparse

import feedparser
import requests
from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")

mcp = FastMCP(
    "agent-reach-research",
    instructions=(
        "Use Agent Reach when the user asks for current, external, multi-source, "
        "URL, GitHub, YouTube, or RSS research. Do not call it for casual conversation, "
        "creative writing, or facts already established in the conversation. Cite URLs "
        "returned by the tool and clearly distinguish retrieved evidence from inference."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)

app = FastAPI(title="Agent Reach Wiki Gateway", version="2.0.0")

TOKEN = os.getenv("GATEWAY_TOKEN", "")
MAX_QUERY = 2000
AUTH_SOURCES = {"reddit", "twitter", "x", "instagram", "facebook", "xiaohongshu", "xueqiu"}
OAUTH_CODES: dict[str, dict] = {}
OAUTH_CLIENTS: dict[str, dict] = {}


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY)
    source: Literal[
        "auto", "web", "search", "youtube", "github", "rss",
        "reddit", "twitter", "x", "instagram", "facebook", "xiaohongshu", "xueqiu"
    ] = "auto"
    limit: int = Field(default=5, ge=1, le=10)


def require_token(authorization: str | None):
    if not TOKEN:
        raise HTTPException(status_code=503, detail="GATEWAY_TOKEN is not configured")
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Bearer token required")
    supplied = authorization[len(prefix):]
    if not hmac.compare_digest(supplied, TOKEN):
        raise HTTPException(status_code=403, detail="Invalid token")


def base_url(request: Request | None = None) -> str:
    if PUBLIC_URL:
        return PUBLIC_URL
    if request:
        return str(request.base_url).rstrip("/")
    return ""


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def issue_access_token(client_id: str) -> str:
    payload = b64url(json.dumps({"sub": client_id, "exp": int(time.time()) + 2592000}, separators=(",", ":")).encode())
    sig = b64url(hmac.new(TOKEN.encode(), payload.encode(), hashlib.sha256).digest())
    return f"ar1.{payload}.{sig}"


def valid_access_token(value: str) -> bool:
    try:
        prefix, payload, signature = value.split(".")
        expected = b64url(hmac.new(TOKEN.encode(), payload.encode(), hashlib.sha256).digest())
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
        return prefix == "ar1" and hmac.compare_digest(signature, expected) and claims["exp"] > time.time()
    except Exception:
        return False


class MCPBearerAuth:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not valid_access_token(token):
            resource = f'{PUBLIC_URL}/.well-known/oauth-protected-resource' if PUBLIC_URL else "/.well-known/oauth-protected-resource"
            response = JSONResponse(
                {"error": "unauthorized", "error_description": "Connect Agent Reach through ChatGPT OAuth."},
                status_code=401,
                headers={"WWW-Authenticate": f'Bearer resource_metadata="{resource}"'},
            )
            return await response(scope, receive, send)
        return await self.inner(scope, receive, send)


def run_cmd(args: list[str], timeout: int = 45):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Upstream tool timed out")
    if p.returncode != 0:
        msg = (p.stderr or p.stdout or "upstream tool failed")[-3000:]
        raise HTTPException(status_code=502, detail=msg)
    return p.stdout


def is_url(text: str) -> bool:
    try:
        parsed = urlparse(text.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def auto_source(query: str) -> str:
    q = query.strip()
    low = q.lower()
    if is_url(q):
        host = urlparse(q).netloc.lower()
        if "youtube.com" in host or "youtu.be" in host:
            return "youtube"
        if "github.com" in host:
            return "github"
        return "web"
    if any(k in low for k in ["github", "깃허브", "repository", "repo "]):
        return "github"
    if any(k in low for k in ["youtube", "유튜브", "youtu.be"]):
        return "search"
    return "search"


def jina_read(url: str):
    r = requests.get("https://r.jina.ai/" + url, timeout=40, headers={"Accept": "text/plain"})
    r.raise_for_status()
    return {"source": "web", "url": url, "content": r.text[:120000]}


def exa_search(query: str, limit: int):
    out = run_cmd([
        "mcporter", "call", "exa.web_search_exa",
        f"query={query}", f"numResults={limit}"
    ], timeout=50)
    try:
        parsed = json.loads(out)
    except Exception:
        parsed = out
    return {"source": "search", "backend": "exa", "query": query, "result": parsed}


def youtube_read(query: str):
    if not is_url(query):
        return exa_search(f"site:youtube.com {query}", 5)
    out = run_cmd(["yt-dlp", "--dump-single-json", "--skip-download", "--no-playlist", query], timeout=60)
    data = json.loads(out)
    keep = {
        k: data.get(k)
        for k in ["id", "title", "description", "uploader", "channel", "duration", "upload_date", "webpage_url", "subtitles", "automatic_captions"]
    }
    return {"source": "youtube", "result": keep}


def github_read(query: str, limit: int):
    if is_url(query) and "github.com" in urlparse(query).netloc.lower():
        out = run_cmd([
            "gh", "repo", "view", query,
            "--json", "nameWithOwner,description,url,stargazerCount,forkCount,updatedAt,licenseInfo,defaultBranchRef"
        ])
        return {"source": "github", "result": json.loads(out)}
    out = run_cmd([
        "gh", "search", "repos", query,
        "--limit", str(limit),
        "--json", "fullName,description,url,stargazersCount,updatedAt"
    ])
    return {"source": "github", "query": query, "result": json.loads(out)}


def rss_read(url: str, limit: int):
    if not is_url(url):
        raise HTTPException(status_code=400, detail="RSS source requires a feed URL")
    feed = feedparser.parse(url)
    entries = []
    for item in feed.entries[:limit]:
        entries.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "published": item.get("published"),
            "summary": re.sub(r"<[^>]+>", "", item.get("summary", ""))[:4000],
        })
    return {
        "source": "rss",
        "feed": {"title": feed.feed.get("title"), "link": feed.feed.get("link")},
        "entries": entries,
    }


def dispatch_research(query: str, source: str = "auto", limit: int = 5):
    selected = auto_source(query) if source == "auto" else source
    if selected in AUTH_SOURCES:
        return {
            "status": "additional_setup_required",
            "source": selected,
            "reason": "This source requires login/cookies or a browser session.",
            "safe_fallback": "Use public web discovery or configure a dedicated session separately.",
        }
    if selected == "web":
        return jina_read(query.strip()) if is_url(query) else exa_search(query, limit)
    if selected == "search":
        return exa_search(query, limit)
    if selected == "youtube":
        return youtube_read(query)
    if selected == "github":
        return github_read(query, limit)
    if selected == "rss":
        return rss_read(query, limit)
    raise ValueError("Unsupported source")


@mcp.tool(
    title="Research with Agent Reach",
    description=(
        "Research current or external information using Agent Reach. Use when the user needs "
        "up-to-date evidence, multiple web sources, a URL read, GitHub repository lookup, "
        "YouTube metadata, or an RSS feed. Do not use for casual conversation, rewriting, "
        "brainstorming, or stable facts that do not need retrieval."
    ),
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True, destructiveHint=False),
)
def research_with_agent_reach(
    query: str,
    source: Literal["auto", "web", "search", "youtube", "github", "rss"] = "auto",
    limit: int = 5,
) -> dict:
    """Return model-readable research evidence and source URLs."""
    if not query.strip() or len(query) > MAX_QUERY:
        raise ValueError(f"query must contain 1-{MAX_QUERY} characters")
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    return dispatch_research(query, source, limit)


@app.get("/.well-known/oauth-protected-resource")
def oauth_resource(request: Request):
    root = base_url(request)
    return {"resource": f"{root}/mcp", "authorization_servers": [root], "bearer_methods_supported": ["header"]}


@app.get("/.well-known/oauth-authorization-server")
def oauth_server(request: Request):
    root = base_url(request)
    return {
        "issuer": root,
        "authorization_endpoint": f"{root}/oauth/authorize",
        "token_endpoint": f"{root}/oauth/token",
        "registration_endpoint": f"{root}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


@app.post("/oauth/register")
async def oauth_register(request: Request):
    data = await request.json()
    redirects = data.get("redirect_uris") or []
    if not redirects or not all(str(x).startswith("https://") for x in redirects):
        raise HTTPException(status_code=400, detail="A valid HTTPS redirect_uri is required")
    client_id = secrets.token_urlsafe(24)
    OAUTH_CLIENTS[client_id] = {"redirect_uris": redirects, "created": time.time()}
    return {"client_id": client_id, "client_id_issued_at": int(time.time()), "redirect_uris": redirects, "token_endpoint_auth_method": "none"}


@app.get("/oauth/authorize", response_class=HTMLResponse)
def oauth_authorize_page(
    client_id: str, redirect_uri: str, state: str, code_challenge: str, code_challenge_method: str = "S256"
):
    client = OAUTH_CLIENTS.get(client_id)
    if not client or redirect_uri not in client["redirect_uris"] or code_challenge_method != "S256":
        raise HTTPException(status_code=400, detail="Invalid OAuth request")
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{v}">' for k, v in {
            "client_id": client_id, "redirect_uri": redirect_uri, "state": state,
            "code_challenge": code_challenge,
        }.items()
    )
    return HTMLResponse(f"""<!doctype html><meta name=viewport content='width=device-width'>
    <title>Agent Reach 연결</title><style>body{{font:16px system-ui;max-width:460px;margin:12vh auto;padding:24px}}input,button{{box-sizing:border-box;width:100%;padding:14px;margin-top:12px}}button{{background:#111;color:white;border:0;border-radius:8px}}</style>
    <h1>Agent Reach 연결</h1><p>Render의 GATEWAY_TOKEN을 한 번 입력하세요. ChatGPT에 원문 토큰은 전달되지 않습니다.</p>
    <form method=post action=/oauth/authorize>{hidden}<input type=password name=access_key required autocomplete=current-password placeholder='GATEWAY_TOKEN'><button>ChatGPT에 연결</button></form>""")


@app.post("/oauth/authorize")
def oauth_authorize_submit(
    client_id: str = Form(), redirect_uri: str = Form(), state: str = Form(),
    code_challenge: str = Form(), access_key: str = Form(),
):
    client = OAUTH_CLIENTS.get(client_id)
    if not TOKEN or not hmac.compare_digest(access_key, TOKEN):
        raise HTTPException(status_code=403, detail="Invalid access key")
    if not client or redirect_uri not in client["redirect_uris"]:
        raise HTTPException(status_code=400, detail="Invalid OAuth client")
    code = secrets.token_urlsafe(32)
    OAUTH_CODES[code] = {"client_id": client_id, "redirect_uri": redirect_uri, "challenge": code_challenge, "expires": time.time() + 300}
    return RedirectResponse(f"{redirect_uri}?{urlencode({'code': code, 'state': state})}", status_code=303)


@app.post("/oauth/token")
def oauth_token(
    grant_type: str = Form(), code: str = Form(), redirect_uri: str = Form(),
    client_id: str = Form(), code_verifier: str = Form(),
):
    saved = OAUTH_CODES.pop(code, None)
    challenge = b64url(hashlib.sha256(code_verifier.encode()).digest())
    if grant_type != "authorization_code" or not saved or saved["expires"] < time.time():
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")
    if saved["client_id"] != client_id or saved["redirect_uri"] != redirect_uri or not hmac.compare_digest(saved["challenge"], challenge):
        raise HTTPException(status_code=400, detail="OAuth validation failed")
    return {"access_token": issue_access_token(client_id), "token_type": "Bearer", "expires_in": 2592000}


@app.get("/health")
def health():
    return {"ok": True, "service": "agent-reach-wiki-gateway", "auth_configured": bool(TOKEN)}


@app.get("/doctor")
def doctor(authorization: str | None = Header(default=None)):
    require_token(authorization)
    out = run_cmd(["agent-reach", "doctor", "--json"], timeout=60)
    try:
        return json.loads(out)
    except Exception:
        return {"raw": out}


@app.post("/research")
def research(req: ResearchRequest, authorization: str | None = Header(default=None)):
    require_token(authorization)
    return dispatch_research(req.query, req.source, req.limit)


app.mount("/mcp", MCPBearerAuth(mcp.streamable_http_app()))
