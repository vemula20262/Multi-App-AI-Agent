export type AgentResponse = {
  status: "CLARIFICATION_NEEDED" | "PERMISSION_REQUIRED" | "COMPLETE" | "ERROR";
  interrupt_id: string | null;
  speech_to_say: string;
  action_type: string;
  data: {
    [key: string]: unknown;
    url?: string;
    expires_at?: number;
    max_characters?: number;
    missing_slot?: string;
    draft_content?: string;
    summary?: string;
    engine?: string;
    dom_read?: boolean;
    audit?: { event: string; at: number }[];
  };
};
export type Health = {
  status: string;
  llm: { available: boolean; model: string; mode: string };
  speech: { available: boolean; engine: string };
  browser: { headless: boolean };
};
export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: AgentResponse;
  time: string;
};
