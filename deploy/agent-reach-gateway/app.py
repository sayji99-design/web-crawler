import hmac
import json
import os
import re
import subprocess
from typing import Literal
from urllib.parse import urlparse

import feedparser
import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Agent Reach Wiki Gateway", version="1.0.0")

TOKEN = os.getenv("GATEWAY_TOKEN", "")
MAX_QUERY = 2000
AUTH_SOURCES = {"reddit", "twitter", "x", "instagram", "facebook", "xiaohongshu", "xueqiu"}


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
    source = auto_source(req.query) if req.source == "auto" else req.source

    if source in AUTH_SOURCES:
        return {
            "status": "additional_setup_required",
            "source": source,
            "reason": "This service requires login/cookies or a browser session. No automatic login or cookie collection is performed.",
            "safe_fallback": "Use public web/Exa discovery when sufficient, or configure a dedicated account/session separately."
        }

    if source == "web":
        if not is_url(req.query):
            return exa_search(req.query, req.limit)
        return jina_read(req.query.strip())
    if source == "search":
        return exa_search(req.query, req.limit)
    if source == "youtube":
        return youtube_read(req.query)
    if source == "github":
        return github_read(req.query, req.limit)
    if source == "rss":
        return rss_read(req.query, req.limit)

    raise HTTPException(status_code=400, detail="Unsupported source")
