export interface EditorSegment {
  voiceover: string;
  video_query: string;
  duration_hint: number;
  clip_name?: string;
  transition?: string;
  effect?: string;
}

export interface SubtitleStyle {
  font_size: number;
  color: string;
  bg_color: string;
  bold: boolean;
  italic: boolean;
  font_family: string;
}

export interface EditorJson {
  schema_version?: number;
  title: string;
  voiceover_text: string;
  segments: EditorSegment[];
  language: string;
  aspect_ratio: string;
  subtitle_style?: SubtitleStyle;
  burn_subtitles?: boolean;
  bg_music?: string;
  bg_music_volume?: number;
  assets?: EditorAsset[];
  tracks?: EditorTrack[];
  items?: EditorTimelineItem[];
  timeline_settings?: EditorTimelineSettings;
}

export interface ClipAsset {
  name: string;
  path: string;
  category: string;
  role?: string;
  size_mb: number;
}

export interface SegmentActionData {
  itemId: string;
  trackId: string;
  kind: EditorItemKind;
  segmentIndex?: number;
  clipName?: string;
  mediaUrl?: string;
  transition?: string;
  effect?: string;
  voiceover?: string;
  text?: string;
}

export const VIDEO_EFFECT_ID = "ghost-video-clip";
export const AUDIO_EFFECT_ID = "ghost-audio";
export const OVERLAY_EFFECT_ID = "ghost-overlay";
export const SUBTITLE_EFFECT_ID = "ghost-subtitle";

export type EditorAssetType = "video" | "audio" | "image";
export type EditorTrackType = "video" | "overlay" | "audio" | "music" | "subtitle";
export type EditorItemKind = "video" | "audio" | "music" | "text" | "image" | "logo" | "subtitle";

export interface EditorAsset {
  id: string;
  type: EditorAssetType;
  name: string;
  path: string;
  category: string;
  role?: string;
  size_mb?: number;
}

export interface EditorTrack {
  id: string;
  type: EditorTrackType;
  name: string;
  muted?: boolean;
  locked?: boolean;
}

export interface EditorTransform {
  x: number;
  y: number;
  scale: number;
  opacity: number;
  rotation: number;
}

export interface EditorKeyframe {
  time: number;
  transform: Partial<EditorTransform>;
}

export interface EditorTimelineItem {
  id: string;
  trackId: string;
  kind: EditorItemKind;
  start: number;
  end: number;
  assetId?: string;
  sourceStart?: number;
  sourceEnd?: number;
  text?: string;
  style?: Partial<SubtitleStyle> & { font_size?: number };
  transform?: EditorTransform;
  keyframes?: EditorKeyframe[];
  volume?: number;
  muted?: boolean;
  locked?: boolean;
  transition?: string;
  effect?: string;
  voiceover?: string;
  video_query?: string;
  segmentIndex?: number;
}

export interface EditorTimelineSettings {
  snap: boolean;
  zoom: number;
  fps: number;
}

export const TRANSITION_PRESETS = [
  "Cross Dissolve",
  "Fade to Black",
  "Dissolve",
  "Zoom Blur",
  "Whip Pan",
] as const;

export const EFFECT_PRESETS = [
  "B&W Film",
  "Cinematic Grain",
  "Dream Blur",
  "Retro Glow",
  "VHS Overlay",
] as const;

export const DEFAULT_SUBTITLE_STYLE: SubtitleStyle = {
  font_size: 28,
  color: "#FFFFFF",
  bg_color: "#80000000",
  bold: true,
  italic: false,
  font_family: "Nirmala UI",
};

export const DEFAULT_OVERLAY_TRANSFORM: EditorTransform = {
  x: 0.5,
  y: 0.5,
  scale: 1,
  opacity: 1,
  rotation: 0,
};
