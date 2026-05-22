export const theme = {
  bgMain: "#050A10",
  bgSec: "#0A121A",
  bgCard: "#0F1A24",
  border: "#1A2B3D",
  accentPri: "#0088FF",
  accentSec: "#00BFFF",
  accentRed: "#FF4444",
  accentWarn: "#FFB800",
  accentGrn: "#00CC66",
  textPri: "#E6F0FF",
  textSec: "#88AADD",
  textHint: "#4A6080",
} as const;

export type SystemState = "READY" | "PROCESSING" | "ERROR";

export const stateColors: Record<SystemState, string> = {
  READY: theme.accentSec,
  PROCESSING: theme.accentWarn,
  ERROR: theme.accentRed,
};
