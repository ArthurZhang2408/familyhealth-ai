export const Config = {
  apiUrl: process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8010/api/v1',
  supabaseUrl: process.env.EXPO_PUBLIC_SUPABASE_URL ?? '',
  supabaseAnonKey: process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? '',
} as const;

/** Dev mode shows detailed agent step internals (tool args, thinking text, memory contents). Prod mode shows polished summary UI. */
export const isDevMode = process.env.EXPO_PUBLIC_DEV_MODE === 'true';
