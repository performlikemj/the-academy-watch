BEGIN;
CREATE TABLE IF NOT EXISTS public.player_match_entries (
  id SERIAL PRIMARY KEY, player_api_id INTEGER NOT NULL, season INTEGER NOT NULL, source VARCHAR(16) NOT NULL, status VARCHAR(16) NOT NULL,
  reported_by_user_id INTEGER NOT NULL REFERENCES public.user_accounts(id), club_program_id INTEGER REFERENCES public.club_programs(id),
  match_date DATE NOT NULL, competition VARCHAR(120), opponent VARCHAR(120) NOT NULL, home_away VARCHAR(8) NOT NULL, result_for INTEGER, result_against INTEGER,
  minutes INTEGER DEFAULT 0 NOT NULL, goals INTEGER DEFAULT 0 NOT NULL, assists INTEGER DEFAULT 0 NOT NULL, yellows INTEGER DEFAULT 0 NOT NULL, reds INTEGER DEFAULT 0 NOT NULL, saves INTEGER, goals_conceded INTEGER, note VARCHAR(500), created_at TIMESTAMPTZ DEFAULT now() NOT NULL, updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  CONSTRAINT ck_player_match_entries_source CHECK (source IN ('self','club')), CONSTRAINT ck_player_match_entries_status CHECK (status IN ('self_reported','club_confirmed','disputed')), CONSTRAINT ck_player_match_entries_home_away CHECK (home_away IN ('home','away','neutral')),
  CONSTRAINT ck_player_match_entries_minutes CHECK (minutes BETWEEN 0 AND 130), CONSTRAINT ck_player_match_entries_counts CHECK (goals BETWEEN 0 AND 20 AND assists BETWEEN 0 AND 20 AND yellows BETWEEN 0 AND 20 AND reds BETWEEN 0 AND 20), CONSTRAINT ck_player_match_entries_optional_counts CHECK ((result_for IS NULL OR result_for BETWEEN 0 AND 20) AND (result_against IS NULL OR result_against BETWEEN 0 AND 20) AND (saves IS NULL OR saves BETWEEN 0 AND 20) AND (goals_conceded IS NULL OR goals_conceded BETWEEN 0 AND 20)),
  CONSTRAINT uq_player_match_entries_identity UNIQUE (player_api_id,match_date,opponent,source,reported_by_user_id)
);
CREATE INDEX IF NOT EXISTS ix_player_match_entries_player_season ON public.player_match_entries(player_api_id,season); CREATE INDEX IF NOT EXISTS ix_player_match_entries_club_program ON public.player_match_entries(club_program_id);
ALTER TABLE "player_match_entries" ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS public.showcase_moderation_events (
  id SERIAL PRIMARY KEY, user_account_id INTEGER REFERENCES public.user_accounts(id), target_kind VARCHAR(32) NOT NULL, target_id INTEGER NOT NULL, action VARCHAR(32) NOT NULL, actor_email VARCHAR(255), metadata JSON, created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  CONSTRAINT ck_showcase_moderation_events_action CHECK (action IN ('approved','rejected','revoked','suppressed'))
);
CREATE INDEX IF NOT EXISTS ix_showcase_moderation_events_user_created ON public.showcase_moderation_events(user_account_id,created_at);
ALTER TABLE "showcase_moderation_events" ENABLE ROW LEVEL SECURITY;
DO $pm01$
BEGIN
  IF to_regclass('public.local_players') IS NOT NULL AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='local_players' AND column_name='api_player_id') AND NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname='ux_local_players_api_player_id') THEN
    IF EXISTS (SELECT 1 FROM public.local_players WHERE api_player_id IS NOT NULL GROUP BY api_player_id HAVING COUNT(*) > 1) THEN
      RAISE WARNING 'Skipping ux_local_players_api_player_id: duplicate non-null api_player_id values';
    ELSE
      EXECUTE 'CREATE UNIQUE INDEX ux_local_players_api_player_id ON public.local_players(api_player_id) WHERE api_player_id IS NOT NULL';
    END IF;
  END IF;
END;
$pm01$;
COMMIT;
