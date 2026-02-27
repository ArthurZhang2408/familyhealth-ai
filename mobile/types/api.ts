// ── Shared ──────────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

// ── Profiles ─────────────────────────────────────────────────────────────────

export type Relationship = 'self' | 'parent' | 'spouse' | 'child' | 'sibling' | 'other';
export type Sex = 'male' | 'female' | 'other';
export type BloodType = 'A+' | 'A-' | 'B+' | 'B-' | 'AB+' | 'AB-' | 'O+' | 'O-';

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
  allergies: Allergy[];
  medications: Medication[];
  medical_conditions: MedicalCondition[];
  family_history: string[];
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
  allergies?: Allergy[];
  medications?: Medication[];
  medical_conditions?: MedicalCondition[];
  family_history?: string[];
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
  status: 'active' | 'closed' | 'resolved' | 'abandoned';
  diagnosis_state: DiagnosisState;
  messages: DiagnosisMessage[];
  created_at: string;
  updated_at: string;
}

export interface DiagnosisMessage {
  role: 'user' | 'assistant';
  content: string;
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

// ── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
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
