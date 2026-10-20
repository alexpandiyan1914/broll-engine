import json, re, httpx
from app.config import settings

STOP = set("the a an and or of to in on for with is are was were be it this that your you we i our their at by from as".split())
last_error = ""


def heuristic_query(sentence: str, names=()) -> str:
    drop = {n.lower() for n in names}
    words = [w for w in re.findall(r"[A-Za-z]+", sentence.lower())
             if w not in STOP and w not in drop]
    return " ".join(words[:4]) or "abstract background"


def llm_query(sentence, context, style, avoid, names):
    global last_error
    if not settings.gemini_api_key:
        last_error = "no GEMINI_API_KEY set"
        return None
    prompt = (
        "You pick stock-video search queries. Given one narration sentence and the overall "
        "topic, return a 2-4 word search query for a concrete, filmable visual that matches "
        "the MEANING, not the literal word (e.g. 'value' as in worth is not a pile of cash; "
        "'bank' may be a river bank or a financial bank depending on context). "
        "Rules: never include names of real people, brands or companies; use a generic "
        "visual instead. For abstract ideas pick a clear everyday metaphor scene. "
        "No readable text or logos. "
        f"Avoid showing: {', '.join(avoid) or 'nothing special'}. "
        f"Do not use these words: {', '.join(names) or 'none'}. Style: {style}.\n"
        f"Topic: {context}\nSentence: {sentence}\n"
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
    except Exception as e:
        last_error = f"LLM call failed: {str(e)[:120]}"
        return None


def make_query(sentence, context, style="bright, modern", avoid=(), names=()):
    q = llm_query(sentence, context, style, avoid, names)
    if q:
        drop = {n.lower() for n in names}
        q = " ".join(w for w in q.split() if w.lower() not in drop)
        if q:
            return q, "llm"
    return heuristic_query(sentence, names), "heuristic"