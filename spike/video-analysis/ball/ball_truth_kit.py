"""Extract every 2 fps sample of all windows for independent human ball clicks."""

from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from label_rule import V2_FIELDS, migrate_row
from common import DEFAULT_MANIFEST, DEFAULT_SOURCE, HERE, dump, load_dataset, samples


def import_labels(path, frames):
    """Strict human-only intake: unknown/duplicate times and bad points fail."""
    allowed = {(f["clip"], round(f["t"], 6)): f for f in frames}
    labels = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            not {"clip", "t", "x", "y", "visible"} <= set(row)
            or set(row)
            - V2_FIELDS
            - {
                "clip",
                "t",
                "x",
                "y",
                "visible",
                "source_accepted",
                "accepted_source",
                "accepted_score",
            }
            or type(row["visible"]) is not bool
        ):
            raise ValueError("expected {clip,t,x,y,visible}")
        if type(row["t"]) not in (int, float) or not math.isfinite(row["t"]):
            raise ValueError("finite timestamp required")
        key = row["clip"], round(row["t"], 6)
        if key not in allowed or key in labels:
            raise ValueError("unknown or duplicate clip/time")
        if row["visible"]:
            size = allowed[key]["source_size"]
            for v, limit in zip((row["x"], row["y"]), size):
                if (
                    type(v) not in (int, float)
                    or not math.isfinite(v)
                    or not 0 <= v < limit
                ):
                    raise ValueError("invalid source coordinates")
        elif row["x"] is not None or row["y"] is not None:
            raise ValueError("invisible coordinates must be null")
        if "source_accepted" in row and type(row["source_accepted"]) is not bool:
            raise ValueError("source_accepted must be boolean")
        if row.get("source_accepted"):
            if (
                not row["visible"]
                or not isinstance(row.get("accepted_source"), str)
                or not row["accepted_source"]
                or type(row.get("accepted_score")) not in (int, float)
                or not math.isfinite(row["accepted_score"])
                or not 0 <= row["accepted_score"] <= 1
            ):
                raise ValueError("accepted suggestion provenance required")
        elif "accepted_source" in row or "accepted_score" in row:
            raise ValueError("provenance requires source_accepted")
        labels[key] = migrate_row(row, allowed[key])
    return labels


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><title>Ball truth review</title>
<style>body{font:16px system-ui;background:#15191d;color:#eee;margin:24px}button,select,input{font:inherit;margin:6px;padding:8px}canvas{width:100%;height:auto;cursor:crosshair}nav{position:sticky;top:0;background:#15191d;padding:8px}#status{color:#ffdc80}</style>
<h1>Ball truth — confirm or correct suggestions</h1><p>Click the centre of a visible ball, or choose No ball at all. Every visible ball counts. Normal labels default to match ball; M toggles the match-ball flag. Review mode defaults to NOT the match ball. Leave uncertain frames unlabelled. Hollow cyan rings are unconfirmed suggestions. Enter/Space accepts; a click overrides; N marks no ball. Arrows change frame; J/K change clip. Suggestions never save themselves. Coordinates export in original source pixels; times are absolute match seconds. Labels save in this browser; export JSONL as a backup.</p>
<nav><button id="review">Review: any visible ball?</button><button id="match">M: toggle match ball</button><select id="clips" aria-label="Clip"></select><button id="prev">Previous</button><button id="next">Next</button><button id="target">Next unlabelled target</button><button id="unlabelled">Next unlabelled frame</button><button id="accept">Accept suggestion</button><button id="none">No ball visible</button><button id="clear">Clear label</button><button id="zoom">Native size</button><button id="export">Export JSONL</button><label>Import JSONL <input id="import" type="file" accept=".jsonl,.json,.txt"></label><p id="progress"></p><p id="caption"></p><p id="status" role="status"></p></nav>
<canvas id="canvas" aria-label="Click the ball centre in the frame"></canvas>
<script>__IO__</script><script>
const reviewQueue=__QUEUE__, reviewKeys=new Set(reviewQueue.map(r=>BallTruth.key(r)));
const frames=__FRAMES__, suggestions=__SUGGESTIONS__, targets=__TARGETS__, storageKey=__KEY__, api=BallTruth;
const suggestionMap=Object.fromEntries(suggestions.map(s=>[api.key(s),s])), targetKeys=new Set(targets.map(api.key));
let reviewMode=false;
const reviewSuggestionMap=Object.fromEntries(reviewQueue.filter(r=>r.suggestion).map(r=>[api.key(r),r.suggestion]));
function suggestionFor(f){return (reviewMode?reviewSuggestionMap:suggestionMap)[api.key(f)];}
function confirmed(r){return r?.review_confirmed && !r.needs_any_ball_review && !r.needs_confirmation;}
let labels=Object.fromEntries(__LABELS__.map(row=>[api.key(row),row])), index=0, generation=0, imageReady=false;
const clearedKey=storageKey+':cleared'; let cleared=new Set();
const status=document.getElementById('status'), canvas=document.getElementById('canvas'), ctx=canvas.getContext('2d');
try {for(const row of api.parse(localStorage.getItem(storageKey)||'',frames)) labels[api.key(row)]=row;} catch(e){status.textContent='Saved labels could not be loaded: '+e.message;}
try {cleared=new Set(JSON.parse(localStorage.getItem(clearedKey)||'[]'));for(const key of cleared)delete labels[key];} catch(e){status.textContent='Cleared-label history could not be loaded: '+e.message;}
const clips=document.getElementById('clips');
for(const clip of [...new Set(frames.map(f=>f.clip))]) {const o=document.createElement('option');o.value=clip;o.textContent=clip;clips.appendChild(o);}
function save(){try{localStorage.setItem(clearedKey,JSON.stringify([...cleared]));localStorage.setItem(storageKey,api.serialize(Object.values(labels),frames));status.textContent='Saved locally. '+Object.keys(labels).length+'/'+frames.length+' labelled.';}catch(e){status.textContent='Storage unavailable: export JSONL now. '+e.message;}}
function show(){document.getElementById('progress').textContent=`labelled ${Object.keys(labels).length} / ${frames.length} (${frames.length-Object.keys(labels).length} remaining) · targets ${Object.keys(labels).filter(k=>targetKeys.has(k)).length} / ${targetKeys.size} (540 on-ball + 100 off-pitch sample)`;if(reviewMode)document.getElementById('progress').textContent=`reviewed ${reviewQueue.filter(f=>confirmed(labels[api.key(f)])).length} / ${reviewQueue.length}`;document.getElementById('accept').disabled=!suggestionFor(frames[index]);imageReady=false;const f=frames[index], row=labels[api.key(f)], token=++generation;clips.value=f.clip;document.getElementById('caption').textContent=`${f.clip} · ${index+1}/${frames.length} · t=${f.t.toFixed(3)} s · ${row?(row.visible?`ball visible · match ball: ${row.match_ball===null?'unknown':row.match_ball?'YES':'NO'}`:'no ball at all'):'UNLABELLED'}`;const suggestion=suggestionFor(f);document.getElementById('caption').textContent += (targetKeys.has(api.key(f))?' · TARGET':' · optional') + (suggestion?` · suggestion ${suggestion.source} (${suggestion.score.toFixed(3)})`:' · no suggestion');const img=new Image();img.onload=()=>{if(token!==generation)return;canvas.width=img.width;canvas.height=img.height;ctx.drawImage(img,0,0);imageReady=true;if(suggestion){ctx.strokeStyle='#50e8ff';ctx.lineWidth=3;ctx.beginPath();ctx.arc(suggestion.x*img.width/f.source_size[0],suggestion.y*img.height/f.source_size[1],15,0,2*Math.PI);ctx.stroke();ctx.font='20px system-ui';ctx.fillStyle='#50e8ff';ctx.fillText(suggestion.source,suggestion.x*img.width/f.source_size[0]+18,suggestion.y*img.height/f.source_size[1]);}if(row&&row.visible){ctx.strokeStyle='#ff3050';ctx.lineWidth=2;ctx.beginPath();ctx.arc(row.x*img.width/f.source_size[0],row.y*img.height/f.source_size[1],10,0,2*Math.PI);ctx.stroke();}};img.src=f.path;}
function label(x,y,visible,provenance={source_accepted:false}){const f=frames[index];cleared.delete(api.key(f));labels[api.key(f)]=api.validate({clip:f.clip,t:f.t,x,y,visible,schema_version:2,match_ball:visible?!reviewMode:null,...(reviewKeys.has(api.key(f))?{review_frame:true,review_confirmed:reviewMode,needs_any_ball_review:!reviewMode,needs_confirmation:!reviewMode}:{}),...provenance},frames);save();show();}
canvas.onclick=e=>{if(!imageReady)return;const r=canvas.getBoundingClientRect(), f=frames[index];label(Math.min(f.source_size[0]-.001,Math.max(0,(e.clientX-r.left)/r.width*f.source_size[0])),Math.min(f.source_size[1]-.001,Math.max(0,(e.clientY-r.top)/r.height*f.source_size[1])),true);};
document.getElementById('zoom').onclick=()=>{const native=canvas.style.width!=='1920px';canvas.style.width=native?'1920px':'100%';document.getElementById('zoom').textContent=native?'Fit width':'Native size';};
document.getElementById('accept').onclick=()=>{if(!imageReady)return;const s=suggestionFor(frames[index]);if(s)label(s.x,s.y,true,{source_accepted:true,accepted_source:s.source,accepted_score:s.score});};
document.getElementById('none').onclick=()=>label(null,null,false);
document.getElementById('clear').onclick=()=>{cleared.add(api.key(frames[index]));delete labels[api.key(frames[index])];save();show();};
function move(step){if(reviewMode){const i=reviewQueue.findIndex(f=>api.key(f)===api.key(frames[index]));const next=reviewQueue[Math.max(0,Math.min(reviewQueue.length-1,i+step))];if(next)index=frames.findIndex(f=>api.key(f)===api.key(next));}else index=Math.max(0,Math.min(frames.length-1,index+step));show();}
document.getElementById('prev').onclick=()=>move(-1);
document.getElementById('review').onclick=()=>{reviewMode=!reviewMode;document.getElementById('review').textContent=reviewMode?'Normal labelling':'Review: any visible ball?';for(const id of ['clips','target','unlabelled'])document.getElementById(id).disabled=reviewMode;if(reviewMode&&reviewQueue.length){const next=reviewQueue.find(f=>!confirmed(labels[api.key(f)]))||reviewQueue[0];index=frames.findIndex(f=>api.key(f)===api.key(next));}show();};
document.getElementById('match').onclick=()=>{const row=labels[api.key(frames[index])];if(!row?.visible)return;row.match_ball=row.match_ball!==true;save();show();};
document.getElementById('target').onclick=()=>{const next=[...frames.keys()].map(i=>(index+1+i)%frames.length).find(i=>targetKeys.has(api.key(frames[i]))&&!labels[api.key(frames[i])]);if(next!==undefined){index=next;show();}};
document.getElementById('unlabelled').onclick=()=>{const next=[...frames.keys()].map(i=>(index+1+i)%frames.length).find(i=>!labels[api.key(frames[i])]);if(next!==undefined){index=next;show();}};
document.getElementById('next').onclick=()=>move(1);
clips.onchange=()=>{index=frames.findIndex(f=>f.clip===clips.value);show();};
document.getElementById('export').onclick=()=>{const url=URL.createObjectURL(new Blob([api.serialize(Object.values(labels),frames)],{type:'application/x-ndjson'})),a=document.createElement('a');a.href=url;a.download='ball-human-truth-v2.jsonl';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
document.getElementById('import').onchange=async e=>{try{const rows=api.parse(await e.target.files[0].text(),frames);for(const row of rows){cleared.delete(api.key(row));labels[api.key(row)]=row;}save();show();}catch(err){status.textContent='Import rejected: '+err.message;}};
document.addEventListener('keydown',e=>{if(e.target.tagName==='SELECT'||e.target.tagName==='INPUT')return;if(['ArrowRight','ArrowLeft','Enter',' ','n','N','j','J','k','K','m','M'].includes(e.key))e.preventDefault();if(e.key==='Enter'||e.key===' ')document.getElementById('accept').click();if(e.key.toLowerCase()==='n')document.getElementById('none').click();if(e.key.toLowerCase()==='m')document.getElementById('match').click();if(['j','k'].includes(e.key.toLowerCase())){if(reviewMode){const ids=[...new Set(reviewQueue.map(f=>f.clip))],step=e.key.toLowerCase()==='j'?1:-1;const cid=ids[Math.max(0,Math.min(ids.length-1,ids.indexOf(frames[index].clip)+step))];const next=reviewQueue.find(f=>f.clip===cid);if(next)index=frames.findIndex(f=>api.key(f)===api.key(next));show();return;}const ids=[...new Set(frames.map(f=>f.clip))],step=e.key.toLowerCase()==='j'?1:-1;index=frames.findIndex(f=>f.clip===ids[Math.max(0,Math.min(ids.length-1,ids.indexOf(frames[index].clip)+step))]);show();}if(e.key==='ArrowRight')document.getElementById('next').click();if(e.key==='ArrowLeft')document.getElementById('prev').click();});show();
</script></html>"""


def build(
    manifest,
    source,
    out,
    suggestions=None,
    human_jsonl=None,
    review=None,
    reuse_only=False,
):
    import cv2

    data, clips = load_dataset(manifest, source)
    out.mkdir(parents=True, exist_ok=True)
    # Reuse verified existing frame files, preserving pixels and browser storage key.
    from human_loop import review_plan, load_suggestions
    from metrics import clip_class

    old_build = (
        json.loads((out / "build.json").read_text())
        if (out / "build.json").exists()
        else {}
    )
    reuse = (
        old_build.get("frozen_set_id") == data["frozen_set_id"]
        and old_build.get("source") == str(source)
        and (out / "frames.json").exists()
    )
    old_frames = json.loads((out / "frames.json").read_text()) if reuse else []
    frames: list[dict] = []
    clips.sort(key=lambda c: clip_class(c) != "on_ball")
    for clip in clips:
        folder = out / clip["clip_id"]
        folder.mkdir(exist_ok=True)
        cached = [f for f in old_frames if f["clip"] == clip["clip_id"]]
        if cached and all((out / f["path"]).is_file() for f in cached):
            frames.extend({**f, "class": clip_class(clip)} for f in cached)
            continue
        if reuse_only:
            raise ValueError("build 9 requires existing cached frames")
        for sample, stack in samples(clip):
            relative = f"{clip['clip_id']}/{sample['sample_index']:05d}.jpg"
            if not cv2.imwrite(
                str(out / relative),
                cv2.cvtColor(stack[-1], cv2.COLOR_RGB2BGR),
                [cv2.IMWRITE_JPEG_QUALITY, 98],
            ):
                raise RuntimeError("image write failed")
            frames.append(
                {
                    **sample,
                    "clip": clip["clip_id"],
                    "path": relative,
                    "source_size": clip["source_size"],
                    "class": clip_class(clip),
                }
            )
        print(f"kit {clip['clip_id']}", flush=True)
    dump(out / "frames.json", frames)
    key = f"ball-human-v1:{data['frozen_set_id']}:{str(source)}:fps2"
    suggestion_rows = load_suggestions(suggestions, frames)
    plan = review_plan(frames)
    confirmed = list(import_labels(human_jsonl, frames).values()) if human_jsonl else []
    queue = json.loads(Path(review).read_text()) if review else []
    page = (
        PAGE.replace("__QUEUE__", json.dumps(queue).replace("<", "\\u003c"))
        .replace("__IO__", (HERE / "truth_io.js").read_text())
        .replace("__LABELS__", json.dumps(confirmed).replace("<", "\\u003c"))
        .replace("__FRAMES__", json.dumps(frames).replace("<", "\\u003c"))
        .replace("__KEY__", json.dumps(key))
        .replace("__SUGGESTIONS__", json.dumps(suggestion_rows).replace("<", "\\u003c"))
        .replace("__TARGETS__", json.dumps(plan["on_ball"] + plan["off_pitch"]))
    )
    (out / "index.html").write_text(page)
    dump(
        out / "build.json",
        {
            "build_version": 9,
            "label_schema_version": 2,
            "review_frames": len(queue),
            "review_suggestions": sum(r["suggestion"] is not None for r in queue),
            "confirmed_seed_labels": len(confirmed),
            "storage_key": key,
            "suggestions": len(suggestion_rows),
            "suggestions_by_source": {
                name: sum(r["source"] == name for r in suggestion_rows)
                for name in sorted({r["source"] for r in suggestion_rows})
            },
            "review_plan": plan,
            "frozen_set_id": data["frozen_set_id"],
            "source": str(source),
            "fps": 2,
            "frames": len(frames),
            "clips": len(clips),
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument("--out", type=Path, default=Path.home() / "ball-truth-review")
    p.add_argument("--suggestions", type=Path)
    p.add_argument(
        "--human-jsonl",
        type=Path,
        help="Seed validated confirmed labels; newer browser labels take precedence",
    )
    p.add_argument("--review", type=Path, help="Saved any-ball review queue")
    a = p.parse_args()
    build(a.manifest, a.source, a.out, a.suggestions, a.human_jsonl, a.review)
    if a.out == Path.home() / "ball-truth-review":
        dump(
            Path.home() / "codex-runs/ball-truth-review-build.json",
            json.loads((a.out / "build.json").read_text()),
        )
