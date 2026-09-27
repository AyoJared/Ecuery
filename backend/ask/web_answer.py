"""Fallback for topics Ecuery has no dataset for: a cited answer from the web, checked quote by quote.

1. Gemini with Google Search finds pages about the question (it only picks the sources). Keys without Search
   grounding quota fall back to Wikipedia's public search API.
2. We download those pages ourselves and keep their exact text: the evidence is what the site says, not what
   the model says it says.
3. Gemini writes the answer, backing every sentence with a verbatim quote from one of the pages.
4. Our code checks each quote really is in that page, and every number in the answer is in a verified quote.
   One rewrite on failure; if anything is still unsupported we refuse rather than show it.
5. The answer, quotes, URLs and a sha256 of each page's text are anchored on Solana, so anyone can later prove
   what the sources said when we answered (Solana proves integrity and time, not truth).
"""

import hashlib
import html
import json
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from google import genai
from google.genai import errors as genai_errors, types
from pydantic import BaseModel, Field

from verify.hashing import build_record, memo_for, sha256_hex
from verify.solana_client import SolanaUnavailable, get_client as get_solana

from .factcheck import _number_ok, evidence_sha256

MAX_SOURCES = 5
PAGE_CHARS = 60_000      # text kept per page (checked against in full)
PROMPT_CHARS = 12_000    # text per page shown to the model
_http = httpx.Client(timeout=15, follow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (compatible; Ecuery/1.0; environmental Q&A with citations)"})


class WebUnavailable(Exception):
    """No usable sources, or no answer that passed the quote check."""


class Claim(BaseModel):
    statement: str = Field(description="One fact used in the answer, in your words")
    source: int = Field(description="Index of the source it comes from (0-based)")
    quote: str = Field(description="Exact words copied from that source that state this fact: a contiguous "
                                   "passage of 5-60 words, character for character, including its numbers")


class WebAnswer(BaseModel):
    answer_text: str = Field(description="2-4 plain sentences answering the question, for the UI and read aloud: "
                                         "no markdown, bullets or emoji. Every number must appear in one of the quotes.")
    claims: list[Claim] = Field(description="Every fact and number in answer_text, each with its supporting quote")
    answered: bool = Field(description="False if the sources don't actually answer the question")


INSTRUCTIONS = """You answer environmental questions using ONLY the numbered source pages given. Do not use your
own knowledge. Every fact and every number in answer_text must come from a source and be listed in claims with
an exact, contiguous quote from that source's text (copy it character for character; do not fix typos, join
passages or paraphrase inside the quote). Only use numbers exactly as they appear in the quotes (you may add
thousands separators). Prefer official and scientific sources (space agencies, NOAA, UN, peer-reviewed studies)
when sources disagree, and mention the source by name in a short clause ("according to NASA"). If the sources
don't answer the question, set answered to false and say briefly what they do cover."""


# ---------------------------------------------------------------- 1-2: find and download sources

def find_sources(client: genai.Client, model: str, question: str) -> list[str]:
    response = client.models.generate_content(
        model=model,
        contents=f"Find authoritative, current sources with data that answer this environmental question: {question}",
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0))
    urls = []
    for cand in response.candidates or []:
        meta = cand.grounding_metadata
        for chunk in (meta.grounding_chunks if meta and meta.grounding_chunks else []):
            if chunk.web and chunk.web.uri and chunk.web.uri not in urls:
                urls.append(chunk.web.uri)
    return urls[:MAX_SOURCES * 2]


WIKI_API = "https://en.wikipedia.org/w/api.php"
# Wikimedia requires an identifying agent with contact details (the same one the data ingest uses).
from ingest.provenance import USER_AGENT as WIKI_AGENT  # noqa: E402


def wikipedia_sources(question: str, topic: str) -> list[dict]:
    """Top Wikipedia articles for the topic and the question, as plain text (no HTML scraping needed)."""
    titles: list[str] = []
    for query in (topic, question):
        try:
            hits = _http.get(WIKI_API, params={"action": "query", "list": "search", "srsearch": query, "srlimit": 3,
                                               "format": "json"}, headers={"User-Agent": WIKI_AGENT}).json()["query"]["search"]
        except (httpx.HTTPError, KeyError, ValueError):
            continue
        titles += [h["title"] for h in hits if h["title"] not in titles]
    sources = []
    for title in titles[:MAX_SOURCES]:
        try:
            pages = _http.get(WIKI_API, params={"action": "query", "prop": "extracts", "explaintext": 1, "titles": title,
                                                "format": "json", "redirects": 1}, headers={"User-Agent": WIKI_AGENT}).json()["query"]["pages"]
        except (httpx.HTTPError, KeyError, ValueError):
            continue
        text = normalize_space(next(iter(pages.values())).get("extract", ""))[:PAGE_CHARS]
        if len(text) < 300:
            continue
        sources.append({"url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"), "title": f"{title} (Wikipedia)",
                        "site": "en.wikipedia.org", "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return sources


def page_text(body: bytes, content_type: str) -> tuple[str, str]:
    """(title, readable text) of an HTML page, with navigation, scripts and styles removed."""
    if "html" not in content_type:
        text = body.decode("utf-8", "replace") if content_type.startswith("text/") else ""
        return "", normalize_space(text)
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg", "aside"]):
        tag.decompose()
    title = normalize_space(soup.title.get_text()) if soup.title else ""
    return title, normalize_space(soup.get_text(" "))


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch_sources(urls: list[str]) -> list[dict]:
    sources = []
    for url in urls:
        try:
            resp = _http.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue  # blocked, gone or slow: skip it
        title, text = page_text(resp.content, resp.headers.get("content-type", ""))
        if len(text) < 300:
            continue  # empty shells (JavaScript-only pages, cookie walls)
        final = str(resp.url)
        if any(s["url"] == final for s in sources):
            continue
        text = text[:PAGE_CHARS]
        sources.append({"url": final, "title": title or httpx.URL(final).host, "site": httpx.URL(final).host,
                        "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        if len(sources) == MAX_SOURCES:
            break
    return sources


# ---------------------------------------------------------------- 3-4: answer, then check every quote and number

def _canon(text: str) -> str:
    """Compare quotes ignoring case, spacing, curly quotes and dash styles."""
    text = text.lower().translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                                                 " ": " "}))
    return re.sub(r"\s+", " ", text).strip()


NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[float]:
    out = set()
    for m in NUMBER.finditer(text):
        try:
            out.add(float(m[0].replace(",", "")))
        except ValueError:
            pass
    return out


def check(answer: WebAnswer, sources: list[dict]) -> dict:
    pages = [_canon(s["text"]) for s in sources]
    verified, bad_quotes = [], []
    for c in answer.claims:
        ok = 0 <= c.source < len(sources) and len(c.quote.split()) >= 3 and _canon(c.quote) in pages[c.source]
        (verified if ok else bad_quotes).append(c)
    quoted = set().union(*(_numbers(c.quote) for c in verified)) if verified else set()
    unsupported = [m[0] for m in NUMBER.finditer(answer.answer_text)
                   if not _number_ok(float(m[0].replace(",", "")), m[0], quoted)]
    return {"ok": answer.answered and bool(verified) and not bad_quotes and not unsupported,
            "checked": len(answer.claims), "verified_quotes": len(verified),
            "quotes_not_found": [c.quote[:120] for c in bad_quotes], "unsupported": unsupported,
            "verified": verified}


def _generate(client, model, question, sources, feedback=None) -> WebAnswer:
    docs = [{"source": i, "title": s["title"], "url": s["url"], "text": s["text"][:PROMPT_CHARS]}
            for i, s in enumerate(sources)]
    contents = json.dumps({"question": question, "sources": docs}, ensure_ascii=False) + (f"\n\n{feedback}" if feedback else "")
    response = client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(system_instruction=INSTRUCTIONS, response_mime_type="application/json",
                                           response_schema=WebAnswer, temperature=0,
                                           automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
    result = response.parsed or WebAnswer.model_validate_json(response.text)
    result.answer_text = html.unescape(result.answer_text)
    return result


def answer_from_web(client: genai.Client, model: str, question: str, topic: str, lap) -> dict:
    try:
        sources = fetch_sources(find_sources(client, model, question))
    except genai_errors.APIError as e:
        if e.code not in (403, 429):
            raise WebUnavailable(f"web search failed ({e.code})")
        sources = []  # no Search grounding quota on this key
    if not sources:
        sources = wikipedia_sources(question, topic)
    lap("search")
    if not sources:
        raise WebUnavailable("no readable sources")

    answer = _generate(client, model, question, sources)
    report = check(answer, sources)
    if not report["ok"] and answer.answered:
        feedback = ("Your previous answer failed verification. " +
                    (f"These quotes are not in the sources verbatim: {report['quotes_not_found']}. " if report["quotes_not_found"] else "") +
                    (f"These numbers are not in any verified quote: {report['unsupported']}. " if report["unsupported"] else "") +
                    "Copy quotes exactly from the source text and only state numbers that appear in them.")
        first = {k: report[k] for k in ("quotes_not_found", "unsupported")}
        answer = _generate(client, model, question, sources, feedback)
        report = check(answer, sources) | {"retried": True, "first_attempt": first}
    lap("analyze")
    if not answer.answered:
        raise WebUnavailable("the sources found don't answer it")
    if not report["ok"]:
        raise WebUnavailable("no answer passed the quote check")

    used = sorted({c.source for c in report["verified"]})
    cited = [{k: sources[i][k] for k in ("url", "title", "site", "text_sha256", "fetched_at")} for i in used]
    index = {i: n for n, i in enumerate(used)}
    quotes = [{"statement": c.statement, "quote": c.quote, "source": index[c.source]} for c in report["verified"]]
    evidence = {"sources": [{"url": s["url"], "text_sha256": s["text_sha256"]} for s in cited], "quotes": quotes}
    fact = {"ok": True, "checked": report["checked"], "unsupported": [], "evidence_sha256": evidence_sha256(evidence),
            "method": "quotes", "verified_quotes": report["verified_quotes"], "retried": report.get("retried", False),
            **({"first_attempt": report["first_attempt"]} if report.get("first_attempt") else {})}

    verification = _anchor(question, answer.answer_text, cited, quotes, fact)
    lap("verify")
    return {
        "kind": "web",
        "answer_text": answer.answer_text,
        "trends": [],
        "comparison": None,
        "web": {"topic": topic, "sources": cited, "quotes": quotes},
        "data_notes": [f"Ecuery has no dataset for {topic}, so this answer comes from {len(cited)} web "
                       f"source{'s' if len(cited) != 1 else ''}. Every figure is quoted from them and each quote was "
                       "checked against the page text we downloaded; the sources themselves are not measured data."],
        "provenance": [],
        "verification": verification,
        "fact_check": fact,
        "grounding": {"ok": True, "label": f"Cited from the web: {report['verified_quotes']} quotes checked against "
                                           f"{len(cited)} source{'s' if len(cited) != 1 else ''}"},
    }


# ---------------------------------------------------------------- 5: anchor

def _anchor(question: str, answer_text: str, cited: list[dict], quotes: list[dict], fact: dict) -> dict:
    record = build_record(
        query=question,
        result={"kind": "web", "answer": answer_text, "quotes": quotes,
                "fact_check": {k: fact[k] for k in ("ok", "checked", "unsupported", "evidence_sha256")}},
        source=json.dumps({"web_sources": [{k: s[k] for k in ("url", "text_sha256", "fetched_at")} for s in cited]},
                          sort_keys=True, separators=(",", ":")))
    digest = sha256_hex(record)
    solana = get_solana()
    try:
        tx = solana.send_memo(memo_for(digest))
    except SolanaUnavailable as e:
        return {"record": record, "hash": digest, "signature": None, "explorer_url": None, "mode": solana.mode,
                "error": str(e), "badge": {"verified": False, "label": "Not verified"}}
    return {"record": record, "hash": digest, "signature": tx.signature, "explorer_url": tx.explorer_url,
            "mode": solana.mode, "cluster": tx.cluster, "slot": tx.slot,
            "badge": {"verified": True, "label": "Anchored on Solana" if solana.mode == "rpc" else "Anchored (simulated)"}}
