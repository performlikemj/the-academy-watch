-- s4d1 pre-apply: two nullable JSON columns on player_feedback (from migrations/versions/s4d1_feedback_development.py on feat/coach-player-development; checker-verified on PG14: no tables/indexes/constraints added)
BEGIN;
ALTER TABLE public.player_feedback ADD COLUMN IF NOT EXISTS development_action json;
ALTER TABLE public.player_feedback ADD COLUMN IF NOT EXISTS development_progress json;
COMMIT;
