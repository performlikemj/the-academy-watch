-- s4c1 pre-apply: EXACT DDL dumped (pg_dump --schema-only) from a local Postgres after 'flask db upgrade' s4b1->s4c1 of feat/pilot-p4-result-corrections @c986509 (2026-09-06); player_match_entries ALTERs from the same DB's catalog. The migration's legacy-adoption backfill is a no-op in prod (0 player_match_entries rows) and is intentionally not pre-applied.
BEGIN;
CREATE TABLE IF NOT EXISTS public.club_results (
    id character varying(36) NOT NULL,
    program_id integer NOT NULL,
    client_request_id character varying(36) NOT NULL,
    create_request_hash character varying(64) NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    match_date date NOT NULL,
    season integer NOT NULL,
    opponent character varying(120) NOT NULL,
    opponent_key character varying(120) NOT NULL,
    competition character varying(120),
    home_away character varying(8) NOT NULL,
    result_for integer NOT NULL,
    result_against integer NOT NULL,
    video_match_id integer,
    created_by_user_id integer,
    updated_by_user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone,
    CONSTRAINT ck_club_results_counts CHECK ((((result_for >= 0) AND (result_for <= 20)) AND ((result_against >= 0) AND (result_against <= 20)))),
    CONSTRAINT ck_club_results_home_away CHECK (((home_away)::text = ANY ((ARRAY['home'::character varying, 'away'::character varying, 'neutral'::character varying])::text[]))),
    CONSTRAINT ck_club_results_version CHECK ((version > 0))
);
ALTER TABLE ONLY public.club_results
    ADD CONSTRAINT pk_club_results PRIMARY KEY (id);
ALTER TABLE ONLY public.club_results
    ADD CONSTRAINT uq_club_results_program UNIQUE (id, program_id);
ALTER TABLE ONLY public.club_results
    ADD CONSTRAINT uq_club_results_request UNIQUE (program_id, client_request_id);
CREATE INDEX IF NOT EXISTS ix_club_results_history ON public.club_results USING btree (program_id, season, match_date, id);
CREATE INDEX IF NOT EXISTS ix_club_results_video_match_id ON public.club_results USING btree (video_match_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_club_results_active ON public.club_results USING btree (program_id, match_date, opponent_key) WHERE (deleted_at IS NULL);
ALTER TABLE ONLY public.club_results
    ADD CONSTRAINT fk_club_results_created_by_user_id FOREIGN KEY (created_by_user_id) REFERENCES public.user_accounts(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.club_results
    ADD CONSTRAINT fk_club_results_program_id FOREIGN KEY (program_id) REFERENCES public.club_programs(id);
ALTER TABLE ONLY public.club_results
    ADD CONSTRAINT fk_club_results_updated_by_user_id FOREIGN KEY (updated_by_user_id) REFERENCES public.user_accounts(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.club_results
    ADD CONSTRAINT fk_club_results_video_match_id FOREIGN KEY (video_match_id) REFERENCES public.video_matches(id) ON DELETE SET NULL;
ALTER TABLE public.club_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_match_entries ADD COLUMN IF NOT EXISTS club_result_id character varying(36);
CREATE INDEX IF NOT EXISTS ix_player_match_entries_club_result_id ON public.player_match_entries USING btree (club_result_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_match_entries_result_player ON public.player_match_entries USING btree (club_result_id, player_api_id);
COMMIT;
