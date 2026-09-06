#!/usr/bin/env bash
# prod_review_demo.sh — run with bash or zsh; public/admin HTTPS API only.
# Export the seven credentials below first. ADMIN_CODE must be an unused ordinary
# login OTP for an ADMIN_EMAILS account; static review codes never grant admin.
# No request-code call: review logins bypass email; ADMIN_CODE is supplied upfront.
set +x
set -eu
set -o pipefail
: "${REVIEW_PLAYER_EMAIL:?Required}" "${REVIEW_PLAYER_CODE:?Required}"
: "${REVIEW_SCOUT_EMAIL:?Required}" "${REVIEW_SCOUT_CODE:?Required}"
: "${ADMIN_API_KEY:=}" "${ADMIN_EMAIL:=}" "${ADMIN_CODE:=}"
API="${API:-https://api.theacademywatch.com/api}"; API="${API%/}"
case "$API" in https://api.theacademywatch.com/api) ;; *) printf 'Production API required\n' >&2; exit 1;; esac
export API REVIEW_PLAYER_EMAIL REVIEW_PLAYER_CODE REVIEW_SCOUT_EMAIL REVIEW_SCOUT_CODE ADMIN_EMAIL ADMIN_CODE ADMIN_API_KEY
command -v curl >/dev/null; command -v python3 >/dev/null
BODY=''; ADMIN_TOKEN=''
fail() {
  printf '%s\n' "$1" >&2
  printf '%s' "$BODY" | python3 -c 'import json,os,sys
s=sys.stdin.read()
try:
 def clean(v):
  if isinstance(v,dict): return {k:("[redacted]" if k in {"token","email","code","verification_code"} else clean(x)) for k,x in v.items()}
  return [clean(x) for x in v] if isinstance(v,list) else v
 s=json.dumps(clean(json.loads(s)))
except ValueError: pass
for k,v in os.environ.items():
 if v and (k.startswith("REVIEW_") or k.startswith("ADMIN_") or k.endswith("_TOKEN") or k=="API"): s=s.replace(v,"[redacted]")
print(s,file=sys.stderr)'
  exit 1
}
j() { printf '%s' "$BODY" | python3 -c 'import json,sys,os; d=json.load(sys.stdin); print(eval(sys.argv[1]))' "$1" || fail 'Invalid API response'; }
payload() { python3 -c "import json,os,uuid; from datetime import datetime,timezone,timedelta; print(json.dumps($1))"; }
api() {
  local method="$1" route="$2" token="${3:-}" data="${4:-}" expected="${5:-200}" raw rc=0
  case "$route" in /admin/*) [ -n "$ADMIN_TOKEN" ] || { printf "NEEDS_ADMIN %s %s\n" "$method" "$route"; exit 3; };; esac
  local -a args
  args=(-q -sS --proto '=https' --connect-timeout 15 --max-time 60 -X "$method" -H 'Accept: application/json')
  [ -z "$token" ] || args+=(-H "Authorization: Bearer $token")
  if [ -n "$ADMIN_TOKEN" ] && [ "$token" = "$ADMIN_TOKEN" ]; then args+=(-H "X-API-Key: $ADMIN_API_KEY"); fi
  [ -z "$data" ] || args+=(-H 'Content-Type: application/json' --data-binary @-)
  raw=$(printf '%s' "$data" | curl "${args[@]}" -w '\n%{http_code}' "$API$route") || rc=$?
  HTTP=${raw##*$'\n'}; BODY=${raw%$'\n'*}
  [ "$rc" -eq 0 ] || fail "Transport failure ($rc): $method $route"
  if [ "$route" = /me/club-invitations ] && [ "$HTTP" = 404 ]; then
    fail 'PILOT_CLUB_RELATIONSHIPS_ENABLED is off or invitations are undeployed (HTTP 404); enable/deploy before retrying.'
  fi
  case " $expected " in *" $HTTP "*) ;; *) fail "HTTP $HTTP: $method $route";; esac
}
login() {
  local persona="$1" role="$2"
  local login_data
  login_data=$(payload "{'email':os.environ['${persona}_EMAIL'],'code':os.environ['${persona}_CODE']}")
  api POST /auth/verify-code '' "$login_data"
  [ "$(j 'd["role"]')" = "$role" ] || fail 'Unexpected login role; admin requires an ordinary unused OTP.'
  j 'd["token"] if isinstance(d.get("token"),str) and d["token"] else 1/0'
}
# Scan every page: older accepted invitations/feedback must prevent duplicates.
find_page() {
  local route="$1" token="$2" expression="$3" cursor=''
  FOUND='{}'
  while :; do
    api GET "$route${cursor:+&before=$cursor}" "$token"
    FOUND=$(j "json.dumps($expression)")
    [ "$FOUND" = '{}' ] || break
    cursor=$(j 'd.get("next_before") or ""')
    [ -n "$cursor" ] || break
  done
}
api GET /health
[ "$(j 'd["status"]')" = healthy ] || fail 'Health preflight failed'
api GET /billing/config
[ "$(j 'd["enabled"]')" = True ] || fail 'Billing configuration is disabled'
PLAYER_TOKEN=$(login REVIEW_PLAYER user); export PLAYER_TOKEN
SCOUT_TOKEN=$(login REVIEW_SCOUT user); export SCOUT_TOKEN
if [ -n "$ADMIN_CODE" ]; then ADMIN_TOKEN=$(login ADMIN admin); else ADMIN_TOKEN=""; fi; export ADMIN_TOKEN
api GET /me/club-invitations "$PLAYER_TOKEN"
printf 'preflight=passed\n'

# Reuse approved self-ownership, or resume our pending synthetic identity.
api GET /me/claims "$PLAYER_TOKEN"
BODY=$(j 'json.dumps(next((c for c in d["claims"] if c.get("local_player_id") and c["relationship_type"]=="player" and c["status"]=="approved" and (c.get("local_player") or {}).get("status")=="approved"), next((c for c in d["claims"] if c.get("local_player_id") and c["relationship_type"]=="player" and c["status"] in ("pending","approved") and c.get("player_name")=="Review Player" and (c.get("local_player") or {}).get("status") in ("pending","approved")), {})))')
if [ "$BODY" = '{}' ]; then
  api POST /local-players "$PLAYER_TOKEN" '{"display_name":"Review Player","birth_date":"1998-04-12","position":"Midfielder","country":"England","relationship_type":"player"}' 201
  BODY=$(j 'json.dumps(d["claim"])')
fi
LP_ID=$(j 'int(d["local_player_id"])'); CLAIM_ID=$(j 'int(d["id"])'); CLAIM_STATUS=$(j 'd["status"]')
export LP_ID CLAIM_ID
api GET "/local-players/$LP_ID" "$PLAYER_TOKEN"
if [ "$(j 'd["player"]["status"]')" != approved ]; then
  api POST "/admin/local-players/$LP_ID/review" "$ADMIN_TOKEN" '{"action":"approve"}'
fi
SIGNED_ID=$(j 'int(d["player"]["api_player_id"])'); PROFILE_NAME=$(j 'd["player"]["display_name"]'); export SIGNED_ID
[ "$SIGNED_ID" = "-$LP_ID" ] || fail 'Local profile lacks the expected signed identity'
if [ "$CLAIM_STATUS" != approved ]; then
  api POST "/admin/showcase/claims/$CLAIM_ID/review" "$ADMIN_TOKEN" '{"action":"approve"}'
fi
# create_local_player ignores contract_status; persist it via the profile API.
api GET "/local-players/$LP_ID/showcase" "$PLAYER_TOKEN"
if [ "$(j 'd["profile"] is None')" = True ]; then
  api PUT "/local-players/$LP_ID/showcase/profile" "$PLAYER_TOKEN" '{"positions":"Midfielder","contract_status":"free_agent"}'
fi
if [ "$(j 'd["profile"].get("status","approved")')" = pending ]; then
  api POST "/admin/showcase/local-profiles/$LP_ID/review" "$ADMIN_TOKEN" '{"action":"approve"}'
fi

# Official-claim review returns claim only; bridge program IDs live here.
program_id() {
  api GET /funding/claims/me "$SCOUT_TOKEN"
  j 'next((c["program"]["id"] for c in sorted(d["claims"],key=lambda c:c["program"]["name"]!="Academy Watch Review FC") if c["status"]=="approved" and c["program"]["platform_status"]=="approved"), "")'
}
PROGRAM_ID=$(program_id)
if [ -z "$PROGRAM_ID" ]; then
  api GET /me/club-claims "$SCOUT_TOKEN"
  BODY=$(j 'json.dumps(next((c for c in d["claims"] if c.get("local_club_id") and c.get("club_name")=="Academy Watch Review FC" and c["status"] in ("pending","approved")), {}))')
  if [ "$BODY" = '{}' ]; then
    api GET '/clubs/search?q=Academy%20Watch%20Review%20FC' "$SCOUT_TOKEN"
    CLUB_ID=$(j 'next((c["id"] for c in d["local_clubs"] if c["name"]=="Academy Watch Review FC" and c["country"]=="England" and c["status"] in ("pending","verified")), "")')
    if [ -z "$CLUB_ID" ]; then
      api POST /local-clubs "$SCOUT_TOKEN" '{"name":"Academy Watch Review FC","country":"England"}' 201
      CLUB_ID=$(j 'int(d["club"]["id"])')
    fi
    api POST /clubs/claim "$SCOUT_TOKEN" "{\"local_club_id\":$CLUB_ID,\"role_title\":\"Demo manager\",\"message\":\"Synthetic Apple App Review club.\"}" 201
    BODY=$(j 'json.dumps(d["claim"])')
  fi
  CLUB_CLAIM_ID=$(j 'int(d["id"])')
  if [ "$(j 'd["status"]')" = pending ]; then
    api POST "/admin/club-claims/$CLUB_CLAIM_ID/review" "$ADMIN_TOKEN" '{"action":"approve"}'
  fi
  PROGRAM_ID=$(program_id)
  [ -n "$PROGRAM_ID" ] || fail 'Approved club claim has no bridge program'
fi
export PROGRAM_ID
api GET "/club/$PROGRAM_ID/profile" "$SCOUT_TOKEN" # Verify active manager grant.

find_page "/me/club-invitations?player_api_id=$SIGNED_ID&limit=50" "$PLAYER_TOKEN" 'next((x for x in d["invitations"] if x["program_id"]==int(os.environ["PROGRAM_ID"]) and x["claim_id"]==int(os.environ["CLAIM_ID"]) and x["status"] in ("accepted","pending")), {})'
if [ "$FOUND" = '{}' ]; then
  DATA=$(payload "{'player_api_id':int(os.environ['SIGNED_ID']),'client_request_id':str(uuid.uuid4())}")
  api POST "/club/$PROGRAM_ID/invitations" "$SCOUT_TOKEN" "$DATA" '200 201'
  FOUND=$(j 'json.dumps(d["invitation"])')
fi
BODY="$FOUND"; INVITATION_ID=$(j 'd["id"]'); INVITATION_STATUS=$(j 'd["status"]'); export INVITATION_ID
if [ "$INVITATION_STATUS" = pending ]; then
  api POST "/me/club-invitations/$INVITATION_ID/accept" "$PLAYER_TOKEN" '{}'
  INVITATION_STATUS=$(j 'd["invitation"]["status"]')
fi
[ "$INVITATION_STATUS" = accepted ] || fail 'Invitation is not accepted'

find_page "/club/$PROGRAM_ID/player-feedback?invitation_id=$INVITATION_ID&limit=100" "$SCOUT_TOKEN" 'next((x for x in d["feedback"] if not x.get("unavailable") and x.get("title")=="Building your next pass"), {})'
if [ "$FOUND" = '{}' ]; then
  # Actual action schema: success / review_on (not success_criterion / review_date).
  DATA=$(payload "{'invitation_id':os.environ['INVITATION_ID'],
    'client_request_id':str(uuid.uuid5(uuid.UUID(os.environ['INVITATION_ID']),'app-review-feedback-v1')),
    'title':'Building your next pass',
    'body':'You are finding good spaces to receive the ball. Scan both shoulders before receiving so you can spot and play the forward pass sooner.',
    'development_action':{'focus':'Scan before receiving',
    'practice':'Check both shoulders before five receptions in the next small-sided game.',
    'success':'Find the forward option before the ball arrives.',
    'review_on':(datetime.now(timezone.utc).date()+timedelta(days=7)).isoformat()}}")
  api POST "/club/$PROGRAM_ID/player-feedback" "$SCOUT_TOKEN" "$DATA" '200 201'
  FOUND=$(j 'json.dumps(d["feedback"])')
fi
BODY="$FOUND"; FEEDBACK_ID=$(j 'd["id"]')
api GET "/me/player-feedback/$FEEDBACK_ID" "$PLAYER_TOKEN" # Prove reviewer visibility.
REVISION=$(j 'int(d["feedback"]["revision"])')
[ "$(j 'bool(d["feedback"].get("development_action"))')" = True ] || fail 'Existing feedback lacks a development action'
printf 'player_profile_id=%s\nprogram_id=%s\ninvitation_status=%s\nfeedback_id=%s revision=%s\n' "$LP_ID" "$PROGRAM_ID" "$INVITATION_STATUS" "$FEEDBACK_ID" "$REVISION"
printf 'Reviewer (player login): Home → My profiles → %s → Coach feedback → Building your next pass\n' "$PROFILE_NAME"
printf 'Accepted connection: Home → Club invitations\n'
