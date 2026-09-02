-- s2f1 pre-apply (DRAFT from the contract; re-verify against the merged migration before running)
BEGIN;
CREATE TABLE IF NOT EXISTS public.player_fans (
  id SERIAL PRIMARY KEY,
  user_account_id INTEGER NOT NULL REFERENCES public.user_accounts(id) ON DELETE CASCADE,
  player_api_id INTEGER NOT NULL,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
  CONSTRAINT uq_player_fans_user_player UNIQUE (user_account_id, player_api_id),
  CONSTRAINT ck_player_fans_nonzero CHECK (player_api_id <> 0)
);
CREATE INDEX IF NOT EXISTS ix_player_fans_player_created ON public.player_fans (player_api_id, created_at);
ALTER TABLE public.player_fans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_accounts ADD COLUMN IF NOT EXISTS profile_activity_email_opt_in BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.user_accounts ADD COLUMN IF NOT EXISTS profile_activity_email_last_sent_at TIMESTAMP WITHOUT TIME ZONE NULL;
COMMIT;
