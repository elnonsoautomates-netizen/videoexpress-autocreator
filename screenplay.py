"""Dialogue movies: idea/script → screenplay (characters, beats, shots with spoken lines),
shot timing from the real voice clips, and the prompts for keyframes and talking clips."""
from __future__ import annotations

import math
import re

from .brain import CLOTHING_LOCK, STYLE_PRESETS, _extract_json

STORY_TYPES = {"narrated": "Narrated documentary", "dialogue": "Dialogue movie", "both": "Narrator + dialogue"}

SCREENPLAY_SYSTEM = """You are a screenwriter AND visual director for short AI-generated films. Characters really talk on
screen (lip-synced), so dialogue must be natural, short and speakable. Keep everything visually concrete and consistent.
Describe looks in POSITIVE terms with exact clothing and colours (image models draw what you mention). No readable text,
signs, logos or captions in images. Violence and romance stay tasteful and non-graphic."""

SCREENPLAY_TASK = """Turn this {kind} into a {minutes}-minute {mode}.
{mode_rules}
If the input already contains dialogue, keep those lines word for word; otherwise write the dialogue yourself.

Return ONLY JSON:
{{
 "title": "short title",
 "logline": "one sentence",
 "era_setting": "time + place in one sentence",
 "visual_style": "ONE paragraph style lock appended to every image prompt. Base it on: {style}",
 "tokens": [
   {{"key": "UPPERCASE 2-6 letters", "kind": "character|place|object|group", "name": "name",
     "look": "full fixed visual description ending with a comma (age, build, face, hair, exact clothing + colours)",
     "gender": "male|female|none", "age": "e.g. 30s / 8-year-old girl", "voice_hint": "e.g. warm deep calm male voice"}}
 ],
 "beats": [{{"b": 1, "location": "<PLACEKEY>", "characters": ["KEY"], "summary": "what happens in this beat"}}],
 "safety": "how sensitive moments are shown",
 "seo": {{"titles": ["4 YouTube titles under 70 chars"], "description": "150-250 word YouTube description", "tags": ["15 tags"], "hashtags": ["#3-6"]}},
 "thumbnails": [{{"concept": "name", "prompt": "16:9 thumbnail image prompt with space for text", "text": "2-4 words"}}]
}}
Use about {beats} beats. Every recurring character and place gets a token.

INPUT:
<<<
{script}
>>>"""

SHOTS_SYSTEM = """You break a screenplay into SHOTS for an AI image-to-video tool. Each shot is one clip of 3-10 seconds.
Rules:
- A shot with dialogue has exactly ONE speaker and ONE line of at most 20 words (about 7 seconds spoken).
- The speaker must be clearly visible facing roughly towards camera in that shot (medium or close shot of the speaker).
  For conversations use shot / reverse-shot: a new shot (continue=false) each time the speaker changes.
- "continue": true means the shot starts from the LAST FRAME of the previous shot (same place, same people, continuous
  action, same camera side). Use it when the same speaker keeps talking or the action flows on. The first shot of a beat
  is always continue=false.
- "image" (only when continue=false): 1-3 sentences describing the start frame; use <KEY> tokens for every character and
  place (the app inserts their locked description). Never describe style (added automatically).
- "action": one sentence of visible motion during the clip (gestures, expressions, camera-relevant movement).
- "camera": camera move/shot type in CAPS, e.g. "MEDIUM CLOSE-UP, SLOW PUSH-IN".
- "speaker": a character KEY, "NARRATOR" (off-screen voice over a silent shot), or "" for a silent shot.
- "delivery": how the line is spoken (emotion, volume, pace).
- "seconds": only for silent shots (3-8).
Return ONLY JSON: {"shots": [{"b": beat, "continue": false, "image": "...", "camera": "...", "action": "...",
 "speaker": "KEY", "line": "...", "delivery": "...", "seconds": 4}]}"""

SHOTS_TASK = """FILM: {title} - {logline}
Era/setting: {era}
Tokens:
{tokens}

ALL BEATS (for context):
{all_beats}

Write the shots for beats {numbers} only. Aim for {per_beat} shots per beat."""

MODE_RULES = {
    "dialogue": "It is a dialogue-driven movie: the story is told through what the characters say and do. "
                "Use a narrator only for at most 2-3 short bridging lines, if at all.",
    "both": "It is a narrated story with dialogue scenes: an off-screen NARRATOR carries the story between scenes, "
            "and the characters speak in the key moments (roughly half narrator lines, half character lines).",
}


def screenplay_prompt(script: str, story_type: str, minutes: float, preset: str) -> tuple[str, str]:
    style = STYLE_PRESETS.get(preset, STYLE_PRESETS["photoreal"])["style"]
    beats = max(3, min(24, round(minutes * 2.5)))
    kind = "script" if len(re.findall(r"\w+", script)) > 120 else "story idea"
    mode = "dialogue movie" if story_type == "dialogue" else "narrated story with dialogue scenes"
    return SCREENPLAY_SYSTEM, SCREENPLAY_TASK.format(kind=kind, minutes=minutes, mode=mode, beats=beats,
                                                      mode_rules=MODE_RULES.get(story_type, MODE_RULES["dialogue"]),
                                                      style=style, script=script)


def shots_prompt(a: dict, beat_nums: list[int], minutes: float) -> tuple[str, str]:
    toks = "\n".join(f"<{t['key']}> = {t['name']} ({t.get('kind', '')}): {t['look']}" for t in a.get("tokens", []))
    beats = a.get("beats", [])
    total_shots = max(6, round(minutes * 60 / 6.5))
    per_beat = max(2, round(total_shots / max(1, len(beats))))
    all_beats = "\n".join(f"{b['b']}. at {b.get('location', '')} with {', '.join(b.get('characters', []))}: {b.get('summary', '')}"
                          for b in beats)
    return SHOTS_SYSTEM, SHOTS_TASK.format(title=a.get("title", ""), logline=a.get("logline", ""), era=a.get("era_setting", ""),
                                           tokens=toks, all_beats=all_beats, numbers=", ".join(map(str, beat_nums)),
                                           per_beat=per_beat)


def normalise_beats(a: dict) -> dict:
    out = []
    for i, b in enumerate(a.get("beats") or []):
        try:
            n = int(b.get("b", i + 1))
        except (TypeError, ValueError):
            n = i + 1
        out.append({"b": n, "location": str(b.get("location", "")), "summary": str(b.get("summary", "")),
                    "characters": [re.sub(r"[^A-Z0-9_]", "", str(c).upper()) for c in (b.get("characters") or [])]})
    a["beats"] = out
    for t in a.get("tokens", []):
        t.setdefault("gender", "")
        t.setdefault("age", "")
        t.setdefault("voice_hint", "")
    return a


def parse_shots(text: str, keys: set[str]) -> list[dict]:
    data = _extract_json(text)
    if isinstance(data, dict):
        data = data.get("shots", [])
    shots = []
    for d in data:
        if not isinstance(d, dict):
            continue
        sp = re.sub(r"[^A-Z0-9_]", "", str(d.get("speaker", "")).upper().strip("<>"))
        if sp and sp != "NARRATOR" and sp not in keys:
            sp = "NARRATOR"
        line = re.sub(r"\s+", " ", str(d.get("line", "") or "")).strip().strip('"').strip()
        if not line:
            sp = ""
        try:
            b = int(d.get("b", 0))
        except (TypeError, ValueError):
            b = 0
        try:
            secs = int(round(float(d.get("seconds", 4) or 4)))
        except (TypeError, ValueError):
            secs = 4
        shots.append({"b": b, "continue": bool(d.get("continue")), "image": str(d.get("image", "") or "").strip(),
                      "camera": str(d.get("camera", "MEDIUM SHOT") or "MEDIUM SHOT").upper(),
                      "action": str(d.get("action", "") or "").strip(), "speaker": sp, "line": line,
                      "delivery": str(d.get("delivery", "") or "").strip(), "seconds": max(3, min(8, secs))})
    return shots


def split_long_lines(shots: list[dict], max_words: int = 22) -> list[dict]:
    """Lines that would run past the 10-second clip limit are split into two continuous shots."""
    out = []
    for s in shots:
        words = s.get("line", "").split()
        if len(words) <= max_words:
            out.append(s)
            continue
        text = s["line"]
        cut = None
        mid = len(text) / 2
        for m in re.finditer(r"[.!?;,:—–-]\s", text):
            if cut is None or abs(m.end() - mid) < abs(cut - mid):
                cut = m.end()
        if cut is None or cut < 15 or len(text) - cut < 15:
            cut = len(" ".join(words[: len(words) // 2])) + 1
        first, second = text[:cut].strip(), text[cut:].strip()
        out.append(dict(s, line=first))
        out.append(dict(s, line=second, **{"continue": True, "image": ""}))
    return split_long_lines(out, max_words) if any(len(x["line"].split()) > max_words for x in out) else out


def fix_continuity(shots: list[dict]) -> list[dict]:
    """A shot can only continue from a previous shot of the same beat that has a start image chain."""
    prev_b = None
    for i, s in enumerate(shots):
        if i == 0 or s["b"] != prev_b:
            s["continue"] = False
        if not s["continue"] and not s["image"]:
            s["image"] = s["action"] or "A cinematic shot of the scene."
        prev_b = s["b"]
    return shots


def to_scenes(shots: list[dict], a: dict) -> list[dict]:
    """Shots → the app's scene records (so the Scenes tab, render and assembly work for both modes)."""
    names = {t["key"]: t["name"] for t in a.get("tokens", [])}
    scenes = []
    for i, s in enumerate(shots, 1):
        who = "Narrator" if s["speaker"] == "NARRATOR" else names.get(s["speaker"], s["speaker"])
        text = f"{who}: “{s['line']}”" if s["line"] else f"(silent) {s['action']}"
        scenes.append({"n": i, "text": text, "beat": f"beat {s['b']}", "b": s["b"], "continue": s["continue"],
                       "image": s["image"], "ctx": "", "shots": [{"camera": s["camera"], "action": s["action"]}],
                       "speaker": s["speaker"], "line": s["line"], "delivery": s["delivery"], "seconds": s["seconds"],
                       "len": s["seconds"], "start": 0, "status": "pending", "tries": 0})
    return scenes


def time_scenes(scenes: list[dict]) -> None:
    """Clip length from the real voice length: line + a short breath, 3-10 s."""
    t = 0
    for sc in scenes:
        if sc.get("audio") and sc["audio"].get("dur_ms"):
            sc["len"] = max(3, min(10, math.ceil(sc["audio"]["dur_ms"] / 1000 + 0.6)))
        else:
            sc["len"] = max(3, min(8, int(sc.get("seconds", 4))))
        sc["start"] = t
        t += sc["len"]


def shot_video_prompt(sc: dict, a: dict, preset: str, expand, voice_mode: str) -> str:
    toks = {t["key"]: t["look"] for t in a.get("tokens", [])}
    tok = {t["key"]: t for t in a.get("tokens", [])}
    motion = STYLE_PRESETS.get(preset, STYLE_PRESETS["photoreal"])["motion"].strip()
    shot = (sc.get("shots") or [{}])[0]
    cam = shot.get("camera", "MEDIUM SHOT")
    act = expand(shot.get("action", ""), toks)
    sp = sc.get("speaker", "")
    no_text = " No subtitles, no captions, no on-screen text, logos or watermarks."
    if sp and sp != "NARRATOR":
        name = tok.get(sp, {}).get("name", sp)
        delivery = sc.get("delivery") or "naturally"
        if voice_mode == "ai":
            hint = tok.get(sp, {}).get("voice_hint", "")
            return (f"{cam}: {act} {name} says{(' in a ' + hint) if hint else ''}, {delivery}: \"{sc['line']}\" "
                    f"Only {name} speaks; clear dialogue audio with natural room tone, no music.{CLOTHING_LOCK}{no_text}")
        return (f"{cam}: {act} {name} speaks {delivery}, with natural lip movement, facial expressions and small "
                f"gestures; other people listen and react.{CLOTHING_LOCK} {motion}{no_text}")
    return (f"{cam}: {act}{CLOTHING_LOCK} {motion} Silent footage for separately added narration. "
            f"No dialogue, no speaking, no music.{no_text}")
