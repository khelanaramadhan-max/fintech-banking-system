/**
 * Fintech — Supabase Client
 * Supabase JS v2 via CDN ESM
 */
import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';

export const SUPABASE_URL = 'https://llchohlypyizjrzuypxr.supabase.co';
export const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxsY2hvaGx5cHlpempyenV5cHhyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM2NjkwNjEsImV4cCI6MjA4OTI0NTA2MX0.THTxZkZ7Rc1pPvH1V3WGmLz4lGtfhyRYBbEBKlIHoPU';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
