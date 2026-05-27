"""FFmpeg filter helpers for editor segment transition/effect presets."""

from __future__ import annotations

# Editor UI preset names → internal keys
_TRANSITION_MAP = {
    "cross dissolve": "xfade",
    "dissolve": "xfade",
    "fade": "xfade",
    "fade to black": "fade_out",
    "zoom blur": "xfade",
    "whip pan": "xfade",
}

_EFFECT_MAP = {
    "b&w film": "grayscale",
    "grayscale": "grayscale",
    "cinematic grain": "grain",
    "dream blur": "blur",
    "retro glow": "grain",
    "vhs overlay": "grain",
}


def normalize_transition(name: str | None) -> str | None:
    if not name:
        return None
    return _TRANSITION_MAP.get(str(name).strip().lower())


def normalize_effect(name: str | None) -> str | None:
    if not name:
        return None
    return _EFFECT_MAP.get(str(name).strip().lower())


def append_effect_to_vf(base_vf: str, effect: str | None) -> str:
    """Append per-segment visual effect filters to the scale vf chain."""
    key = normalize_effect(effect)
    if not key:
        return base_vf
    if key == "grayscale":
        return f"{base_vf},format=gray"
    if key == "grain":
        return f"{base_vf},noise=alls=20:allf=t+u"
    if key == "blur":
        return f"{base_vf},boxblur=2:1"
    return base_vf


def append_fade_out_to_vf(vf: str, duration: float, fade_sec: float = 0.5) -> str:
    """Fade clip to black at tail (Fade to Black transition on incoming segment)."""
    fade = min(max(0.2, fade_sec), max(0.2, duration * 0.4))
    start = max(0.0, duration - fade)
    return f"{vf},fade=t=out:st={start:.3f}:d={fade:.3f}"


def segment_trim_vf(
    base_vf: str,
    duration: float,
    effect: str | None,
    transition: str | None,
) -> str:
    """
    Build vf for trimming one segment: scale + optional effect + optional fade-out.
    ``transition`` on segment i is applied to clip i when it is a fade-to-black.
    Cross-dissolve is handled at concat time (segment i > 0).
    """
    vf = append_effect_to_vf(base_vf, effect)
    if normalize_transition(transition) == "fade_out":
        vf = append_fade_out_to_vf(vf, duration)
    return vf


def xfade_transition_name(transition: str | None) -> str:
    """Map editor transition label to ffmpeg xfade transition name."""
    key = normalize_transition(transition)
    if key == "xfade":
        return "fade"
    return "fade"


def build_xfade_filter_complex(
    input_count: int,
    durations: list[float],
    segments: list[dict],
    xfade_dur: float = 0.5,
) -> tuple[str, str]:
    """
    Build filter_complex for chained xfade between consecutive clips.
    ``segments[i].transition`` (i > 0) controls dissolve into clip i.
    Returns (filter_complex, output_video_label).
    """
    if input_count < 2:
        return "", "[0:v]"

    parts: list[str] = []
    prev_label = "[0:v]"
    offset = durations[0] - xfade_dur

    for i in range(1, input_count):
        trans = segments[i].get("transition") if i < len(segments) else None
        tname = xfade_transition_name(trans)
        out_label = f"[v{i}]"
        parts.append(
            f"{prev_label}[{i}:v]xfade=transition={tname}:duration={xfade_dur:.3f}:offset={max(0.0, offset):.3f}{out_label}"
        )
        prev_label = out_label
        if i < len(durations):
            offset += durations[i] - xfade_dur

    return ";".join(parts), prev_label


def any_xfade_transitions(segments: list[dict]) -> bool:
    """True when at least one segment (index > 0) uses a cross-dissolve style transition."""
    for i, seg in enumerate(segments):
        if i == 0:
            continue
        if normalize_transition(seg.get("transition")) == "xfade":
            return True
    return False
