BEGIN;
CREATE TABLE IF NOT EXISTS player_highlights (
	id VARCHAR(36) NOT NULL, 
	program_id INTEGER NOT NULL, 
	video_match_id INTEGER, 
	roster_entry_id INTEGER, 
	tracklet_id INTEGER, 
	player_api_id INTEGER, 
	local_player_id INTEGER, 
	claim_id INTEGER, 
	recipient_user_id INTEGER, 
	picker_user_id INTEGER, 
	pick_key VARCHAR(64) NOT NULL, 
	source_etag VARCHAR(100) NOT NULL, 
	source_snapshot VARCHAR(64) NOT NULL, 
	source_fingerprint VARCHAR(64) NOT NULL, 
	source_version INTEGER DEFAULT '1' NOT NULL, 
	start_s FLOAT NOT NULL, 
	end_s FLOAT NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	version INTEGER DEFAULT '1' NOT NULL, 
	club_picked_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	player_decision VARCHAR(20) DEFAULT 'pending' NOT NULL, 
	decision_user_id INTEGER, 
	decision_at TIMESTAMP WITHOUT TIME ZONE, 
	approved_source_version INTEGER, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE, 
	revoke_reason VARCHAR(30), 
	render_status VARCHAR(20) DEFAULT 'queued' NOT NULL, 
	output_blob_path VARCHAR(500), 
	output_etag VARCHAR(100), 
	output_bytes INTEGER, 
	render_source_version INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_player_highlights_pick UNIQUE (pick_key), 
	CONSTRAINT ck_highlight_subject_xor CHECK ((player_api_id IS NOT NULL AND local_player_id IS NULL) OR (player_api_id IS NULL AND local_player_id IS NOT NULL)), 
	CONSTRAINT ck_highlight_range CHECK (start_s >= 0 AND end_s > start_s AND end_s-start_s <= 60), 
	CONSTRAINT ck_highlight_decision CHECK (player_decision IN ('pending','approve','private')), 
	CONSTRAINT ck_highlight_render CHECK (render_status IN ('queued','running','ready','failed','stale')), 
	FOREIGN KEY(program_id) REFERENCES club_programs (id) ON DELETE CASCADE, 
	FOREIGN KEY(video_match_id) REFERENCES video_matches (id) ON DELETE SET NULL, 
	FOREIGN KEY(roster_entry_id) REFERENCES video_roster_entries (id) ON DELETE SET NULL, 
	FOREIGN KEY(tracklet_id) REFERENCES video_tracklets (id) ON DELETE SET NULL, 
	FOREIGN KEY(local_player_id) REFERENCES local_players (id) ON DELETE CASCADE, 
	FOREIGN KEY(claim_id) REFERENCES player_profile_claims (id) ON DELETE SET NULL, 
	FOREIGN KEY(recipient_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL, 
	FOREIGN KEY(picker_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL, 
	FOREIGN KEY(decision_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL
);
ALTER TABLE public.player_highlights ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS highlight_consent_events (
	id SERIAL NOT NULL, 
	highlight_id VARCHAR(36) NOT NULL, 
	actor_user_id INTEGER, 
	action VARCHAR(30) NOT NULL, 
	version INTEGER NOT NULL, 
	source_version INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(highlight_id) REFERENCES player_highlights (id) ON DELETE CASCADE, 
	FOREIGN KEY(actor_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL
);
ALTER TABLE public.highlight_consent_events ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS highlight_footage_reviews (
	video_match_id INTEGER NOT NULL, 
	reviewer_user_id INTEGER, 
	classification VARCHAR(20) NOT NULL, 
	source_etag VARCHAR(100) NOT NULL, 
	source_snapshot VARCHAR(64) NOT NULL, 
	reviewed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (video_match_id), 
	CONSTRAINT ck_highlight_footage_review CHECK (classification IN ('adult_only','private')), 
	FOREIGN KEY(video_match_id) REFERENCES video_matches (id) ON DELETE CASCADE, 
	FOREIGN KEY(reviewer_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL
);
ALTER TABLE public.highlight_footage_reviews ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS highlight_render_jobs (
	id VARCHAR(36) NOT NULL, 
	highlight_id VARCHAR(36), 
	kind VARCHAR(30) NOT NULL, 
	source_version INTEGER, 
	status VARCHAR(20) DEFAULT 'queued' NOT NULL, 
	attempt INTEGER DEFAULT '0' NOT NULL, 
	lease_token VARCHAR(36), 
	lease_expires_at TIMESTAMP WITHOUT TIME ZONE, 
	blob_path VARCHAR(500), 
	error_code VARCHAR(40), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_highlight_job_kind CHECK (kind IN ('highlight_cut','highlight_delete')), 
	CONSTRAINT ck_highlight_job_status CHECK (status IN ('queued','running','succeeded','failed','cancelled')), 
	FOREIGN KEY(highlight_id) REFERENCES player_highlights (id) ON DELETE SET NULL
);
ALTER TABLE public.highlight_render_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.highlight_footage_reviews ADD COLUMN IF NOT EXISTS squad_adult_attested BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS ix_player_highlights_local_player_id ON player_highlights (local_player_id);
CREATE INDEX IF NOT EXISTS ix_player_highlights_recipient_user_id ON player_highlights (recipient_user_id);
CREATE INDEX IF NOT EXISTS ix_player_highlights_video_match_id ON player_highlights (video_match_id);
CREATE INDEX IF NOT EXISTS ix_player_highlights_player_api_id ON player_highlights (player_api_id);
CREATE INDEX IF NOT EXISTS ix_player_highlights_program_id ON player_highlights (program_id);
CREATE INDEX IF NOT EXISTS ix_highlight_consent_events_highlight_id ON highlight_consent_events (highlight_id);
CREATE INDEX IF NOT EXISTS ix_highlight_render_jobs_highlight_id ON highlight_render_jobs (highlight_id);
CREATE INDEX IF NOT EXISTS ix_highlight_render_jobs_status ON highlight_render_jobs (status);
-- Schema-only, idempotent source-version fencing. Included verbatim by p2c2 and preapply.
CREATE OR REPLACE FUNCTION public.p2c2_invalidate_match(mid integer) RETURNS void LANGUAGE plpgsql AS $$
DECLARE changed RECORD;
BEGIN
 -- All writers serialize on the match before touching consent rows.
 PERFORM id FROM public.video_matches WHERE id=mid FOR UPDATE;
 FOR changed IN
  UPDATE public.player_highlights SET player_decision='pending',approved_source_version=NULL,
   revoked_at=timezone('UTC',now()),revoke_reason='source_changed',render_status='stale',version=version+1,source_version=source_version+1
   WHERE video_match_id=mid AND revoked_at IS NULL RETURNING id,version,source_version
 LOOP
  INSERT INTO public.highlight_consent_events(highlight_id,action,version,source_version,created_at)
   VALUES(changed.id,'source_changed',changed.version,changed.source_version,timezone('UTC',now()));
  INSERT INTO public.highlight_render_jobs(id,kind,highlight_id,source_version,status,attempt,blob_path,created_at)
   SELECT md5(random()::text || clock_timestamp()::text), 'highlight_delete',NULL,1,'queued',0,path,timezone('UTC',now())+interval '20 minutes'
   FROM (SELECT output_blob_path AS path FROM public.player_highlights WHERE id=changed.id
         UNION SELECT blob_path FROM public.highlight_render_jobs WHERE highlight_id=changed.id) assets
   WHERE path IS NOT NULL;
  UPDATE public.highlight_render_jobs SET status='cancelled',lease_token=NULL
   WHERE highlight_id=changed.id AND status IN ('queued','running');
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION public.p2c2_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE mid integer;
BEGIN
 IF TG_OP='UPDATE' AND to_jsonb(NEW)=to_jsonb(OLD) THEN RETURN NEW; END IF;
 IF TG_TABLE_NAME='highlight_footage_reviews' AND TG_OP='UPDATE'
  AND (to_jsonb(NEW)-'reviewer_user_id')=(to_jsonb(OLD)-'reviewer_user_id') THEN RETURN NEW; END IF;
 IF TG_TABLE_NAME='video_matches' THEN
  IF TG_OP='UPDATE' AND OLD.status='finalized' AND NEW.status='expired'
   AND NEW.blob_path IS NULL AND NEW.blob_etag IS NULL
   AND (to_jsonb(NEW)-ARRAY['status','blob_path','blob_etag','updated_at']) = (to_jsonb(OLD)-ARRAY['status','blob_path','blob_etag','updated_at'])
   THEN RETURN NEW; END IF;
  IF TG_OP='UPDATE' AND
   (to_jsonb(NEW)->'match_date',to_jsonb(NEW)->'blob_path',to_jsonb(NEW)->'blob_etag',to_jsonb(NEW)->'scoped_snapshot',to_jsonb(NEW)->'scoped_ready_etag',
    to_jsonb(NEW)->'duration_s',to_jsonb(NEW)->'finalized_at',to_jsonb(NEW)->'club_program_id',to_jsonb(NEW)->'squad_id',
    to_jsonb(NEW)->'our_team_cluster',to_jsonb(NEW)->'kickoff_s',to_jsonb(NEW)->'halftime_s',to_jsonb(NEW)->'second_half_kickoff_s') IS NOT DISTINCT FROM
   (to_jsonb(OLD)->'match_date',to_jsonb(OLD)->'blob_path',to_jsonb(OLD)->'blob_etag',to_jsonb(OLD)->'scoped_snapshot',to_jsonb(OLD)->'scoped_ready_etag',
    to_jsonb(OLD)->'duration_s',to_jsonb(OLD)->'finalized_at',to_jsonb(OLD)->'club_program_id',to_jsonb(OLD)->'squad_id',
    to_jsonb(OLD)->'our_team_cluster',to_jsonb(OLD)->'kickoff_s',to_jsonb(OLD)->'halftime_s',to_jsonb(OLD)->'second_half_kickoff_s')
   THEN RETURN NEW; END IF;
  IF TG_OP='INSERT' THEN RETURN NEW; END IF;
  mid=OLD.id;
 ELSIF TG_TABLE_NAME='club_roster_members' THEN
  IF TG_OP='INSERT' THEN RETURN NEW; END IF;
  IF TG_OP='UPDATE' AND (NEW.player_api_id,NEW.local_player_id,NEW.program_id,NEW.squad_id) IS NOT DISTINCT FROM
   (OLD.player_api_id,OLD.local_player_id,OLD.program_id,OLD.squad_id) THEN RETURN NEW; END IF;
  FOR mid IN SELECT video_match_id FROM public.video_roster_entries WHERE club_roster_member_id=OLD.id
  LOOP PERFORM public.p2c2_invalidate_match(mid); END LOOP;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
 ELSE
  mid=COALESCE((to_jsonb(NEW)->>'video_match_id')::integer,(to_jsonb(OLD)->>'video_match_id')::integer);
 END IF;
 PERFORM public.p2c2_invalidate_match(mid);
 IF TG_OP='UPDATE' AND TG_TABLE_NAME NOT IN ('video_matches','club_roster_members') THEN
  IF OLD.video_match_id <> NEW.video_match_id THEN PERFORM public.p2c2_invalidate_match(OLD.video_match_id); END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
DO $$ DECLARE source_table text;
BEGIN
 FOREACH source_table IN ARRAY ARRAY['video_matches','video_roster_entries','video_tracklets','video_player_reports','highlight_footage_reviews','club_roster_members']
 LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS p2c2_source_guard ON public.%I',source_table);
  EXECUTE format('CREATE TRIGGER p2c2_source_guard %s INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.p2c2_source_guard()',
                 CASE WHEN source_table IN ('club_roster_members','video_matches') THEN 'BEFORE' ELSE 'AFTER' END, source_table);
 END LOOP;
END $$;

CREATE OR REPLACE FUNCTION public.p2c2_delete_highlight() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO public.highlight_render_jobs(id,kind,status,attempt,blob_path,created_at)
 SELECT md5(random()::text || clock_timestamp()::text),'highlight_delete','queued',0,path,timezone('UTC',now())+interval '20 minutes'
 FROM (SELECT OLD.output_blob_path AS path UNION SELECT blob_path FROM public.highlight_render_jobs WHERE highlight_id=OLD.id) assets
 WHERE path IS NOT NULL;
 UPDATE public.highlight_render_jobs SET status='cancelled',lease_token=NULL WHERE highlight_id=OLD.id AND status IN ('queued','running');
 RETURN OLD;
END $$;
DROP TRIGGER IF EXISTS p2c2_delete_highlight ON public.player_highlights;
CREATE TRIGGER p2c2_delete_highlight BEFORE DELETE ON public.player_highlights FOR EACH ROW EXECUTE FUNCTION public.p2c2_delete_highlight();

COMMIT;
