import { theme } from "../theme/tokens";

interface Props {
  ttsBackend: string;
}

export function StatusBar({ ttsBackend }: Props) {
  return (
    <>
      <div style={{ height: 2, background: theme.border }} />
      <footer
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          height: 30,
          padding: "0 20px",
          background: theme.bgMain,
          fontSize: 11,
          fontFamily: "monospace",
        }}
      >
        <span style={{ color: theme.textSec }}>NEURAL CORE: HunterIsLive</span>
        <span style={{ color: theme.accentPri }}>AUDIO_SUBROUTINE: [{ttsBackend}]</span>
      </footer>
    </>
  );
}
