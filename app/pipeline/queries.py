import json, re, httpx
from app.config import settings

STOP = set("the a an and or of to in on for with is are was were be it this that your you we i our their at by from as".split())

def heuristic_query(sentence: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z]+", sentence.lower()) if w not in STOP]
    return " ".join(words[:4]) or "abstract background"

def llm_query(sentence: str, context: str, style: str) -> str | None:
    if not settings.gemini_api_key:
        return None
    prompt = (
        "You pick stock-video search queries. Given one narration sentence and the "
        f"overall topic, return a 2-4 word search query describing a concrete, filmable "
        "visual that matches the MEANING (not the literal word). Avoid readable text, "
        f"logos and real people. Style: {style}.\nTopic: {context}\nSentence: {sentence}\n"
        'Reply only as JSON: {"query": "..."}')
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{settings.llm_model}:generateContent")
    try:
        r = httpx.post(url, params={"key": settings.gemini_api_key}, timeout=30,
                       json={"contents": [{"parts": [{"text": prompt}]}],
                             "generationConfig": {"responseMimeType": "application/json"}})
        r.raise_for_status()
        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(txt)["query"]
    except Exception:
        return None  # fall back silently, caller records a warning

def make_query(sentence, context, style="bright, modern"):
    q = llm_query(sentence, context, style)
    if q:
        return q, "llm"
    return heuristic_query(sentence), "heuristic"