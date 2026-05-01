"""
modules/tts_number_normalize.py
=================================
Expand Arabic numerals in narration to spoken words in the pipeline language
so TTS (OmniVoice, Edge, etc.) reads years and counts naturally.

Uses: num2words (en, te, bn, kn, …), Open-Tamil (ta), Devanagari rules (hi, mr),
      English words as fallback for unsupported scripts (e.g. gu).
"""

from __future__ import annotations

import re
from functools import lru_cache

from config import get_logger

log = get_logger("tts_numbers")

# Hindi / Marathi (Devanagari) cardinals 0–99 — shared convention for TTS
_H: tuple[str, ...] = (
    "शून्य",
    "एक",
    "दो",
    "तीन",
    "चार",
    "पाँच",
    "छह",
    "सात",
    "आठ",
    "नौ",
    "दस",
    "ग्यारह",
    "बारह",
    "तेरह",
    "चौदह",
    "पंद्रह",
    "सोलह",
    "सत्रह",
    "अठारह",
    "उन्नीस",
    "बीस",
    "इक्कीस",
    "बाईस",
    "तेईस",
    "चौबीस",
    "पच्चीस",
    "छब्बीस",
    "सत्ताईस",
    "अट्ठाईस",
    "उनतीस",
    "तीस",
    "इकतीस",
    "बत्तीस",
    "तैंतीस",
    "चौंतीस",
    "पैंतीस",
    "छत्तीस",
    "सैंतीस",
    "अड़तीस",
    "उनतालीस",
    "चालीस",
    "इकतालीस",
    "बयालीस",
    "तैतालीस",
    "चौवालीस",
    "पैंतालीस",
    "छियालीस",
    "सैंतालीस",
    "अड़तालीस",
    "उनचास",
    "पचास",
    "इक्यावन",
    "बावन",
    "तिरपन",
    "चौवन",
    "पचपन",
    "छप्पन",
    "सत्तावन",
    "अट्ठावन",
    "उनसठ",
    "साठ",
    "इकसठ",
    "बासठ",
    "तिरसठ",
    "चौंसठ",
    "पैंसठ",
    "छियासठ",
    "सड़सठ",
    "अड़सठ",
    "उनहत्तर",
    "सत्तर",
    "इकहत्तर",
    "बहत्तर",
    "तिहत्तर",
    "चौहत्तर",
    "पचहत्तर",
    "छिहत्तर",
    "सतहत्तर",
    "अठहत्तर",
    "उन्नासी",
    "अस्सी",
    "इक्यासी",
    "बयासी",
    "तिरासी",
    "चौरासी",
    "पचासी",
    "छियासी",
    "सतासी",
    "अट्ठासी",
    "नवासी",
    "नब्बे",
    "इक्यानवे",
    "बानवे",
    "तिरानवे",
    "चौरानवे",
    "पचानवे",
    "छियानवे",
    "सतानवे",
    "अट्ठानवे",
    "निन्यानवे",
)

assert len(_H) == 100


def _devanagari_indian_cardinal(n: int) -> str:
    """Cardinal n in Hindi-style Devanagari (Indian grouping: हज़ार, लाख, करोड़)."""
    if n < 0:
        return "ऋण " + _devanagari_indian_cardinal(-n)
    if n < 100:
        return _H[n]
    parts: list[str] = []
    if n >= 10_000_000:
        c, n = divmod(n, 10_000_000)
        parts.append(_devanagari_indian_cardinal(c).strip() + " करोड़")
    if n >= 100_000:
        l, n = divmod(n, 100_000)
        if l:
            parts.append(_devanagari_indian_cardinal(l).strip() + " लाख")
    if n >= 1000:
        t, n = divmod(n, 1000)
        if t:
            parts.append(_devanagari_indian_cardinal(t).strip() + " हज़ार")
    if n >= 100:
        h, n = divmod(n, 100)
        if h:
            parts.append(_H[h] + " सौ")
    if n:
        parts.append(_H[n])
    return " ".join(parts)


@lru_cache(maxsize=32)
def _num2words_mod():
    try:
        from num2words import num2words as _nw
        return _nw
    except ImportError:
        log.warning("num2words not installed — number expansion falls back to digits for some languages. pip install num2words")
        return None


@lru_cache(maxsize=4)
def _tamil_num2str():
    try:
        from tamil.numeral import num2tamilstr
        return num2tamilstr
    except ImportError:
        log.warning("open-tamil not installed — Tamil numbers use English words. pip install open-tamil")
        return None


def _int_to_words_lang(n: int, lang: str) -> str:
    """Spoken integer in target convention for TTS."""
    lang = (lang or "hi").lower().strip()
    nw = _num2words_mod()

    if lang in ("hi", "mr"):
        return _devanagari_indian_cardinal(int(n))
    if lang == "ta":
        fn = _tamil_num2str()
        if fn is not None:
            try:
                return str(fn(int(n)))
            except Exception as exc:
                log.debug("Tamil num2str failed %s: %s", n, exc)
        if nw is not None:
            return nw(int(n), lang="en")
        return str(n)
    if lang == "te" and nw is not None:
        try:
            return nw(int(n), lang="te")
        except Exception:
            pass
    if lang == "bn" and nw is not None:
        try:
            return nw(int(n), lang="bn")
        except Exception:
            pass
    if lang == "kn" and nw is not None:
        try:
            return nw(int(n), lang="kn")
        except Exception:
            pass
    if lang in ("en", "hinglish"):
        if nw is not None:
            return nw(int(n), lang="en")
        return str(n)
    if lang == "gu" and nw is not None:
        try:
            return nw(int(n), lang="en")
        except Exception:
            pass
    if lang == "or" and nw is not None:
        # num2words has no Odia converter — English words, still better for TTS than digits
        try:
            return nw(int(n), lang="en")
        except Exception:
            pass
    if nw is not None:
        try:
            return nw(int(n), lang="en")
        except Exception:
            pass
    return str(n)


def _decimal_to_words(s: str, lang: str) -> str:
    """Expand 3.14 etc. for TTS."""
    if "." not in s:
        return _int_to_words_lang(int(s), lang)
    whole, frac = s.split(".", 1)
    frac = re.sub(r"\D", "", frac)
    if not frac:
        return _int_to_words_lang(int(whole or 0), lang)
    lang = (lang or "hi").lower().strip()
    wpart = _int_to_words_lang(int(whole or 0), lang)
    if lang in ("hi", "mr"):
        sep = " दशमलव "
        fdigs = " ".join(_H[int(c)] for c in frac if c.isdigit())
        return wpart + sep + fdigs
    if lang == "ta":
        sep = " புள்ளி "
        fn = _tamil_num2str()
        nx = _num2words_mod()
        parts_d: list[str] = []
        for c in frac:
            if not c.isdigit():
                continue
            if fn is not None:
                try:
                    parts_d.append(str(fn(int(c))))
                    continue
                except Exception:
                    pass
            if nx is not None:
                parts_d.append(nx(int(c), lang="en"))
            else:
                parts_d.append(c)
        fdigs = " ".join(parts_d)
        return wpart + sep + fdigs
    nx = _num2words_mod()
    if nx is not None:
        fdigs = " ".join(nx(int(c), lang="en") for c in frac if c.isdigit())
        return f"{wpart} point {fdigs}"
    return s


def expand_numbers_in_text(text: str | None, lang: str | None) -> str:
    """
    Replace standalone Arabic numerals and simple decimals with spoken words.
    Conservative: only digits on word boundaries; strips thousand commas first.
    """
    if not text:
        return text or ""
    s = str(text)
    lang = (lang or "hi").lower().strip()

    # Remove thousand separators inside numbers
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"(?<=\d),(?=\d)", "", s)

    def repl_dec(m: re.Match) -> str:
        try:
            return _decimal_to_words(m.group(0), lang)
        except Exception:
            return m.group(0)

    # Decimals before integers so 3.14 doesn't become 3 + .14
    s = re.sub(r"\b\d+\.\d+\b", repl_dec, s)

    def repl_int(m: re.Match) -> str:
        raw = m.group(0)
        try:
            n = int(raw)
        except ValueError:
            return raw
        if n < 0:
            return raw
        try:
            return _int_to_words_lang(n, lang)
        except Exception:
            return raw

    s = re.sub(r"\b\d{1,12}\b", repl_int, s)
    return s


def normalize_documentary_script_numbers(script: dict, lang: str | None) -> dict:
    """Expand numerals in each segment voiceover, then re-stitch voiceover_text."""
    if not script:
        return script
    lang = (lang or "hi").lower().strip()
    for seg in script.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        svo = seg.get("voiceover")
        if svo:
            seg["voiceover"] = expand_numbers_in_text(str(svo), lang)
    segs = script.get("segments") or []
    if segs:
        script["voiceover_text"] = " ".join(
            str(s.get("voiceover", "")).strip() for s in segs if s.get("voiceover")
        )
    elif script.get("voiceover_text"):
        script["voiceover_text"] = expand_numbers_in_text(script["voiceover_text"], lang)
    return script
