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
  INSERT INTO public.notification_outbox(dedupe_key,recipient_user_id,event_type,entity_type,entity_id,template,payload)
   SELECT 'highlight_source:'||changed.id||':'||changed.version||':'||uid,uid,
    'highlight_source_changed','user_account',uid::text,'highlight_source_changed',
    json_build_object('highlight_id',changed.id,'version',changed.version)
   FROM (
    SELECT recipient_user_id AS uid FROM public.player_highlights WHERE id=changed.id
    UNION
    SELECT m.user_account_id FROM public.club_program_managers m
    JOIN public.player_highlights h ON h.program_id=m.program_id AND h.id=changed.id
    JOIN public.club_program_claims c ON c.id=m.source_claim_id AND c.program_id=m.program_id AND c.user_account_id=m.user_account_id
    WHERE m.status='active' AND c.status='approved'
   ) recipients WHERE uid IS NOT NULL
   ON CONFLICT(dedupe_key) DO NOTHING;
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
