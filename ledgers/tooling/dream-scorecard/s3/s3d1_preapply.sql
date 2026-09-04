-- s3d1 pre-apply: EXACT DDL dumped (pg_dump --schema-only) from a throwaway Postgres copy after 'flask db upgrade' s3c1->s3d1 of feat/gol-credits-backend @200afbb on 2026-09-04, then guarded. Re-verify against the MERGED migration before running on prod.
BEGIN;
CREATE TABLE IF NOT EXISTS public.gol_credit_ledger (
    id integer NOT NULL,
    user_account_id integer NOT NULL,
    bucket character varying(20) NOT NULL,
    kind character varying(20) NOT NULL,
    delta integer NOT NULL,
    idempotency_key character varying(120) NOT NULL,
    debit_id integer,
    client_msg_id character varying(64),
    attempt integer,
    stripe_event_id character varying(255),
    stripe_session_id character varying(255),
    stripe_payment_intent_id character varying(255),
    pack_id character varying(40),
    amount_paid_cents integer,
    currency character varying(3),
    refunded_cents integer DEFAULT 0 NOT NULL,
    note character varying(200),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_gol_credit_ledger_bucket CHECK (((bucket)::text = ANY ((ARRAY['free_allowance'::character varying, 'prepaid'::character varying])::text[]))),
    CONSTRAINT ck_gol_credit_ledger_delta_nonzero CHECK ((delta <> 0)),
    CONSTRAINT ck_gol_credit_ledger_kind CHECK (((kind)::text = ANY ((ARRAY['grant'::character varying, 'debit'::character varying, 'reversal'::character varying, 'adjustment'::character varying])::text[])))
);
CREATE SEQUENCE IF NOT EXISTS public.gol_credit_ledger_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.gol_credit_ledger_id_seq OWNED BY public.gol_credit_ledger.id;
ALTER TABLE ONLY public.gol_credit_ledger ALTER COLUMN id SET DEFAULT nextval('public.gol_credit_ledger_id_seq'::regclass);
ALTER TABLE ONLY public.gol_credit_ledger
    ADD CONSTRAINT gol_credit_ledger_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.gol_credit_ledger
    ADD CONSTRAINT uq_gol_credit_ledger_idempotency_key UNIQUE (idempotency_key);
ALTER TABLE ONLY public.gol_credit_ledger
    ADD CONSTRAINT uq_gol_credit_ledger_stripe_session_id UNIQUE (stripe_session_id);
CREATE INDEX IF NOT EXISTS ix_gol_credit_ledger_payment_intent ON public.gol_credit_ledger USING btree (stripe_payment_intent_id);
CREATE INDEX IF NOT EXISTS ix_gol_credit_ledger_user_bucket ON public.gol_credit_ledger USING btree (user_account_id, bucket);
ALTER TABLE ONLY public.gol_credit_ledger
    ADD CONSTRAINT gol_credit_ledger_debit_id_fkey FOREIGN KEY (debit_id) REFERENCES public.gol_credit_ledger(id);
ALTER TABLE ONLY public.gol_credit_ledger
    ADD CONSTRAINT gol_credit_ledger_user_account_id_fkey FOREIGN KEY (user_account_id) REFERENCES public.user_accounts(id) ON DELETE CASCADE;
ALTER TABLE public.gol_credit_ledger ENABLE ROW LEVEL SECURITY;
COMMIT;
