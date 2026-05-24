import { useState } from "react";
import { createPortal } from "react-dom";
import { ScriptReviewData } from "../api/client";
import { theme } from "../theme/tokens";

interface Props {
  data: ScriptReviewData;
  onApprove: (data: ScriptReviewData) => void;
  onRegenerate: () => void;
  onCancel: () => void;
}

export function ScriptReviewModal({ data, onApprove, onRegenerate, onCancel }: Props) {
  const [title, setTitle] = useState(data?.title || "");
  const [voiceover, setVoiceover] = useState(data?.voiceover || "");
  const [prompts, setPrompts] = useState<string[]>(data?.image_prompts ? [...data.image_prompts] : []);

  const wordCount = (voiceover || "").trim().split(/\s+/).filter(Boolean).length;

  return createPortal(
    <div style={styles.overlay}>
      <div style={styles.modal}>
        <h2 style={{ color: theme.accentPri }}>📝 Script Review — Step 2 of 6</h2>
        <p style={{ color: theme.textHint, fontSize: 12, marginBottom: 12 }}>
          Review and edit the script before voice synthesis begins.
        </p>

        <label style={styles.label}>Title</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: "100%", marginBottom: 12 }} />

        <label style={styles.label}>Voiceover ({wordCount} words)</label>
        <textarea
          value={voiceover}
          onChange={(e) => setVoiceover(e.target.value)}
          rows={8}
          style={{ width: "100%", marginBottom: 12, resize: "vertical" }}
        />

        <label style={styles.label}>Image prompts ({prompts.length})</label>
        <div style={{ maxHeight: 200, overflow: "auto", marginBottom: 16 }}>
          {prompts.map((p, i) => (
            <textarea
              key={i}
              value={p}
              onChange={(e) => {
                const next = [...prompts];
                next[i] = e.target.value;
                setPrompts(next);
              }}
              rows={2}
              style={{ width: "100%", marginBottom: 6, fontSize: 11 }}
            />
          ))}
        </div>

        <div style={styles.btnRow}>
          <button type="button" style={styles.cancelBtn} onClick={onCancel}>Cancel</button>
          <button type="button" style={styles.regenBtn} onClick={onRegenerate}>🔄 Regenerate</button>
          <button
            type="button"
            style={styles.approveBtn}
            onClick={() => onApprove({ title, voiceover, image_prompts: prompts })}
          >
            ✅ Approve & Continue
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: "rgba(0,0,0,0.75)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 10000,
  },
  modal: {
    background: theme.bgMain,
    border: `1px solid ${theme.border}`,
    padding: 24,
    width: 780,
    maxWidth: "95vw",
    maxHeight: "90vh",
    overflow: "auto",
  },
  label: { display: "block", color: theme.textSec, fontSize: 11, marginBottom: 4, fontWeight: 600 },
  btnRow: { display: "flex", gap: 8, justifyContent: "flex-end" },
  cancelBtn: { padding: "10px 16px", background: theme.bgSec, color: theme.textSec, border: `1px solid ${theme.border}` },
  regenBtn: { padding: "10px 16px", background: "#330044", color: theme.textPri, border: `1px solid #A020F0` },
  approveBtn: { padding: "10px 16px", background: theme.accentGrn, color: "#000", border: "none", fontWeight: 700 },
};
