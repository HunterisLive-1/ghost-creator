export const theme = {
  bgMain: "#050209",
  bgSec: "#0C0616",
  bgCard: "#120921",
  border: "#251442",
  accentPri: "#BF00FF",
  accentSec: "#D400FF",
  accentRed: "#FF4444",
  accentWarn: "#FFB800",
  accentGrn: "#00CC66",
  textPri: "#F5F0FF",
  textSec: "#BCA2E8",
  textHint: "#6E5A8E",
} as const;

export type SystemState = "READY" | "PROCESSING" | "ERROR";

export const stateColors: Record<SystemState, string> = {
  READY: theme.accentSec,
  PROCESSING: theme.accentWarn,
  ERROR: theme.accentRed,
};
