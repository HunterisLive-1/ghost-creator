import type { TimelineAction, TimelineEffect, TimelineRow } from "@keplar-404/react-timeline-editor";
import { getApiBaseUrl } from "../api/client";
import type {
  ClipAsset,
  EditorAsset,
  EditorJson,
  EditorTimelineItem,
  EditorTrack,
  EditorTrackType,
  SegmentActionData,
} from "./types";
import {
  AUDIO_EFFECT_ID,
  DEFAULT_OVERLAY_TRANSFORM,
  OVERLAY_EFFECT_ID,
  SUBTITLE_EFFECT_ID,
  VIDEO_EFFECT_ID,
} from "./types";

export function clipMediaUrl(path: string): string {
  const normalizedPath = path.replace(/\\/g, "/");
  return `${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(normalizedPath)}`;
}

export function defaultClipName(index: number): string {
  return `e_${String(index).padStart(2, "0")}.mp4`;
}

export function makeEditorId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function resolveClipForSegment(
  seg: { clip_name?: string },
  index: number,
  clips: ClipAsset[]
): ClipAsset | undefined {
  const editPool = clips.filter(
    (c) => c.category === "clips_for_edit" || c.category === "edit" || c.role === "edit"
  );
  const pool = editPool.length > 0 ? editPool : clips;
  const byName = seg.clip_name ? pool.find((c) => c.name === seg.clip_name) : undefined;
  if (byName) return byName;
  if (index >= 0 && index < pool.length) return pool[index];
  return pool.find((c) => c.name === seg.clip_name);
}

function clipToAsset(c: ClipAsset, type: EditorAsset["type"] = "video"): EditorAsset {
  return {
    id: `asset-${type}-${c.name.replace(/[^a-z0-9_-]/gi, "_")}`,
    type,
    name: c.name,
    path: c.path,
    category: c.category,
    role: c.role,
    size_mb: c.size_mb,
  };
}

export function defaultEditorTracks(): EditorTrack[] {
  return [
    { id: "video-main", type: "video", name: "Main Video" },
    { id: "overlay-1", type: "overlay", name: "Overlays" },
    { id: "audio-voice", type: "audio", name: "Voiceover" },
    { id: "music-1", type: "music", name: "Music" },
    { id: "subtitle-1", type: "subtitle", name: "Subtitles" },
  ];
}

export function ensureV2EditorJson(data: EditorJson, editClips: ClipAsset[], stockClips: ClipAsset[] = []): EditorJson {
  const existingAssets = data.assets ?? [];
  const generatedAssets = [...editClips, ...stockClips].map((c) => clipToAsset(c));
  const assetsById = new Map<string, EditorAsset>();
  [...generatedAssets, ...existingAssets].forEach((asset) => assetsById.set(asset.id, asset));
  const assets = [...assetsById.values()];

  if (data.schema_version && data.schema_version >= 2 && data.tracks?.length && data.items) {
    return {
      ...data,
      assets,
      tracks: data.tracks,
      items: data.items,
      timeline_settings: { snap: true, zoom: 80, fps: 30, ...(data.timeline_settings ?? {}) },
    };
  }

  const tracks = defaultEditorTracks();
  let cursor = 0;
  const items: EditorTimelineItem[] = (data.segments || []).map((seg, idx) => {
    const dur = Math.max(0.5, seg.duration_hint || 5);
    const clipName = seg.clip_name || defaultClipName(idx);
    const clip = resolveClipForSegment({ clip_name: clipName }, idx, editClips);
    const asset = clip ? clipToAsset(clip) : undefined;
    const item: EditorTimelineItem = {
      id: `seg-${idx}`,
      trackId: "video-main",
      kind: "video",
      start: cursor,
      end: cursor + dur,
      assetId: asset?.id,
      sourceStart: 0,
      sourceEnd: dur,
      voiceover: seg.voiceover,
      video_query: seg.video_query,
      transition: seg.transition,
      effect: seg.effect,
      segmentIndex: idx,
    };
    cursor += dur;
    return item;
  });

  return {
    ...data,
    schema_version: 2,
    assets,
    tracks,
    items,
    timeline_settings: { snap: true, zoom: 80, fps: 30, ...(data.timeline_settings ?? {}) },
  };
}

function effectIdForItem(item: EditorTimelineItem): string {
  if (item.kind === "audio" || item.kind === "music") return AUDIO_EFFECT_ID;
  if (item.kind === "text" || item.kind === "image" || item.kind === "logo") return OVERLAY_EFFECT_ID;
  if (item.kind === "subtitle") return SUBTITLE_EFFECT_ID;
  return VIDEO_EFFECT_ID;
}

export function editorJsonToTimeline(
  data: EditorJson,
  clips: ClipAsset[] = []
): { editorData: TimelineRow[]; effects: Record<string, TimelineEffect>; totalDuration: number } {
  const v2 = ensureV2EditorJson(data, clips);
  const assetsById = new Map((v2.assets ?? []).map((a) => [a.id, a]));
  const rows: TimelineRow[] = (v2.tracks ?? defaultEditorTracks()).map((track) => ({
    id: track.id,
    actions: (v2.items ?? [])
      .filter((item) => item.trackId === track.id)
      .map((item) => {
        const asset = item.assetId ? assetsById.get(item.assetId) : undefined;
        const data: SegmentActionData = {
          itemId: item.id,
          trackId: item.trackId,
          kind: item.kind,
          segmentIndex: item.segmentIndex,
          clipName: asset?.name,
          mediaUrl: asset ? clipMediaUrl(asset.path) : undefined,
          transition: item.transition,
          effect: item.effect,
          voiceover: item.voiceover,
          text: item.text,
        };
        return {
          id: item.id,
          start: Math.max(0, item.start),
          end: Math.max(item.start + 0.1, item.end),
          effectId: effectIdForItem(item),
          flexible: !item.locked,
          movable: !item.locked,
          data,
        } satisfies TimelineAction;
      }),
  }));
  const totalDuration = Math.max(0, ...(v2.items ?? []).map((item) => item.end));

  return {
    editorData: rows,
    effects: {
      [VIDEO_EFFECT_ID]: { id: VIDEO_EFFECT_ID, name: "Video" },
      [AUDIO_EFFECT_ID]: { id: AUDIO_EFFECT_ID, name: "Audio" },
      [OVERLAY_EFFECT_ID]: { id: OVERLAY_EFFECT_ID, name: "Overlay" },
      [SUBTITLE_EFFECT_ID]: { id: SUBTITLE_EFFECT_ID, name: "Subtitle" },
    },
    totalDuration,
  };
}

function trackTypeFromId(trackId: string, tracks: EditorTrack[]): EditorTrackType {
  return tracks.find((track) => track.id === trackId)?.type ?? "video";
}

export function timelineToEditorJson(timeline: TimelineRow[], base: EditorJson): EditorJson {
  const v2 = ensureV2EditorJson(base, []);
  const existing = new Map((v2.items ?? []).map((item) => [item.id, item]));
  const tracks = v2.tracks ?? defaultEditorTracks();
  const items: EditorTimelineItem[] = timeline.flatMap((row) =>
    [...row.actions].sort((a, b) => a.start - b.start).map((action, orderIdx) => {
      const data = (action.data ?? {}) as Partial<SegmentActionData>;
      const previous = existing.get(action.id);
      const type = trackTypeFromId(row.id, tracks);
      const fallbackKind = type === "music" ? "music" : type === "audio" ? "audio" : type === "overlay" ? "text" : type;
      return {
        ...(previous ?? {
          id: action.id,
          kind: fallbackKind,
          trackId: row.id,
          start: action.start,
          end: action.end,
          transform: fallbackKind === "text" ? DEFAULT_OVERLAY_TRANSFORM : undefined,
        }),
        id: action.id,
        trackId: row.id,
        start: Math.max(0, action.start),
        end: Math.max(action.start + 0.1, action.end),
        segmentIndex: data.segmentIndex ?? previous?.segmentIndex ?? orderIdx,
      };
    })
  );

  const mainTrack = tracks.find((t) => t.type === "video")?.id ?? "video-main";
  const assetsById = new Map((v2.assets ?? []).map((a) => [a.id, a]));
  const segments = items
    .filter((item) => item.trackId === mainTrack && item.kind === "video")
    .sort((a, b) => a.start - b.start)
    .map((item, idx) => {
      const prevSeg = base.segments[item.segmentIndex ?? idx] ?? base.segments[idx] ?? {
        voiceover: item.voiceover ?? "",
        video_query: item.video_query ?? "",
        duration_hint: 5,
      };
      const asset = item.assetId ? assetsById.get(item.assetId) : undefined;
      return {
        ...prevSeg,
        voiceover: item.voiceover ?? prevSeg.voiceover ?? "",
        video_query: item.video_query ?? prevSeg.video_query ?? "",
        duration_hint: Math.round(Math.max(0.5, item.end - item.start) * 10) / 10,
        clip_name: asset?.name || prevSeg.clip_name || defaultClipName(idx),
        transition: item.transition ?? prevSeg.transition,
        effect: item.effect ?? prevSeg.effect,
      };
    });

  return { ...v2, items, tracks, segments };
}

export function normalizeEditorJson(raw: EditorJson, clips: ClipAsset[], stockClips: ClipAsset[] = []): EditorJson {
  const segments = (raw.segments || []).map((seg, idx) => ({
    ...seg,
    clip_name: seg.clip_name || clips[idx]?.name || defaultClipName(idx),
    duration_hint: seg.duration_hint || 5,
  }));
  return ensureV2EditorJson(
    {
      ...raw,
      segments,
      subtitle_style: raw.subtitle_style,
      burn_subtitles: raw.burn_subtitles,
      bg_music_volume: raw.bg_music_volume ?? 0.25,
    },
    clips,
    stockClips
  );
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
  const v2 = ensureV2EditorJson(base, clips);
  const { editorData } = editorJsonToTimeline(v2, clips);
  const round = timelineToEditorJson(editorData, v2);
  return (
    round.schema_version === 2 &&
    round.segments.length === 2 &&
    round.segments[0].duration_hint === 3 &&
    round.segments[1].duration_hint === 4 &&
    round.segments[0].transition === "Cross Dissolve" &&
    round.segments[1].effect === "B&W Film"
  );
}
