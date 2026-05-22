import { useEffect, useRef, useCallback } from "react";
import { PipelineMessage, pipelineWsUrl } from "../api/client";

export function usePipelineWebSocket(onMessage: (msg: PipelineMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(pipelineWsUrl());
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as PipelineMessage;
        onMessageRef.current(msg);
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => {
      setTimeout(connect, 2000);
    };
    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);
}
