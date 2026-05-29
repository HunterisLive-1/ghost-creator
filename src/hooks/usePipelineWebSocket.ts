import { useEffect, useRef, useCallback } from "react";
import { PipelineMessage, pipelineWsUrl, api } from "../api/client";

export function usePipelineWebSocket(onMessage: (msg: PipelineMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const lastSeqRef = useRef<number>(0);
  const lastRunIdRef = useRef<string | number | undefined>(undefined);
  const pollTimerRef = useRef<number | null>(null);

  const processMessage = useCallback((msg: PipelineMessage) => {
    // Reset tracker if the run ID changes (new pipeline run started)
    if (msg.run_id !== undefined && msg.run_id !== lastRunIdRef.current) {
      console.log(`[PipelineProgress] Run ID changed from ${lastRunIdRef.current} to ${msg.run_id}, resetting sequence tracker.`);
      lastRunIdRef.current = msg.run_id;
      lastSeqRef.current = 0;
    }

    if (msg._seq !== undefined) {
      if (msg._seq <= lastSeqRef.current) {
        // Skip duplicate message
        return;
      }
      lastSeqRef.current = msg._seq;
    }

    onMessageRef.current(msg);
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log("[WS] Already connected, skipping reconnect");
      return;
    }
    const url = pipelineWsUrl();
    console.log("[WS] Connecting to:", url);
    const ws = new WebSocket(url);
    ws.onopen = () => {
      console.log("[WS] Connected successfully to", url);
    };
    ws.onerror = (err) => {
      console.error("[WS] Connection error:", err);
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as PipelineMessage;
        console.log("[WS] Parsed message: step=", msg.step, "run_id=", msg.run_id, "level=", msg.level, "seq=", msg._seq);
        processMessage(msg);
      } catch {
        console.error("[WS] Failed to parse message:", ev.data);
      }
    };
    ws.onclose = (e) => {
      console.log("[WS] Disconnected, code:", e.code, ", reason:", e.reason, ", reconnecting in 2s");
      setTimeout(connect, 2000);
    };
    wsRef.current = ws;
  }, [processMessage]);

  const pollProgress = useCallback(async () => {
    const wsConnected = wsRef.current && wsRef.current.readyState === WebSocket.OPEN;
    if (!wsConnected) {
      try {
        const res = await api.pipelineProgress(lastSeqRef.current);
        if (res && res.messages && res.messages.length > 0) {
          console.log("[Poll] Received messages:", res.messages.length, "after seq:", lastSeqRef.current);
          for (const msg of res.messages) {
            processMessage(msg);
          }
        }
      } catch (err) {
        console.error("[Poll] Error fetching pipeline progress:", err);
      }
    }
    pollTimerRef.current = window.setTimeout(pollProgress, 1000);
  }, [processMessage]);

  useEffect(() => {
    connect();
    pollProgress();

    return () => {
      wsRef.current?.close();
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
      }
    };
  }, [connect, pollProgress]);
}
