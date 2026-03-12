// ── Shared ──────────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

// ── Profiles ─────────────────────────────────────────────────────────────────

export type Relationship =
  | 'self'
  | 'parent' | 'father' | 'mother'
  | 'spouse'
  | 'child' | 'son' | 'daughter'
  | 'sibling' | 'brother' | 'sister'
  | 'grandparent' | 'grandfather' | 'grandmother'
  | 'other';
export type Sex = 'male' | 'female' | 'other';
export type BloodType = 'A' | 'A+' | 'A-' | 'B' | 'B+' | 'B-' | 'AB' | 'AB+' | 'AB-' | 'O' | 'O+' | 'O-';
export type SmokingStatus = 'never' | 'former' | 'current';
export type AlcoholFrequency = 'none' | 'occasional' | 'moderate' | 'heavy';

export interface SurgicalProcedure {
  procedure: string;
  year?: number;
}

export interface Allergy {
  name: string;
  severity: string;
  reaction?: string;
}

export interface Medication {
  name: string;
  dosage?: string;
  frequency?: string;
  condition?: string;
}

export interface MedicalCondition {
  name: string;
  diagnosed_date?: string;
  status?: string;
  notes?: string;
}

export interface EmergencyContact {
  name: string;
  relationship: string;
  phone: string;
}

export interface Profile {
  id: string;
  account_id: string;
  name: string;
  relationship: Relationship;
  date_of_birth?: string;
  sex?: Sex;
  blood_type?: BloodType;
  height_cm?: number;
  weight_kg?: number;
  smoking_status?: SmokingStatus;
  alcohol_frequency?: AlcoholFrequency;
  is_pregnant?: boolean;
  surgical_history: SurgicalProcedure[];
  allergies: Allergy[];
  medications: Medication[];
  medical_conditions: MedicalCondition[];
  family_history: Record<string, string[]>;
  emergency_contacts: EmergencyContact[];
  created_at: string;
  updated_at: string;
}

export interface ProfileCreate {
  name: string;
  relationship: Relationship;
  date_of_birth?: string;
  sex?: Sex;
  blood_type?: BloodType;
  height_cm?: number;
  weight_kg?: number;
  smoking_status?: SmokingStatus;
  alcohol_frequency?: AlcoholFrequency;
  is_pregnant?: boolean;
  surgical_history?: SurgicalProcedure[];
  allergies?: Allergy[];
  medications?: Medication[];
  medical_conditions?: MedicalCondition[];
  family_history?: Record<string, string[]>;
  emergency_contacts?: EmergencyContact[];
}

export type ProfileUpdate = Partial<ProfileCreate>;

// ── Diagnosis ─────────────────────────────────────────────────────────────────

export type DiagnosisPhase = 'gathering' | 'analyzing' | 'complete';
export type Severity = 'mild' | 'moderate' | 'severe' | 'critical';
export type DiagnosisUrgency = 'routine' | 'soon' | 'urgent' | 'emergency';

export interface DifferentialDiagnosis {
  condition: string;
  confidence: number;
  reasoning: string;
  action_plan: string;
  urgency: DiagnosisUrgency;
}

export interface InformationGathered {
  chief_complaint?: string;
  onset?: string;
  location?: string;
  duration?: string;
  character?: string;
  aggravating_factors?: string[];
  relieving_factors?: string[];
  severity_rating?: number;
  associated_symptoms?: string[];
}

export interface DiagnosisState {
  phase: DiagnosisPhase;
  turn_number: number;
  severity?: Severity;
  red_flags: string[];
  information_gathered: InformationGathered;
  differential_diagnoses: DifferentialDiagnosis[];
  suggested_next_questions: string[];
  ready_for_differential: boolean;
  drug_interaction_warnings: string[];
}

export interface DiagnosisSession {
  id: string;
  profile_id: string;
  chief_complaint: string;
  title?: string;
  status: 'active' | 'closed' | 'resolved' | 'abandoned';
  diagnosis_state: DiagnosisState;
  messages: DiagnosisMessage[];
  created_at: string;
  updated_at: string;
}

export interface DiagnosisMessage {
  role: 'user' | 'assistant';
  content: string;
  content_parts?: MessagePart[];
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface DiagnosisTurnResponse {
  message: string;
  diagnosis_state: DiagnosisState;
  disclaimer: string;
}

// ── Reports ───────────────────────────────────────────────────────────────────

export type ReportFileType = 'pdf' | 'jpg' | 'jpeg' | 'png' | 'webp';
export type ReportStatus = 'pending' | 'processing' | 'complete' | 'failed';

export interface Finding {
  name: string;
  value: string;
  unit?: string;
  status: 'normal' | 'low' | 'high' | 'critical';
  reference_range?: string;
  explanation?: string;
}

export interface AnalysisResult {
  summary: string;
  findings: Finding[];
  alerts: string[];
  recommendations: string[];
}

export interface Report {
  id: string;
  profile_id: string;
  file_url: string;
  file_type: ReportFileType;
  original_filename: string;
  analysis_result?: AnalysisResult;
  extracted_facts?: Record<string, unknown>;
  status: ReportStatus;
  error_message?: string;
  disclaimer?: string;
  created_at: string;
  updated_at: string;
}

// ── Message Parts ────────────────────────────────────────────────────────────

export interface AssessmentCondition {
  name: string;
  confidence: 'most_likely' | 'possible' | 'less_likely';
  reasoning: string;
  confirming_tests?: string;
}

export interface AssessmentAction {
  action: string;
  detail?: string;
}

export interface AssessmentMedication {
  name: string;
  dosage: string;
  notes?: string;
}

export interface AssessmentTest {
  name: string;
  reason: string;
  urgency?: string;
}

export interface AssessmentSource {
  title: string;
  url: string;
}

export type MessagePart =
  | { type: 'text'; text: string }
  | { type: 'image'; url: string; mime_type: string; filename?: string }
  | { type: 'tool_call'; id: string; name: string; arguments: Record<string, unknown> }
  | { type: 'tool_result'; call_id: string; name: string; output: Record<string, unknown>; is_error?: boolean; summary?: string }
  | { type: 'agent_steps'; steps: Array<{ id: string; message: string; tool?: string; details?: string[] }> }
  | { type: 'memory_context'; memories: Array<{ text: string; date?: string }>; count: number }
  | { type: 'thinking'; text: string }
  | { type: 'structured_input'; input_type: string; prompt: string; options?: Array<Record<string, unknown>>; range?: Record<string, unknown>; selected?: unknown }
  | { type: 'assessment'; conditions: AssessmentCondition[]; self_care: AssessmentAction[]; medications: AssessmentMedication[]; tests: AssessmentTest[]; warnings: string[]; follow_up?: string; sources?: AssessmentSource[] };

// ── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  content_parts?: MessagePart[];
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface ChatConversation {
  id: string;
  profile_id: string;
  topic?: string;
  created_at: string;
  updated_at: string;
}

export interface ChatConversationDetail extends ChatConversation {
  messages: ChatMessage[];
}

export interface ChatTurnResponse {
  message: ChatMessage;
  disclaimer: string;
}

// ── Streaming ────────────────────────────────────────────────────────────────

export interface AgentStep {
  id: string;
  message: string;
  tool?: string;
  details?: string[];
  status: 'active' | 'done';
}

/** Server-Sent Event from /stream endpoints */
export type StreamEvent =
  | { type: 'status'; step: string; message: string; tool?: string; details?: string[]; conversation_id?: string; session_id?: string }
  | { type: 'text_delta'; content: string }
  | { type: 'thinking_delta'; content: string }
  | { type: 'tool_call'; tool: string; arguments?: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; summary: string }
  | { type: 'structured_question'; input_type: string; prompt: string; options?: Array<{ label: string; value: string }>; range?: { min: number; max: number; step?: number; labels?: { min: string; max: string } } }
  | { type: 'structured_assessment'; conditions: AssessmentCondition[]; self_care?: AssessmentAction[]; medications?: AssessmentMedication[]; tests?: AssessmentTest[]; warnings?: string[]; follow_up?: string; sources?: AssessmentSource[] }
  | { type: 'error'; message?: string }
  | { type: 'done'; content: string; id?: string; user_message_id?: string; conversation_id?: string; session_id?: string; disclaimer?: string; diagnosis_state?: DiagnosisState };
