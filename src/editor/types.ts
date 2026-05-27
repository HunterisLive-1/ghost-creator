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
  title: string;
  voiceover_text: string;
  segments: EditorSegment[];
  language: string;
  aspect_ratio: string;
  subtitle_style?: SubtitleStyle;
  bg_music?: string;
  bg_music_volume?: number;
}

export interface ClipAsset {
  name: string;
  path: string;
  category: string;
  size_mb: number;
}

export interface SegmentActionData {
  segmentIndex: number;
  clipName: string;
  mediaUrl: string;
  transition?: string;
  effect?: string;
  voiceover: string;
}

export const VIDEO_EFFECT_ID = "ghost-video-clip";

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
