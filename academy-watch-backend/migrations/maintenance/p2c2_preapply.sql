BEGIN;
SET LOCAL lock_timeout = '5s';
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
ALTER TABLE public.highlight_footage_reviews ADD COLUMN IF NOT EXISTS source_context VARCHAR(64);
ALTER TABLE public.highlight_footage_reviews ADD COLUMN IF NOT EXISTS classification_context VARCHAR(64);
ALTER TABLE public.player_highlights ADD COLUMN IF NOT EXISTS admin_taken_down BOOLEAN NOT NULL DEFAULT false;

UPDATE public.player_highlights SET admin_taken_down=true WHERE revoke_reason='admin_takedown';

CREATE TABLE IF NOT EXISTS public.highlight_takedowns (
	id VARCHAR(36) NOT NULL, 
	video_match_id INTEGER NOT NULL, 
	start_s FLOAT NOT NULL, 
	end_s FLOAT NOT NULL, 
	lifted_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_highlight_takedown_range CHECK (start_s >= 0 AND end_s > start_s AND end_s-start_s <= 60), 
	FOREIGN KEY(video_match_id) REFERENCES video_matches (id) ON DELETE CASCADE
);
ALTER TABLE public.highlight_takedowns ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_highlight_takedown_window ON highlight_takedowns (video_match_id,start_s,end_s);
INSERT INTO public.highlight_takedowns(id,video_match_id,start_s,end_s) SELECT id,video_match_id,start_s,end_s FROM public.player_highlights WHERE admin_taken_down=true AND video_match_id IS NOT NULL ON CONFLICT(id) DO NOTHING;

-- Classification, rather than display spelling, is publication evidence.
CREATE OR REPLACE FUNCTION public.p2c2_squad_classification(label text, kind text, age_limit integer)
RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE lim text[];
BEGIN
 IF age_limit IS NOT NULL AND age_limit <= 18 THEN RETURN 'youth'; END IF;
 label = lower(trim(regexp_replace(translate(normalize(COALESCE(label,''), NFKC), '0123456789٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹߀߁߂߃߄߅߆߇߈߉०१२३४५६७८९০১২৩৪৫৬৭৮৯੦੧੨੩੪੫੬੭੮੯૦૧૨૩૪૫૬૭૮૯୦୧୨୩୪୫୬୭୮୯௦௧௨௩௪௫௬௭௮௯౦౧౨౩౪౫౬౭౮౯೦೧೨೩೪೫೬೭೮೯൦൧൨൩൪൫൬൭൮൯෦෧෨෩෪෫෬෭෮෯๐๑๒๓๔๕๖๗๘๙໐໑໒໓໔໕໖໗໘໙༠༡༢༣༤༥༦༧༨༩၀၁၂၃၄၅၆၇၈၉႐႑႒႓႔႕႖႗႘႙០១២៣៤៥៦៧៨៩᠐᠑᠒᠓᠔᠕᠖᠗᠘᠙᥆᥇᥈᥉᥊᥋᥌᥍᥎᥏᧐᧑᧒᧓᧔᧕᧖᧗᧘᧙᪀᪁᪂᪃᪄᪅᪆᪇᪈᪉᪐᪑᪒᪓᪔᪕᪖᪗᪘᪙᭐᭑᭒᭓᭔᭕᭖᭗᭘᭙᮰᮱᮲᮳᮴᮵᮶᮷᮸᮹᱀᱁᱂᱃᱄᱅᱆᱇᱈᱉᱐᱑᱒᱓᱔᱕᱖᱗᱘᱙꘠꘡꘢꘣꘤꘥꘦꘧꘨꘩꣐꣑꣒꣓꣔꣕꣖꣗꣘꣙꤀꤁꤂꤃꤄꤅꤆꤇꤈꤉꧐꧑꧒꧓꧔꧕꧖꧗꧘꧙꧰꧱꧲꧳꧴꧵꧶꧷꧸꧹꩐꩑꩒꩓꩔꩕꩖꩗꩘꩙꯰꯱꯲꯳꯴꯵꯶꯷꯸꯹０１２３４５６７８９𐒠𐒡𐒢𐒣𐒤𐒥𐒦𐒧𐒨𐒩𐴰𐴱𐴲𐴳𐴴𐴵𐴶𐴷𐴸𐴹𐵀𐵁𐵂𐵃𐵄𐵅𐵆𐵇𐵈𐵉𑁦𑁧𑁨𑁩𑁪𑁫𑁬𑁭𑁮𑁯𑃰𑃱𑃲𑃳𑃴𑃵𑃶𑃷𑃸𑃹𑄶𑄷𑄸𑄹𑄺𑄻𑄼𑄽𑄾𑄿𑇐𑇑𑇒𑇓𑇔𑇕𑇖𑇗𑇘𑇙𑋰𑋱𑋲𑋳𑋴𑋵𑋶𑋷𑋸𑋹𑑐𑑑𑑒𑑓𑑔𑑕𑑖𑑗𑑘𑑙𑓐𑓑𑓒𑓓𑓔𑓕𑓖𑓗𑓘𑓙𑙐𑙑𑙒𑙓𑙔𑙕𑙖𑙗𑙘𑙙𑛀𑛁𑛂𑛃𑛄𑛅𑛆𑛇𑛈𑛉𑛐𑛑𑛒𑛓𑛔𑛕𑛖𑛗𑛘𑛙𑛚𑛛𑛜𑛝𑛞𑛟𑛠𑛡𑛢𑛣𑜰𑜱𑜲𑜳𑜴𑜵𑜶𑜷𑜸𑜹𑣠𑣡𑣢𑣣𑣤𑣥𑣦𑣧𑣨𑣩𑥐𑥑𑥒𑥓𑥔𑥕𑥖𑥗𑥘𑥙𑯰𑯱𑯲𑯳𑯴𑯵𑯶𑯷𑯸𑯹𑱐𑱑𑱒𑱓𑱔𑱕𑱖𑱗𑱘𑱙𑵐𑵑𑵒𑵓𑵔𑵕𑵖𑵗𑵘𑵙𑶠𑶡𑶢𑶣𑶤𑶥𑶦𑶧𑶨𑶩𑽐𑽑𑽒𑽓𑽔𑽕𑽖𑽗𑽘𑽙𖄰𖄱𖄲𖄳𖄴𖄵𖄶𖄷𖄸𖄹𖩠𖩡𖩢𖩣𖩤𖩥𖩦𖩧𖩨𖩩𖫀𖫁𖫂𖫃𖫄𖫅𖫆𖫇𖫈𖫉𖭐𖭑𖭒𖭓𖭔𖭕𖭖𖭗𖭘𖭙𖵰𖵱𖵲𖵳𖵴𖵵𖵶𖵷𖵸𖵹𜳰𜳱𜳲𜳳𜳴𜳵𜳶𜳷𜳸𜳹𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿𞅀𞅁𞅂𞅃𞅄𞅅𞅆𞅇𞅈𞅉𞋰𞋱𞋲𞋳𞋴𞋵𞋶𞋷𞋸𞋹𞓰𞓱𞓲𞓳𞓴𞓵𞓶𞓷𞓸𞓹𞗱𞗲𞗳𞗴𞗵𞗶𞗷𞗸𞗹𞗺𞥐𞥑𞥒𞥓𞥔𞥕𞥖𞥗𞥘𞥙🯰🯱🯲🯳🯴🯵🯶🯷🯸🯹', '0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789'), '[^[:alnum:]]+', ' ', 'g')));
 IF label ~ '\y(?:[y]outh[[:alnum:]_]*|academ[[:alnum:]_]*|junior[[:alnum:]_]*|juven[[:alnum:]_]*|cadet[[:alnum:]_]*|minor[[:alnum:]_]*|teen[[:alnum:]_]*|mini[[:alnum:]_]*|colt[[:alnum:]_]*|boy[[:alnum:]_]*|girl[[:alnum:]_]*|child[[:alnum:]_]*|kid[[:alnum:]_]*|school[[:alnum:]_]*|scholar[[:alnum:]_]*|infantil[[:alnum:]_]*|varsity|development|underage|under age|jugend[[:alnum:]_]*|freshm[ae]n|sophomore[[:alnum:]_]*|primary|secondary|jv|(?:[e]ight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen)s?)\y' OR label ~ '\yunder\s+[a-z]+' THEN RETURN 'youth'; END IF;
 FOR lim IN SELECT regexp_matches(label, '\y(?:[u]|under|sub|o|jo|mo|age|aged|yr|year|grade|j|p|f)\s*([0-9]{1,2})(?![0-9])', 'g') UNION ALL SELECT regexp_matches(label, '(?<![0-9])([0-9]{1,2})\s*(?:[u]\y|s\y|(?:[a]nd\s+)?under\y)', 'g')
 LOOP IF lim[1]::integer <= 18 THEN RETURN 'youth'; END IF; END LOOP;
 IF kind='age_group' OR age_limit IS NOT NULL OR label ~ '\y(?:[u]|under|sub|o|jo|mo|age|aged|yr|year|grade|j|p|f)\s*([0-9]{1,2})(?![0-9])' OR label ~ '(?<![0-9])([0-9]{1,2})\s*(?:[u]\y|s\y|(?:[a]nd\s+)?under\y)' THEN RETURN 'unknown'; END IF;
 IF kind IN ('first_team','reserves') AND label = ANY(ARRAY['1st xi','2nd xi','a team','b team','first team','ladies','men','reserves','senior','seniors','veterans','vets','women']) THEN RETURN 'adult'; END IF;
 RETURN 'unknown';
END $$;
-- Python's canonical JSON uses ASCII escapes, including UTF-16 surrogate pairs.
CREATE OR REPLACE FUNCTION public.p2c2_json_string(value text) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE encoded text; result text := ''; ch text; code integer;
BEGIN
 IF value IS NULL THEN RETURN 'null'; END IF;
 encoded = to_json(value)::text;
 FOR i IN 1..char_length(encoded) LOOP
  ch = substr(encoded,i,1); code = ascii(ch);
  IF code < 128 THEN result = result || ch;
  ELSIF code <= 65535 THEN result = result || '\u' || lpad(to_hex(code),4,'0');
  ELSE result = result || '\u' || to_hex(55296 + ((code-65536)/1024)) || '\u' || to_hex(56320 + ((code-65536)%1024)); END IF;
 END LOOP;
 RETURN result;
END $$;
-- Checked compatibility: retain the opaque consent fingerprint of an exact,
-- still-valid prior context; never revive cleared reviews or revoked clips.
CREATE OR REPLACE FUNCTION public.p2c2_context_hash(mid integer, legacy boolean DEFAULT false)
RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE m public.video_matches; s public.club_squads; stamp text; squads text; body text;
BEGIN
 SELECT * INTO m FROM public.video_matches WHERE id=mid;
 stamp = CASE WHEN m.finalized_at IS NULL THEN 'null' ELSE to_json(
  to_char(m.finalized_at,'YYYY-MM-DD HH24:MI:SS') || CASE WHEN (extract(microseconds FROM m.finalized_at)::bigint % 1000000) = 0 THEN ''
  ELSE '.'||lpad((extract(microseconds FROM m.finalized_at)::bigint % 1000000)::text,6,'0') END)::text END;
 IF legacy THEN
  SELECT * INTO s FROM public.club_squads WHERE id=m.squad_id;
  squads = CASE WHEN s.id IS NULL THEN 'null' ELSE '['||public.p2c2_json_string(s.name)||','||public.p2c2_json_string(s.kind)||','||COALESCE(s.age_limit::text,'null')||']' END;
 ELSE
  SELECT '['||string_agg(CASE WHEN cs.id IS NULL THEN 'null' ELSE '['||cs.id||','||to_json(cs.kind)::text||','||COALESCE(cs.age_limit::text,'null')||','||to_json(public.p2c2_squad_classification(cs.name,cs.kind,cs.age_limit))::text||']' END,',' ORDER BY COALESCE(ids.sid,0))||']' INTO squads
  FROM (SELECT m.squad_id AS sid UNION SELECT r.squad_id FROM public.video_roster_entries e LEFT JOIN public.club_roster_members r ON r.id=e.club_roster_member_id WHERE e.video_match_id=mid) ids
  LEFT JOIN public.club_squads cs ON cs.id=ids.sid;
 END IF;
 body = '['||COALESCE(to_json(m.match_date)::text,'null')||','||COALESCE(m.squad_id::text,'null')||','||stamp||','||squads||']';
 RETURN encode(sha256(convert_to(body,'UTF8')),'hex');
END $$;
-- Schema-only, idempotent source-version fencing. Included verbatim by p2c2 and preapply.
CREATE OR REPLACE FUNCTION public.p2c2_invalidate_match(mid integer) RETURNS void LANGUAGE plpgsql AS $$
DECLARE changed RECORD; notice_ids varchar[] := ARRAY[]::varchar[]; event_key text := md5(random()::text || clock_timestamp()::text);
BEGIN
 -- All writers serialize on the match before touching consent rows.
 PERFORM id FROM public.video_matches WHERE id=mid FOR UPDATE;
 FOR changed IN
  WITH previous AS MATERIALIZED (
   SELECT id,player_decision FROM public.player_highlights WHERE video_match_id=mid AND revoked_at IS NULL ORDER BY id FOR UPDATE
  )
  UPDATE public.player_highlights h SET player_decision='pending',approved_source_version=NULL,
   revoked_at=timezone('UTC',now()),revoke_reason='source_changed',render_status='stale',version=h.version+1,source_version=h.source_version+1
   FROM previous WHERE h.id=previous.id RETURNING h.id,h.version,h.source_version,previous.player_decision
 LOOP
  INSERT INTO public.highlight_consent_events(highlight_id,action,version,source_version,created_at)
   VALUES(changed.id,'source_changed',changed.version,changed.source_version,timezone('UTC',now()));
  INSERT INTO public.highlight_render_jobs(id,kind,highlight_id,source_version,status,attempt,blob_path,created_at)
   SELECT md5(random()::text || clock_timestamp()::text), 'highlight_delete',NULL,1,'queued',0,path,timezone('UTC',now())+interval '20 minutes'
   FROM (SELECT output_blob_path AS path FROM public.player_highlights WHERE id=changed.id
         UNION SELECT blob_path FROM public.highlight_render_jobs WHERE highlight_id=changed.id) assets
   WHERE path IS NOT NULL;
  IF changed.player_decision <> 'private' THEN notice_ids := array_append(notice_ids,changed.id); END IF;
  UPDATE public.highlight_render_jobs SET status='cancelled',lease_token=NULL
   WHERE highlight_id=changed.id AND status IN ('queued','running');
 END LOOP;
 INSERT INTO public.notification_outbox(dedupe_key,recipient_user_id,event_type,entity_type,entity_id,template,payload)
 SELECT 'highlight_source:'||mid||':'||event_key||':'||uid,uid,
  'highlight_source_changed','user_account',uid::text,'highlight_source_changed',
  json_build_object('highlight_id',id,'version',version)
 FROM (
  SELECT DISTINCT ON (uid) uid,id,version FROM (
   SELECT recipient_user_id AS uid,id,version FROM public.player_highlights WHERE id=ANY(notice_ids)
   UNION
   SELECT m.user_account_id,h.id,h.version FROM public.club_program_managers m
   JOIN public.player_highlights h ON h.program_id=m.program_id AND h.id=ANY(notice_ids)
   JOIN public.club_program_claims c ON c.id=m.source_claim_id AND c.program_id=m.program_id AND c.user_account_id=m.user_account_id
   WHERE m.status='active' AND c.status='approved'
  ) recipients WHERE uid IS NOT NULL ORDER BY uid,id
 ) grouped ON CONFLICT(dedupe_key) DO NOTHING;
END $$;
CREATE OR REPLACE FUNCTION public.p2c2_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE mid integer;
BEGIN
 IF TG_OP='UPDATE' AND to_jsonb(NEW)=to_jsonb(OLD) THEN RETURN NEW; END IF;
 IF TG_TABLE_NAME='highlight_footage_reviews' AND TG_OP='UPDATE' THEN
  IF OLD.classification_context IS NULL AND NEW.classification_context=public.p2c2_context_hash(NEW.video_match_id)
  AND NEW.source_context=public.p2c2_context_hash(NEW.video_match_id,true)
  AND (to_jsonb(NEW)-'classification_context')=(to_jsonb(OLD)-'classification_context') THEN RETURN NEW; END IF;
 END IF;
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
  IF TG_OP='UPDATE' AND (NEW.match_date,NEW.squad_id,NEW.finalized_at) IS DISTINCT FROM (OLD.match_date,OLD.squad_id,OLD.finalized_at) THEN
   UPDATE public.highlight_footage_reviews SET source_context=NULL WHERE video_match_id=mid AND source_context IS NOT NULL;
  END IF;
 ELSIF TG_TABLE_NAME='club_squads' THEN
  IF TG_OP='INSERT' THEN RETURN NEW; END IF;
  IF TG_OP='UPDATE' AND (NEW.kind,NEW.age_limit) IS NOT DISTINCT FROM (OLD.kind,OLD.age_limit)
   AND public.p2c2_squad_classification(NEW.name,NEW.kind,NEW.age_limit) = public.p2c2_squad_classification(OLD.name,OLD.kind,OLD.age_limit) THEN RETURN NEW; END IF;
  FOR mid IN SELECT id FROM public.video_matches WHERE squad_id=OLD.id OR id IN (
   SELECT e.video_match_id FROM public.video_roster_entries e JOIN public.club_roster_members m ON m.id=e.club_roster_member_id WHERE m.squad_id=OLD.id
  ) ORDER BY id FOR UPDATE
  LOOP
   UPDATE public.highlight_footage_reviews SET source_context=NULL WHERE video_match_id=mid AND source_context IS NOT NULL;
   PERFORM public.p2c2_invalidate_match(mid);
  END LOOP;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
 ELSIF TG_TABLE_NAME='club_roster_members' THEN
  IF TG_OP='INSERT' THEN RETURN NEW; END IF;
  IF TG_OP='UPDATE' AND (NEW.player_api_id,NEW.local_player_id,NEW.program_id,NEW.squad_id) IS NOT DISTINCT FROM
   (OLD.player_api_id,OLD.local_player_id,OLD.program_id,OLD.squad_id) THEN RETURN NEW; END IF;
  FOR mid IN SELECT video_match_id FROM public.video_roster_entries WHERE club_roster_member_id=OLD.id
  LOOP
   UPDATE public.highlight_footage_reviews SET source_context=NULL WHERE video_match_id=mid AND source_context IS NOT NULL;
   PERFORM public.p2c2_invalidate_match(mid);
  END LOOP;
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
 FOREACH source_table IN ARRAY ARRAY['video_matches','video_roster_entries','video_tracklets','video_player_reports','highlight_footage_reviews','club_roster_members','club_squads']
 LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS p2c2_source_guard ON public.%I',source_table);
  EXECUTE format('CREATE TRIGGER p2c2_source_guard %s INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.p2c2_source_guard()',
                 CASE WHEN source_table IN ('club_roster_members','video_matches','club_squads') THEN 'BEFORE' ELSE 'AFTER' END, source_table);
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

UPDATE public.highlight_footage_reviews r SET classification_context=public.p2c2_context_hash(m.id)
FROM public.video_matches m LEFT JOIN public.club_squads s ON s.id=m.squad_id
WHERE r.video_match_id=m.id AND r.classification_context IS NULL
 AND r.source_context=public.p2c2_context_hash(m.id,true)
 AND r.classification='adult_only' AND m.status IN ('finalized','expired')
 AND r.source_etag=m.scoped_ready_etag AND r.source_snapshot=m.scoped_snapshot
 AND (public.p2c2_squad_classification(s.name,s.kind,s.age_limit)='adult'
      OR (public.p2c2_squad_classification(s.name,s.kind,s.age_limit)='unknown' AND r.squad_adult_attested))
 AND EXISTS(SELECT 1 FROM public.video_roster_entries WHERE video_match_id=m.id)
 AND NOT EXISTS(SELECT 1 FROM public.video_roster_entries e LEFT JOIN public.club_roster_members member ON member.id=e.club_roster_member_id
  WHERE e.video_match_id=m.id AND (member.id IS NULL OR member.squad_id IS DISTINCT FROM m.squad_id));
COMMIT;
