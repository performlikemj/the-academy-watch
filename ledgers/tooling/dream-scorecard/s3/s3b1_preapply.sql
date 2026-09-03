-- s3b1 pre-apply: EXACT DDL dumped (pg_dump --schema-only) from the basecamp sim DB after 'flask db upgrade' of feat/s3-p0-billing @ c189942 on 2026-09-03, then guarded with IF NOT EXISTS. Re-verify against the MERGED migration before running on prod.
BEGIN;
CREATE TABLE IF NOT EXISTS public.billing_checkout_sessions (
    id integer NOT NULL,
    scope_type character varying(20) NOT NULL,
    scope_id integer NOT NULL,
    product_code character varying(40) NOT NULL,
    price_code character varying(20) NOT NULL,
    purchaser_user_id integer NOT NULL,
    client_key character varying(64) NOT NULL,
    stripe_session_id character varying(255),
    checkout_url text,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    expires_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    completed_at timestamp without time zone,
    CONSTRAINT ck_billing_checkout_sessions_scope_type CHECK (((scope_type)::text = ANY ((ARRAY['user'::character varying, 'club_program'::character varying])::text[]))),
    CONSTRAINT ck_billing_checkout_sessions_status CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'complete'::character varying, 'expired'::character varying])::text[])))
);
CREATE SEQUENCE IF NOT EXISTS public.billing_checkout_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.billing_checkout_sessions_id_seq OWNED BY public.billing_checkout_sessions.id;
CREATE TABLE IF NOT EXISTS public.billing_customers (
    id integer NOT NULL,
    user_account_id integer NOT NULL,
    stripe_customer_id character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS public.billing_customers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.billing_customers_id_seq OWNED BY public.billing_customers.id;
CREATE TABLE IF NOT EXISTS public.billing_subscriptions (
    id integer NOT NULL,
    scope_type character varying(20) NOT NULL,
    scope_id integer NOT NULL,
    product_code character varying(40) NOT NULL,
    price_code character varying(20) NOT NULL,
    purchaser_user_id integer,
    stripe_customer_id character varying(255) NOT NULL,
    stripe_subscription_id character varying(255) NOT NULL,
    stripe_price_id character varying(255) NOT NULL,
    status character varying(30) NOT NULL,
    unit_amount integer,
    currency character varying(3),
    "interval" character varying(10),
    current_period_start timestamp without time zone,
    current_period_end timestamp without time zone,
    cancel_at_period_end boolean DEFAULT false NOT NULL,
    canceled_at timestamp without time zone,
    last_event_created integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_billing_subscriptions_scope_type CHECK (((scope_type)::text = ANY ((ARRAY['user'::character varying, 'club_program'::character varying])::text[])))
);
CREATE SEQUENCE IF NOT EXISTS public.billing_subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.billing_subscriptions_id_seq OWNED BY public.billing_subscriptions.id;
CREATE TABLE IF NOT EXISTS public.stripe_webhook_events (
    id integer NOT NULL,
    event_id character varying(255) NOT NULL,
    event_type character varying(120) NOT NULL,
    payload_hash character varying(64) NOT NULL,
    status character varying(20) NOT NULL,
    error text,
    received_at timestamp without time zone DEFAULT now() NOT NULL,
    processed_at timestamp without time zone,
    CONSTRAINT ck_stripe_webhook_events_status CHECK (((status)::text = ANY ((ARRAY['processed'::character varying, 'ignored'::character varying, 'failed'::character varying])::text[])))
);
CREATE SEQUENCE IF NOT EXISTS public.stripe_webhook_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.stripe_webhook_events_id_seq OWNED BY public.stripe_webhook_events.id;
ALTER TABLE ONLY public.billing_checkout_sessions ALTER COLUMN id SET DEFAULT nextval('public.billing_checkout_sessions_id_seq'::regclass);
ALTER TABLE ONLY public.billing_customers ALTER COLUMN id SET DEFAULT nextval('public.billing_customers_id_seq'::regclass);
ALTER TABLE ONLY public.billing_subscriptions ALTER COLUMN id SET DEFAULT nextval('public.billing_subscriptions_id_seq'::regclass);
ALTER TABLE ONLY public.stripe_webhook_events ALTER COLUMN id SET DEFAULT nextval('public.stripe_webhook_events_id_seq'::regclass);
ALTER TABLE ONLY public.billing_checkout_sessions
    ADD CONSTRAINT billing_checkout_sessions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.billing_customers
    ADD CONSTRAINT billing_customers_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.billing_subscriptions
    ADD CONSTRAINT billing_subscriptions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.stripe_webhook_events
    ADD CONSTRAINT stripe_webhook_events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.billing_checkout_sessions
    ADD CONSTRAINT uq_billing_checkout_idem UNIQUE (scope_type, scope_id, product_code, purchaser_user_id, client_key);
ALTER TABLE ONLY public.billing_checkout_sessions
    ADD CONSTRAINT uq_billing_checkout_sessions_stripe_session_id UNIQUE (stripe_session_id);
ALTER TABLE ONLY public.billing_customers
    ADD CONSTRAINT uq_billing_customers_stripe_customer_id UNIQUE (stripe_customer_id);
ALTER TABLE ONLY public.billing_customers
    ADD CONSTRAINT uq_billing_customers_user_account_id UNIQUE (user_account_id);
ALTER TABLE ONLY public.billing_subscriptions
    ADD CONSTRAINT uq_billing_subscriptions_stripe_subscription_id UNIQUE (stripe_subscription_id);
ALTER TABLE ONLY public.stripe_webhook_events
    ADD CONSTRAINT uq_stripe_webhook_events_event_id UNIQUE (event_id);
CREATE INDEX IF NOT EXISTS ix_billing_subscriptions_purchaser_user_id ON public.billing_subscriptions USING btree (purchaser_user_id);
CREATE INDEX IF NOT EXISTS ix_billing_subscriptions_scope ON public.billing_subscriptions USING btree (scope_type, scope_id, product_code);
ALTER TABLE ONLY public.billing_checkout_sessions
    ADD CONSTRAINT billing_checkout_sessions_purchaser_user_id_fkey FOREIGN KEY (purchaser_user_id) REFERENCES public.user_accounts(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.billing_customers
    ADD CONSTRAINT billing_customers_user_account_id_fkey FOREIGN KEY (user_account_id) REFERENCES public.user_accounts(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.billing_subscriptions
    ADD CONSTRAINT billing_subscriptions_purchaser_user_id_fkey FOREIGN KEY (purchaser_user_id) REFERENCES public.user_accounts(id) ON DELETE SET NULL;
ALTER TABLE public.billing_checkout_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stripe_webhook_events ENABLE ROW LEVEL SECURITY;
COMMIT;
