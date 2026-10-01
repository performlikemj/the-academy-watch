"""Two-key standalone highlights, guarded private tables + RLS.

Revision ID: p2c2
Revises: p2c1
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import table_exists

revision = "p2c2"
down_revision = "p2c1"
branch_labels = None
depends_on = None

TABLES = {
    "player_highlights": "CREATE TABLE player_highlights (\n\tid VARCHAR(36) NOT NULL, \n\tprogram_id INTEGER NOT NULL, \n\tvideo_match_id INTEGER, \n\troster_entry_id INTEGER, \n\ttracklet_id INTEGER, \n\tplayer_api_id INTEGER, \n\tlocal_player_id INTEGER, \n\tclaim_id INTEGER, \n\trecipient_user_id INTEGER, \n\tpicker_user_id INTEGER, \n\tpick_key VARCHAR(64) NOT NULL, \n\tsource_etag VARCHAR(100) NOT NULL, \n\tsource_snapshot VARCHAR(64) NOT NULL, \n\tsource_fingerprint VARCHAR(64) NOT NULL, \n\tsource_version INTEGER DEFAULT '1' NOT NULL, \n\tstart_s FLOAT NOT NULL, \n\tend_s FLOAT NOT NULL, \n\ttitle VARCHAR(160) NOT NULL, \n\tversion INTEGER DEFAULT '1' NOT NULL, \n\tclub_picked_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tplayer_decision VARCHAR(20) DEFAULT 'pending' NOT NULL, \n\tdecision_user_id INTEGER, \n\tdecision_at TIMESTAMP WITHOUT TIME ZONE, \n\tapproved_source_version INTEGER, \n\trevoked_at TIMESTAMP WITHOUT TIME ZONE, \n\trevoke_reason VARCHAR(30), \n\trender_status VARCHAR(20) DEFAULT 'queued' NOT NULL, \n\toutput_blob_path VARCHAR(500), \n\toutput_etag VARCHAR(100), \n\toutput_bytes INTEGER, \n\trender_source_version INTEGER, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_player_highlights_pick UNIQUE (pick_key), \n\tCONSTRAINT ck_highlight_subject_xor CHECK ((player_api_id IS NOT NULL AND local_player_id IS NULL) OR (player_api_id IS NULL AND local_player_id IS NOT NULL)), \n\tCONSTRAINT ck_highlight_range CHECK (start_s >= 0 AND end_s > start_s AND end_s-start_s <= 60), \n\tCONSTRAINT ck_highlight_decision CHECK (player_decision IN ('pending','approve','private')), \n\tCONSTRAINT ck_highlight_render CHECK (render_status IN ('queued','running','ready','failed','stale')), \n\tFOREIGN KEY(program_id) REFERENCES club_programs (id) ON DELETE CASCADE, \n\tFOREIGN KEY(video_match_id) REFERENCES video_matches (id) ON DELETE SET NULL, \n\tFOREIGN KEY(roster_entry_id) REFERENCES video_roster_entries (id) ON DELETE SET NULL, \n\tFOREIGN KEY(tracklet_id) REFERENCES video_tracklets (id) ON DELETE SET NULL, \n\tFOREIGN KEY(local_player_id) REFERENCES local_players (id) ON DELETE CASCADE, \n\tFOREIGN KEY(claim_id) REFERENCES player_profile_claims (id) ON DELETE SET NULL, \n\tFOREIGN KEY(recipient_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL, \n\tFOREIGN KEY(picker_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL, \n\tFOREIGN KEY(decision_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL\n)",
    "highlight_consent_events": "CREATE TABLE highlight_consent_events (\n\tid SERIAL NOT NULL, \n\thighlight_id VARCHAR(36) NOT NULL, \n\tactor_user_id INTEGER, \n\taction VARCHAR(30) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tsource_version INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(highlight_id) REFERENCES player_highlights (id) ON DELETE CASCADE, \n\tFOREIGN KEY(actor_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL\n)",
    "highlight_footage_reviews": "CREATE TABLE highlight_footage_reviews (\n\tvideo_match_id INTEGER NOT NULL, \n\treviewer_user_id INTEGER, \n\tclassification VARCHAR(20) NOT NULL, \n\tsource_etag VARCHAR(100) NOT NULL, \n\tsource_snapshot VARCHAR(64) NOT NULL, \n\treviewed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (video_match_id), \n\tCONSTRAINT ck_highlight_footage_review CHECK (classification IN ('adult_only','private')), \n\tFOREIGN KEY(video_match_id) REFERENCES video_matches (id) ON DELETE CASCADE, \n\tFOREIGN KEY(reviewer_user_id) REFERENCES user_accounts (id) ON DELETE SET NULL\n)",
    "highlight_render_jobs": "CREATE TABLE highlight_render_jobs (\n\tid VARCHAR(36) NOT NULL, \n\thighlight_id VARCHAR(36), \n\tkind VARCHAR(30) NOT NULL, \n\tsource_version INTEGER, \n\tstatus VARCHAR(20) DEFAULT 'queued' NOT NULL, \n\tattempt INTEGER DEFAULT '0' NOT NULL, \n\tlease_token VARCHAR(36), \n\tlease_expires_at TIMESTAMP WITHOUT TIME ZONE, \n\tblob_path VARCHAR(500), \n\terror_code VARCHAR(40), \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tcompleted_at TIMESTAMP WITHOUT TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_highlight_job_kind CHECK (kind IN ('highlight_cut','highlight_delete')), \n\tCONSTRAINT ck_highlight_job_status CHECK (status IN ('queued','running','succeeded','failed','cancelled')), \n\tFOREIGN KEY(highlight_id) REFERENCES player_highlights (id) ON DELETE SET NULL\n)",
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_player_highlights_local_player_id ON player_highlights (local_player_id)",
    "CREATE INDEX IF NOT EXISTS ix_player_highlights_recipient_user_id ON player_highlights (recipient_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_player_highlights_video_match_id ON player_highlights (video_match_id)",
    "CREATE INDEX IF NOT EXISTS ix_player_highlights_player_api_id ON player_highlights (player_api_id)",
    "CREATE INDEX IF NOT EXISTS ix_player_highlights_program_id ON player_highlights (program_id)",
    "CREATE INDEX IF NOT EXISTS ix_highlight_consent_events_highlight_id ON highlight_consent_events (highlight_id)",
    "CREATE INDEX IF NOT EXISTS ix_highlight_render_jobs_highlight_id ON highlight_render_jobs (highlight_id)",
    "CREATE INDEX IF NOT EXISTS ix_highlight_render_jobs_status ON highlight_render_jobs (status)",
]


# Freeze the SQL in this revision; future maintenance-file edits must not rewrite history.
SOURCE_GUARDS = "-- Schema-only, idempotent source-version fencing. Included verbatim by p2c2 and preapply.\nCREATE OR REPLACE FUNCTION public.p2c2_invalidate_match(mid integer) RETURNS void LANGUAGE plpgsql AS $$\nDECLARE changed RECORD;\nBEGIN\n FOR changed IN\n  UPDATE public.player_highlights SET player_decision='pending',approved_source_version=NULL,\n   revoked_at=now(),revoke_reason='source_changed',render_status='stale',version=version+1,source_version=source_version+1\n   WHERE video_match_id=mid AND revoked_at IS NULL RETURNING id,version,source_version\n LOOP\n  INSERT INTO public.highlight_consent_events(highlight_id,action,version,source_version,created_at)\n   VALUES(changed.id,'source_changed',changed.version,changed.source_version,now());\n  INSERT INTO public.highlight_render_jobs(id,kind,highlight_id,source_version,status,attempt,blob_path,created_at)\n   SELECT md5(random()::text || clock_timestamp()::text), 'highlight_delete',NULL,1,'queued',0,path,now()+interval '20 minutes'\n   FROM (SELECT output_blob_path AS path FROM public.player_highlights WHERE id=changed.id\n         UNION SELECT blob_path FROM public.highlight_render_jobs WHERE highlight_id=changed.id) assets\n   WHERE path IS NOT NULL;\n  UPDATE public.highlight_render_jobs SET status='cancelled',lease_token=NULL\n   WHERE highlight_id=changed.id AND status IN ('queued','running');\n END LOOP;\nEND $$;\nCREATE OR REPLACE FUNCTION public.p2c2_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$\nDECLARE mid integer;\nBEGIN\n IF TG_OP='UPDATE' AND to_jsonb(NEW)=to_jsonb(OLD) THEN RETURN NEW; END IF;\n IF TG_TABLE_NAME='video_matches' THEN\n  IF TG_OP='UPDATE' AND\n   (to_jsonb(NEW)->'blob_path',to_jsonb(NEW)->'blob_etag',to_jsonb(NEW)->'scoped_snapshot',to_jsonb(NEW)->'scoped_ready_etag',\n    to_jsonb(NEW)->'duration_s',to_jsonb(NEW)->'finalized_at',to_jsonb(NEW)->'club_program_id',to_jsonb(NEW)->'squad_id',\n    to_jsonb(NEW)->'our_team_cluster',to_jsonb(NEW)->'kickoff_s',to_jsonb(NEW)->'halftime_s',to_jsonb(NEW)->'second_half_kickoff_s') IS NOT DISTINCT FROM\n   (to_jsonb(OLD)->'blob_path',to_jsonb(OLD)->'blob_etag',to_jsonb(OLD)->'scoped_snapshot',to_jsonb(OLD)->'scoped_ready_etag',\n    to_jsonb(OLD)->'duration_s',to_jsonb(OLD)->'finalized_at',to_jsonb(OLD)->'club_program_id',to_jsonb(OLD)->'squad_id',\n    to_jsonb(OLD)->'our_team_cluster',to_jsonb(OLD)->'kickoff_s',to_jsonb(OLD)->'halftime_s',to_jsonb(OLD)->'second_half_kickoff_s')\n   THEN RETURN NEW; END IF;\n  IF TG_OP='INSERT' THEN RETURN NEW; END IF;\n  mid=OLD.id;\n ELSIF TG_TABLE_NAME='club_roster_members' THEN\n  IF TG_OP='INSERT' THEN RETURN NEW; END IF;\n  IF TG_OP='UPDATE' AND (NEW.player_api_id,NEW.local_player_id,NEW.program_id,NEW.squad_id) IS NOT DISTINCT FROM\n   (OLD.player_api_id,OLD.local_player_id,OLD.program_id,OLD.squad_id) THEN RETURN NEW; END IF;\n  FOR mid IN SELECT video_match_id FROM public.video_roster_entries WHERE club_roster_member_id=OLD.id\n  LOOP PERFORM public.p2c2_invalidate_match(mid); END LOOP;\n  IF TG_OP='DELETE' THEN RETURN OLD; END IF;\n  RETURN NEW;\n ELSE\n  mid=COALESCE((to_jsonb(NEW)->>'video_match_id')::integer,(to_jsonb(OLD)->>'video_match_id')::integer);\n END IF;\n PERFORM public.p2c2_invalidate_match(mid);\n IF TG_OP='UPDATE' AND TG_TABLE_NAME NOT IN ('video_matches','club_roster_members') THEN\n  IF OLD.video_match_id <> NEW.video_match_id THEN PERFORM public.p2c2_invalidate_match(OLD.video_match_id); END IF;\n END IF;\n RETURN NULL;\nEND $$;\nDO $$ DECLARE source_table text;\nBEGIN\n FOREACH source_table IN ARRAY ARRAY['video_matches','video_roster_entries','video_tracklets','video_player_reports','highlight_footage_reviews','club_roster_members']\n LOOP\n  EXECUTE format('DROP TRIGGER IF EXISTS p2c2_source_guard ON public.%I',source_table);\n  EXECUTE format('CREATE TRIGGER p2c2_source_guard %s INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.p2c2_source_guard()',\n                 CASE WHEN source_table='club_roster_members' THEN 'BEFORE' ELSE 'AFTER' END, source_table);\n END LOOP;\nEND $$;\n"


def upgrade():
    for table, ddl in TABLES.items():
        if not table_exists(table):
            op.execute(ddl)
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    for sql in INDEXES:
        op.execute(sql)
    op.execute(SOURCE_GUARDS)


def downgrade():
    for table in TABLES:
        if table_exists(table) and op.get_bind().execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")).scalar():
            raise RuntimeError(f"Preserve retained {table}; refusing downgrade")
    for table in (
        "video_matches",
        "video_roster_entries",
        "video_tracklets",
        "video_player_reports",
        "highlight_footage_reviews",
        "club_roster_members",
    ):
        if table_exists(table):
            op.execute(f"DROP TRIGGER IF EXISTS p2c2_source_guard ON public.{table}")
    op.execute("DROP FUNCTION IF EXISTS public.p2c2_source_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.p2c2_invalidate_match(integer)")
    for table in reversed(TABLES):
        if table_exists(table):
            op.drop_table(table)
