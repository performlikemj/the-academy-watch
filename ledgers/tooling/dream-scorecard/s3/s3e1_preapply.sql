-- s3e1 pre-apply: EXACT DDL dumped (pg_dump --schema-only) from a local Postgres after 'flask db upgrade' s3d1->s3e1 of fix/ms-m1-money-safety @0a9f32c (2026-09-05)
BEGIN;
CREATE TABLE IF NOT EXISTS public.gol_chat_executions (
    id integer NOT NULL,
    user_account_id integer NOT NULL,
    client_msg_id character varying(64) NOT NULL,
    attempt integer NOT NULL,
    debit_id integer,
    status character varying(20) NOT NULL,
    input_hash character varying(64) NOT NULL,
    lease_generation integer DEFAULT 1 NOT NULL,
    lease_started_at timestamp without time zone DEFAULT now() NOT NULL,
    response_text text,
    response_events text,
    recover_count integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    completed_at timestamp without time zone,
    CONSTRAINT ck_gol_chat_execution_status CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])))
);
CREATE SEQUENCE IF NOT EXISTS public.gol_chat_executions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.gol_chat_executions_id_seq OWNED BY public.gol_chat_executions.id;
CREATE TABLE IF NOT EXISTS public.gol_checkout_terms (
    id integer NOT NULL,
    purchase_key character varying(36) NOT NULL,
    checkout_row_id integer,
    stripe_session_id character varying(255),
    price_code character varying(40) NOT NULL,
    credits integer NOT NULL,
    unit_amount_cents integer NOT NULL,
    currency character varying(3) NOT NULL,
    stripe_price_id character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    attached_at timestamp without time zone
);
CREATE SEQUENCE IF NOT EXISTS public.gol_checkout_terms_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.gol_checkout_terms_id_seq OWNED BY public.gol_checkout_terms.id;
CREATE TABLE IF NOT EXISTS public.gol_payment_settlements (
    id integer NOT NULL,
    stripe_payment_intent_id character varying(255) NOT NULL,
    grant_ledger_id integer,
    refund_target_cents integer DEFAULT 0 NOT NULL,
    refund_applied_cents integer DEFAULT 0 NOT NULL,
    last_refund_event_id character varying(255),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS public.gol_payment_settlements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.gol_payment_settlements_id_seq OWNED BY public.gol_payment_settlements.id;
ALTER TABLE ONLY public.gol_chat_executions ALTER COLUMN id SET DEFAULT nextval('public.gol_chat_executions_id_seq'::regclass);
ALTER TABLE ONLY public.gol_checkout_terms ALTER COLUMN id SET DEFAULT nextval('public.gol_checkout_terms_id_seq'::regclass);
ALTER TABLE ONLY public.gol_payment_settlements ALTER COLUMN id SET DEFAULT nextval('public.gol_payment_settlements_id_seq'::regclass);
ALTER TABLE ONLY public.gol_chat_executions
    ADD CONSTRAINT gol_chat_executions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.gol_checkout_terms
    ADD CONSTRAINT gol_checkout_terms_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.gol_payment_settlements
    ADD CONSTRAINT gol_payment_settlements_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.gol_chat_executions
    ADD CONSTRAINT uq_gol_chat_execution_attempt UNIQUE (user_account_id, client_msg_id, attempt);
ALTER TABLE ONLY public.gol_checkout_terms
    ADD CONSTRAINT uq_gol_checkout_terms_purchase_key UNIQUE (purchase_key);
ALTER TABLE ONLY public.gol_checkout_terms
    ADD CONSTRAINT uq_gol_checkout_terms_session UNIQUE (stripe_session_id);
ALTER TABLE ONLY public.gol_payment_settlements
    ADD CONSTRAINT uq_gol_payment_settlements_intent UNIQUE (stripe_payment_intent_id);
CREATE INDEX IF NOT EXISTS ix_gol_chat_executions_debit ON public.gol_chat_executions USING btree (debit_id);
CREATE INDEX IF NOT EXISTS ix_gol_checkout_terms_checkout_row_id ON public.gol_checkout_terms USING btree (checkout_row_id);
CREATE INDEX IF NOT EXISTS ix_gol_payment_settlements_grant_ledger_id ON public.gol_payment_settlements USING btree (grant_ledger_id);
ALTER TABLE ONLY public.gol_chat_executions
    ADD CONSTRAINT gol_chat_executions_debit_id_fkey FOREIGN KEY (debit_id) REFERENCES public.gol_credit_ledger(id);
ALTER TABLE ONLY public.gol_chat_executions
    ADD CONSTRAINT gol_chat_executions_user_account_id_fkey FOREIGN KEY (user_account_id) REFERENCES public.user_accounts(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.gol_checkout_terms
    ADD CONSTRAINT gol_checkout_terms_checkout_row_id_fkey FOREIGN KEY (checkout_row_id) REFERENCES public.billing_checkout_sessions(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.gol_payment_settlements
    ADD CONSTRAINT gol_payment_settlements_grant_ledger_id_fkey FOREIGN KEY (grant_ledger_id) REFERENCES public.gol_credit_ledger(id) ON DELETE SET NULL;
ALTER TABLE public.gol_chat_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gol_checkout_terms ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gol_payment_settlements ENABLE ROW LEVEL SECURITY;
COMMIT;
