import type { TimelineAction, TimelineEffect, TimelineRow } from "@keplar-404/react-timeline-editor";
import { getApiBaseUrl } from "../api/client";
import type { ClipAsset, EditorJson, SegmentActionData } from "./types";
import { VIDEO_EFFECT_ID } from "./types";

export function clipMediaUrl(path: string): string {
  return `${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(path)}`;
}

export function defaultClipName(index: number): string {
  return `e_${String(index).padStart(2, "0")}.mp4`;
}

export function resolveClipForSegment(
  seg: { clip_name?: string },
  index: number,
  clips: ClipAsset[]
): ClipAsset | undefined {
  const byName = seg.clip_name ? clips.find((c) => c.name === seg.clip_name) : undefined;
  return byName ?? clips[index];
}

export function editorJsonToTimeline(
  data: EditorJson,
  clips: ClipAsset[]
): { editorData: TimelineRow[]; effects: Record<string, TimelineEffect>; totalDuration: number } {
  let cursor = 0;
  const actions: TimelineAction[] = [];

  data.segments.forEach((seg, idx) => {
    const dur = Math.max(0.5, seg.duration_hint || 5);
    const clipName = seg.clip_name || defaultClipName(idx);
    const clip = resolveClipForSegment({ clip_name: clipName }, idx, clips);
    const actionData: SegmentActionData = {
      segmentIndex: idx,
      clipName,
      mediaUrl: clip ? clipMediaUrl(clip.path) : "",
      transition: seg.transition,
      effect: seg.effect,
      voiceover: seg.voiceover,
    };
    actions.push({
      id: `seg-${idx}`,
      start: cursor,
      end: cursor + dur,
      effectId: VIDEO_EFFECT_ID,
      flexible: true,
      movable: true,
      data: actionData,
    });
    cursor += dur;
  });

  return {
    editorData: [{ id: "video-track", actions }],
    effects: {
      [VIDEO_EFFECT_ID]: { id: VIDEO_EFFECT_ID, name: "Video Clip" },
    },
    totalDuration: cursor,
  };
}

export function timelineToEditorJson(timeline: TimelineRow[], base: EditorJson): EditorJson {
  const videoRow = timeline.find((r) => r.id === "video-track") ?? timeline[0];
  if (!videoRow) return base;

  const sorted = [...videoRow.actions].sort((a, b) => a.start - b.start);
  const segments = sorted.map((action, orderIdx) => {
    const data = (action.data ?? {}) as Partial<SegmentActionData>;
    const srcIdx = typeof data.segmentIndex === "number" ? data.segmentIndex : orderIdx;
    const prevSeg = base.segments[srcIdx] ?? base.segments[orderIdx] ?? {
      voiceover: "",
      video_query: "",
      duration_hint: 5,
    };
    const dur = Math.max(0.5, action.end - action.start);
    return {
      ...prevSeg,
      duration_hint: Math.round(dur * 10) / 10,
      clip_name: data.clipName || prevSeg.clip_name || defaultClipName(orderIdx),
      transition: data.transition ?? prevSeg.transition,
      effect: data.effect ?? prevSeg.effect,
    };
  });

  return { ...base, segments };
}

export function normalizeEditorJson(raw: EditorJson, clips: ClipAsset[]): EditorJson {
  const segments = (raw.segments || []).map((seg, idx) => ({
    ...seg,
    clip_name: seg.clip_name || clips[idx]?.name || defaultClipName(idx),
    duration_hint: seg.duration_hint || 5,
  }));
  return {
    ...raw,
    segments,
    subtitle_style: raw.subtitle_style,
    burn_subtitles: raw.burn_subtitles,
    bg_music_volume: raw.bg_music_volume ?? 0.25,
  };
}

/** Lightweight round-trip self-check for smoke tests. */
export function adapterSelfTest(): boolean {
  const base: EditorJson = {
    title: "Test",
    voiceover_text: "Hello world",
    language: "en",
    aspect_ratio: "9:16",
    segments: [
      { voiceover: "A", video_query: "q1", duration_hint: 3, clip_name: "e_00.mp4", transition: "Cross Dissolve" },
      { voiceover: "B", video_query: "q2", duration_hint: 4, clip_name: "e_01.mp4", effect: "B&W Film" },
    ],
  };
  const clips: ClipAsset[] = [
    { name: "e_00.mp4", path: "C:/runs/e_00.mp4", category: "edit", size_mb: 1 },
    { name: "e_01.mp4", path: "C:/runs/e_01.mp4", category: "edit", size_mb: 1 },
  ];
  const { editorData } = editorJsonToTimeline(base, clips);
  const round = timelineToEditorJson(editorData, base);
  return (
    round.segments.length === 2 &&
    round.segments[0].duration_hint === 3 &&
    round.segments[1].duration_hint === 4 &&
    round.segments[0].transition === "Cross Dissolve" &&
    round.segments[1].effect === "B&W Film"
  );
}
