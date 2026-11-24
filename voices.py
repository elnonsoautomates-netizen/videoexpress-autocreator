"""VideoExpress Text-to-Speech voices (English, US) and automatic voice casting for characters.
The full list is refreshed from your account when you run the self-test; these are the defaults."""
from __future__ import annotations

# id -> display name (as listed in VideoExpress, Oct 2026)
VOICES: list[tuple[str, str, str]] = [  # (id, name, kind) kind: m=male, f=female, c=child
    ("en-US-AndrewMultilingualNeural", "Andrew Multilingual", "m"), ("en-US-GuyNeural", "Guy", "m"),
    ("en-US-DavisNeural", "Davis", "m"), ("en-US-JasonNeural", "Jason", "m"), ("en-US-TonyNeural", "Tony", "m"),
    ("en-US-BrianNeural", "Brian", "m"), ("en-US-ChristopherNeural", "Christopher", "m"), ("en-US-EricNeural", "Eric", "m"),
    ("en-US-SteffanNeural", "Steffan", "m"), ("en-US-RogerNeural", "Roger", "m"), ("en-US-BrandonNeural", "Brandon", "m"),
    ("en-US-JacobNeural", "Jacob", "m"), ("en-US-AndrewNeural", "Andrew", "m"), ("local:Voices/V1/Marcus.mp3", "Marcus", "m"),
    ("local:Voices/V1/Kofi.mp3", "Kofi", "m"), ("local:Voices/V1/Daniel.mp3", "Daniel", "m"), ("local:Voices/V1/George.mp3", "George", "m"),
    ("local:Voices/V1/William.mp3", "William", "m"), ("local:Voices/V1/Nathan.mp3", "Nathan", "m"), ("local:Voices/V1/Isaiah.mp3", "Isaiah", "m"),
    ("local:Voices/V1/Sizwe.mp3", "Sizwe", "m"), ("local:Voices/V1/Omar.mp3", "Omar", "m"), ("local:Voices/V1/Ethan.mp3", "Ethan", "m"),
    ("en-US-AriaNeural", "Aria", "f"), ("en-US-JennyNeural", "Jenny", "f"), ("en-US-JaneNeural", "Jane", "f"),
    ("en-US-NancyNeural", "Nancy", "f"), ("en-US-SaraNeural", "Sara", "f"), ("en-US-AvaNeural", "Ava", "f"),
    ("en-US-EmmaNeural", "Emma", "f"), ("en-US-MichelleNeural", "Michelle", "f"), ("en-US-MonicaNeural", "Monica", "f"),
    ("en-US-AshleyNeural", "Ashley", "f"), ("en-US-CoraNeural", "Cora", "f"), ("en-US-ElizabethNeural", "Elizabeth", "f"),
    ("en-US-AmberNeural", "Amber", "f"), ("local:Voices/V1/Grace.mp3", "Grace", "f"), ("local:Voices/V1/Hannah.mp3", "Hannah", "f"),
    ("local:Voices/V1/Amara.mp3", "Amara", "f"), ("local:Voices/V1/Zainab.mp3", "Zainab", "f"), ("local:Voices/V1/Tariro.mp3", "Tariro", "f"),
    ("local:Voices/V1/Lily.mp3", "Lily", "f"), ("local:Voices/V1/Sofia.mp3", "Sofia", "f"), ("local:Voices/V1/Claire.mp3", "Claire", "f"),
    ("en-US-AnaNeural", "Ana (child)", "c"),
]
VOICE_NAMES = {v: n.replace(" (child)", "") for v, n, _ in VOICES}


def cast_voices(tokens: list[dict], narrator: str, extra: list[list[str]] | None = None) -> None:
    """Give every speaking character a distinct voice that fits their gender/age (kept if already set)."""
    by_name = {n.lower(): v for v, n, _ in VOICES}
    used = {t.get("voice") for t in tokens if t.get("voice")} | {narrator, by_name.get(str(narrator).lower(), narrator)}
    pools = {k: [v for v, _, kind in VOICES if kind == k] for k in "mfc"}
    for t in tokens:
        if t.get("kind") not in ("character", "") or t.get("voice"):
            continue
        g = str(t.get("gender", "")).lower()
        age = str(t.get("age", "")).lower()
        k = "c" if ("child" in g or "child" in age or "boy" in age or "girl" in age) else ("f" if g.startswith("f") or "woman" in g else "m")
        pool = [v for v in pools[k] if v not in used] or [v for v in pools["m" if k == "c" else k] if v not in used] or pools[k]
        t["voice"] = pool[0]
        used.add(pool[0])


def voice_choices(cached: list[list[str]] | None) -> list[dict]:
    """Voices for the Characters tab: curated ones first, then everything the account offers."""
    out, seen = [], set()
    for v, n, kind in VOICES:
        out.append({"id": v, "name": n, "kind": {"m": "male", "f": "female", "c": "child"}[kind]})
        seen.add(v)
    for v, n in cached or []:
        if v not in seen:
            out.append({"id": v, "name": n, "kind": ""})
            seen.add(v)
    return out


def voice_name_of(v: str) -> str:
    return VOICE_NAMES.get(v, v or "default")
