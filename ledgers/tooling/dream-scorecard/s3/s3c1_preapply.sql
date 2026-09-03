-- s3c1 pre-apply: EXACT DDL dumped (pg_dump --schema-only) from a throwaway Postgres copy after 'flask db upgrade' s3b1->s3c1 of feat/s3-p2a-clubs on 2026-09-03, then guarded. Re-verify against the MERGED migration before running on prod.
BEGIN;
CREATE TABLE IF NOT EXISTS public.club_program_updates (
    id integer NOT NULL,
    program_id integer NOT NULL,
    author_user_id integer,
    title character varying(140) NOT NULL,
    body text NOT NULL,
    impact text,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    reviewed_by character varying(200),
    review_reason text,
    reviewed_at timestamp without time zone,
    published_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_club_program_updates_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying, 'withdrawn'::character varying])::text[])))
);
CREATE SEQUENCE IF NOT EXISTS public.club_program_updates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.club_program_updates_id_seq OWNED BY public.club_program_updates.id;
ALTER TABLE ONLY public.club_program_updates ALTER COLUMN id SET DEFAULT nextval('public.club_program_updates_id_seq'::regclass);
ALTER TABLE ONLY public.club_program_updates
    ADD CONSTRAINT club_program_updates_pkey PRIMARY KEY (id);
CREATE INDEX IF NOT EXISTS ix_club_program_updates_program_status_published ON public.club_program_updates USING btree (program_id, status, published_at);
ALTER TABLE ONLY public.club_program_updates
    ADD CONSTRAINT club_program_updates_author_user_id_fkey FOREIGN KEY (author_user_id) REFERENCES public.user_accounts(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.club_program_updates
    ADD CONSTRAINT club_program_updates_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.club_programs(id) ON DELETE CASCADE;
ALTER TABLE public.club_program_updates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_program_profile_revisions ADD COLUMN IF NOT EXISTS external_support_provider VARCHAR(30);
ALTER TABLE public.club_program_profile_revisions ADD COLUMN IF NOT EXISTS external_support_url VARCHAR(500);
COMMIT;
