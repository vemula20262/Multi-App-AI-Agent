import { useCallback, useEffect, useRef, useState } from "react";
import { startRecording } from "./audio";

type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  processLocally?: boolean;
  onresult:
    | ((event: {
        results: { isFinal: boolean; 0: { transcript: string } }[];
      }) => void)
    | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
type SpeechWindow = Window & {
  SpeechRecognition?: new () => Recognition;
  webkitSpeechRecognition?: new () => Recognition;
};

export function useVoice(
  onText: (text: string) => void,
  onError: (error: string) => void,
) {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorder = useRef<Awaited<ReturnType<typeof startRecording>> | null>(
    null,
  );
  const recognition = useRef<Recognition | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const starting = useRef(false);
  const callback = useRef(onText);
  callback.current = onText;
  const errorCallback = useRef(onError);
  errorCallback.current = onError;
  const finish = useCallback(async () => {
    clearTimeout(timer.current);
    if (recognition.current) {
      recognition.current.stop();
      return;
    }
    const current = recorder.current;
    if (!current) return;
    recorder.current = null;
    setRecording(false);
    setTranscribing(true);
    try {
      const audio = await current.stop();
      const response = await fetch("/speech/transcribe", {
        method: "POST",
        headers: { "Content-Type": "audio/wav" },
        body: audio,
        signal: AbortSignal.timeout(70000),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Transcription failed.");
      if (data.text.trim()) callback.current(data.text.trim());
      else
        errorCallback.current(
          "No speech detected. Try again or type your request.",
        );
    } catch (error) {
      errorCallback.current(
        error instanceof Error ? error.message : "Could not transcribe audio.",
      );
    } finally {
      setTranscribing(false);
    }
  }, []);
  const toggle = useCallback(
    async (mode: "whisper" | "browser") => {
      if (starting.current || transcribing) return;
      if (recording) {
        await finish();
        return;
      }
      starting.current = true;
      window.speechSynthesis?.cancel();
      try {
        if (mode === "browser") {
          const win = window as SpeechWindow;
          const Constructor =
            win.SpeechRecognition || win.webkitSpeechRecognition;
          if (!Constructor)
            throw new Error(
              "This browser does not support speech recognition. Use local Whisper or text.",
            );
          const rec = new Constructor();
          if (!("processLocally" in rec))
            throw new Error(
              "On-device browser speech is unavailable. Use local Whisper; cloud recognition is disabled.",
            );
          rec.processLocally = true;
          rec.lang = "en-US";
          rec.interimResults = false;
          rec.continuous = false;
          rec.onresult = (event) => {
            const result = Array.from(event.results)
              .filter((r) => r.isFinal)
              .map((r) => r[0].transcript)
              .join(" ");
            if (result.trim()) callback.current(result.trim());
          };
          rec.onerror = (event) =>
            errorCallback.current(
              `Browser speech: ${event.error}. Use local Whisper or text input.`,
            );
          rec.onend = () => {
            setRecording(false);
            recognition.current = null;
            clearTimeout(timer.current);
          };
          recognition.current = rec;
          rec.start();
        } else recorder.current = await startRecording();
        setRecording(true);
        timer.current = setTimeout(() => void finish(), 55000);
      } catch (error) {
        recognition.current = null;
        errorCallback.current(
          error instanceof Error
            ? error.message
            : "Microphone access failed. Please use text input.",
        );
      } finally {
        starting.current = false;
      }
    },
    [recording, transcribing, finish],
  );
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      recognition.current?.abort();
      void recorder.current?.stop();
    },
    [],
  );
  return { recording, transcribing, toggle };
}
