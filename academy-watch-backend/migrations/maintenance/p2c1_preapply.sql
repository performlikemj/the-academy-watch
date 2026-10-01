-- Phase2 C1: preapply after p2b3, before deploying p2c1 code. No flag activation.
BEGIN;
ALTER TABLE public.contact_requests ADD COLUMN IF NOT EXISTS club_first BOOLEAN NOT NULL DEFAULT false;
DO $$ BEGIN
IF to_regclass('public.club_player_publications') IS NULL THEN
CREATE TABLE public.club_player_publications (
 id SERIAL PRIMARY KEY,
 program_id INTEGER NOT NULL REFERENCES public.club_programs(id),
 local_player_id INTEGER NOT NULL REFERENCES public.local_players(id),
 recipient_email VARCHAR(254),
 recipient_user_id INTEGER REFERENCES public.user_accounts(id),
 claim_id INTEGER REFERENCES public.player_profile_claims(id),
 invite_token_hash VARCHAR(64) UNIQUE, invite_expires_at TIMESTAMP,
 adult_invited_at TIMESTAMP NOT NULL, claimed_at TIMESTAMP,
 association_confirmed_at TIMESTAMP,
 association_confirmed_by INTEGER REFERENCES public.user_accounts(id),
 consent_version VARCHAR(40), consented_at TIMESTAMP,
 moderation_status VARCHAR(20) NOT NULL DEFAULT 'pending',
 reviewed_by VARCHAR(254), reviewed_at TIMESTAMP,
 withdrawn_at TIMESTAMP, club_revoked_at TIMESTAMP,
 creator_user_id INTEGER REFERENCES public.user_accounts(id),
 version INTEGER NOT NULL DEFAULT 1,
 created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
 CONSTRAINT uq_club_player_publication UNIQUE(program_id,local_player_id),
 CONSTRAINT ck_publication_moderation CHECK(moderation_status IN ('pending','approved','rejected')),
 CONSTRAINT ck_publication_version CHECK(version > 0)
);
END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_publication_recipient ON public.club_player_publications(recipient_user_id);
ALTER TABLE public.club_player_publications ALTER COLUMN recipient_email DROP NOT NULL;
CREATE INDEX IF NOT EXISTS ix_publication_local_player ON public.club_player_publications(local_player_id);
ALTER TABLE public.club_player_publications ENABLE ROW LEVEL SECURITY;
DROP INDEX IF EXISTS public.uq_profile_claim_local_player_user;
CREATE UNIQUE INDEX uq_profile_claim_local_player_user ON public.player_profile_claims(local_player_id, user_account_id) WHERE verification_method IS NULL OR verification_method <> 'club_vouch_retired';
DO $$ BEGIN
IF to_regclass('public.follows') IS NOT NULL THEN
UPDATE public.follows f SET label = NULL FROM public.local_players p WHERE f.kind = 'player' AND f.label IS NOT NULL AND f.selector->>'player_api_id' = (-p.id)::text AND p.provenance = 'club';
END IF;
END $$;
COMMIT;
