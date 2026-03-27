# Landing Page Build Prompt

Build the privacy policy and terms of service pages for **salk.health**.

## Context
Salk is a family health management app (iOS, TestFlight beta). One account manages multiple health profiles (self, parents, spouse, children). AI-powered health chat, structured diagnosis, and medical report analysis. Each profile has segregated long-term memory.

## Tech Stack (for the pages)
Build as static pages hosted on salk.health. Use whatever is simplest — plain HTML, or a static site generator if one is already set up. The app links to:
- `https://salk.health/privacy`
- `https://salk.health/terms`

## Privacy Policy — Required Content

Apple requires a privacy policy for health apps. Cover these points:

### Data collected
- **Account data**: email address (via Supabase Auth), Google/Apple sign-in tokens
- **Health profiles**: name, relationship, date of birth, sex, height, weight, allergies, medications, medical conditions, surgical history, family medical history, smoking/alcohol status, pregnancy status
- **Conversations**: health chat messages, diagnosis sessions (questions + answers + assessments), medical report uploads + AI analysis results
- **Health memories**: AI-extracted health facts per profile (stored in vector database for personalized responses)
- **Usage data**: LLM interaction traces (prompts, responses, timing, token counts) for debugging and quality improvement. No PII in traces — only session IDs

### How data is stored
- **Database**: PostgreSQL hosted on Railway (US region)
- **Auth**: Supabase Auth (hosted, US)
- **File storage**: Supabase Storage for medical report uploads
- **Memory**: Mem0 with pgvector (self-hosted PostgreSQL on Railway)
- **Encryption**: All data encrypted at rest (Railway + Supabase default encryption). TLS in transit
- **Profile segregation**: Each health profile's data (conversations, memories, reports) is strictly isolated. Profile A's data is never accessible from profile B's context

### Data sharing
- **LLM providers**: Health data is sent to AI providers (Google Gemini, Cerebras, Qwen via Ollama) for processing. These providers process data per their own policies but Salk does not store data on their servers beyond the request lifecycle
- **No advertising**: Data is never sold or shared with advertisers
- **No third-party analytics**: No tracking pixels, no Google Analytics, no Facebook SDK
- **Error monitoring**: Sentry (optional, errors only — no health data in error reports)

### User rights
- **Access**: View all your data in the app
- **Deletion**: "Delete account" in Settings permanently removes all data (profiles, conversations, memories, reports) from all systems including the auth provider. This is irreversible
- **Data portability**: Not yet available (planned)
- **Contact**: [your email] for privacy questions

### Children
The app is not directed at children under 13. Health profiles for children are created and managed by their parent/guardian account holder.

### Retention
- LLM traces: auto-deleted after 30 days
- All other data: retained until account deletion
- Soft-deleted profiles: data retained for recovery but excluded from app queries

## Terms of Service — Required Content

### Medical disclaimer (CRITICAL — Apple reviews this for health apps)
- Salk provides AI-generated health information, NOT medical diagnosis or treatment
- Always consult a qualified healthcare professional
- In emergencies, call local emergency number
- AI assessments are educational tools, not replacements for professional medical advice
- Salk is not liable for health decisions made based on AI output

### Acceptable use
- One account per person
- Health profiles must be for people you have authority to manage health information for (yourself, your children, family members you care for)
- Do not use the app to make emergency medical decisions
- Do not enter false health information with intent to mislead

### Account
- Users must be 18+ to create an account
- Account holder is responsible for all profiles under their account
- Salk reserves the right to suspend accounts that violate terms

### Limitations
- AI responses may be inaccurate, outdated, or incomplete
- Service availability is not guaranteed (beta)
- Salk is not responsible for data loss during beta period (though we make reasonable efforts to prevent it)

### Beta disclaimer
- This is a beta product distributed via TestFlight
- Features may change, break, or be removed without notice
- Feedback is welcome at [your email]

## Design requirements
- Clean, readable, mobile-friendly (users will open these from the iOS app)
- Match Salk branding: primary blue (#2563eb), dark text, clean sans-serif font
- Include Salk name/logo at top
- Last updated date
- Keep it concise — real humans will read this, not just Apple reviewers
