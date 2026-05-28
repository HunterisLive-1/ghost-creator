let _baseUrl = "http://127.0.0.1:8766";

export function setApiBaseUrl(url: string) {
  _baseUrl = url.replace(/\/$/, "");
}

export function getApiBaseUrl() {
  if (typeof window !== "undefined" && window.location) {
    const host = window.location.hostname;
    if (host === "localhost" && _baseUrl.includes("127.0.0.1")) {
      return _baseUrl.replace("127.0.0.1", "localhost");
    }
    if (host === "127.0.0.1" && _baseUrl.includes("localhost")) {
      return _baseUrl.replace("localhost", "127.0.0.1");
    }
  }
  return _baseUrl;
}

export function wsUrl(path: string) {
  return getApiBaseUrl().replace(/^http/, "ws") + path;
}

export function pipelineWsUrl() {
  return wsUrl("/api/pipeline/ws");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${_baseUrl}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ ok: boolean; version: string }>("/health"),
  getConfig: () => request<Record<string, unknown>>("/api/config"),
  patchConfig: (updates: Record<string, unknown>) =>
    request<{ ok: boolean }>("/api/config", { method: "PATCH", body: JSON.stringify(updates) }),
  saveConfig: () => request<{ ok: boolean }>("/api/config/save", { method: "POST" }),
  openEnvLocal: () => request<{ ok: boolean }>("/api/config/open-env", { method: "POST" }),

  systemInfo: () =>
    request<{ version: string; device_name: string; env_local_path: string }>("/api/system/info"),

  pipelineStart: (body: { topic?: string | null; run_id?: number; mode?: string; custom_script?: string }) =>
    request<{ ok: boolean; run_id?: number; error?: string }>("/api/pipeline/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  pipelineStop: () => request<{ ok: boolean }>("/api/pipeline/stop", { method: "POST" }),
  pipelineRetry: () => request<{ ok: boolean }>("/api/pipeline/retry", { method: "POST" }),
  pipelineScriptReview: () =>
    request<{ waiting: boolean; data: ScriptReviewData | null; run_id?: number | null }>(
      "/api/pipeline/script-review"
    ),
  pipelineScriptApprove: (data: ScriptReviewData) =>
    request<{ ok: boolean }>("/api/pipeline/script/approve", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  pipelineScriptCancel: () =>
    request<{ ok: boolean }>("/api/pipeline/script/cancel", { method: "POST" }),

  pipelineEditorReview: () =>
    request<{ waiting: boolean; data: EditorReviewData | null; run_id?: number | null }>(
      "/api/pipeline/editor-review"
    ),
  pipelineEditorContinue: () =>
    request<{ ok: boolean }>("/api/pipeline/editor/continue", { method: "POST" }),
  pipelineEditorCancel: () =>
    request<{ ok: boolean }>("/api/pipeline/editor/cancel", { method: "POST" }),

  workshopChat: (body: { message: string; history: { role: string; content: string }[] }) =>
    request<{ reply: string; plan: WorkshopPlan | null }>("/api/workshop/chat", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  analyseError: (body: { error_message: string }) =>
    request<{ analysis: string }>("/api/error/analyse", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  uploadStart: (body: UploadRequest) =>
    request<{ job_id: string }>("/api/upload/start", { method: "POST", body: JSON.stringify(body) }),
  uploadAiFill: (body: { video_path: string }) =>
    request<{ title: string; description: string; tags: string }>("/api/upload/ai-fill", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getHistory: () => request<{ entries: HistoryEntry[] }>("/api/history"),
  historyRerender: (body: { run_dir: string }) =>
    request<{ job_id: string }>("/api/history/rerender", { method: "POST", body: JSON.stringify(body) }),

  loadEditor: (runDir: string) => request<any>(`/api/history/load-editor?run_dir=${encodeURIComponent(runDir)}`),
  saveEditor: (runDir: string, data: any) =>
    request<{ ok: boolean }>("/api/history/save-editor", {
      method: "POST",
      body: JSON.stringify({ run_dir: runDir, data }),
    }),
  listClips: (runDir: string) =>
    request<{
      edit_clips: { name: string; path: string; category: string; role?: string; size_mb: number }[];
      stock_clips: { name: string; path: string; category: string; role?: string; size_mb: number }[];
      clips: { name: string; path: string; category: string; role?: string; size_mb: number }[];
    }>(`/api/history/list-clips?run_dir=${encodeURIComponent(runDir)}`),
  uploadAudio: (runDir: string, file: File) => {
    const formData = new FormData();
    formData.append("run_dir", runDir);
    formData.append("file", file);
    return fetch(`${_baseUrl}/api/history/upload-audio`, {
      method: "POST",
      body: formData,
    }).then((res) => {
      if (!res.ok) throw new Error("Upload audio failed");
      return res.json() as Promise<{ ok: boolean; filename: string; path: string }>;
    });
  },
  uploadClip: (runDir: string, file: File) => {
    const formData = new FormData();
    formData.append("run_dir", runDir);
    formData.append("file", file);
    return fetch(`${_baseUrl}/api/history/upload-clip`, {
      method: "POST",
      body: formData,
    }).then((res) => {
      if (!res.ok) throw new Error("Upload clip failed");
      return res.json() as Promise<{ ok: boolean; filename: string; path: string }>;
    });
  },
  uploadImage: (runDir: string, file: File) => {
    const formData = new FormData();
    formData.append("run_dir", runDir);
    formData.append("file", file);
    return fetch(`${_baseUrl}/api/history/upload-image`, {
      method: "POST",
      body: formData,
    }).then((res) => {
      if (!res.ok) throw new Error("Upload image failed");
      return res.json() as Promise<{ ok: boolean; filename: string; path: string }>;
    });
  },
  getStockAssets: () =>
    request<{
      music: { name: string; filename: string; path: string }[];
      sfx: { name: string; filename: string; path: string }[];
    }>("/api/history/stock-assets"),


  testOllama: (url: string) =>
    request<{ ok: boolean; models?: string[]; error?: string }>("/api/system/test-ollama", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  probeOllama: () => request<{ status: string; detail: string; suggested_model?: string }>("/api/system/probe-ollama"),

  chromeProfileSetup: (name: string) =>
    request<{ ok: boolean; message: string }>("/api/chrome-profile/setup", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  metaAiTestLogin: () =>
    request<{ ok: boolean; message: string }>("/api/meta-ai/test-login", { method: "POST" }),
  metaAiSetupProfile: () =>
    request<{ ok: boolean; message: string; profile_path?: string }>("/api/meta-ai/setup-profile", {
      method: "POST",
    }),
  grokAiTestLogin: () =>
    request<{ ok: boolean; message: string }>("/api/grok-ai/test-login", { method: "POST" }),

  // YouTube Analytics API (OAuth2)
  ytAnalyticsStatus: (profileIndex: number) =>
    request<{ ok: boolean; connected: boolean; error?: string }>(`/api/yt-analytics/status?profile_index=${profileIndex}`),
  ytAnalyticsConnect: (profileIndex: number) =>
    request<{ ok: boolean; message?: string; error?: string }>("/api/yt-analytics/connect", {
      method: "POST",
      body: JSON.stringify({ profile_index: profileIndex }),
    }),
  ytAnalyticsSync: (profileIndex: number) =>
    request<{
      ok: boolean;
      views?: number;
      subs?: number;
      earnings?: number;
      views_series?: number[];
      subs_series?: number[];
      earnings_series?: number[];
      views_growth?: string;
      subs_growth?: string;
      earnings_growth?: string;
      channel_name?: string;
      channel_thumb?: string;
      total_subs?: number;
      error?: string;
    }>("/api/yt-analytics/sync", {
      method: "POST",
      body: JSON.stringify({ profile_index: profileIndex }),
    }),
  ytAnalyticsDisconnect: (profileIndex: number) =>
    request<{ ok: boolean; message?: string; error?: string }>("/api/yt-analytics/disconnect", {
      method: "POST",
      body: JSON.stringify({ profile_index: profileIndex }),
    }),
  ytAnalyticsResolveChannel: (url: string) =>
    request<{ ok: boolean; channel_id?: string; channel_name?: string; avatar_url?: string; error?: string }>("/api/yt-analytics/resolve-channel", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  // Legacy scraper fallback
  chromeProfileSync: (profileIndex: number) =>
    request<{ ok: boolean; views?: number; subs?: number; earnings?: number; error?: string }>("/api/chrome-profile/sync", {
      method: "POST",
      body: JSON.stringify({ profile_index: profileIndex }),
    }),
};

export interface ScriptReviewData {
  title: string;
  voiceover: string;
  image_prompts: string[];
}

export interface EditorReviewData {
  run_dir: string;
  title: string;
  segment_count: number;
}

export interface WorkshopPlan {
  topic?: string;
  format?: string;
  tone?: string;
  style?: string;
  suggested_title?: string;
  suggested_tags?: string;
}

export interface UploadRequest {
  video_path: string;
  title: string;
  description: string;
  tags: string;
  visibility: string;
}

export interface HistoryEntry {
  run_dir: string;
  title: string;
  topic: string;
  timestamp: string;
  description: string;
  tags: string;
  video_path: string;
  duration: string;
  can_rerender: boolean;
}

export interface PipelineMessage {
  step: number;
  message: string;
  level: "INFO" | "SUCCESS" | "ERROR" | "WARNING";
  timestamp: string;
  done?: boolean;
  output_path?: string;
  run_id?: string | number;
  retry_available?: boolean;
  event?: string;
  data?: unknown;
}

export interface JobLogMessage {
  job_id: string;
  message: string;
  level?: string;
  done?: boolean;
  result?: unknown;
}
