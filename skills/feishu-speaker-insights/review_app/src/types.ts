export type Customer = {
  customer_id: string;
  name: string;
  registered?: boolean;
  directory_relpath?: string;
};

export type FileItem = {
  path: string;
  relative_path: string;
  kind: "audio" | "transcript";
};

export type Segment = {
  segment_id: string;
  label: string;
  display_label?: string;
  meeting_title?: string;
  timestamp: string;
  start: number;
  end: number;
  duration: number;
  quality: number;
  text: string;
  playable?: boolean;
};

export type Cluster = {
  cluster_id: string;
  window_count: number;
  seconds: number;
  representative_segment_ids: string[];
  segment_ids: string[];
};

export type Label = {
  label: string;
  meeting_title?: string;
  excluded_by_manifest?: boolean;
  risk: "green" | "yellow" | "red";
  risk_notes: string[];
  suggestion: { person_id?: string; name?: string; source?: string };
  quality: {
    window_count: number;
    usable_seconds: number;
    candidate_window_count?: number;
    expanded_for_mixture?: boolean;
  };
  acoustic: Record<string, unknown>;
  clusters: Cluster[];
  outlier_segment_ids: string[];
};

export type Person = {
  person_id: string;
  name: string;
  role?: string;
  scope?: string;
  organization?: string;
  customer_id?: string | null;
  current_version?: number | null;
  voiceprint_enabled?: boolean;
};

export type ProfileVersionSummary = {
  version: number;
  is_current: boolean;
  created_at?: string;
  parent_version?: number | null;
  creation_mode?: string;
  source_count: number;
  reference_count: number;
  holdout_count: number;
  usable_seconds?: number | null;
  review_session_id?: string | null;
};

export type ProfileSummary = Person & {
  customer_name?: string | null;
  profile_status: "enabled" | "disabled";
  version_count: number;
  current_version_created_at?: string | null;
  current_version_summary?: ProfileVersionSummary | null;
};

export type ProfilePage = {
  items: ProfileSummary[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type ProfileSource = {
  source_id?: string;
  customer_id?: string;
  meeting_id?: string;
  title?: string;
  audio_relative_path?: string;
  transcript_relative_path?: string;
  audio_sha256?: string;
  transcript_sha256?: string;
  selected_window_count?: number;
  kind?: string;
};

export type ProfileWindow = {
  window_id: string;
  array_kind: "references" | "heldouts";
  array_index: number;
  source_id?: string;
  meeting_title?: string;
  label?: string;
  timestamp?: string;
  start?: number;
  end?: number;
  duration?: number;
  quality?: number;
  text?: string;
};

export type ProfileVersionDetail = {
  person: Person;
  summary: ProfileVersionSummary;
  sources: ProfileSource[];
  windows: ProfileWindow[];
  model: Record<string, unknown>;
  statistics: Record<string, unknown>;
};

export type Package = {
  kind?: string;
  session_id: string;
  display_title?: string;
  manifest: {
    customer: Customer;
    meeting: { id: string; title: string };
    meetings?: { id: string; title: string }[];
  };
  people: Person[];
  labels: Label[];
  segments: Segment[];
  selection_requirements: { minimum_windows: number; minimum_seconds: number };
  profile_revision?: { person_id: string; base_version: number };
};

export type ReviewProgress = {
  phase?: string;
  message?: string;
  meeting_index?: number;
  meeting_total?: number;
  label?: string;
  label_index?: number;
  label_total?: number;
  embedding_completed?: number;
  embedding_total?: number;
  valid_window_count?: number;
};

export type ReviewJob = { status: string; progress?: ReviewProgress | null };

export type NewPerson = {
  draft_id: string;
  name: string;
  role: string;
  organization: "customer" | "yingdao";
};

export type Assignment = string | { person_id: string; include?: boolean };

export type Decision = {
  assignments: Record<string, Assignment>;
  new_people: NewPerson[];
  acknowledge_warnings?: boolean;
  make_current?: boolean;
};

export type Session = {
  session_id: string;
  kind: string;
  status: string;
  revision: number;
  decision?: Decision | null;
  package?: Package;
  playback_count?: number;
  error_message?: string;
  can_retry_edit?: boolean;
  retry_edit_reason?: string;
  job?: ReviewJob | null;
  customer_id?: string;
  customer_name?: string;
  display_title?: string;
  meeting_titles?: string[];
  recording_count?: number;
  task_type?: string;
  updated_at?: string;
  created_at?: string;
};

export type Summary = {
  customers_total: number;
  tasks: Record<string, number>;
  active_profile_people: number;
  profile_versions_total: number;
  pending_candidates: number;
  recent_sessions: Session[];
};

export type MeetingDraft = { audio: string; transcript: string };

export type TranscriptPreview = {
  path: string;
  relative_path: string;
  content: string;
  truncated: boolean;
};

export type ValidationResult = {
  valid: boolean;
  errors: string[];
  warnings: string[];
};
