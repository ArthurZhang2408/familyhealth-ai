## Text-Out Models

| Model | RPM | TPM | RPD | Input Price (per 1M tokens) | Output Price (per 1M tokens) | Context Caching (read per 1M tokens / storage per 1M tokens/hr) |
|---|---|---|---|---|---|---|
| `gemini-3.1-pro-preview` | 25 | 2M | 250 | $2.00 (≤200k) · $4.00 (>200k) | $12.00 (≤200k) · $18.00 (>200k) | $0.20 (≤200k) · $0.40 (>200k) / $4.50 |
| `gemini-2.5-pro` | 150 | 2M | 1K | $1.25 (≤200k) · $2.50 (>200k) | $10.00 (≤200k) · $15.00 (>200k) | $0.125 (≤200k) · $0.25 (>200k) / $4.50 |
| `gemini-3-flash-preview` | 1K | 2M | 10K | $0.50 text/img/vid · $1.00 audio | $3.00 | $0.05 text/img/vid · $0.10 audio / $1.00 |
| `gemini-2.5-flash` | 1K | 1M | 10K | $0.30 text/img/vid · $1.00 audio | $2.50 | $0.03 text/img/vid · $0.10 audio / $1.00 |
| `gemini-3.1-flash-lite-preview` | 4K | 4M | 150K | $0.25 text/img/vid · $0.50 audio | $1.50 | $0.025 text/img/vid · $0.05 audio / $1.00 |
| `gemini-2.5-flash-lite` | 4K | 4M | Unlimited | $0.10 text/img/vid · $0.30 audio | $0.40 | $0.01 text/img/vid · $0.03 audio / $1.00 |

## Text-to-Speech Models

| Model | RPM | TPM | RPD | Input Price (per 1M tokens) | Output Price (per 1M tokens) | Context Caching |
|---|---|---|---|---|---|---|
| `gemini-2.5-pro-preview-tts` | 10 | 10K | 50 | $1.00 (text) | $20.00 (audio) | Not available |
| `gemini-2.5-flash-preview-tts` | 10 | 10K | 100 | $0.50 (text) | $10.00 (audio) | Not available |

## Embedding Models

| Model | RPM | TPM | RPD | Input Price (per 1M tokens) | Output Price | Context Caching |
|---|---|---|---|---|---|---|
| `gemini-embedding-2-preview` | 3K | 1M | Unlimited | $0.25 text/img/vid · $0.50 audio | N/A | Not available |
| `gemini-embedding-001` | 3K | 1M | Unlimited | $0.15 (text only) | N/A | Not available |

## Other

| Model | Category | RPM | TPM | RPD | Input Price (per 1M tokens) | Output Price (per 1M tokens) | Context Caching (read per 1M tokens / storage per 1M tokens/hr) |
|---|---|---|---|---|---|---|---|
| `deep-research-pro-preview-12-2025` | Agents | 1 | 500K | 1.44K | $2.00 (≤200k) · $4.00 (>200k) + $14/1K search queries | $12.00 (≤200k) · $18.00 (>200k) | $0.20 (≤200k) · $0.40 (>200k) / $4.50 |
| `gemini-live-2.5-flash-native-audio` | Live API | Unlimited | 1M | Unlimited | $0.50 text · $3.00 audio/video | $2.00 text · $12.00 audio | Not available |
