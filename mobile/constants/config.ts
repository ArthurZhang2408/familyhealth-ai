export const Config = {
  apiUrl: process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8010/api/v1',
  supabaseUrl: process.env.EXPO_PUBLIC_SUPABASE_URL ?? '',
  supabaseAnonKey: process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? '',
} as const;
