# FamilyHealth AI — API Specification

**Base URL**: `https://api.familyhealth.app/v1`
**Protocol**: HTTPS only
**Content-Type**: `application/json` (unless noted otherwise)

## Table of Contents

1. [Authentication](#1-authentication)
2. [Conventions](#2-conventions)
3. [Rate Limiting](#3-rate-limiting)
4. [Endpoints — Auth](#4-endpoints--auth)
5. [Endpoints — Profiles](#5-endpoints--profiles)
6. [Endpoints — Diagnosis](#6-endpoints--diagnosis)
7. [Endpoints — Reports](#7-endpoints--reports)
8. [Endpoints — Chat](#8-endpoints--chat)
9. [Endpoints — Memory](#9-endpoints--memory)
10. [Real-Time: SSE vs WebSocket](#10-real-time-sse-vs-websocket)

---

## 1. Authentication

### Flow

```mermaid
sequenceDiagram
    participant App as Mobile App
    participant SB as Supabase Auth
    participant API as FastAPI Backend

    App->>SB: Sign in (Google / Apple / email)
    SB-->>App: access_token (JWT) + refresh_token

    App->>API: Any request<br/>Authorization: Bearer <access_token>
    API->>API: Decode JWT, verify signature<br/>against Supabase JWKS
    API->>API: Extract account_id from sub claim

    alt Token valid
        API-->>App: 200 + response
    else Token expired
        API-->>App: 401 TOKEN_EXPIRED
        App->>SB: Refresh token
        SB-->>App: New access_token
        App->>API: Retry with new token
    end
```

### JWT Details

The backend **never issues its own tokens**. Supabase Auth is the sole identity provider. The backend verifies JWTs by fetching the JWKS from Supabase at startup and caching it.

**JWT Claims used:**

| Claim | Type | Usage |
|-|-|-|
| `sub` | `string` (UUID) | Account ID — maps to `auth.users.id` |
| `email` | `string` | Display purposes, logging |
| `exp` | `number` (Unix timestamp) | Token expiration |
| `aud` | `string` | Must match configured audience |

**Header format:**

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

Every endpoint except `GET /health` requires a valid JWT. Missing or invalid tokens return `401`.

---

## 2. Conventions

### Pagination

All list endpoints accept pagination query parameters and return a paginated envelope.

**Query parameters:**

| Param | Type | Default | Description |
|-|-|-|-|
| `page` | `integer` | `1` | Page number (1-indexed) |
| `per_page` | `integer` | `20` | Items per page (max: `100`) |

**Response envelope:**

```typescript
interface PaginatedResponse<T> {
  items: T[];
  total: number;     // total items matching the query
  page: number;      // current page
  per_page: number;  // items per page
}
```

### Timestamps

All timestamps are ISO 8601 strings in UTC with timezone offset:

```
"2026-02-25T14:30:00.000Z"
```

### IDs

All entity IDs are UUIDs (v4), represented as strings:

```
"a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### Error Responses

All errors follow a consistent shape:

```typescript
interface ErrorResponse {
  detail: string;  // human-readable message
  code: string;    // machine-readable error code
}
```

**Standard error codes:**

| HTTP Status | Code | Meaning |
|-|-|-|
| 400 | `VALIDATION_ERROR` | Request body failed validation |
| 400 | `INVALID_STATUS_TRANSITION` | e.g., resolving an already-abandoned session |
| 401 | `TOKEN_MISSING` | No Authorization header |
| 401 | `TOKEN_INVALID` | JWT signature verification failed |
| 401 | `TOKEN_EXPIRED` | JWT expired — client should refresh |
| 404 | `NOT_FOUND` | Resource doesn't exist or caller has no access |
| 409 | `CONFLICT` | e.g., creating a duplicate "self" profile |
| 413 | `FILE_TOO_LARGE` | Upload exceeds size limit |
| 422 | `UNPROCESSABLE_ENTITY` | Valid JSON but semantically invalid |
| 429 | `RATE_LIMITED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Server error |
| 502 | `LLM_UNAVAILABLE` | Upstream LLM provider returned an error |
| 504 | `LLM_TIMEOUT` | Upstream LLM provider timed out |

### Medical Disclaimer

Every response from diagnosis and report analysis endpoints includes:

```typescript
interface DisclaimerMixin {
  disclaimer: "This is AI-generated health information, not a medical diagnosis. Always consult a qualified healthcare professional.";
}
```

---

## 3. Rate Limiting

### Strategy: Token Bucket per Account

Rate limits are applied per `account_id` (extracted from JWT). v1 uses in-memory rate limiting via `slowapi` with a token-bucket algorithm. For production multi-instance deployments, upgrade to Redis-backed rate limiting.

| Tier | Endpoints | Limit | Burst |
|-|-|-|-|
| Standard | `GET` on all resources | 120 req/min | 20 |
| Write | `POST`, `PATCH`, `DELETE` on profiles, memory | 60 req/min | 10 |
| LLM | Diagnosis messages, chat, report analysis | 20 req/min | 5 |
| Upload | Report uploads | 10 req/min | 3 |

**Response headers** (included on every response):

```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 117
X-RateLimit-Reset: 1740500000
```

**When rate limited** — `429`:

```json
{
  "detail": "Rate limit exceeded. Retry after 12 seconds.",
  "code": "RATE_LIMITED"
}
```

```
Retry-After: 12
```

---

## 4. Endpoints — Auth

### `POST /auth/verify`

Verify a Supabase JWT and return account info. Used on app launch to confirm the token is still valid and fetch the server-side account state.

**Request body:** None (token is in the header).

**Response `200`:**

```typescript
interface AuthVerifyResponse {
  account_id: string;   // UUID
  email: string;
  profile_count: number;
  created_at: string;   // ISO 8601
}
```

**Errors:** `401 TOKEN_MISSING`, `401 TOKEN_INVALID`, `401 TOKEN_EXPIRED`

---

### `GET /auth/me`

Get current account info. Alias for verify with a GET semantic for convenience.

**Response `200`:** Same as `POST /auth/verify`.

**Errors:** `401`

---

## 5. Endpoints — Profiles

### Types

```typescript
type Relationship = "self" | "parent" | "spouse" | "child" | "sibling" | "other";
type Sex = "male" | "female" | "other";
type BloodType = "A+" | "A-" | "B+" | "B-" | "AB+" | "AB-" | "O+" | "O-";

interface Allergy {
  allergen: string;
  severity: "mild" | "moderate" | "severe";
  reaction?: string;
}

interface Medication {
  name: string;
  dosage: string;        // e.g., "500mg"
  frequency: string;     // e.g., "2x daily"
}

interface MedicalCondition {
  condition: string;
  diagnosed?: string;    // year or date string, e.g., "2019"
  status: "active" | "resolved" | "managed";
}

interface EmergencyContact {
  name: string;
  phone: string;         // E.164 format preferred
  relationship: string;
}

interface Profile {
  id: string;                                   // UUID
  account_id: string;                           // UUID
  name: string;
  relationship: Relationship;
  sex: Sex | null;
  date_of_birth: string | null;                 // "YYYY-MM-DD"
  blood_type: BloodType | null;
  allergies: Allergy[];
  current_medications: Medication[];
  medical_conditions: MedicalCondition[];
  family_medical_history: Record<string, string[]>;  // {"father": ["heart disease"]}
  emergency_contacts: EmergencyContact[];
  created_at: string;                           // ISO 8601
  updated_at: string;                           // ISO 8601
}
```

---

### `GET /profiles`

List all profiles belonging to the authenticated account.

**Query parameters:**

| Param | Type | Default | Description |
|-|-|-|-|
| `page` | `integer` | `1` | Page number |
| `per_page` | `integer` | `20` | Items per page |

**Response `200`:**

```typescript
PaginatedResponse<Profile>
```

---

### `POST /profiles`

Create a new health profile.

**Request body:**

```typescript
interface CreateProfileRequest {
  name: string;                                          // required, 1-100 chars
  relationship: Relationship;                            // required
  sex?: Sex;
  date_of_birth?: string;                                // "YYYY-MM-DD"
  blood_type?: BloodType;
  allergies?: Allergy[];                                 // default: []
  current_medications?: Medication[];                    // default: []
  medical_conditions?: MedicalCondition[];               // default: []
  family_medical_history?: Record<string, string[]>;     // default: {}
  emergency_contacts?: EmergencyContact[];               // default: []
}
```

**Response `201`:**

```typescript
Profile
```

**Errors:**

| Status | Code | Condition |
|-|-|-|
| 400 | `VALIDATION_ERROR` | Missing required fields, invalid enum values |
| 409 | `CONFLICT` | A profile with `relationship: "self"` already exists for this account |

---

### `GET /profiles/{pid}`

Get a single profile by ID.

**Path parameters:**

| Param | Type | Description |
|-|-|-|
| `pid` | `string` (UUID) | Profile ID |

**Response `200`:**

```typescript
Profile
```

**Errors:** `404 NOT_FOUND`

---

### `PATCH /profiles/{pid}`

Partial profile update. Only provided fields are updated. Omitted fields are unchanged.

**Request body:**

```typescript
interface UpdateProfileRequest {
  name?: string;
  relationship?: Relationship;
  sex?: Sex | null;
  date_of_birth?: string | null;                         // "YYYY-MM-DD", null to clear
  blood_type?: BloodType | null;
  allergies?: Allergy[];
  current_medications?: Medication[];
  medical_conditions?: MedicalCondition[];
  family_medical_history?: Record<string, string[]>;
  emergency_contacts?: EmergencyContact[];
}
```

**Response `200`:**

```typescript
Profile  // updated profile
```

**Errors:** `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `409 CONFLICT`

---

### `DELETE /profiles/{pid}`

Soft-delete a profile. Sets `deleted_at` timestamp; the profile and its associated data are retained for 30 days before permanent deletion by a scheduled cleanup job. Mem0 memories are deleted immediately on soft delete to comply with data minimization. The profile will no longer appear in `GET /profiles` responses.

**Response `204`:** No content.

**Errors:** `404 NOT_FOUND`

---

## 6. Endpoints — Diagnosis

### Types

```typescript
type DiagnosisStatus = "active" | "resolved" | "abandoned";
type MessageRole = "user" | "assistant" | "system";

type DiagnosisUrgency = "emergency" | "see_doctor_today" | "see_doctor_this_week" | "see_doctor_soon" | "monitor_at_home";
type DiagnosisPhase = "triage" | "characterization" | "system_review" | "self_tests" | "risk_factors" | "differential" | "follow_up" | "unknown";
type Severity = "emergency" | "urgent" | "moderate" | "mild" | "informational";

interface DifferentialDiagnosis {
  condition: string;
  confidence: number;   // 0.0 – 1.0
  reasoning: string;
  action_plan: string;           // specific next steps for this condition
  urgency: DiagnosisUrgency;
}

interface InformationGathered {
  chief_complaint: string | null;
  onset: string | null;
  location: string | null;
  duration: string | null;
  character: string | null;            // sharp, dull, burning, etc.
  aggravating_factors: string | null;
  relieving_factors: string | null;
  temporal_pattern: string | null;
  severity_rating: string | null;
  associated_symptoms: string[];
  self_test_results: string[];
  relevant_risk_factors: string[];
}

interface DiagnosisState {
  phase: DiagnosisPhase;
  turn_number: number;
  severity: Severity;
  red_flags_detected: string[];
  information_gathered: InformationGathered;
  differential_diagnoses: DifferentialDiagnosis[];
  suggested_next_questions: string[];
  ready_for_differential: boolean;
  drug_interaction_warnings: string[];
}

interface DiagnosisMessage {
  id: string;           // UUID
  session_id: string;   // UUID
  role: MessageRole;
  content: string;
  created_at: string;   // ISO 8601
}

interface DiagnosisSession {
  id: string;                                // UUID
  profile_id: string;                        // UUID
  status: DiagnosisStatus;
  chief_complaint: string | null;
  differential_diagnoses: DifferentialDiagnosis[];
  resolution_notes: string | null;
  resolved_at: string | null;                // ISO 8601
  created_at: string;                        // ISO 8601
  updated_at: string;                        // ISO 8601
}

interface DiagnosisSessionWithMessages extends DiagnosisSession {
  messages: DiagnosisMessage[];
}

// Response for create_session and send_message
interface DiagnosisTurnResponse {
  message: DiagnosisMessage;        // the AI's response
  diagnosis_state: DiagnosisState;  // structured assessment state (extracted via Pass 2)
  disclaimer: string;               // always present, injected by backend
}
```

---

### `POST /profiles/{pid}/diagnosis`

Start a new diagnosis session.

**Request body:**

```typescript
interface CreateDiagnosisRequest {
  chief_complaint: string;   // required, 1-2000 chars — initial symptom description
}
```

**Response `201`:**

```typescript
DiagnosisTurnResponse
// {
//   message: DiagnosisMessage,        // AI's first response (follow-up questions or emergency escalation)
//   diagnosis_state: DiagnosisState,  // phase, severity, red flags, gathered info
//   disclaimer: string
// }
```

The backend performs a red-flag pre-check on the chief complaint. If red flags are detected, returns a templated emergency response without an LLM call. Otherwise, loads the profile (Tier 1) + episodic memories (Tier 2) via `ContextBuilder`, sends to Gemini with the diagnosis system prompt (Pass 1), extracts structured state via a second Gemini Flash call (Pass 2), and returns the AI's first response. The session is created with `status: "active"`. Memory extraction fires in the background.

**Errors:** `400 VALIDATION_ERROR`, `404 NOT_FOUND` (profile), `502 LLM_UNAVAILABLE`

---

### `GET /profiles/{pid}/diagnosis`

List diagnosis sessions for a profile.

**Query parameters:**

| Param | Type | Default | Description |
|-|-|-|-|
| `status` | `DiagnosisStatus` | (all) | Filter by status |
| `page` | `integer` | `1` | Page number |
| `per_page` | `integer` | `20` | Items per page |

**Response `200`:**

```typescript
PaginatedResponse<DiagnosisSession>  // without messages — use GET /{sid} for full history
```

---

### `GET /profiles/{pid}/diagnosis/{sid}`

Get a diagnosis session with its full message history.

**Path parameters:**

| Param | Type | Description |
|-|-|-|
| `pid` | `string` (UUID) | Profile ID |
| `sid` | `string` (UUID) | Session ID |

**Response `200`:**

```typescript
DiagnosisSessionWithMessages
```

**Errors:** `404 NOT_FOUND`

---

### `POST /profiles/{pid}/diagnosis/{sid}/messages`

Send a message in a diagnosis conversation. Returns the AI's response.

**Request body:**

```typescript
interface SendDiagnosisMessageRequest {
  content: string;   // required, 1-5000 chars
}
```

**Request headers (optional):**

| Header | Value | Effect |
|-|-|-|
| `Accept` | `text/event-stream` | Return SSE stream instead of JSON |

**Response `201` (JSON — default):**

```typescript
DiagnosisTurnResponse
// Same shape as create_session — AI response + updated diagnosis state + disclaimer
```

**Response `200` (SSE — when `Accept: text/event-stream`):**

See [Section 10: Real-Time](#10-real-time-sse-vs-websocket) for SSE format.

**Errors:**

| Status | Code | Condition |
|-|-|-|
| 400 | `INVALID_STATUS_TRANSITION` | Session is not `active` |
| 404 | `NOT_FOUND` | Profile or session not found |
| 502 | `LLM_UNAVAILABLE` | Gemini API error |
| 504 | `LLM_TIMEOUT` | Gemini did not respond within 30s |

---

### `PATCH /profiles/{pid}/diagnosis/{sid}`

Update a diagnosis session — close it, resolve it, or add notes.

**Request body:**

```typescript
interface UpdateDiagnosisRequest {
  status?: "resolved" | "abandoned";   // can only transition from "active"
  resolution_notes?: string;           // max 5000 chars
}
```

**Response `200`:**

```typescript
DiagnosisSession  // updated session
```

**Valid state transitions:**

| From | To | Trigger |
|-|-|-|
| `active` | `resolved` | User or system marks resolved |
| `active` | `abandoned` | User abandons or 7-day auto-expiry |

Transitioning to `resolved` automatically sets `resolved_at` to the current timestamp. Transitioning from `resolved` or `abandoned` is not allowed.

**Errors:** `400 INVALID_STATUS_TRANSITION`, `404 NOT_FOUND`

---

## 7. Endpoints — Reports

### Types

```typescript
type ReportFileType = "blood_test" | "xray" | "prescription" | "lab_report" | "other" | "unknown";
type ReportStatus = "pending" | "processing" | "completed" | "failed";

interface ReportFinding {
  name: string;              // "hemoglobin"
  value: number | string;    // 14.2 or "positive"
  unit: string;              // "g/dL"
  status: "normal" | "elevated" | "low" | "critical" | "positive" | "negative";
  reference_range: string;   // "12.0-17.5"
}

interface AnalysisResult {
  summary: string;
  findings: ReportFinding[];
  recommendations: string[];
  alerts: string[];          // urgent items
}

interface ReportAnalysis {
  id: string;                          // UUID
  profile_id: string;                  // UUID
  file_url: string;
  file_type: ReportFileType;
  original_filename: string | null;
  analysis_result: AnalysisResult | null;      // null while pending/processing
  extracted_facts: string[] | null;            // null while pending/processing
  status: ReportStatus;
  error_message: string | null;                // populated on failure
  created_at: string;                          // ISO 8601
  updated_at: string;                          // ISO 8601
}
```

---

### `POST /profiles/{pid}/reports`

Upload a medical report for analysis. Supports two flows:

**Flow A — Direct upload (multipart):**

```
Content-Type: multipart/form-data
```

| Field | Type | Required | Description |
|-|-|-|-|
| `file` | binary | yes | The report file (image or PDF) |
| `file_type` | `ReportFileType` | no | Hint for analysis (default: `"unknown"`) |

**Flow B — Presigned URL:**

```
Content-Type: application/json
```

```typescript
interface CreateReportPresignedRequest {
  filename: string;          // "blood_test_2026.pdf"
  file_type?: ReportFileType;
  content_type: string;      // MIME type: "application/pdf", "image/jpeg"
}
```

**Response `201` (Flow A):**

```typescript
interface CreateReportResponse extends ReportAnalysis, DisclaimerMixin {}
// status will be "pending" or "processing"
```

**Response `201` (Flow B):**

```typescript
interface CreateReportPresignedResponse {
  report_id: string;         // UUID — use to poll status
  upload_url: string;        // Supabase Storage presigned URL
  expires_in: number;        // seconds until URL expires (default: 600)
}
```

After uploading to the presigned URL, the client calls `POST /profiles/{pid}/reports/{rid}/reanalyze` to trigger analysis. (The same endpoint is used for both initial analysis and re-analysis.)

**File constraints:**

| Constraint | Value |
|-|-|
| Max file size | 20 MB |
| Allowed MIME types | `image/jpeg`, `image/png`, `image/webp`, `application/pdf` |
| Max pages (PDF) | 20 |

**Errors:** `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `413 FILE_TOO_LARGE`

---

### `GET /profiles/{pid}/reports`

List report analyses for a profile.

**Query parameters:**

| Param | Type | Default | Description |
|-|-|-|-|
| `status` | `ReportStatus` | (all) | Filter by analysis status |
| `file_type` | `ReportFileType` | (all) | Filter by report type |
| `page` | `integer` | `1` | Page number |
| `per_page` | `integer` | `20` | Items per page |

**Response `200`:**

```typescript
PaginatedResponse<ReportAnalysis>
```

---

### `GET /profiles/{pid}/reports/{rid}`

Get a specific report analysis.

**Response `200`:**

```typescript
interface GetReportResponse extends ReportAnalysis, DisclaimerMixin {}
```

`disclaimer` is included only when `status === "completed"` and `analysis_result` is present.

**Errors:** `404 NOT_FOUND`

---

### `POST /profiles/{pid}/reports/{rid}/reanalyze`

Re-trigger analysis on an existing report. Useful after a failure or to get updated analysis with new profile context.

**Request body:** None.

**Response `202`:**

```typescript
interface ReanalyzeResponse {
  report_id: string;
  status: "processing";
  message: "Analysis re-triggered successfully.";
}
```

**Errors:** `404 NOT_FOUND`, `400 INVALID_STATUS_TRANSITION` (if already `processing`)

---

## 8. Endpoints — Chat

### Types

```typescript
interface ChatConversation {
  id: string;           // UUID
  profile_id: string;   // UUID
  topic: string | null;
  created_at: string;   // ISO 8601
  updated_at: string;   // ISO 8601
}

interface ChatMessage {
  id: string;              // UUID
  conversation_id: string; // UUID
  role: MessageRole;
  content: string;
  created_at: string;      // ISO 8601
}
```

---

### `POST /profiles/{pid}/chat`

Send a general health chat message. If `conversation_id` is provided, appends to that conversation. Otherwise, creates a new conversation. The backend loads profile context and episodic memories, then routes to Qwen for a response.

**Request body:**

```typescript
interface SendChatRequest {
  content: string;           // required, 1-5000 chars
  conversation_id?: string;  // UUID — existing conversation to continue
  topic?: string;            // optional topic tag (used when creating a new conversation)
}
```

**Request headers (optional):**

| Header | Value | Effect |
|-|-|-|
| `Accept` | `text/event-stream` | Return SSE stream instead of JSON |

**Response `200` (JSON):**

```typescript
interface SendChatResponse extends DisclaimerMixin {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}
```

**Response `200` (SSE):** See [Section 10](#10-real-time-sse-vs-websocket).

**Errors:** `400 VALIDATION_ERROR`, `404 NOT_FOUND`, `502 LLM_UNAVAILABLE`, `504 LLM_TIMEOUT`

---

### `GET /profiles/{pid}/chat`

List chat conversations for a profile.

**Query parameters:**

| Param | Type | Default | Description |
|-|-|-|-|
| `topic` | `string` | (all) | Filter by topic |
| `page` | `integer` | `1` | Page number |
| `per_page` | `integer` | `20` | Items per page |

**Response `200`:**

```typescript
PaginatedResponse<ChatConversation>
```

---

### `GET /profiles/{pid}/chat/{cid}`

Get messages for a specific chat conversation.

**Query parameters:**

| Param | Type | Default | Description |
|-|-|-|-|
| `page` | `integer` | `1` | Page number |
| `per_page` | `integer` | `50` | Items per page (higher than standard 20 because chat messages are individually small and users typically scroll through recent history) |

**Response `200`:**

```typescript
PaginatedResponse<ChatMessage>
```

Messages are returned in reverse chronological order (newest first).

---

## 9. Endpoints — Memory

These endpoints expose the Mem0 episodic memory layer for debugging and admin purposes.

### Types

```typescript
interface MemoryFact {
  id: string;              // Mem0-assigned ID
  content: string;         // the extracted fact
  metadata: Record<string, unknown>;
  created_at: string;      // ISO 8601
}

interface MemorySummary {
  profile_id: string;
  total_facts: number;
  recent_facts: MemoryFact[];       // last 10
  memory_categories: {
    category: string;               // "medications", "symptoms", "lifestyle", etc.
    count: number;
  }[];
}
```

---

### `GET /profiles/{pid}/memory`

Get a summary of the memory state for a profile.

**Response `200`:**

```typescript
MemorySummary
```

---

### `GET /profiles/{pid}/memory/facts`

List all extracted episodic memory facts.

**Query parameters:**

| Param | Type | Default | Description |
|-|-|-|-|
| `page` | `integer` | `1` | Page number |
| `per_page` | `integer` | `50` | Items per page |

**Response `200`:**

```typescript
PaginatedResponse<MemoryFact>
```

---

### `DELETE /profiles/{pid}/memory/{mid}`

Delete a specific memory fact. Admin/debug only — the backend verifies the memory belongs to the given profile before deletion.

**Response `204`:** No content.

**Errors:** `404 NOT_FOUND`

---

## 10. Real-Time: SSE vs WebSocket

### Decision: SSE for Streaming Responses

We use **Server-Sent Events (SSE)** for streaming LLM responses rather than WebSocket.

**Rationale:**

| Factor | SSE | WebSocket |
|-|-|-|
| Protocol | HTTP/1.1+, works with existing infra | Separate protocol, needs upgrade |
| Direction | Server → Client (sufficient for LLM streaming) | Bidirectional (overkill here) |
| Auth | Standard `Authorization` header | Auth must be handled in handshake or first message |
| Reconnection | Built-in `EventSource` reconnect with `Last-Event-ID` | Manual reconnect logic needed |
| Load balancers | Works with standard HTTP LBs | Requires sticky sessions or WS-aware LBs |
| Railway support | Supported out of the box | Supported, but more config |
| React Native | `EventSource` polyfill available | `WebSocket` native, but auth is harder |
| Complexity | Minimal — one-way stream on existing REST endpoint | New connection lifecycle, ping/pong, state management |

**When WebSocket would be better:** If we later add features like collaborative sessions (multiple family members viewing a diagnosis in real-time) or push notifications from the server. At that point, adding a `/ws` endpoint is straightforward.

### Connection Limits

Maximum 3 concurrent SSE connections per account. Additional connection attempts receive `429 RATE_LIMITED`.

### SSE Protocol

Streaming is requested by setting `Accept: text/event-stream` on message-sending endpoints:
- `POST /profiles/{pid}/diagnosis/{sid}/messages`
- `POST /profiles/{pid}/chat`

**Event stream format:**

```
event: message_start
data: {"message_id": "uuid-of-assistant-message", "role": "assistant"}

event: content_delta
data: {"delta": "Based on your"}

event: content_delta
data: {"delta": " symptoms, I'd like"}

event: content_delta
data: {"delta": " to ask a few follow-up questions."}

event: diagnoses_update
data: {"differential_diagnoses": [{"condition": "...", "confidence": 0.6, "reasoning": "...", "action_plan": "...", "urgency": "see_doctor_this_week"}]}

event: message_end
data: {"finish_reason": "stop", "usage": {"prompt_tokens": 1200, "completion_tokens": 85}}

event: disclaimer
data: {"disclaimer": "This is AI-generated health information, not a medical diagnosis. Always consult a qualified healthcare professional."}

event: done
data: [DONE]
```

**Event types:**

| Event | Sent | Payload |
|-|-|-|
| `message_start` | Once, at stream start | `{ message_id: string, role: "assistant" }` |
| `content_delta` | Multiple times | `{ delta: string }` — incremental text chunk |
| `diagnoses_update` | Once (diagnosis only) | `{ differential_diagnoses: DifferentialDiagnosis[] }` |
| `message_end` | Once, after all content | `{ finish_reason: "stop" \| "length" \| "error", usage: { prompt_tokens: number, completion_tokens: number } }` |
| `disclaimer` | Once, after message_end | `{ disclaimer: string }` |
| `done` | Once, final event | `[DONE]` — client should close the connection |
| `error` | If error occurs mid-stream | `{ code: string, detail: string }` |

**Error during stream:**

If an error occurs after streaming has started (e.g., LLM connection drops), the server sends an `error` event and closes the stream:

```
event: error
data: {"code": "LLM_UNAVAILABLE", "detail": "Upstream provider connection lost."}
```

The client receives whatever partial content was streamed. The user message is still saved; the assistant message is saved with whatever content was generated before the error.

### Client Implementation Notes

**React Native (Expo):**

```typescript
// Use a polyfill like react-native-sse or event-source-polyfill
import EventSource from "react-native-sse";

const es = new EventSource(
  `${BASE_URL}/profiles/${pid}/diagnosis/${sid}/messages`,
  {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    method: "POST",
    body: JSON.stringify({ content: userMessage }),
  }
);

es.addEventListener("content_delta", (event) => {
  appendToMessage(JSON.parse(event.data).delta);
});

es.addEventListener("done", () => {
  es.close();
});

es.addEventListener("error", (event) => {
  handleError(JSON.parse(event.data));
  es.close();
});
```

### Fallback: JSON Polling

If SSE is unavailable (network restrictions, proxy issues), the client sends the request without `Accept: text/event-stream` and receives the full JSON response after generation completes. For long-running requests, the client shows a loading indicator.

**Timeout:** LLM responses time out after 60 seconds. If the response isn't complete by then, a `504 LLM_TIMEOUT` is returned (or an `error` SSE event if streaming).

---

## Appendix A: Full Endpoint Reference

| Method | Path | Rate Tier | Auth | Streaming |
|-|-|-|-|-|
| `POST` | `/auth/verify` | Standard | Yes | No |
| `GET` | `/auth/me` | Standard | Yes | No |
| `GET` | `/profiles` | Standard | Yes | No |
| `POST` | `/profiles` | Write | Yes | No |
| `GET` | `/profiles/{pid}` | Standard | Yes | No |
| `PATCH` | `/profiles/{pid}` | Write | Yes | No |
| `DELETE` | `/profiles/{pid}` | Write | Yes | No |
| `POST` | `/profiles/{pid}/diagnosis` | LLM | Yes | No |
| `GET` | `/profiles/{pid}/diagnosis` | Standard | Yes | No |
| `GET` | `/profiles/{pid}/diagnosis/{sid}` | Standard | Yes | No |
| `POST` | `/profiles/{pid}/diagnosis/{sid}/messages` | LLM | Yes | SSE opt-in |
| `PATCH` | `/profiles/{pid}/diagnosis/{sid}` | Write | Yes | No |
| `POST` | `/profiles/{pid}/reports` | Upload | Yes | No |
| `GET` | `/profiles/{pid}/reports` | Standard | Yes | No |
| `GET` | `/profiles/{pid}/reports/{rid}` | Standard | Yes | No |
| `POST` | `/profiles/{pid}/reports/{rid}/reanalyze` | LLM | Yes | No |
| `POST` | `/profiles/{pid}/chat` | LLM | Yes | SSE opt-in |
| `GET` | `/profiles/{pid}/chat` | Standard | Yes | No |
| `GET` | `/profiles/{pid}/chat/{cid}` | Standard | Yes | No |
| `GET` | `/profiles/{pid}/memory` | Standard | Yes | No |
| `GET` | `/profiles/{pid}/memory/facts` | Standard | Yes | No |
| `DELETE` | `/profiles/{pid}/memory/{mid}` | Write | Yes | No |

## Appendix B: Health Check

### `GET /health`

No authentication required. Used by Railway health checks and monitoring.

**Response `200`:**

```typescript
interface HealthResponse {
  status: "ok";
  version: string;        // semver: "0.1.0"
  database: "connected" | "disconnected";
  mem0: "connected" | "disconnected";
}
```
