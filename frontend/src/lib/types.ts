export type FieldType = "TEXT" | "NUMBER" | "DATE" | "PHONE" | "EMAIL" | "SELECT" | "CHECKBOX" | "LONG_TEXT" | "SIGNATURE";
export type Role = "A" | "B";

export interface Position {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Field {
  field_id: string;
  label: string;
  type: FieldType;
  value: string | boolean | null;
  required: boolean;
  assignee: "A" | "B" | "ANY";
  page: number | null;
  position: Position | null;
  options: string[];
  validation: Record<string, unknown>;
}

export interface Suggestion {
  suggestion_id: string;
  label: string;
  type: FieldType;
  required: boolean;
  assignee: "A" | "B" | "ANY";
  match_text: string;
  start: number;
  end: number;
  line: number;
  confidence: number;
  reason: string;
  options: string[];
}

export interface PositionSuggestion {
  label: string;
  type: FieldType;
  page: number;
  position: Position;
  confidence: number;
  reason: string;
}

export interface Party {
  role: Role;
  role_label: string;
  name: string | null;
  joined: boolean;
  is_me: boolean;
  identity_status: "PENDING" | "VERIFIED";
  reviewed: boolean;
  signature_status: "PENDING" | "STARTED" | "SIGNED" | "INVALIDATED";
  signed_version_no: number | null;
  signed_at: string | null;
  invite_pending: boolean;
}

export interface Anchor {
  status: "NOT_REQUESTED" | "PENDING" | "RETRY" | "SUBMITTED" | "CONFIRMED" | "FAILED";
  tx_id?: string | null;
  network?: string;
  provider?: string;
  attempts?: number;
  confirmed_at?: string | null;
  block_number?: number | null;
  mode?: string;
  merkle_root?: string | null;
  last_error?: string | null;
  explorer_url?: string | null;
}

export interface VersionInfo {
  version_no: number;
  status: string;
  sealed: boolean;
  reason: string;
  changed_fields: string[];
  content_hash: string;
  created_at: string;
}

export interface ContractView {
  id: string;
  contract_no: string;
  title: string;
  contract_type: string;
  source: "TEXT" | "PDF" | "TEMPLATE";
  status: "DRAFT" | "READY" | "INVITED" | "SIGNING" | "COMPLETED" | "CANCELED" | "EXPIRED";
  my_role: Role;
  current_version_no: number;
  final_version_no: number | null;
  content_hash: string;
  document_hash: string | null;
  verification_id: string | null;
  completed_at: string | null;
  created_at: string;
  purge_at: string | null;
  purged: boolean;
  retention_note: string | null;
  allow_extended_retention: boolean;
  keep_encrypted_original: boolean;
  payload: { title: string; body_text: string; fields: Field[]; source: string; pages?: { width: number; height: number }[] } | null;
  parties: Party[];
  versions: VersionInfo[];
  payment: { status: string; id: string | null; amount: number | null; failure_reason: string | null };
  anchor: Anchor;
  blockchain_enabled: boolean;
  blockchain_price: number;
}

export interface ContractSummary {
  id: string;
  title: string;
  status: ContractView["status"];
  my_role: Role;
  counterparty: string | null;
  created_at: string;
  completed_at: string | null;
  anchor_status: Anchor["status"];
  needs_my_action: boolean;
}

export interface TemplateSummary {
  id: string;
  group?: "everyday" | "employment";
  name: string;
  subtitle: string;
  title: string;
  note?: string | null;
}
