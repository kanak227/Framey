-- ==========================================
-- Supabase Setup Script for Framey
-- ==========================================
-- Copy and run this script in your Supabase SQL Editor.
-- It will set up the 'jobs' table, configure Row Level Security (RLS) policies,
-- enable Realtime replication, and initialize the 'clips' storage bucket.

-- 1. Create the Jobs Table
CREATE TABLE IF NOT EXISTS public.jobs (
    id TEXT PRIMARY KEY,
    user_id UUID REFERENCES auth.users NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    step TEXT NOT NULL DEFAULT 'Initializing...',
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    clips JSONB DEFAULT '[]'::jsonb,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Enable Row Level Security (RLS)
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

-- 3. Create RLS Policies for the Jobs Table
-- Note: Background workers use the service-role client (which bypasses RLS).
-- The policies below ensure that clients using the Anon key (such as the React app)
-- can securely view only their own jobs.

DROP POLICY IF EXISTS "Users can view their own jobs" ON public.jobs;
CREATE POLICY "Users can view their own jobs"
ON public.jobs
FOR SELECT
TO authenticated
USING (auth.uid() = user_id);

-- Optional: Allow users to delete their own jobs history
DROP POLICY IF EXISTS "Users can delete their own jobs" ON public.jobs;
CREATE POLICY "Users can delete their own jobs"
ON public.jobs
FOR DELETE
TO authenticated
USING (auth.uid() = user_id);


-- 4. Enable Realtime updates for the Jobs table
-- This allows the frontend to listen to Postgres changes via WebSockets.
BEGIN;
  -- Remove the table from publication if it was already added to avoid errors
  ALTER PUBLICATION supabase_realtime DROP TABLE IF EXISTS public.jobs;
  -- Add table to publication
  ALTER PUBLICATION supabase_realtime ADD TABLE public.jobs;
COMMIT;


-- 5. Set up the 'clips' Storage Bucket
-- Ensure the public 'clips' bucket exists in Supabase Storage.
INSERT INTO storage.buckets (id, name, public)
VALUES ('clips', 'clips', TRUE)
ON CONFLICT (id) DO NOTHING;

-- Storage RLS Policies for the 'clips' Bucket:
-- 5a. Allow public read access to all files in the 'clips' bucket (needed to play generated clips)
DROP POLICY IF EXISTS "Give public access to clips" ON storage.objects;
CREATE POLICY "Give public access to clips"
ON storage.objects
FOR SELECT
TO public
USING (bucket_id = 'clips');

-- 5b. Allow authenticated users to upload video files to the 'clips' bucket
DROP POLICY IF EXISTS "Allow authenticated uploads" ON storage.objects;
CREATE POLICY "Allow authenticated uploads"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (bucket_id = 'clips');

-- 5c. Allow authenticated users to delete their uploaded files
DROP POLICY IF EXISTS "Allow authenticated deletes" ON storage.objects;
CREATE POLICY "Allow authenticated deletes"
ON storage.objects
FOR DELETE
TO authenticated
USING (bucket_id = 'clips');
