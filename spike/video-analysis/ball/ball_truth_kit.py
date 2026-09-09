"""Extract every 2 fps sample of all windows for independent human ball clicks."""

from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
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
            set(row) != {"clip", "t", "x", "y", "visible"}
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
        labels[key] = row
    return labels


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><title>Ball truth review</title>
<style>body{font:16px system-ui;background:#15191d;color:#eee;margin:24px}button,select,input{font:inherit;margin:6px;padding:8px}canvas{width:100%;height:auto;cursor:crosshair}nav{position:sticky;top:0;background:#15191d;padding:8px}#status{color:#ffdc80}</style>
<h1>Ball truth — independent human labels</h1><p>Click the centre of the match ball, or choose No ball visible. Leave uncertain frames unlabelled. No detector predictions are shown. Coordinates export in original source pixels; times are absolute match seconds. Labels save in this browser; export JSONL as a backup.</p>
<nav><select id="clips" aria-label="Clip"></select><button id="prev">Previous</button><button id="next">Next</button><button id="none">No ball visible</button><button id="clear">Clear label</button><button id="zoom">Native size</button><button id="export">Export JSONL</button><label>Import JSONL <input id="import" type="file" accept=".jsonl,.json,.txt"></label><p id="caption"></p><p id="status" role="status"></p></nav>
<canvas id="canvas" aria-label="Click the ball centre in the frame"></canvas>
<script>__IO__</script><script>
const frames=__FRAMES__, storageKey=__KEY__, api=BallTruth;
let labels={}, index=0, generation=0, imageReady=false;
const status=document.getElementById('status'), canvas=document.getElementById('canvas'), ctx=canvas.getContext('2d');
try {for(const row of api.parse(localStorage.getItem(storageKey)||'',frames)) labels[api.key(row)]=row;} catch(e){status.textContent='Saved labels could not be loaded: '+e.message;}
const clips=document.getElementById('clips');
for(const clip of [...new Set(frames.map(f=>f.clip))]) {const o=document.createElement('option');o.value=clip;o.textContent=clip;clips.appendChild(o);}
function save(){try{localStorage.setItem(storageKey,api.serialize(Object.values(labels),frames));status.textContent='Saved locally. '+Object.keys(labels).length+'/'+frames.length+' labelled.';}catch(e){status.textContent='Storage unavailable: export JSONL now. '+e.message;}}
function show(){imageReady=false;const f=frames[index], row=labels[api.key(f)], token=++generation;clips.value=f.clip;document.getElementById('caption').textContent=`${f.clip} · ${index+1}/${frames.length} · t=${f.t.toFixed(3)} s · ${row?(row.visible?'ball visible':'no ball visible'):'UNLABELLED'}`;const img=new Image();img.onload=()=>{if(token!==generation)return;canvas.width=img.width;canvas.height=img.height;ctx.drawImage(img,0,0);imageReady=true;if(row&&row.visible){ctx.strokeStyle='#ff3050';ctx.lineWidth=2;ctx.beginPath();ctx.arc(row.x*img.width/f.source_size[0],row.y*img.height/f.source_size[1],10,0,2*Math.PI);ctx.stroke();}};img.src=f.path;}
function label(x,y,visible){const f=frames[index];labels[api.key(f)]=api.validate({clip:f.clip,t:f.t,x,y,visible},frames);save();show();}
canvas.onclick=e=>{if(!imageReady)return;const r=canvas.getBoundingClientRect(), f=frames[index];label(Math.min(f.source_size[0]-.001,Math.max(0,(e.clientX-r.left)/r.width*f.source_size[0])),Math.min(f.source_size[1]-.001,Math.max(0,(e.clientY-r.top)/r.height*f.source_size[1])),true);};
document.getElementById('zoom').onclick=()=>{const native=canvas.style.width!=='1920px';canvas.style.width=native?'1920px':'100%';document.getElementById('zoom').textContent=native?'Fit width':'Native size';};
document.getElementById('none').onclick=()=>label(null,null,false);
document.getElementById('clear').onclick=()=>{delete labels[api.key(frames[index])];save();show();};
document.getElementById('prev').onclick=()=>{index=Math.max(0,index-1);show();};
document.getElementById('next').onclick=()=>{index=Math.min(frames.length-1,index+1);show();};
clips.onchange=()=>{index=frames.findIndex(f=>f.clip===clips.value);show();};
document.getElementById('export').onclick=()=>{const url=URL.createObjectURL(new Blob([api.serialize(Object.values(labels),frames)],{type:'application/x-ndjson'})),a=document.createElement('a');a.href=url;a.download='ball-human-truth.jsonl';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
document.getElementById('import').onchange=async e=>{try{const rows=api.parse(await e.target.files[0].text(),frames);for(const row of rows)labels[api.key(row)]=row;save();show();}catch(err){status.textContent='Import rejected: '+err.message;}};
document.addEventListener('keydown',e=>{if(e.target.tagName==='SELECT'||e.target.tagName==='INPUT')return;if(e.key==='ArrowRight')document.getElementById('next').click();if(e.key==='ArrowLeft')document.getElementById('prev').click();});show();
</script></html>"""


def build(manifest, source, out):
    import cv2

    data, clips = load_dataset(manifest, source)
    out.mkdir(parents=True, exist_ok=True)
    frames = []
    for clip in clips:
        folder = out / clip["clip_id"]
        folder.mkdir(exist_ok=True)
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
                }
            )
        print(f"kit {clip['clip_id']}", flush=True)
    dump(out / "frames.json", frames)
    key = f"ball-human-v1:{data['frozen_set_id']}:{str(source)}:fps2"
    page = (
        PAGE.replace("__IO__", (HERE / "truth_io.js").read_text())
        .replace("__FRAMES__", json.dumps(frames).replace("<", "\\u003c"))
        .replace("__KEY__", json.dumps(key))
    )
    (out / "index.html").write_text(page)
    dump(
        out / "build.json",
        {
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
    a = p.parse_args()
    build(a.manifest, a.source, a.out)
