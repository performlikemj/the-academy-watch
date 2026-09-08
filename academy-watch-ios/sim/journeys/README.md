# iOS journey JSON v1.3

Every file is a fixture-backed journey. The host reads selected files, injects their JSON content
as one `SIM_JOURNEYS_JSON` array, and the UI-test process iterates them in one test invocation.
The test process never reads a Mac path. As a secondary channel, `SIM_JOURNEYS` selects
comma-separated bundle resource names matching `^[a-z0-9-]+$`.
With neither variable present, `testJourneys` skips before app launch, making the runner safe inside
an app's normal UI-test target; a present but empty or malformed injection still fails.

Add bundle resources to the UI-test target. With XcodeGen:

```yaml
targets:
  AppUITests:
    type: bundle.ui-testing
    platform: iOS
    sources: [UITests]
    resources:
      - path: sim/journeys
```

## Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Harness iOS journey v1.3",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "name", "fixture_evidence", "steps"],
  "properties": {
    "version": {"enum": ["1.1", "1.2", "1.3"]},
    "name": {"type": "string", "minLength": 1},
    "settle_ms": {"type": "integer", "minimum": 1, "default": 400},
    "settle_timeout_ms": {"type": "integer", "minimum": 1, "default": 4000},
    "settle_quiet_ratio": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.005},
    "fixture_evidence": {
      "type": "object",
      "additionalProperties": false,
      "required": ["offered_inputs", "server_state", "layout", "preflight"],
      "properties": {
        "offered_inputs": {"$ref": "#/$defs/claims"},
        "server_state": {"$ref": "#/$defs/claims"},
        "server_state_reason": {"type": "string", "minLength": 1},
        "layout": {"$ref": "#/$defs/claims"},
        "preflight": {
          "type": "object", "additionalProperties": false, "required": ["kind", "note"],
          "properties": {"kind": {"enum": ["none", "api"]}, "note": {"type": "string", "minLength": 1}}
        }
      }
    },
    "preconditions": {
      "type": "array",
      "items": {
        "oneOf": [
          {"type":"object","additionalProperties":false,"required":["kind","service","bundle_id"],"properties":{"kind":{"const":"resetPermission"},"service":{"type":"string"},"bundle_id":{"type":"string"}}},
          {"type":"object","additionalProperties":false,"required":["kind","service","bundle_id"],"properties":{"kind":{"const":"grantPermission"},"service":{"type":"string"},"bundle_id":{"type":"string"}}},
          {"type":"object","additionalProperties":false,"required":["kind","bundle_id","payload"],"properties":{"kind":{"const":"push"},"bundle_id":{"type":"string"},"payload":{"type":"object"}}}
        ]
      }
    },
    "steps": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["id", "expectation", "action"],
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "expectation": {"type": "string"},
          "checkpoint": {"type": "boolean", "default": false},
          "continueOnFailure": {"type": "boolean", "default": false},
          "settle_ms": {"type": "integer", "minimum": 1},
          "settle_timeout_ms": {"type": "integer", "minimum": 1},
          "settle_quiet_ratio": {"type": "number", "minimum": 0, "maximum": 1},
          "settle": {"type":"object","additionalProperties":false,"required":["waitFor","timeout"],"properties":{"waitFor":{"$ref":"#/$defs/settle_locator"},"timeout":{"type":"number","exclusiveMinimum":0}}},
          "action": {
            "oneOf": [
              {"type":"object","required":["launch"],"properties":{"launch":{"type":"object","properties":{"args":{"type":"array","items":{"type":"string"}},"env":{"type":"object","additionalProperties":{"type":"string"}}}}}},
              {"type":"object","required":["tap"],"properties":{"tap":{"$ref":"#/$defs/locator"}}},
              {"type":"object","required":["type"],"properties":{"type":{"$ref":"#/$defs/type"}}},
              {"type":"object","required":["clearAndType"],"properties":{"clearAndType":{"$ref":"#/$defs/type"}}},
              {"type":"object","required":["swipe"],"properties":{"swipe":{"type":"object","required":["dir"],"properties":{"dir":{"enum":["up","down","left","right"]},"id":{"type":"string","minLength":1}}}}},
              {"type":"object","required":["waitFor"],"properties":{"waitFor":{"allOf":[{"$ref":"#/$defs/locator"},{"type":"object","required":["timeout"],"properties":{"timeout":{"type":"number","exclusiveMinimum":0}}}]}}},
              {"type":"object","required":["assertVisible"],"properties":{"assertVisible":{"$ref":"#/$defs/locator"}}},
              {"type":"object","additionalProperties":false,"required":["assertAbsent"],"properties":{"assertAbsent":{"$ref":"#/$defs/absence"}}},
              {"type":"object","additionalProperties":false,"required":["assertSelected"],"properties":{"assertSelected":{"type":"object","additionalProperties":false,"required":["id"],"properties":{"id":{"type":"string","minLength":1},"timeout":{"type":"number","exclusiveMinimum":0,"default":3}}}}},
              {"type":"object","required":["dismissKeyboard"],"properties":{"dismissKeyboard":{"type":"object","maxProperties":0}}},
              {"type":"object","required":["systemAlert"],"properties":{"systemAlert":{"type":"object","additionalProperties":false,"required":["action","timeout"],"properties":{"action":{"enum":["allow","deny","dismiss"]},"timeout":{"type":"number","exclusiveMinimum":0}}}}},
              {"type":"object","required":["screenshot"],"properties":{"screenshot":{"type":"object","maxProperties":0}}}
            ]
          }
        }
      }
    }
  },
  "$defs": {
    "absence": {"oneOf":[{"type":"object","additionalProperties":false,"required":["id"],"properties":{"id":{"type":"string","minLength":1},"timeout":{"type":"number","exclusiveMinimum":0,"default":3}}},{"type":"object","additionalProperties":false,"required":["text","why"],"properties":{"text":{"type":"string","minLength":1},"why":{"type":"string","minLength":1},"timeout":{"type":"number","exclusiveMinimum":0,"default":3}}}]},
    "claims": {"type":"array","items":{"type":"object","additionalProperties":false,"required":["claim","source"],"properties":{"claim":{"type":"string","minLength":1},"source":{"type":"string","pattern":"^.+:[0-9]+(-[0-9]+)?$"}}}},
    "locator": {"oneOf":[{"type":"object","additionalProperties":false,"required":["id"],"properties":{"id":{"type":"string","minLength":1}}},{"type":"object","additionalProperties":false,"required":["text","why"],"properties":{"text":{"type":"string","minLength":1},"why":{"type":"string","minLength":1}}}]},
    "settle_locator": {"oneOf":[{"type":"object","additionalProperties":false,"required":["id"],"properties":{"id":{"type":"string","minLength":1}}},{"type":"object","additionalProperties":false,"required":["text"],"properties":{"text":{"type":"string","minLength":1}}}]},
    "type": {"type":"object","additionalProperties":false,"required":["id","text"],"properties":{"id":{"type":"string","minLength":1},"text":{"type":"string"}}}
  }
}
```

If `server_state` is empty, `server_state_reason` is required and must say why the journey is a
signed-out preview. The host rejects every precondition kind outside `resetPermission`,
`grantPermission`, and `push`; it executes only those through `simctl`.

Schema v1.2 adds settled capture while preserving v1.1: omitted fields use the same defaults.
After each successful action, an explicit `settle.waitFor` first waits for its id or text to exist
and be hittable for at most `settle.timeout` seconds. Otherwise, a tapped id beginning
`tab-bar-` waits up to three seconds for `isSelected == true`. Every capture then compares two
120×260 RGBA samples `settle_ms` apart (journey default 400 ms, overridable per step). A pixel is
changed when any channel differs by more than 8/255; the frame is quiet when the changed-pixel
ratio is at most `settle_quiet_ratio` (default 0.005, overridable per journey or step) within
`settle_timeout_ms` (default 4000 ms). A timeout keeps the action `ok:true`, writes
`note:"settle timeout"`, and captures the latest frame. Each step records `settle_ms_used`, the
last measured `settle_diff_ratio`, and `settle_reason`: `predicate`, `selected`, `quiet`, or
`timeout`.

## v1.3 predicates

Only version `"1.3"` accepts `assertAbsent` and `assertSelected`; the host still rejects unknown
versions/actions. v1.1/v1.2 action and settle behavior is unchanged. Every exported journey now
carries `run_mode: "checkpoint" | "full"`, copied from execution rather than inferred from receipts.

- `{"assertAbsent":{"id":"home","timeout":3}}` polls for disappearance (default three seconds),
  then settles and checks absence with capture. Text requires `text` plus `why`. The app must be
  foreground and the previous action must have settled successfully; settle exhaustion fails
  with screenshot and label/id dump. A missing tree after a failed launch cannot prove absence.
- `{"assertSelected":{"id":"tab-bar-desk","timeout":3}}` polls for existence and `isSelected`,
  then rechecks at settled capture. Text locators are forbidden. Both timeout values are seconds.
- Use separate uniquely named steps for each predicate, including before/after states. A story's
  `proof.asserts` names those exact steps; tab membership uses visible expected tabs + absent exclusions.

## Complete example

```json
{
  "version": "1.2",
  "name": "edit-profile",
  "settle_ms": 400,
  "settle_quiet_ratio": 0.005,
  "fixture_evidence": {
    "offered_inputs": [{"claim": "Yuki is an offered profile seed.", "source": "Fixtures.swift:20"}],
    "server_state": [],
    "server_state_reason": "Signed-out preview; no server state is read.",
    "layout": [{"claim": "The editor exposes stable ids.", "source": "ProfileView.swift:42"}],
    "preflight": {"kind": "none", "note": "Local preview data is deterministic."}
  },
  "preconditions": [{"kind": "resetPermission", "service": "notifications", "bundle_id": "com.example.app"}],
  "steps": [
    {
      "id": "launch-profile",
      "expectation": "The profile screen shows the Edit profile button.",
      "checkpoint": true,
      "action": {"launch": {"args": ["-uiPreview"], "env": {"DEMO_MODE": "1"}}}
    },
    {
      "id": "open-editor",
      "expectation": "The name field is visible in the profile editor.",
      "action": {"tap": {"id": "profile-edit-button"}},
      "settle": {"waitFor": {"id": "profile-name-field"}, "timeout": 3}
    },
    {
      "id": "replace-name",
      "expectation": "The name field visibly contains Yuki.",
      "action": {"clearAndType": {"id": "profile-name-field", "text": "Yuki"}}
    },
    {
      "id": "confirm-title",
      "expectation": "The editor title Profile is visible.",
      "action": {"assertVisible": {"text": "Profile", "why": "This step deliberately verifies user-facing copy."}}
    }
  ]
}
```

## Evidence and selector discipline

- Read ids and fixture claims from source before authoring (Law 14). A new hash has no
  checkpoint-one receipt, so it runs only through its first `checkpoint:true` step. A successful
  checkpoint writes `report/.receipts/<sha256>`; the next run may execute the full journey.
- `tap`, `waitFor`, and `assertVisible` use `id`. A visible-text exception requires `why`,
  which is copied into the report note. `type` and `clearAndType` always require an id.
- `continueOnFailure` defaults false. Failure attaches a screenshot and the first 200 visible
  static-text/button ids and labels; only an explicit true continues.
- Expectations describe evidence visible in that step's screenshot. Empty means `observed`,
  never pass. Network calls, persistence, timing, and earlier frames are not visible evidence.
- Launch environment names containing password, token, secret, or bearer are rejected and never
  forwarded. `systemAlert` is the only permitted cross-process action.
