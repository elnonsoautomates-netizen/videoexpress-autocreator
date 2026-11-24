"""AI script writer: study reference transcripts, extract their FORMULA, and write a new, original
narration script (or story outline for movies) on your topic that follows the same formula."""
from __future__ import annotations

import re

from .brain import APIError, BrainError, _extract_json

FORMULA_SYSTEM = """You are a senior YouTube script analyst. You reverse-engineer WHY a video script keeps viewers
watching. Describe the formula so precisely that another writer could reproduce it on a completely different topic.
Return ONLY JSON."""

FORMULA_TASK = """Study these reference transcript(s) and extract their shared formula.
Return JSON:
{{
 "summary": "2-3 sentences: what makes this formula work",
 "hook": "how the first 15-30 seconds work (devices used, length, tone)",
 "structure": [{{"section": "name", "share": "percent of the script", "purpose": "what it does", "devices": "retention devices used"}}],
 "voice": "narrator voice: person, tense, tone, sentence length, vocabulary level, rhythm",
 "retention_devices": ["open loops", "rhetorical questions", "..."],
 "cta": "where and how calls to action / subscribe lines appear (paraphrase, never quote)",
 "ending": "how it ends",
 "words_per_minute": estimated speaking pace as a number,
 "avoid": ["things this formula never does"]
}}

REFERENCE TRANSCRIPT(S):
<<<
{refs}
>>>"""

WRITE_SYSTEM = """You are a top YouTube scriptwriter. You write ORIGINAL narration scripts that follow a proven formula.
Rules:
- Follow the formula's hook, section order and proportions, narrator voice, retention devices, CTA placement and ending.
- 100% original wording about the NEW topic: never reuse sentences or distinctive phrases from the reference
  (no run of more than 5 words copied).
- Facts must be accurate. Use well-established facts; if you are not sure of a number, date or quote, leave it out.
  Never invent quotes. If web search is available, check key facts.
- Write ONLY the words the narrator speaks: no headings, no labels, no stage directions, no brackets, no emojis,
  no "[music]" or timestamps. Paragraphs separated by one blank line. Easy to speak aloud.
- Hit the requested length (±10 %)."""

WRITE_TASK = """NEW TOPIC: {topic}
{extra}
TARGET LENGTH: about {words} words (≈ {minutes:g} minutes spoken).
{channel}
FORMULA TO FOLLOW:
{formula}

Write the complete narration script now."""

DEFAULT_FORMULA = {
    "summary": "Documentary storytelling: a dramatic cold open, then a chronological story with rising stakes, "
               "short punchy sentences and open loops that pay off later.",
    "hook": "Start in the middle of the most dramatic moment, 3-5 short sentences, then promise what the viewer will learn.",
    "structure": [{"section": "Cold open hook", "share": "8%", "purpose": "grab attention"},
                  {"section": "Background / setup", "share": "20%", "purpose": "who, where, why it matters"},
                  {"section": "Rising tension", "share": "35%", "purpose": "events build, open loops"},
                  {"section": "Climax", "share": "22%", "purpose": "the turning point"},
                  {"section": "Aftermath and meaning", "share": "15%", "purpose": "what changed, lasting lesson"}],
    "voice": "third person, past tense, confident and vivid, mostly short sentences with occasional long ones",
    "retention_devices": ["open loops", "rhetorical questions", "cliffhanger before each section"],
    "cta": "one short subscribe line after the hook and one at the very end",
    "ending": "a reflective final line that ties back to the opening image",
    "words_per_minute": 160,
    "avoid": ["lists", "dry dates without story", "clichés like 'in today's video'"],
}


def _clip_refs(refs: str, max_words: int) -> str:
    words = refs.split()
    if len(words) <= max_words:
        return refs
    # keep the beginning (hook) and evenly sampled later parts so the whole structure is visible
    head = " ".join(words[: max_words // 2])
    rest = words[max_words // 2:]
    step = max(1, len(rest) // (max_words // 2))
    tail = " ".join(rest[::step][: max_words // 2])
    return head + "\n[...]\n" + tail


def clean_transcript(text: str) -> str:
    """Strip timestamps, [Music] tags and caption line breaks from pasted YouTube transcripts."""
    t = re.sub(r"\[\s*(music|applause|laughter|__)\s*\]", " ", text, flags=re.I)
    t = re.sub(r"(?m)^\s*\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s*", "", t)
    t = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def study_formula(brain, refs: str, log=print) -> dict:
    refs = clean_transcript(refs)
    if not refs:
        return dict(DEFAULT_FORMULA)
    limit = 3200 if brain.provider == "groq" else 12000
    task = FORMULA_TASK.format(refs=_clip_refs(refs, limit))
    log("Studying the reference transcript(s) to learn their formula…")
    f = _extract_json(brain.ask(FORMULA_SYSTEM, task, 3000, log=log))
    return f if isinstance(f, dict) and f.get("structure") else dict(DEFAULT_FORMULA)


def write_script(brain, topic: str, formula: dict, minutes: float, wpm: float, extra: str = "",
                 channel: str = "", research: bool = True, log=print) -> str:
    words = int(round(minutes * float(formula.get("words_per_minute") or wpm or 160)))
    task = WRITE_TASK.format(topic=topic.strip(), extra=("NOTES: " + extra.strip()) if extra.strip() else "",
                             words=words, minutes=minutes,
                             channel=(f"CHANNEL NAME for the subscribe lines: {channel}" if channel else
                                      "No channel name: subscribe lines stay generic."),
                             formula=_formula_text(formula))
    max_tokens = min(8000, int(words * 1.8) + 800)
    text = ""
    if research and brain.provider in ("groq", "gemini", "claude"):
        try:
            log("Writing the script (checking facts on the web)…")
            text = brain.ask(WRITE_SYSTEM, task, max_tokens, log=log, json_mode=False, research=True)
        except (APIError, BrainError) as e:
            log(f"Web research not available ({str(e)[:90]}) - writing from the AI's own knowledge.")
            text = ""
    if not text.strip():
        log("Writing the script…")
        text = brain.ask(WRITE_SYSTEM, task, max_tokens, log=log, json_mode=False)
    return tidy_script(text)


def tidy_script(text: str) -> str:
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    t = re.sub(r"\*\*(narrator|voiceover|vo)\s*:\s*\*\*", r"\1:", t, flags=re.I)
    t = re.sub(r"(?m)^[ \t]*(#+[ \t].*|\*\*[^*\n]+\*\*[ \t]*:?[ \t]*|\[[^\]\n]*\]|\([^)\n]*(music|pause|sfx|beat)[^)\n]*\))[ \t]*$", "", t, flags=re.I)
    t = re.sub(r"(?m)^[ \t]*(narrator|voiceover|vo)[ \t]*:[ \t]*", "", t, flags=re.I)
    t = t.replace("**", "").replace("__", "")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _formula_text(f: dict) -> str:
    lines = [f"Summary: {f.get('summary', '')}", f"Hook: {f.get('hook', '')}", "Structure:"]
    for s in f.get("structure", []):
        lines.append(f"  - {s.get('section', '')} ({s.get('share', '')}): {s.get('purpose', '')}"
                     + (f" [{s.get('devices')}]" if s.get("devices") else ""))
    lines += [f"Voice: {f.get('voice', '')}", f"Retention devices: {', '.join(f.get('retention_devices', []))}",
              f"CTA: {f.get('cta', '')}", f"Ending: {f.get('ending', '')}", f"Avoid: {', '.join(f.get('avoid', []))}"]
    return "\n".join(lines)


def formula_for_story(formula: dict | None) -> str:
    """Short style note handed to the screenplay writer for movie mode."""
    if not formula:
        return ""
    return ("Follow this storytelling formula learned from the reference videos (structure and pacing only, original "
            "words): " + _formula_text(formula)[:1500])
