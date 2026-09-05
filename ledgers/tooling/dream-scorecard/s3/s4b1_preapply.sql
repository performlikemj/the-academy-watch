-- s4b1 pre-apply: EXACT DDL dumped (pg_dump --schema-only) from a local Postgres after 'flask db upgrade' s4a1->s4b1 of feat/pilot-p3-player-feedback @5d6aef4 (2026-09-06)
BEGIN;
CREATE TABLE IF NOT EXISTS public.player_feedback (
    id character varying(36) NOT NULL,
    thread_id character varying(36) NOT NULL,
    revision integer NOT NULL,
    program_id integer NOT NULL,
    invitation_id character varying(36) NOT NULL,
    claim_id integer NOT NULL,
    recipient_user_id integer NOT NULL,
    player_api_id integer NOT NULL,
    author_user_id integer,
    video_match_id integer,
    title character varying(140) NOT NULL,
    body text NOT NULL,
    observation_refs json DEFAULT '[]'::json NOT NULL,
    client_request_id character varying(36) NOT NULL,
    request_hash character varying(64) NOT NULL,
    published_at timestamp without time zone NOT NULL,
    acknowledged_at timestamp without time zone,
    withdrawn_at timestamp without time zone,
    audit_expires_at timestamp without time zone,
    CONSTRAINT ck_player_feedback_revision CHECK ((revision >= 1)),
    CONSTRAINT ck_player_feedback_subject CHECK (((player_api_id <> 0) AND ((player_api_id >= '-2147483647'::integer) AND (player_api_id <= 2147483647))))
);
ALTER TABLE ONLY public.player_feedback
    ADD CONSTRAINT pk_player_feedback PRIMARY KEY (id);
ALTER TABLE ONLY public.player_feedback
    ADD CONSTRAINT uq_player_feedback_request UNIQUE (program_id, client_request_id);
ALTER TABLE ONLY public.player_feedback
    ADD CONSTRAINT uq_player_feedback_revision UNIQUE (thread_id, revision);
CREATE INDEX IF NOT EXISTS ix_player_feedback_invitation ON public.player_feedback USING btree (invitation_id, thread_id, revision);
CREATE INDEX IF NOT EXISTS ix_player_feedback_recipient ON public.player_feedback USING btree (recipient_user_id, published_at, id);
ALTER TABLE ONLY public.player_feedback
    ADD CONSTRAINT fk_player_feedback_author_user_id FOREIGN KEY (author_user_id) REFERENCES public.user_accounts(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.player_feedback
    ADD CONSTRAINT fk_player_feedback_claim_id FOREIGN KEY (claim_id) REFERENCES public.player_profile_claims(id);
ALTER TABLE ONLY public.player_feedback
    ADD CONSTRAINT fk_player_feedback_invitation_id FOREIGN KEY (invitation_id) REFERENCES public.club_invitations(id);
ALTER TABLE ONLY public.player_feedback
    ADD CONSTRAINT fk_player_feedback_program_id FOREIGN KEY (program_id) REFERENCES public.club_programs(id);
ALTER TABLE ONLY public.player_feedback
    ADD CONSTRAINT fk_player_feedback_recipient_user_id FOREIGN KEY (recipient_user_id) REFERENCES public.user_accounts(id);
ALTER TABLE ONLY public.player_feedback
    ADD CONSTRAINT fk_player_feedback_video_match_id FOREIGN KEY (video_match_id) REFERENCES public.video_matches(id) ON DELETE SET NULL;
ALTER TABLE public.player_feedback ENABLE ROW LEVEL SECURITY;
COMMIT;
