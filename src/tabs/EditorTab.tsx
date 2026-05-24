import { useCallback, useEffect, useState, useRef } from "react";
import { api, getApiBaseUrl } from "../api/client";
import { theme } from "../theme/tokens";

interface Props {
  runDir: string | null;
  onClearRunDir: () => void;
}

interface Segment {
  voiceover: string;
  video_query: string;
  duration_hint: number;
  clip_name?: string;
  transition?: string; // Transition applied (e.g. Cross Dissolve)
  effect?: string;     // Visual effect applied (e.g. Grayscale)
}

interface SubtitleStyle {
  font_size: number;
  color: string;
  bg_color: string;
  bold: boolean;
  italic: boolean;
  font_family: string;
}

interface EditorData {
  title: string;
  voiceover_text: string;
  segments: Segment[];
  language: string;
  aspect_ratio: string;
  subtitle_style?: SubtitleStyle;
  bg_music?: string;
  bg_music_volume?: number;
}

interface ClipAsset {
  name: string;
  path: string;
  category: string;
  size_mb: number;
}

interface RecentRun {
  run_dir: string;
  title: string;
  timestamp: string;
  topic: string;
  video_path: string;
  duration: string;
}

type LibraryTab = "media" | "stock" | "audio" | "titles" | "transitions" | "effects" | "filters" | "stickers" | "templates";

export function EditorTab({ runDir, onClearRunDir }: Props) {
  const [activeRunDir, setActiveRunDir] = useState<string | null>(runDir);
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [editorData, setEditorData] = useState<EditorData | null>(null);
  const [clips, setClips] = useState<ClipAsset[]>([]);
  const [selectedSegIndex, setSelectedSegIndex] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [rerendering, setRerendering] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [libraryTab, setLibraryTab] = useState<LibraryTab>("media");

  // Stock assets list loaded from backend
  const [stockAssets, setStockAssets] = useState<{
    music: { name: string; filename: string; path: string }[];
    sfx: { name: string; filename: string; path: string }[];
  }>({ music: [], sfx: [] });

  // File Input Ref for Media Import
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Undo/Redo Stacks
  const [historyStack, setHistoryStack] = useState<EditorData[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // Voiceover Microphone recording state
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [recordingMediaRecorder, setRecordingMediaRecorder] = useState<MediaRecorder | null>(null);
  const [recordingChunks, setRecordingChunks] = useState<Blob[]>([]);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const [audioMeterLevel, setAudioMeterLevel] = useState(0);

  // Active video player properties
  const [playerResolution, setPlayerResolution] = useState("Full Quality");
  const [playerFitPercentage, setPlayerFitPercentage] = useState("Fit");
  const [timelineMarkers, setTimelineMarkers] = useState<{ markIn?: number; markOut?: number }>({});
  
  // Track states
  const [trackMuted, setTrackMuted] = useState<Record<string, boolean>>({
    video2: false,
    video1: false,
    audio1: false,
    audio2: false,
  });
  const [trackLocked, setTrackLocked] = useState<Record<string, boolean>>({
    video2: false,
    video1: false,
    audio1: false,
    audio2: false,
  });
  const [trackHidden, setTrackHidden] = useState<Record<string, boolean>>({
    video2: false,
    video1: false,
  });

  // Timeline Zoom level (pixels per second)
  const [zoomFactor, setZoomFactor] = useState(12);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const playheadRef = useRef<HTMLDivElement | null>(null);
  const timelineRulerRef = useRef<HTMLDivElement | null>(null);
  const timecodeRef = useRef<HTMLSpanElement | null>(null);
  const isDraggingPlayhead = useRef(false);

  // Mic analysis interval
  const micIntervalRef = useRef<any>(null);
  const recordingTimerRef = useRef<any>(null);

  // Fetch compiled history runs
  const loadRecentRuns = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getHistory();
      const validRuns = res.entries
        .filter((e) => e.can_rerender)
        .map((e) => ({
          run_dir: e.run_dir,
          title: e.title,
          timestamp: e.timestamp,
          topic: e.topic,
          video_path: e.video_path,
          duration: e.duration,
        }));
      setRecentRuns(validRuns);
    } catch (err) {
      console.error("Failed to load runs", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initialize/Load target editor details
  const loadRunEditor = useCallback(async (dir: string) => {
    setLoading(true);
    try {
      const [data, clipRes] = await Promise.all([
        api.loadEditor(dir),
        api.listClips(dir),
      ]);
      
      const updatedSegments = (data.segments || []).map((seg: Segment, idx: number) => {
        if (!seg.clip_name) {
          const defaultClip = clipRes.clips[idx];
          return { ...seg, clip_name: defaultClip ? defaultClip.name : `e_${idx}.mp4` };
        }
        return seg;
      });

      const initialData: EditorData = {
        ...data,
        segments: updatedSegments,
        subtitle_style: data.subtitle_style || {
          font_size: 28,
          color: "#FFFFFF",
          bg_color: "#80000000",
          bold: true,
          italic: false,
          font_family: "Nirmala UI",
        },
      };

      setEditorData(initialData);
      setClips(clipRes.clips);
      setSelectedSegIndex(updatedSegments.length > 0 ? 0 : null);
      
      // Reset Undo/Redo stacks
      setHistoryStack([initialData]);
      setHistoryIndex(0);
    } catch (err) {
      alert(`Failed to load project: ${err}`);
      setActiveRunDir(null);
      onClearRunDir();
    } finally {
      setLoading(false);
    }
  }, [onClearRunDir]);

  useEffect(() => {
    if (runDir) {
      setActiveRunDir(runDir);
      loadRunEditor(runDir);
    } else {
      loadRecentRuns();
    }
  }, [runDir, loadRecentRuns, loadRunEditor]);

  // Fetch stock assets and clean mic streams on mount
  useEffect(() => {
    const fetchStock = async () => {
      try {
        const res = await api.getStockAssets();
        setStockAssets(res);
      } catch (err) {
        console.error("Failed to load stock assets", err);
      }
    };
    fetchStock();
  }, []);

  // Clean mic streams on unmount
  useEffect(() => {
    return () => {
      if (micStream) micStream.getTracks().forEach((track) => track.stop());
      clearInterval(micIntervalRef.current);
      clearInterval(recordingTimerRef.current);
    };
  }, [micStream]);

  // Format second timestamps to HH:MM:SS:FF or MM:SS:FF
  const formatTimecode = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const frames = Math.floor((seconds % 1) * 30); // 30fps simulation
    return `${hrs.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}:${frames.toString().padStart(2, "0")}`;
  };

  const getTimelineDuration = () => {
    if (!editorData?.segments) return 0;
    return editorData.segments.reduce((acc, seg) => acc + (seg.duration_hint || 0), 0);
  };

  // Push new state onto history stack
  const updateEditorDataWithHistory = (newData: EditorData) => {
    const updatedStack = historyStack.slice(0, historyIndex + 1);
    updatedStack.push(newData);
    setHistoryStack(updatedStack);
    setHistoryIndex(updatedStack.length - 1);
    setEditorData(newData);
  };

  // Undo edit action
  const handleUndo = () => {
    if (historyIndex > 0) {
      const targetIdx = historyIndex - 1;
      setHistoryIndex(targetIdx);
      setEditorData(historyStack[targetIdx]);
      setSelectedSegIndex(0);
      setPlaybackTime(0);
      if (videoRef.current) videoRef.current.currentTime = 0;
    }
  };

  // Redo edit action
  const handleRedo = () => {
    if (historyIndex < historyStack.length - 1) {
      const targetIdx = historyIndex + 1;
      setHistoryIndex(targetIdx);
      setEditorData(historyStack[targetIdx]);
      setSelectedSegIndex(0);
      setPlaybackTime(0);
      if (videoRef.current) videoRef.current.currentTime = 0;
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current && !isDraggingPlayhead.current) {
      const t = videoRef.current.currentTime;
      setPlaybackTime(t);
      updatePlayheadDOM(t);
    }
  };

  const updatePlayheadDOM = (time: number) => {
    if (playheadRef.current) {
      const x = time * zoomFactor;
      playheadRef.current.style.left = `${x}px`;
    }
    if (timecodeRef.current && editorData) {
      timecodeRef.current.innerText = `${formatTimecode(time)} / ${formatTimecode(getTimelineDuration())}`;
    }
  };

  // Throttled video seeks during dragging to prevent Chromium playback lag
  const handleTimelineScrub = (clientX: number, isFinal = false) => {
    if (timelineRulerRef.current && editorData) {
      const rect = timelineRulerRef.current.getBoundingClientRect();
      const mouseX = Math.max(0, clientX - rect.left);
      const time = mouseX / zoomFactor;
      const totalDur = getTimelineDuration();
      const clampedTime = Math.min(totalDur, Math.max(0, time));
      
      updatePlayheadDOM(clampedTime);

      if (videoRef.current) {
        // Only trigger seek if previous seek completed (prevents stack locking)
        if (!videoRef.current.seeking || isFinal) {
          videoRef.current.currentTime = clampedTime;
        }
      }
      
      if (isFinal) {
        setPlaybackTime(clampedTime);
      }
    }
  };

  const handleScrubberMouseDown = (e: React.MouseEvent) => {
    isDraggingPlayhead.current = true;
    handleTimelineScrub(e.clientX);
    
    const onMouseMove = (moveEvent: MouseEvent) => {
      if (isDraggingPlayhead.current) {
        // Use requestAnimationFrame for smooth CSS rendering
        window.requestAnimationFrame(() => {
          handleTimelineScrub(moveEvent.clientX);
        });
      }
    };

    const onMouseUp = (upEvent: MouseEvent) => {
      isDraggingPlayhead.current = false;
      handleTimelineScrub(upEvent.clientX, true);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  };

  const selectSegment = (idx: number) => {
    if (!editorData) return;
    setSelectedSegIndex(idx);
    setIsPlaying(false);
    if (videoRef.current) {
      videoRef.current.pause();
    }
    
    // Seek to segment start time
    let startTime = 0;
    for (let i = 0; i < idx; i++) {
      startTime += editorData.segments[i].duration_hint || 0;
    }
    setPlaybackTime(startTime);
    updatePlayheadDOM(startTime);
    if (videoRef.current) {
      videoRef.current.currentTime = startTime;
    }
  };

  const handlePlayPause = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play().catch(console.error);
      }
      setIsPlaying(!isPlaying);
    }
  };

  const frameForward = () => {
    if (videoRef.current) {
      const t = Math.min(getTimelineDuration(), videoRef.current.currentTime + 0.04);
      videoRef.current.currentTime = t;
      setPlaybackTime(t);
      updatePlayheadDOM(t);
    }
  };

  const frameBackward = () => {
    if (videoRef.current) {
      const t = Math.max(0, videoRef.current.currentTime - 0.04);
      videoRef.current.currentTime = t;
      setPlaybackTime(t);
      updatePlayheadDOM(t);
    }
  };

  const captureSnapshot = () => {
    if (videoRef.current) {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = videoRef.current.videoWidth || 1280;
        canvas.height = videoRef.current.videoHeight || 720;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
          const dataUrl = canvas.toDataURL("image/png");
          const link = document.createElement("a");
          link.download = `snapshot_${Math.floor(Date.now() / 1000)}.png`;
          link.href = dataUrl;
          link.click();
        }
      } catch (err) {
        alert("Could not capture video frame snapshot: Cross-origin security block.");
      }
    }
  };

  const updateSelectedSegment = (field: keyof Segment, value: any) => {
    if (selectedSegIndex === null || !editorData) return;
    const updated = [...editorData.segments];
    updated[selectedSegIndex] = {
      ...updated[selectedSegIndex],
      [field]: value,
    };
    const nextData = { ...editorData, segments: updated };
    updateEditorDataWithHistory(nextData);
  };

  const handleSegmentSwap = (fromIdx: number, toIdx: number) => {
    if (!editorData || toIdx < 0 || toIdx >= editorData.segments.length) return;
    const updated = [...editorData.segments];
    const [moved] = updated.splice(fromIdx, 1);
    updated.splice(toIdx, 0, moved);
    
    const nextData = { ...editorData, segments: updated };
    updateEditorDataWithHistory(nextData);
    setSelectedSegIndex(toIdx);
  };

  const deleteSegment = (idx: number) => {
    if (!editorData || editorData.segments.length <= 1) {
      alert("Timeline requires at least 1 video block.");
      return;
    }
    const updated = [...editorData.segments];
    updated.splice(idx, 1);
    
    const nextData = { ...editorData, segments: updated };
    updateEditorDataWithHistory(nextData);
    setSelectedSegIndex(idx > 0 ? idx - 1 : 0);
  };

  const duplicateSegment = (idx: number) => {
    if (!editorData) return;
    const updated = [...editorData.segments];
    const copy = { ...updated[idx] };
    updated.splice(idx + 1, 0, copy);
    
    const nextData = { ...editorData, segments: updated };
    updateEditorDataWithHistory(nextData);
    setSelectedSegIndex(idx + 1);
  };

  // Splitting segment with scissors logic
  const splitSegmentAtPlayhead = () => {
    if (!editorData) return;
    let accumulated = 0;
    let targetIdx = -1;
    for (let i = 0; i < editorData.segments.length; i++) {
      const segDur = editorData.segments[i].duration_hint;
      if (playbackTime >= accumulated && playbackTime <= accumulated + segDur) {
        targetIdx = i;
        break;
      }
      accumulated += segDur;
    }

    if (targetIdx !== -1) {
      const target = editorData.segments[targetIdx];
      const timeInSegment = playbackTime - accumulated;
      if (timeInSegment > 0.5 && timeInSegment < target.duration_hint - 0.5) {
        const updated = [...editorData.segments];
        updated[targetIdx] = {
          ...target,
          duration_hint: Math.round(timeInSegment),
          voiceover: target.voiceover.split(" ").slice(0, Math.floor(target.voiceover.split(" ").length / 2)).join(" "),
        };
        updated.splice(targetIdx + 1, 0, {
          voiceover: target.voiceover.split(" ").slice(Math.floor(target.voiceover.split(" ").length / 2)).join(" "),
          video_query: `${target.video_query} split`,
          duration_hint: Math.max(1, target.duration_hint - Math.round(timeInSegment)),
          clip_name: target.clip_name,
        });
        
        const nextData = { ...editorData, segments: updated };
        updateEditorDataWithHistory(nextData);
        setSelectedSegIndex(targetIdx + 1);
      } else {
        // Split segment right in half
        splitSegment(selectedSegIndex ?? 0);
      }
    }
  };

  const splitSegment = (idx: number) => {
    if (!editorData) return;
    const target = editorData.segments[idx];
    const dur = Math.max(1, Math.floor(target.duration_hint / 2));
    
    const updated = [...editorData.segments];
    updated[idx] = {
      ...target,
      duration_hint: dur,
      voiceover: target.voiceover.split(" ").slice(0, Math.floor(target.voiceover.split(" ").length / 2)).join(" "),
    };
    updated.splice(idx + 1, 0, {
      voiceover: target.voiceover.split(" ").slice(Math.floor(target.voiceover.split(" ").length / 2)).join(" "),
      video_query: `${target.video_query} split`,
      duration_hint: Math.max(1, target.duration_hint - dur),
      clip_name: target.clip_name,
    });

    const nextData = { ...editorData, segments: updated };
    updateEditorDataWithHistory(nextData);
    setSelectedSegIndex(idx + 1);
  };

  const addBlankSegment = () => {
    if (!editorData) return;
    const updated = [...editorData.segments];
    const defaultClip = clips[0]?.name || "e0.mp4";
    updated.push({
      voiceover: "Add voice narration details here",
      video_query: "new action overlay clip",
      duration_hint: 5,
      clip_name: defaultClip,
    });
    
    const nextData = { ...editorData, segments: updated };
    updateEditorDataWithHistory(nextData);
    setSelectedSegIndex(updated.length - 1);
  };

  const handleImportMediaClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !activeRunDir) return;
    
    setLoading(true);
    try {
      await api.uploadClip(activeRunDir, file);
      // Refresh clips list
      const clipRes = await api.listClips(activeRunDir);
      setClips(clipRes.clips);
      alert(`Imported media "${file.name}" successfully!`);
    } catch (err) {
      alert(`Import failed: ${err}`);
    } finally {
      setLoading(false);
      if (e.target) e.target.value = ""; // Reset input
    }
  };

  const applyBackgroundMusic = (filename: string) => {
    if (!editorData) return;
    const nextData = {
      ...editorData,
      bg_music: filename,
      bg_music_volume: editorData.bg_music_volume ?? 0.25
    };
    updateEditorDataWithHistory(nextData);
    alert(`Applied background music: ${filename.replace(/_/g, " ").replace(".mp3", "")}`);
  };

  const applySoundEffect = (filename: string) => {
    if (selectedSegIndex === null || !editorData) {
      alert("Please select a video clip on the timeline first.");
      return;
    }
    const updated = [...editorData.segments];
    updated[selectedSegIndex] = {
      ...updated[selectedSegIndex],
      video_query: `${updated[selectedSegIndex].video_query} sfx:${filename.replace(".mp3", "")}`
    };
    const nextData = { ...editorData, segments: updated };
    updateEditorDataWithHistory(nextData);
    alert(`Applied Sound Effect "${filename.replace(/_/g, " ").replace(".mp3", "")}" to segment #${selectedSegIndex + 1}`);
  };

  const pollRerender = async (jobId: string, offset = 0) => {
    const res = await fetch(`${getApiBaseUrl()}/api/history/job/${jobId}?offset=${offset}`);
    const data = await res.json();
    if (data.logs?.length) {
      setLogs((prev) => [...prev, ...data.logs.map((l: any) => l.message)]);
    }
    if (data.done) {
      setRerendering(false);
      alert("Final Video compiled successfully!");
    } else {
      setTimeout(() => pollRerender(jobId, offset + (data.logs?.length || 0)), 600);
    }
  };

  const saveAndExport = async () => {
    if (!activeRunDir || !editorData) return;
    setSaving(true);
    setLogs([]);
    try {
      await api.saveEditor(activeRunDir, editorData);
      setSaving(false);
      setRerendering(true);
      setLogs(["[START] Connecting to FFmpeg video re-render queue..."]);
      const { job_id } = await api.historyRerender({ run_dir: activeRunDir });
      pollRerender(job_id);
    } catch (err) {
      alert(`Save/Render failed: ${err}`);
      setSaving(false);
      setRerendering(false);
    }
  };

  const handleBack = () => {
    setActiveRunDir(null);
    setEditorData(null);
    setSelectedSegIndex(null);
    onClearRunDir();
    loadRecentRuns();
  };

  const getSelectedClipAsset = () => {
    if (selectedSegIndex === null || !editorData) return null;
    const clipName = editorData.segments[selectedSegIndex].clip_name;
    return clips.find((c) => c.name === clipName) || clips[0] || null;
  };

  // Toggle properties of track channels
  const toggleTrackMute = (track: string) => {
    setTrackMuted((prev) => ({ ...prev, [track]: !prev[track] }));
  };
  const toggleTrackLock = (track: string) => {
    setTrackLocked((prev) => ({ ...prev, [track]: !prev[track] }));
  };
  const toggleTrackHide = (track: string) => {
    setTrackHidden((prev) => ({ ...prev, [track]: !prev[track] }));
  };

  // Subtitle custom styling inputs
  const updateSubtitleStyle = (key: keyof SubtitleStyle, value: any) => {
    if (!editorData) return;
    const nextStyle = {
      ...(editorData.subtitle_style || {
        font_size: 28,
        color: "#FFFFFF",
        bg_color: "#80000000",
        bold: true,
        italic: false,
        font_family: "Nirmala UI",
      }),
      [key]: value,
    };
    const nextData = { ...editorData, subtitle_style: nextStyle };
    updateEditorDataWithHistory(nextData);
  };

  // Microphone Voice Recording Action
  const toggleVoiceRecording = async () => {
    if (!activeRunDir) return;
    if (isRecording) {
      // Stop Recording
      if (recordingMediaRecorder) {
        recordingMediaRecorder.stop();
      }
      setIsRecording(false);
      if (micStream) {
        micStream.getTracks().forEach((track) => track.stop());
      }
      clearInterval(micIntervalRef.current);
      clearInterval(recordingTimerRef.current);
      setAudioMeterLevel(0);
    } else {
      // Start Recording
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setMicStream(stream);
        const options = { mimeType: "audio/webm" };
        const recorder = new MediaRecorder(stream, options);
        const chunks: Blob[] = [];

        // Mic volume bar meter simulation
        const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
        const source = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        source.connect(analyser);

        micIntervalRef.current = setInterval(() => {
          analyser.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
          }
          const average = sum / bufferLength;
          setAudioMeterLevel(Math.min(100, Math.round(average * 1.5)));
        }, 100);

        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) {
            chunks.push(e.data);
          }
        };

        recorder.onstop = async () => {
          const blob = new Blob(chunks, { type: "audio/webm" });
          const file = new File([blob], "voiceover_recorded.mp3", { type: "audio/webm" });
          
          setLogs((prev) => [...prev, "[MIC] Uploading audio recording to project run..."]);
          try {
            await api.uploadAudio(activeRunDir, file);
            alert("Custom recorded voiceover saved successfully to run timeline!");
            setLogs((prev) => [...prev, "[MIC] Voiceover voiceover_recorded.mp3 registered! Re-compile to hear changes."]);
          } catch (err) {
            alert(`Voice upload failed: ${err}`);
          }
        };

        setRecordingChunks([]);
        setRecordingMediaRecorder(recorder);
        recorder.start();
        setIsRecording(true);
        setRecordingSeconds(0);

        recordingTimerRef.current = setInterval(() => {
          setRecordingSeconds((s) => s + 1);
        }, 1000);
      } catch (err) {
        alert(`Cannot access microphone: ${err}`);
      }
    }
  };

  // Mock Preset library data
  const stockMediaAssets = [
    { name: "Abstract Cyber Lights", query: "neon code light" },
    { name: "Mountain Drone View", query: "mountain flyover drone" },
    { name: "Cinematic Ocean Wave", query: "ocean waves background" },
    { name: "Tech Digital HUD", query: "digital futuristic interface" },
    { name: "Vlog Morning Sunlight", query: "cozy coffee warm morning" },
  ];



  const transitionPresets = ["Cross Dissolve", "Fade to Black", "Zoom Blur", "Whip Pan", "Dissolve"];
  const effectPresets = ["Dream Blur", "Cinematic Grain", "B&W Film", "Retro Glow", "VHS Overlay"];
  const filterPresets = ["Warm Sunset", "Cool Teal & Orange", "Monochrome Noir", "Vintage Tint"];
  const stickerPresets = ["Subscribe Bell", "Arrow Pointer", "Fire Spark", "Heart Pulse"];
  const templatePresets = ["Vlog Intro Duo", "Modern News Split", "Documentary Title Layout"];

  // ── Render Workspace ──────────────────────────────────────────────────────
  if (activeRunDir && editorData) {
    const currentClip = getSelectedClipAsset();
    const timelineTotal = getTimelineDuration();
    const activeVideoPath = editorData.segments[selectedSegIndex || 0]?.clip_name 
      ? clips.find((c) => c.name === editorData.segments[selectedSegIndex || 0].clip_name)?.path 
      : null;

    return (
      <div style={styles.filmoraWorkspace}>
        
        {/* Wondershare Filmora Header Menu Bar */}
        <header style={styles.filmoraHeader}>
          <div style={styles.filmoraHeaderLeft}>
            <span style={styles.filmoraLogo}>🎬 GHOST FILMORA PRO</span>
            <nav style={styles.menuNav}>
              <span>File</span>
              <span>Edit</span>
              <span>Tools</span>
              <span>View</span>
              <span>Extended</span>
              <span>Help</span>
              <span>Version</span>
            </nav>
          </div>
          
          <div style={styles.projectTitleBox}>
            <input
              value={editorData.title}
              onChange={(e) => updateEditorDataWithHistory({ ...editorData, title: e.target.value })}
              style={styles.projectTitleInput}
              title="Project Name"
            />
          </div>

          <div style={styles.filmoraHeaderRight}>
            <div style={styles.purchaseBadge}>Purchase</div>
            <button
              type="button"
              style={{ ...styles.filmoraExportBtn, opacity: saving || rerendering ? 0.6 : 1 }}
              onClick={saveAndExport}
              disabled={saving || rerendering}
            >
              {saving ? "Saving..." : rerendering ? "Rendering..." : "Export ▾"}
            </button>
            <button type="button" style={styles.closeEditorBtn} onClick={handleBack}>✖</button>
          </div>
        </header>

        {/* 3-Column Middle Workspace Panels */}
        <div style={styles.topPanelsWrapper}>
          
          {/* Column 1: Asset Media Library Tabs */}
          <div style={styles.libraryPanel}>
            <div style={styles.libraryTabs}>
              <div style={{ ...styles.libTabItem, ...(libraryTab === "media" ? styles.libTabActive : {}) }} onClick={() => setLibraryTab("media")}>📁 Media</div>
              <div style={{ ...styles.libTabItem, ...(libraryTab === "stock" ? styles.libTabActive : {}) }} onClick={() => setLibraryTab("stock")}>🎬 Stock Media</div>
              <div style={{ ...styles.libTabItem, ...(libraryTab === "audio" ? styles.libTabActive : {}) }} onClick={() => setLibraryTab("audio")}>🎵 Audio</div>
              <div style={{ ...styles.libTabItem, ...(libraryTab === "titles" ? styles.libTabActive : {}) }} onClick={() => setLibraryTab("titles")}>T Titles</div>
              <div style={{ ...styles.libTabItem, ...(libraryTab === "transitions" ? styles.libTabActive : {}) }} onClick={() => setLibraryTab("transitions")}>⚡ Transitions</div>
              <div style={{ ...styles.libTabItem, ...(libraryTab === "effects" ? styles.libTabActive : {}) }} onClick={() => setLibraryTab("effects")}>✨ Effects</div>
              <div style={{ ...styles.libTabItem, ...(libraryTab === "filters" ? styles.libTabActive : {}) }} onClick={() => setLibraryTab("filters")}>🔮 Filters</div>
              <div style={{ ...styles.libTabItem, ...(libraryTab === "stickers" ? styles.libTabActive : {}) }} onClick={() => setLibraryTab("stickers")}>⭐ Stickers</div>
              <div style={{ ...styles.libTabItem, ...(libraryTab === "templates" ? styles.libTabActive : {}) }} onClick={() => setLibraryTab("templates")}>📰 Templates</div>
            </div>

            <div style={styles.libraryWorkspace}>
              <div style={styles.libraryInnerSidebar}>
                <div style={styles.innerSideItemActive}>Project Media</div>
                <div style={styles.innerSideItem}>Folder</div>
                <div style={styles.innerSideItem}>Global Media</div>
                <div style={styles.innerSideItem}>Cloud Media</div>
                <div style={styles.innerSideItem}>Editing Presets</div>
                <div style={styles.innerSideItem}>Influence Kit</div>
              </div>

              <div style={styles.libraryGridContent}>
                {libraryTab === "media" && (
                  <div style={styles.mediaGrid}>
                    <div style={styles.importMediaTile} onClick={handleImportMediaClick}>
                      <span style={{ fontSize: 24, color: "#00B0FF" }}>+</span>
                      <span style={{ fontSize: 9, color: "#8a94a6", marginTop: 4 }}>Import Media</span>
                    </div>
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileImport}
                      accept="video/*,image/*,audio/*"
                      style={{ display: "none" }}
                    />
                    {clips.map((c) => (
                      <div key={c.name} style={styles.mediaCard} onClick={() => {
                        const targetIdx = editorData.segments.findIndex((s) => s.clip_name === c.name);
                        if (targetIdx !== -1) selectSegment(targetIdx);
                      }}>
                        <div style={styles.mediaCardThumb}>
                          <span style={styles.mediaCardDur}>00:0{Math.round(c.size_mb * 0.1)}s</span>
                        </div>
                        <div style={styles.mediaCardLabel}>{c.name}</div>
                      </div>
                    ))}
                  </div>
                )}

                {libraryTab === "stock" && (
                  <div style={styles.presetList}>
                    {stockMediaAssets.map((asset) => (
                      <div
                        key={asset.name}
                        style={styles.presetItem}
                        onClick={() => {
                          if (selectedSegIndex !== null) {
                            updateSelectedSegment("video_query", asset.query);
                            alert(`Applied query "${asset.query}" to Segment #${selectedSegIndex + 1}`);
                          }
                        }}
                      >
                        <span style={{ fontSize: 13 }}>🎞️</span>
                        <div style={{ flex: 1 }}>
                          <div style={styles.presetItemName}>{asset.name}</div>
                          <div style={styles.presetItemDetail}>Query: {asset.query}</div>
                        </div>
                        <button style={styles.applyPresetBtn}>Apply</button>
                      </div>
                    ))}
                  </div>
                )}

                {libraryTab === "audio" && (
                  <div style={styles.presetList}>
                    <div style={styles.widgetHeader}>🎵 Background Music</div>
                    {stockAssets.music.length === 0 ? (
                      <div style={styles.presetItemDetail}>Downloading stock music files...</div>
                    ) : (
                      stockAssets.music.map((music) => (
                        <div
                          key={music.filename}
                          style={styles.presetItem}
                          onClick={() => applyBackgroundMusic(music.filename)}
                        >
                          <span style={{ fontSize: 13 }}>🎵</span>
                          <div style={{ flex: 1 }}>
                            <div style={styles.presetItemName}>{music.name}</div>
                            <div style={styles.presetItemDetail}>{music.filename}</div>
                          </div>
                          <button
                            type="button"
                            style={{ ...styles.applyPresetBtn, background: "#00E676", color: "#000", marginRight: 6, width: "auto", padding: "4px 8px" }}
                            onClick={(e) => {
                              e.stopPropagation();
                              const audioUrl = `${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(music.path)}`;
                              const audio = new Audio(audioUrl);
                              audio.volume = 0.4;
                              audio.play();
                              alert(`Preview playing: ${music.name}`);
                            }}
                          >
                            ▶ Play
                          </button>
                          <button type="button" style={styles.applyPresetBtn}>Use</button>
                        </div>
                      ))
                    )}

                    <div style={{ ...styles.widgetHeader, marginTop: 12 }}>🔊 Sound Effects</div>
                    {stockAssets.sfx.length === 0 ? (
                      <div style={styles.presetItemDetail}>Downloading stock sound effects...</div>
                    ) : (
                      stockAssets.sfx.map((sfx) => (
                        <div
                          key={sfx.filename}
                          style={styles.presetItem}
                          onClick={() => applySoundEffect(sfx.filename)}
                        >
                          <span style={{ fontSize: 13 }}>🔊</span>
                          <div style={{ flex: 1 }}>
                            <div style={styles.presetItemName}>{sfx.name}</div>
                            <div style={styles.presetItemDetail}>{sfx.filename}</div>
                          </div>
                          <button
                            type="button"
                            style={{ ...styles.applyPresetBtn, background: "#00E676", color: "#000", marginRight: 6, width: "auto", padding: "4px 8px" }}
                            onClick={(e) => {
                              e.stopPropagation();
                              const audioUrl = `${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(sfx.path)}`;
                              const audio = new Audio(audioUrl);
                              audio.play();
                            }}
                          >
                            ▶ Play
                          </button>
                          <button type="button" style={styles.applyPresetBtn}>Use</button>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {libraryTab === "transitions" && (
                  <div style={styles.badgeList}>
                    {transitionPresets.map((t) => (
                      <button
                        key={t}
                        style={styles.badgeItem}
                        onClick={() => {
                          if (selectedSegIndex !== null) {
                            updateSelectedSegment("transition", t);
                          } else {
                            alert("Select a video clip in the timeline to apply transition.");
                          }
                        }}
                      >
                        ⚡ {t}
                      </button>
                    ))}
                  </div>
                )}

                {libraryTab === "effects" && (
                  <div style={styles.badgeList}>
                    {effectPresets.map((eff) => (
                      <button
                        key={eff}
                        style={styles.badgeItem}
                        onClick={() => {
                          if (selectedSegIndex !== null) {
                            updateSelectedSegment("effect", eff);
                          } else {
                            alert("Select a clip to apply effect.");
                          }
                        }}
                      >
                        ✨ {eff}
                      </button>
                    ))}
                  </div>
                )}

                {libraryTab === "filters" && (
                  <div style={styles.badgeList}>
                    {filterPresets.map((f) => (
                      <button
                        key={f}
                        style={styles.badgeItem}
                        onClick={() => alert(`Applied visual filter "${f}"`)}
                      >
                        🔮 {f}
                      </button>
                    ))}
                  </div>
                )}

                {libraryTab === "stickers" && (
                  <div style={styles.badgeList}>
                    {stickerPresets.map((st) => (
                      <button key={st} style={styles.badgeItem} onClick={() => alert(`Sticker "${st}" dragged to Video 2 overlay.`)}>
                        ⭐ {st}
                      </button>
                    ))}
                  </div>
                )}

                {libraryTab === "templates" && (
                  <div style={styles.presetList}>
                    {templatePresets.map((tpl) => (
                      <div key={tpl} style={styles.presetItem} onClick={() => alert(`Template "${tpl}" loaded.`)}>
                        <span style={{ fontSize: 13 }}>📰</span>
                        <div style={styles.presetItemName}>{tpl}</div>
                        <button style={styles.applyPresetBtn}>Load</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Column 2: HTML5 Preview Screen Player */}
          <div style={styles.previewPanel}>
            <div style={styles.playerTabs}>
              <span style={styles.playerTabActive}>Timeline Preview</span>
              <span style={styles.playerTab}>Source Monitor</span>
            </div>

            <div style={styles.playerBox}>
              {activeVideoPath ? (
                <video
                  ref={videoRef}
                  src={`${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(activeVideoPath)}`}
                  style={styles.playerScreen}
                  onTimeUpdate={handleTimeUpdate}
                  onEnded={() => setIsPlaying(false)}
                />
              ) : (
                <div style={styles.playerScreenPlaceholder}>
                  <div style={styles.errorCircle}>!</div>
                  <span style={{ color: "#8a94a6", fontSize: 11, marginTop: 8 }}>[ Click timeline clip to load video monitor ]</span>
                </div>
              )}
            </div>

            {/* Video Controls bar */}
            <div style={styles.playerSubControls}>
              <div style={styles.playbackButtons}>
                <button type="button" style={styles.playerActionBtn} onClick={() => { if (videoRef.current) videoRef.current.currentTime = 0; }} title="Go to Beginning">|◀</button>
                <button type="button" style={styles.playerActionBtn} onClick={frameBackward} title="Previous Frame (1/25s)">◀</button>
                <button type="button" style={styles.playerPlayBtn} onClick={handlePlayPause} title="Play/Pause">
                  {isPlaying ? "⏸" : "▶"}
                </button>
                <button type="button" style={styles.playerActionBtn} onClick={frameForward} title="Next Frame (1/25s)">▶</button>
                <button type="button" style={styles.playerActionBtn} onClick={() => { if (videoRef.current) videoRef.current.currentTime = getTimelineDuration(); }} title="Go to End">▶|</button>
              </div>

              {/* Real-time DOM ref update timecode */}
              <div style={styles.timecodeDisplay}>
                <span ref={timecodeRef} style={{ color: "#00E676" }}>
                  {formatTimecode(playbackTime)} / {formatTimecode(timelineTotal)}
                </span>
              </div>

              <div style={styles.playerRightControls}>
                {/* Snapshot button */}
                <button type="button" style={styles.playerAuxBtn} onClick={captureSnapshot} title="Capture Snapshot Frame">📷</button>
                
                {/* Marker In/Out */}
                <button type="button" style={{ ...styles.playerAuxBtn, color: timelineMarkers.markIn !== undefined ? "#00E676" : "#8a94a6" }} onClick={() => setTimelineMarkers({ ...timelineMarkers, markIn: playbackTime })} title="Mark In">{`{`}</button>
                <button type="button" style={{ ...styles.playerAuxBtn, color: timelineMarkers.markOut !== undefined ? "#00E676" : "#8a94a6" }} onClick={() => setTimelineMarkers({ ...timelineMarkers, markOut: playbackTime })} title="Mark Out">{`}`}</button>
                
                {/* Resolution selector */}
                <select
                  value={playerResolution}
                  onChange={(e) => setPlayerResolution(e.target.value)}
                  style={styles.playerSelector}
                >
                  <option>Full Quality</option>
                  <option>1/2 Quality</option>
                  <option>1/4 Quality</option>
                </select>

                {/* Scale factor selector */}
                <select
                  value={playerFitPercentage}
                  onChange={(e) => setPlayerFitPercentage(e.target.value)}
                  style={styles.playerSelector}
                >
                  <option>Fit</option>
                  <option>100%</option>
                  <option>50%</option>
                </select>
              </div>
            </div>
          </div>

          {/* Column 3: Project Info Metadata Panel */}
          <div style={styles.projectInfoPanel}>
            <div style={styles.infoTitle}>Project Properties</div>
            <div style={styles.infoGrid}>
              <div style={styles.infoRow}><span style={styles.infoLabel}>Project Name:</span><span style={styles.infoValue}>{editorData.title.slice(0, 16)}...</span></div>
              <div style={styles.infoRow}><span style={styles.infoLabel}>Files Dir:</span><span style={styles.infoValue}>output/runs/</span></div>
              <div style={styles.infoRow}><span style={styles.infoLabel}>Resolution:</span><span style={styles.infoValue}>{editorData.aspect_ratio === "9:16" ? "1080 x 1920" : "1920 x 1080"}</span></div>
              <div style={styles.infoRow}><span style={styles.infoLabel}>Frame Rate:</span><span style={styles.infoValue}>24.00 fps</span></div>
              <div style={styles.infoRow}><span style={styles.infoLabel}>Color Space:</span><span style={styles.infoValue}>SDR - Rec.709</span></div>
              <div style={styles.infoRow}><span style={styles.infoLabel}>Sample Rate:</span><span style={styles.infoValue}>44100 Hz</span></div>
              <div style={styles.infoRow}><span style={styles.infoLabel}>Duration:</span><span style={styles.infoValue}>{timelineTotal.toFixed(1)}s</span></div>
            </div>
            
            <button style={styles.editInfoBtn} onClick={() => alert("Project details configured for editing.")}>Edit Settings</button>

            {/* Live voice recorder tool */}
            <div style={styles.voiceRecorderWidget}>
              <div style={styles.widgetHeader}>🎤 Voiceover Recording</div>
              <div style={styles.recordControls}>
                <button
                  type="button"
                  style={{ ...styles.recordBtn, ...(isRecording ? styles.recordBtnActive : {}) }}
                  onClick={toggleVoiceRecording}
                >
                  {isRecording ? "🔴 STOP REC" : "🎙️ RECORD VO"}
                </button>
                {isRecording && <span style={styles.recordTimer}>{recordingSeconds}s</span>}
              </div>
              {isRecording && (
                <div style={styles.audioMeterWrap}>
                  <div style={{ ...styles.audioMeterFill, width: `${audioMeterLevel}%` }} />
                </div>
              )}
            </div>

            {/* Render queue feedback logs */}
            {rerendering && (
              <div style={styles.buildConsole}>
                <div style={styles.buildConsoleTitle}>FFMPEG LOGS</div>
                <div style={styles.buildConsoleContent}>
                  {logs.map((log, index) => (
                    <div key={index} style={styles.buildConsoleLine}>{log}</div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Timeline Editor Bottom Section */}
        <div style={styles.timelineWorkspace}>
          
          {/* Timeline Toolbar controls */}
          <div style={styles.timelineToolbar}>
            <div style={styles.timelineToolsLeft}>
              <button type="button" style={styles.toolBtn} onClick={handleUndo} disabled={historyIndex <= 0} title="Undo (Ctrl+Z)">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z"/></svg>
              </button>
              <button type="button" style={styles.toolBtn} onClick={handleRedo} disabled={historyIndex >= historyStack.length - 1} title="Redo (Ctrl+Y)">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M18.4 10.6C16.55 8.99 14.15 8 11.5 8c-4.65 0-8.58 3.03-9.96 7.22L3.9 16c1.05-3.19 4.05-5.5 7.6-5.5 1.95 0 3.73.72 5.12 1.88L13 16h9V7l-3.6 3.6z"/></svg>
              </button>
              <div style={styles.toolSeparator} />
              
              <button type="button" style={styles.toolBtn} onClick={splitSegmentAtPlayhead} title="Split Clip at Playhead (Scissors)">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M6 12c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm0-4c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1zm0 10c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm0-4c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1zm6-3.5c-.28 0-.5-.22-.5-.5s.22-.5.5-.5.5.22.5.5-.22.5-.5.5zm7-4.5c0-.83-.67-1.5-1.5-1.5S16 5.17 16 6c0 .54.29 1.01.72 1.28L12 11.44l-4.72-4.16c.43-.27.72-.74.72-1.28 0-.83-.67-1.5-1.5-1.5S5 5.17 5 6c0 .83.67 1.5 1.5 1.5.31 0 .6-.1.84-.27L12 11.56l4.66-4.33c.24.17.53.27.84.27.83 0 1.5-.67 1.5-1.5z"/></svg>
              </button>
              <button type="button" style={styles.toolBtn} onClick={() => selectedSegIndex !== null && deleteSegment(selectedSegIndex)} title="Delete Clip">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
              </button>
              <button type="button" style={styles.toolBtn} onClick={() => selectedSegIndex !== null && duplicateSegment(selectedSegIndex)} title="Duplicate Clip">
                📂 Dupe
              </button>
              <button type="button" style={styles.toolBtn} onClick={() => selectedSegIndex !== null && handleSegmentSwap(selectedSegIndex, selectedSegIndex - 1)} disabled={selectedSegIndex === 0} title="Move Left">
                ◀ Move
              </button>
              <button type="button" style={styles.toolBtn} onClick={() => selectedSegIndex !== null && handleSegmentSwap(selectedSegIndex, selectedSegIndex + 1)} disabled={selectedSegIndex === null || selectedSegIndex === editorData.segments.length - 1} title="Move Right">
                Move ▶
              </button>
              <button type="button" style={styles.toolBtn} onClick={addBlankSegment} title="Add New Clip">
                ➕ Add Clip
              </button>
            </div>

            {/* Selected segment properties inline editors */}
            {selectedSegIndex !== null && (
              <div style={styles.timelineSubTextEditor}>
                <span style={{ fontSize: 9, color: "#8a94a6" }}>SUBTITLE:</span>
                <input
                  value={editorData.segments[selectedSegIndex].voiceover}
                  onChange={(e) => updateSelectedSegment("voiceover", e.target.value)}
                  style={styles.subTextInput}
                />
                
                <span style={{ fontSize: 9, color: "#8a94a6", marginLeft: 8 }}>DURATION:</span>
                <input
                  type="number"
                  value={editorData.segments[selectedSegIndex].duration_hint || 5}
                  onChange={(e) => updateSelectedSegment("duration_hint", Math.max(1, parseInt(e.target.value, 10) || 1))}
                  style={styles.durTextInput}
                />

                <span style={{ fontSize: 9, color: "#8a94a6", marginLeft: 8 }}>CLIP:</span>
                <select
                  value={editorData.segments[selectedSegIndex].clip_name || ""}
                  onChange={(e) => updateSelectedSegment("clip_name", e.target.value)}
                  style={styles.clipSelectInput}
                >
                  {clips.map((c) => (
                    <option key={c.name} value={c.name}>{c.name}</option>
                  ))}
                </select>
              </div>
            )}

            <div style={styles.timelineZoomBox}>
              <span style={{ fontSize: 10, color: "#8a94a6" }}>Zoom:</span>
              <input
                type="range"
                min="4"
                max="30"
                value={zoomFactor}
                onChange={(e) => setZoomFactor(parseInt(e.target.value, 10))}
                style={styles.zoomRangeSlider}
              />
            </div>
          </div>

          {/* Subtitle Style Customization Bar */}
          <div style={styles.subtitleStyleBar}>
            <span style={styles.styleBarLabel}>Subtitle Style:</span>
            
            <span style={styles.styleSubLabel}>Font:</span>
            <select
              value={editorData.subtitle_style?.font_family || "Nirmala UI"}
              onChange={(e) => updateSubtitleStyle("font_family", e.target.value)}
              style={styles.styleSelector}
            >
              <option>Nirmala UI</option>
              <option>Arial</option>
              <option>Courier New</option>
              <option>Georgia</option>
            </select>

            <span style={styles.styleSubLabel}>Size:</span>
            <input
              type="number"
              min="12"
              max="60"
              value={editorData.subtitle_style?.font_size || 28}
              onChange={(e) => updateSubtitleStyle("font_size", parseInt(e.target.value, 10) || 28)}
              style={styles.styleSizeInput}
            />

            <span style={styles.styleSubLabel}>Text Color:</span>
            <input
              type="color"
              value={editorData.subtitle_style?.color || "#FFFFFF"}
              onChange={(e) => updateSubtitleStyle("color", e.target.value)}
              style={styles.styleColorInput}
            />

            <span style={styles.styleSubLabel}>BG Color:</span>
            <input
              type="color"
              value={editorData.subtitle_style?.bg_color?.startsWith("&H") ? "#000000" : (editorData.subtitle_style?.bg_color || "#80000000")}
              onChange={(e) => updateSubtitleStyle("bg_color", e.target.value)}
              style={styles.styleColorInput}
            />

            <button
              style={{ ...styles.styleToggleBtn, ...(editorData.subtitle_style?.bold ? styles.styleToggleBtnActive : {}) }}
              onClick={() => updateSubtitleStyle("bold", !editorData.subtitle_style?.bold)}
            >
              <b>B</b>
            </button>
            <button
              style={{ ...styles.styleToggleBtn, ...(editorData.subtitle_style?.italic ? styles.styleToggleBtnActive : {}) }}
              onClick={() => updateSubtitleStyle("italic", !editorData.subtitle_style?.italic)}
            >
              <i>I</i>
            </button>
          </div>

          {/* Timeline Multi-Track Editor View */}
          <div style={styles.timelineTracksContainer}>
            
            {/* Horizontal Timeline Ruler ticks */}
            <div style={styles.timelineRulerRow}>
              <div style={styles.trackHeaderLabelDummy}>Ruler</div>
              <div ref={timelineRulerRef} style={styles.trackTimelineRuler} onMouseDown={handleScrubberMouseDown}>
                {Array.from({ length: Math.ceil(timelineTotal) + 5 }).map((_, i) => (
                  <div key={i} style={{ ...styles.rulerTick, left: `${i * zoomFactor}px`, height: i % 5 === 0 ? 10 : 5 }}>
                    {i % 5 === 0 && <span style={styles.rulerTimeLabel}>{i}s</span>}
                  </div>
                ))}
              </div>
            </div>

            {/* Scrollable Tracks container */}
            <div style={styles.tracksScroller}>
              
              {/* Floating Vertical Scrubber Red Playhead line */}
              <div ref={playheadRef} style={{ ...styles.playheadLine, height: "100%" }}>
                <div style={styles.playheadHandle} onMouseDown={handleScrubberMouseDown}>
                  <span style={styles.playheadScissorsIcon} onClick={splitSegmentAtPlayhead}>✂️</span>
                </div>
              </div>

              {/* Video 2 Track (Logo Watermark, Stickers) */}
              <div style={{ ...styles.trackRow, opacity: trackHidden.video2 ? 0.3 : 1 }}>
                <div style={styles.trackHeader}>
                  <span style={styles.trackTitle}>Video 2</span>
                  <div style={styles.trackControls}>
                    <span onClick={() => toggleTrackHide("video2")} title="Hide Track">{trackHidden.video2 ? "🙈" : "👁️"}</span>
                    <span onClick={() => toggleTrackLock("video2")} title="Lock Track">{trackLocked.video2 ? "🔒" : "🔓"}</span>
                  </div>
                </div>
                <div style={styles.trackTrackBody}>
                  <div style={{ ...styles.logoWatermarkBlock, width: `${timelineTotal * zoomFactor}px` }}>
                    ✨ Watermark Logo Channel Overlay
                  </div>
                </div>
              </div>

              {/* Video 1 Track (Main Visual Clips) */}
              <div style={{ ...styles.trackRow, opacity: trackHidden.video1 ? 0.3 : 1 }}>
                <div style={styles.trackHeader}>
                  <span style={styles.trackTitle}>Video 1</span>
                  <div style={styles.trackControls}>
                    <span onClick={() => toggleTrackHide("video1")} title="Hide Track">{trackHidden.video1 ? "🙈" : "👁️"}</span>
                    <span onClick={() => toggleTrackLock("video1")} title="Lock Track">{trackLocked.video1 ? "🔒" : "🔓"}</span>
                  </div>
                </div>
                <div style={styles.trackTrackBody}>
                  {editorData.segments.map((seg, sIdx) => {
                    const isSelected = selectedSegIndex === sIdx;
                    const w = (seg.duration_hint || 5) * zoomFactor;
                    return (
                      <div
                        key={sIdx}
                        style={{
                          ...styles.timelineClipBlock,
                          width: `${w}px`,
                          borderColor: isSelected ? "#00E676" : "#2d3243",
                          background: isSelected ? "rgba(0, 230, 118, 0.2)" : "#151821",
                        }}
                        onClick={() => selectSegment(sIdx)}
                      >
                        <div style={styles.clipBlockHeader}>
                          #{sIdx + 1} | {seg.clip_name}
                        </div>
                        {seg.transition && <div style={styles.clipBadge}>⚡ {seg.transition}</div>}
                        {seg.effect && <div style={styles.clipBadge}>✨ {seg.effect}</div>}
                        <div style={styles.clipBlockDur}>{seg.duration_hint}s</div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Audio 1 Track (Synthesized Voice narration channel) */}
              <div style={styles.trackRow}>
                <div style={styles.trackHeader}>
                  <span style={styles.trackTitle}>Audio 1</span>
                  <div style={styles.trackControls}>
                    <span onClick={() => toggleTrackMute("audio1")} title="Mute">{trackMuted.audio1 ? "🔇" : "🔊"}</span>
                    <span onClick={() => toggleTrackLock("audio1")} title="Lock">{trackLocked.audio1 ? "🔒" : "🔓"}</span>
                  </div>
                </div>
                <div style={styles.trackTrackBody}>
                  <div style={{ ...styles.timelineVoiceoverTrack, width: `${timelineTotal * zoomFactor}px` }}>
                    🗣️ Synthesized Voiceover stream waveform block
                  </div>
                </div>
              </div>

              {/* Audio 2 Track (Ambient Bed Music channel) */}
              <div style={styles.trackRow}>
                <div style={styles.trackHeader}>
                  <span style={styles.trackTitle}>Audio 2</span>
                  <div style={styles.trackControls}>
                    <span onClick={() => toggleTrackMute("audio2")} title="Mute">{trackMuted.audio2 ? "🔇" : "🔊"}</span>
                    <span onClick={() => toggleTrackLock("audio2")} title="Lock">{trackLocked.audio2 ? "🔒" : "🔓"}</span>
                  </div>
                </div>
                <div style={styles.trackTrackBody}>
                  <div style={{ ...styles.timelineMusicTrack, width: `${timelineTotal * zoomFactor}px` }}>
                    🎵 Ambient Background Bed Music: {editorData.bg_music ? editorData.bg_music.replace(".mp3", "").replace(/_/g, " ").toUpperCase() : "NONE (SELECT FROM AUDIO LIBRARY)"}
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Project Selection Dashboard Screen ───────────────────────────────────
  return (
    <div style={styles.selectionScreen}>
      <div style={styles.toolbar}>
        <span style={styles.title}>🎬 VIDEO TIMELINE EDITOR</span>
        <button type="button" style={styles.refreshBtn} onClick={loadRecentRuns} disabled={loading}>
          ↻ REFRESH PROJECTS
        </button>
      </div>

      <div style={styles.runsGrid}>
        {loading ? (
          <div style={styles.empty}>[ LOADING RUN PROJECTS... ]</div>
        ) : recentRuns.length === 0 ? (
          <div style={styles.empty}>
            [ NO COMPILABLE RUNS FOUND ]<br /><br />
            Create a documentary first. Runs with active settings will be loaded here.
          </div>
        ) : (
          recentRuns.map((r) => (
            <div key={r.run_dir} style={styles.runCard}>
              <div style={styles.cardTitle}>{r.title}</div>
              <div style={styles.cardMeta}>{r.timestamp}</div>
              {r.topic && <div style={styles.cardTopic}>Topic: {r.topic}</div>}
              <div style={styles.cardButtons}>
                <button
                  type="button"
                  style={styles.editBtn}
                  onClick={() => {
                    setActiveRunDir(r.run_dir);
                    loadRunEditor(r.run_dir);
                  }}
                >
                  ✏️ EDIT IN TIMELINE
                </button>
                <button
                  type="button"
                  style={styles.folderBtn}
                  onClick={() => window.electronAPI?.showItemInFolder(r.run_dir)}
                >
                  OPEN FOLDER
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  // Selection Screen
  selectionScreen: { height: "100%", display: "flex", flexDirection: "column", padding: 16, background: "#0c0e14" },
  toolbar: { display: "flex", alignItems: "center", gap: 12, paddingBottom: 12, borderBottom: `1px solid #2a3040` },
  title: { color: "#00B0FF", fontWeight: 700, fontSize: 16 },
  refreshBtn: { marginLeft: "auto", padding: "6px 12px", background: "transparent", border: `1px solid #00B0FF`, color: "#00B0FF", fontSize: 12, cursor: "pointer", borderRadius: 3 },
  runsGrid: { flex: 1, overflow: "auto", paddingTop: 16 },
  empty: { textAlign: "center", color: theme.textHint, padding: 80, fontFamily: "monospace", fontSize: 14 },
  runCard: { background: "#171b26", border: `1px solid #2a3040`, padding: 16, marginBottom: 12, borderRadius: 4 },
  cardTitle: { color: "#fff", fontWeight: 700, fontSize: 14, marginBottom: 4 },
  cardMeta: { fontSize: 11, color: theme.textHint, marginBottom: 6 },
  cardTopic: { fontSize: 12, color: theme.textSec, marginBottom: 10 },
  cardButtons: { display: "flex", gap: 8 },
  editBtn: { padding: "6px 14px", background: "#00B0FF", color: "#fff", border: "none", fontSize: 11, fontWeight: 600, borderRadius: 2, cursor: "pointer" },
  folderBtn: { padding: "6px 14px", background: "#212635", border: `1px solid #2a3040`, color: theme.textSec, fontSize: 11, borderRadius: 2, cursor: "pointer" },

  // Filmora Workspace Layout
  filmoraWorkspace: { height: "100%", display: "flex", flexDirection: "column", background: "#0B0E14", color: "#d2d8e8", fontFamily: "'Inter', sans-serif" },
  filmoraHeader: { display: "flex", alignItems: "center", justifyContent: "space-between", height: 42, padding: "0 16px", background: "#121620", borderBottom: "1px solid #232836" },
  filmoraHeaderLeft: { display: "flex", alignItems: "center", gap: 20 },
  filmoraLogo: { fontSize: 12, fontWeight: 800, color: "#00B0FF", letterSpacing: 0.5 },
  menuNav: { display: "flex", gap: 14, fontSize: 11, color: "#8a94a6", cursor: "pointer" },
  projectTitleBox: { display: "flex", justifySelf: "center", width: 250 },
  projectTitleInput: { width: "100%", background: "#090B0F", border: "1px solid #232836", borderRadius: 3, padding: "4px 8px", fontSize: 11, color: "#fff", textAlign: "center" },
  filmoraHeaderRight: { display: "flex", alignItems: "center", gap: 12 },
  purchaseBadge: { padding: "3px 10px", background: "#FFD600", color: "#000", fontSize: 11, fontWeight: 700, borderRadius: 3 },
  filmoraExportBtn: { padding: "4px 18px", background: "#00E676", color: "#000", border: "none", borderRadius: 4, fontSize: 12, fontWeight: 700, cursor: "pointer", transition: "all 0.15s ease" },
  closeEditorBtn: { padding: "4px 10px", background: "#212635", border: "1px solid #232836", color: "#8a94a6", borderRadius: 4, fontSize: 11, cursor: "pointer" },

  // Top Columns Layout
  topPanelsWrapper: { height: "calc(100% - 280px)", display: "flex", borderBottom: "1px solid #232836", overflow: "hidden" },
  
  // Library Panel
  libraryPanel: { flex: 1.4, display: "flex", flexDirection: "column", borderRight: "1px solid #232836", background: "#121620" },
  libraryTabs: { display: "flex", height: 35, borderBottom: "1px solid #232836", background: "#0E1118", overflowX: "auto" },
  libTabItem: { display: "flex", alignItems: "center", padding: "0 10px", fontSize: 10, fontWeight: 600, color: "#8a94a6", cursor: "pointer", transition: "all 0.15s ease", whiteSpace: "nowrap" },
  libTabActive: { background: "#121620", color: "#fff", borderBottom: "2px solid #00B0FF" },
  libraryWorkspace: { flex: 1, display: "flex", overflow: "hidden" },
  libraryInnerSidebar: { width: 130, borderRight: "1px solid #232836", background: "#0E1118", padding: 8, display: "flex", flexDirection: "column", gap: 4 },
  innerSideItem: { padding: "6px 10px", fontSize: 10, color: "#8a94a6", borderRadius: 3, cursor: "pointer" },
  innerSideItemActive: { padding: "6px 10px", fontSize: 10, color: "#fff", background: "#1C2030", borderRadius: 3, fontWeight: 600 },
  libraryGridContent: { flex: 1, padding: 12, overflowY: "auto", background: "#121620" },
  mediaGrid: { display: "flex", flexWrap: "wrap", gap: 10 },
  importMediaTile: { width: 100, height: 80, border: "2px dashed #232836", borderRadius: 4, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", cursor: "pointer", background: "#0B0E14" },
  mediaCard: { width: 100, display: "flex", flexDirection: "column", gap: 4, cursor: "pointer" },
  mediaCardThumb: { width: "100%", height: 60, background: "#0B0E14", borderRadius: 4, position: "relative", border: "1px solid #232836", backgroundImage: "linear-gradient(45deg, #131722 25%, transparent 25%, transparent 75%, #131722 75%, #131722), linear-gradient(45deg, #131722 25%, #1b2030 25%, #1b2030 75%, #131722 75%, #131722)", backgroundSize: "20px 20px" },
  mediaCardDur: { position: "absolute", bottom: 2, right: 4, background: "rgba(0,0,0,0.7)", color: "#fff", fontSize: 9, padding: "1px 3px", borderRadius: 2 },
  mediaCardLabel: { fontSize: 10, color: "#8a94a6", textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap", textAlign: "center" },
  
  // Library lists & presets
  presetList: { display: "flex", flexDirection: "column", gap: 8 },
  presetItem: { display: "flex", alignItems: "center", gap: 10, padding: 8, background: "#0E1118", border: "1px solid #232836", borderRadius: 4, cursor: "pointer" },
  presetItemName: { fontSize: 11, fontWeight: 700, color: "#fff" },
  presetItemDetail: { fontSize: 9, color: "#8a94a6" },
  applyPresetBtn: { padding: "4px 8px", background: "#00B0FF", border: "none", color: "#fff", fontSize: 9, borderRadius: 2, cursor: "pointer", marginLeft: "auto" },
  badgeList: { display: "flex", flexWrap: "wrap", gap: 8 },
  badgeItem: { padding: "6px 12px", background: "#0E1118", border: "1px solid #232836", borderRadius: 16, color: "#fff", fontSize: 10, cursor: "pointer" },

  // Preview Panel
  previewPanel: { flex: 1.2, display: "flex", flexDirection: "column", borderRight: "1px solid #232836", background: "#121620" },
  playerTabs: { display: "flex", height: 35, borderBottom: "1px solid #232836", background: "#0E1118", paddingLeft: 12 },
  playerTabActive: { display: "flex", alignItems: "center", padding: "0 14px", fontSize: 11, fontWeight: 700, color: "#fff", borderBottom: "2px solid #00B0FF" },
  playerTab: { display: "flex", alignItems: "center", padding: "0 14px", fontSize: 11, color: "#8a94a6" },
  playerBox: { flex: 1, background: "#000", display: "flex", alignItems: "center", justifyContent: "center", minHeight: 200 },
  playerScreen: { width: "100%", height: "100%", objectFit: "contain" },
  playerScreenPlaceholder: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" },
  errorCircle: { width: 36, height: 36, borderRadius: "50%", background: "#FF5252", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, fontWeight: 700 },
  playerSubControls: { height: 40, borderTop: "1px solid #232836", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 12px", background: "#0E1118" },
  timecodeDisplay: { fontSize: 11, fontFamily: "monospace" },
  playbackButtons: { display: "flex", gap: 8, alignItems: "center" },
  playerActionBtn: { background: "none", border: "none", color: "#8a94a6", fontSize: 12, cursor: "pointer" },
  playerPlayBtn: { background: "#00B0FF", border: "none", width: 24, height: 24, borderRadius: "50%", color: "#fff", fontSize: 10, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" },
  playerAuxBtn: { background: "none", border: "none", color: "#8a94a6", fontSize: 13, cursor: "pointer", padding: "0 4px" },
  playerRightControls: { display: "flex", gap: 6, alignItems: "center" },
  playerSelector: { background: "#090B0F", border: "1px solid #232836", borderRadius: 3, padding: "2px 4px", fontSize: 9, color: "#fff" },

  // Project Info Panel
  projectInfoPanel: { width: 240, display: "flex", flexDirection: "column", background: "#121620", padding: 12, overflowY: "auto" },
  infoTitle: { fontSize: 11, fontWeight: 700, color: "#fff", borderBottom: "1px solid #232836", paddingBottom: 6, marginBottom: 8 },
  infoGrid: { display: "flex", flexDirection: "column", gap: 6, fontSize: 10 },
  infoRow: { display: "flex", justifyContent: "space-between" },
  infoLabel: { color: "#8a94a6" },
  infoValue: { color: "#fff", fontWeight: 600 },
  editInfoBtn: { marginTop: 8, padding: "4px 8px", background: "#212635", border: "1px solid #232836", color: "#fff", borderRadius: 3, fontSize: 10, cursor: "pointer" },
  buildConsole: { height: 100, marginTop: 12, border: "1px solid #232836", borderRadius: 4, background: "#090B0F", display: "flex", flexDirection: "column", padding: 8, overflow: "hidden" },
  buildConsoleTitle: { fontSize: 9, color: "#00B0FF", fontWeight: 700, marginBottom: 4 },
  buildConsoleContent: { flex: 1, overflowY: "auto", fontFamily: "monospace", fontSize: 9, color: "#A7FFEB" },
  buildConsoleLine: { marginBottom: 2, whiteSpace: "nowrap" },
  
  // Voice Recording Widget
  voiceRecorderWidget: { marginTop: 16, padding: 8, background: "#0E1118", border: "1px solid #232836", borderRadius: 4, display: "flex", flexDirection: "column", gap: 6 },
  widgetHeader: { fontSize: 10, color: "#fff", fontWeight: 700 },
  recordControls: { display: "flex", alignItems: "center", justifyContent: "space-between" },
  recordBtn: { padding: "4px 10px", background: "#00B0FF", color: "#fff", border: "none", borderRadius: 3, fontSize: 9, fontWeight: 700, cursor: "pointer" },
  recordBtnActive: { background: "#FF5252" },
  recordTimer: { fontSize: 10, color: "#FF5252", fontWeight: 700 },
  audioMeterWrap: { height: 4, background: "#232836", borderRadius: 2, overflow: "hidden" },
  audioMeterFill: { height: "100%", background: "#00E676", transition: "width 0.05s ease" },

  // Bottom Timeline Workspace
  timelineWorkspace: { height: 238, background: "#0E1118", display: "flex", flexDirection: "column" },
  timelineToolbar: { height: 35, borderBottom: "1px solid #232836", display: "flex", alignItems: "center", padding: "0 12px", gap: 8, background: "#121620" },
  timelineToolsLeft: { display: "flex", gap: 4, alignItems: "center" },
  toolBtn: { padding: "3px 8px", background: "#212635", border: "1px solid #2b3145", color: "#8a94a6", fontSize: 9, cursor: "pointer", borderRadius: 3, display: "flex", alignItems: "center", justifyContent: "center" },
  toolSeparator: { width: 1, height: 16, background: "#232836", margin: "0 4px" },
  timelineSubTextEditor: { flex: 1, display: "flex", alignItems: "center", gap: 6, maxWidth: 650, marginLeft: 6 },
  subTextInput: { flex: 1.5, background: "#090B0F", border: "1px solid #232836", borderRadius: 3, padding: "3px 6px", fontSize: 9, color: "#fff" },
  durTextInput: { width: 36, background: "#090B0F", border: "1px solid #232836", borderRadius: 3, padding: "3px 6px", fontSize: 9, color: "#fff", textAlign: "center" },
  clipSelectInput: { flex: 1, background: "#090B0F", border: "1px solid #232836", borderRadius: 3, padding: "3px 6px", fontSize: 9, color: "#fff" },
  timelineZoomBox: { display: "flex", alignItems: "center", gap: 8, marginLeft: "auto" },
  zoomRangeSlider: { width: 70, accentColor: "#00B0FF", height: 3 },

  // Subtitle custom styles bar
  subtitleStyleBar: { height: 28, background: "#0A0C12", borderBottom: "1px solid #232836", display: "flex", alignItems: "center", padding: "0 12px", gap: 10 },
  styleBarLabel: { fontSize: 10, fontWeight: 700, color: "#00B0FF" },
  styleSubLabel: { fontSize: 9, color: "#8a94a6" },
  styleSelector: { background: "#121620", border: "1px solid #232836", borderRadius: 3, fontSize: 9, color: "#fff", padding: "1px 4px" },
  styleSizeInput: { width: 35, background: "#121620", border: "1px solid #232836", borderRadius: 3, fontSize: 9, color: "#fff", padding: "1px 4px", textAlign: "center" },
  styleColorInput: { width: 22, height: 16, border: "none", background: "none", cursor: "pointer", padding: 0 },
  styleToggleBtn: { background: "#121620", border: "1px solid #232836", borderRadius: 3, color: "#8a94a6", fontSize: 9, padding: "1px 6px", cursor: "pointer" },
  styleToggleBtnActive: { background: "#00B0FF", color: "#fff" },

  // Timeline Tracks
  timelineTracksContainer: { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" },
  timelineRulerRow: { display: "flex", height: 24, borderBottom: "1px solid #232836", background: "#0B0E14", position: "relative" },
  trackHeaderLabelDummy: { width: 75, borderRight: "1px solid #232836" },
  trackTimelineRuler: { flex: 1, position: "relative", cursor: "ew-resize" },
  rulerTick: { position: "absolute", bottom: 0, width: 1, background: "#232836" },
  rulerTimeLabel: { position: "absolute", bottom: 10, left: -6, fontSize: 9, color: "#54607a", fontFamily: "monospace" },

  tracksScroller: { flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", position: "relative", overflowX: "auto" },
  
  // Playhead Vertical Scrubber Line
  playheadLine: { position: "absolute", top: 0, width: 2, background: "#FF5252", zIndex: 10, pointerEvents: "none" },
  playheadHandle: { position: "absolute", top: -20, left: -14, width: 30, height: 20, background: "#FF5252", borderRadius: "3px 3px 0 0", cursor: "ew-resize", display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "auto", boxShadow: "0 2px 4px rgba(0,0,0,0.5)" },
  playheadScissorsIcon: { fontSize: 10, cursor: "pointer" },

  // Track rows styling
  trackRow: { display: "flex", borderBottom: "1px solid #1c2030", minHeight: 44, background: "#0E1118" },
  trackHeader: { width: 75, background: "#121620", borderRight: "1px solid #232836", display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 6px", gap: 3 },
  trackTitle: { fontSize: 9, fontWeight: 700, color: "#fff" },
  trackControls: { display: "flex", gap: 6, fontSize: 10, color: "#8a94a6", cursor: "pointer" },
  trackTrackBody: { flex: 1, position: "relative", display: "flex", background: "#0A0D14" },

  logoWatermarkBlock: { background: "rgba(0, 176, 255, 0.08)", border: "1px dashed #00B0FF", display: "flex", alignItems: "center", paddingLeft: 12, fontSize: 10, color: "#00B0FF", height: "100%" },
  timelineClipBlock: { border: "1px solid", display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 6px", cursor: "pointer", overflow: "hidden", height: "100%", transition: "all 0.1s ease" },
  clipBlockHeader: { fontSize: 9, fontWeight: 700, color: "#fff", textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" },
  clipBadge: { fontSize: 8, color: "#00B0FF", fontWeight: 600, display: "inline-block", background: "rgba(0, 176, 255, 0.15)", padding: "1px 3px", borderRadius: 2, alignSelf: "flex-start", marginTop: 2 },
  clipBlockDur: { fontSize: 8, color: theme.textHint, marginTop: 2 },

  timelineVoiceoverTrack: { background: "repeating-linear-gradient(45deg, #2b1f47, #2b1f47 10px, #3a2a61 10px, #3a2a61 20px)", border: "1px solid #4a347c", display: "flex", alignItems: "center", paddingLeft: 12, fontSize: 9, color: "#b09aff", height: "100%" },
  timelineMusicTrack: { background: "repeating-linear-gradient(45deg, #103b2b, #103b2b 10px, #18523c 10px, #18523c 20px)", border: "1px solid #00E676", display: "flex", alignItems: "center", paddingLeft: 12, fontSize: 9, color: "#00E676", height: "100%" },
};
