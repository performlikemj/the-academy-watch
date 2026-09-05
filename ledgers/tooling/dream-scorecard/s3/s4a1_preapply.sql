-- s4a1 pre-apply: EXACT DDL dumped (pg_dump --schema-only) from a local Postgres after 'flask db upgrade' s3e1->s4a1 of feat/pilot-p2-club-relationship @fbd3226 (2026-09-05); roster ALTERs derived from the same DB's catalog
BEGIN;
CREATE TABLE IF NOT EXISTS public.club_invitations (
    id character varying(36) NOT NULL,
    program_id integer NOT NULL,
    player_api_id integer NOT NULL,
    claim_id integer NOT NULL,
    recipient_user_id integer NOT NULL,
    created_by_user_id integer,
    source_manager_claim_id integer,
    client_request_id character varying(36) NOT NULL,
    request_hash character varying(64) NOT NULL,
    status character varying(20) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    responded_at timestamp without time zone,
    revoked_at timestamp without time zone,
    CONSTRAINT ck_club_invitation_expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_club_invitation_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'accepted'::character varying, 'declined'::character varying, 'revoked'::character varying, 'expired'::character varying])::text[]))),
    CONSTRAINT ck_club_invitation_subject CHECK ((player_api_id <> 0))
);
ALTER TABLE ONLY public.club_invitations
    ADD CONSTRAINT pk_club_invitations PRIMARY KEY (id);
ALTER TABLE ONLY public.club_invitations
    ADD CONSTRAINT uq_club_invitation_request UNIQUE (program_id, created_by_user_id, client_request_id);
CREATE INDEX IF NOT EXISTS ix_club_invitation_program ON public.club_invitations USING btree (program_id, status, created_at, id);
CREATE INDEX IF NOT EXISTS ix_club_invitation_recipient ON public.club_invitations USING btree (recipient_user_id, status, created_at, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_club_invitation_active ON public.club_invitations USING btree (program_id, player_api_id) WHERE ((status)::text = ANY ((ARRAY['pending'::character varying, 'accepted'::character varying])::text[]));
ALTER TABLE ONLY public.club_invitations
    ADD CONSTRAINT fk_club_invitations_claim_id FOREIGN KEY (claim_id) REFERENCES public.player_profile_claims(id);
ALTER TABLE ONLY public.club_invitations
    ADD CONSTRAINT fk_club_invitations_created_by_user_id FOREIGN KEY (created_by_user_id) REFERENCES public.user_accounts(id);
ALTER TABLE ONLY public.club_invitations
    ADD CONSTRAINT fk_club_invitations_program_id FOREIGN KEY (program_id) REFERENCES public.club_programs(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.club_invitations
    ADD CONSTRAINT fk_club_invitations_recipient_user_id FOREIGN KEY (recipient_user_id) REFERENCES public.user_accounts(id);
ALTER TABLE ONLY public.club_invitations
    ADD CONSTRAINT fk_club_invitations_source_manager_claim_id FOREIGN KEY (source_manager_claim_id) REFERENCES public.club_program_claims(id) ON DELETE SET NULL;
ALTER TABLE public.club_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_roster_members ADD COLUMN IF NOT EXISTS requires_player_acceptance boolean NOT NULL DEFAULT false;
ALTER TABLE public.club_roster_members ADD COLUMN IF NOT EXISTS accepted_invitation_id character varying(36);
CREATE INDEX IF NOT EXISTS ix_club_roster_members_accepted_invitation_id ON public.club_roster_members USING btree (accepted_invitation_id);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_club_roster_members_accepted_invitation_id') THEN
    ALTER TABLE public.club_roster_members ADD CONSTRAINT fk_club_roster_members_accepted_invitation_id FOREIGN KEY (accepted_invitation_id) REFERENCES public.club_invitations(id) ON DELETE SET NULL;
  END IF;
END $$;
COMMIT;
