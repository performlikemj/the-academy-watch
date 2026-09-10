const api=BallTruth, store=BallStorage;
const byKey=Object.fromEntries(frames.map((f,i)=>[api.key(f),i]));
const suggestionMap=Object.fromEntries(suggestions.map(s=>[api.key(s),s]));
const reviewSuggestionMap=Object.fromEntries(savedReviewSuggestions.map(s=>[api.key(s),s]));
for(const row of initialReviewQueue) if(row.suggestion) reviewSuggestionMap[api.key(row)]=row.suggestion;
const targetKeys=new Set(targets.map(api.key));
const status=document.getElementById('status'), safety=document.getElementById('safety');
const canvas=document.getElementById('canvas'), ctx=canvas.getContext('2d'), clips=document.getElementById('clips');
let state=store.empty(), labels={}, reviewKeys=new Set(), reviewQueue=[], reviewMode=false;
let index=0, generation=0, imageReady=false, initialized=false, readOnly=false, recoveryExported=false;
let recoveryRaw=null, writes=Promise.resolve();
let conflictCount=0;
const seenConflicts=new Set(), legacyHashKey=storageKey+':legacy-sha256';
function recordConflict(key,local,stored) {
  const signature=JSON.stringify([key,local.updated_at,[store.values(local),store.values(stored)].sort()]);
  if(seenConflicts.has(signature))return;
  seenConflicts.add(signature);conflictCount++;
  const notice=document.getElementById('conflicts');notice.hidden=false;
  notice.textContent=`Merge conflicts: ${conflictCount}. Kept the confirmed decision already in storage. Review or export before changing it.`;
}
async function checkLegacyHash(raw=localStorage.getItem(legacyKey)) {
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(raw)));
  const hash=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
  const baseline=localStorage.getItem(legacyHashKey);
  if(baseline===null)localStorage.setItem(legacyHashKey,hash);
  else if(baseline!==hash) {
    const banner=document.getElementById('legacy-warning');banner.hidden=false;
    banner.textContent='The old click page was used after this page started. Export from it and import here to include those labels.';
  }
}
const confirmed=api.confirmed;
for(const clip of [...new Set(frames.map(f=>f.clip))]) {
  const o=document.createElement('option');o.value=clip;o.textContent=clip;clips.appendChild(o);
}
function suggestionFor(f) { return (reviewMode?reviewSuggestionMap:suggestionMap)[api.key(f)]; }
function rebuildQueue() {
  labels=state.labels;
  reviewKeys=api.reviewKeys(labels,baseReviewKeys);
  reviewQueue=[...reviewKeys].map(k=> {
    if (!(k in byKey)) throw new Error('Review key absent from frame catalog: '+k);
    return {...frames[byKey[k]],suggestion:reviewSuggestionMap[k]||null};
  }).sort((a,b)=>(b.suggestion?.score??-1)-(a.suggestion?.score??-1)||a.clip.localeCompare(b.clip)||a.t-b.t);
}
function failClosed(error) {
  readOnly=true;
  recoveryExported=false;
  try { recoveryRaw={v2:localStorage.getItem(storageKey),legacy:localStorage.getItem(legacyKey),legacy_cleared:localStorage.getItem(legacyKey+':cleared')}; }
  catch (_) { recoveryRaw={error:String(error)}; }
  safety.hidden=false;
  safety.textContent='READ-ONLY: stored labels could not be validated. Export a recovery backup, then re-import repaired JSONL. No edits will be saved. '+error.message;
  document.getElementById('export').textContent='Export recovery backup';
}
function locked(task) {
  // Web Locks serializes read/merge/write across Chromium tabs. Storage-event
  // reconciliation also merges deterministically where Web Locks is unavailable.
  return navigator.locks ? navigator.locks.request(storageKey,task) : task();
}
function enqueue(task) {
  writes=writes.then(()=>locked(task)).catch(error=>{failClosed(error);show();});
  return writes;
}
function refreshStored() {
  const stored=store.parse(localStorage.getItem(storageKey),frames);
  state=store.merge(state,stored,recordConflict);
  rebuildQueue();
  return stored;
}
function persist() {
  const value=store.serialize(state);
  if(localStorage.getItem(storageKey)!==value) localStorage.setItem(storageKey,value);
}
function save(change) {
  if(readOnly || !initialized) return Promise.resolve(false);
  return enqueue(()=> {
    if(readOnly) return false;
    refreshStored(); // No edits to memory until the full stored value validates.
    const next=change(state,store.clock(state));
    if(next===false) { show(); return false; }
    state=next;
    persist();rebuildQueue();show();
    status.textContent='Saved locally. '+Object.keys(labels).length+'/'+frames.length+' labelled.';
    return true;
  });
}
function put(row, time) {
  return api.validate({...row,updated_at:time},frames);
}
function setLabel(x,y,visible,provenance={source_accepted:false}) {
  if(!imageReady || readOnly) return;
  const f=frames[index], key=api.key(f), reviewing=reviewMode;
  return save((latest,time)=> {
    const row={clip:f.clip,t:f.t,x,y,visible,schema_version:2,match_ball:visible?!reviewing:null,...provenance};
    if(reviewKeys.has(key)) Object.assign(row,{review_frame:true,review_confirmed:reviewing,needs_any_ball_review:!reviewing,needs_confirmation:!reviewing});
    return {...latest,labels:{...latest.labels,[key]:put(row,time)}};
  });
}
function show() {
  rebuildQueue();
  if(reviewMode && !reviewKeys.has(api.key(frames[index])) && reviewQueue.length) index=byKey[api.key(reviewQueue[0])];
  const f=frames[index], row=labels[api.key(f)], suggestion=suggestionFor(f), token=++generation;
  document.getElementById('progress').textContent=reviewMode
    ?`reviewed ${reviewQueue.filter(f=>confirmed(labels[api.key(f)])).length} / ${reviewQueue.length}`
    :`labelled ${Object.keys(labels).length} / ${frames.length} (${frames.length-Object.keys(labels).length} remaining) · targets ${Object.keys(labels).filter(k=>targetKeys.has(k)).length} / ${targetKeys.size}`;
  for(const id of ['none','clear','match','confirm','accept']) document.getElementById(id).disabled=readOnly||!initialized;
  document.getElementById('accept').disabled ||= !suggestion;
  document.getElementById('match').disabled ||= !row?.visible;
  document.getElementById('confirm').disabled ||= !reviewMode||!row?.visible;
  document.getElementById('caption').textContent=`${f.clip} · s${f.sample_index} · t=${f.t.toFixed(3)} s · ${row?(row.visible?`ball visible · match ball: ${row.match_ball===null?'unknown':row.match_ball?'YES':'NO'}`:'no ball at all'):'UNLABELLED'}${suggestion?` · suggestion ${suggestion.source} (${suggestion.score.toFixed(3)})`:' · no suggestion'}`;
  clips.value=f.clip;imageReady=false;
  const img=new Image();
  img.onload=()=> {
    if(token!==generation) return;
    canvas.width=img.width;canvas.height=img.height;ctx.drawImage(img,0,0);imageReady=true;
    function ring(x,y,color,radius) {ctx.strokeStyle=color;ctx.lineWidth=3;ctx.beginPath();ctx.arc(x*img.width/f.source_size[0],y*img.height/f.source_size[1],radius,0,2*Math.PI);ctx.stroke();}
    if(suggestion) {ring(suggestion.x,suggestion.y,'#50e8ff',15);ctx.font='20px system-ui';ctx.fillStyle='#50e8ff';ctx.fillText(suggestion.source,suggestion.x*img.width/f.source_size[0]+18,suggestion.y*img.height/f.source_size[1]);}
    if(row?.visible) ring(row.x,row.y,'#ff3050',10);
  };
  img.onerror=()=>{if(token===generation)status.textContent='Frame unavailable. Check the shared frames directory.';};
  img.src=f.path;
}
function move(step) {
  if(reviewMode) {
    const i=reviewQueue.findIndex(f=>api.key(f)===api.key(frames[index]));
    const next=reviewQueue[Math.max(0,Math.min(reviewQueue.length-1,i+step))];
    if(next) index=byKey[api.key(next)];
  } else index=Math.max(0,Math.min(frames.length-1,index+step));
  show();
}
function moveClip(step) {
  const available=reviewMode?reviewQueue:frames;
  const ids=[...new Set(available.map(f=>f.clip))];
  const cid=ids[Math.max(0,Math.min(ids.length-1,ids.indexOf(frames[index].clip)+step))];
  const next=available.find(f=>f.clip===cid);
  if(next)index=byKey[api.key(next)];show();
}
canvas.onclick=e=> {
  if(!imageReady||readOnly)return;
  const r=canvas.getBoundingClientRect(), f=frames[index];
  setLabel(Math.min(f.source_size[0]-.001,Math.max(0,(e.clientX-r.left)/r.width*f.source_size[0])),Math.min(f.source_size[1]-.001,Math.max(0,(e.clientY-r.top)/r.height*f.source_size[1])),true);
};
document.getElementById('accept').onclick=()=>{const s=suggestionFor(frames[index]);if(s)setLabel(s.x,s.y,true,{source_accepted:true,accepted_source:s.source,accepted_score:s.score});};
document.getElementById('none').onclick=()=>setLabel(null,null,false);
document.getElementById('clear').onclick=()=> {
  if(readOnly||!imageReady)return;
  const key=api.key(frames[index]);
  save((latest,time)=>store.merge(latest,{labels:{},deleted:{[key]:time}}));
};
document.getElementById('match').onclick=()=> {
  if(readOnly||!imageReady)return;
  const key=api.key(frames[index]);
  save((latest,time)=> {
    const row=latest.labels[key];if(!row?.visible)return false;
    return {...latest,labels:{...latest.labels,[key]:put({...row,match_ball:row.match_ball!==true},time)}};
  });
};
document.getElementById('confirm').onclick=()=> {
  if(readOnly||!imageReady||!reviewMode)return;
  const key=api.key(frames[index]);
  save((latest,time)=> {
    const row=latest.labels[key];if(!row?.visible||!reviewKeys.has(key))return false;
    return {...latest,labels:{...latest.labels,[key]:put({...row,match_ball:false,review_frame:true,review_confirmed:true,needs_confirmation:false,needs_any_ball_review:false},time)}};
  });
};
document.getElementById('review').onclick=()=> {
  reviewMode=!reviewMode;
  document.getElementById('review').textContent=reviewMode?'Normal labelling':'Review: any visible ball?';
  for(const id of ['clips','target','unlabelled'])document.getElementById(id).disabled=reviewMode;
  if(reviewMode&&reviewQueue.length)index=byKey[api.key(reviewQueue.find(f=>!confirmed(labels[api.key(f)]))||reviewQueue[0])];
  show();
};
document.getElementById('prev').onclick=()=>move(-1);
document.getElementById('next').onclick=()=>move(1);
for(const [id,predicate] of [['target',f=>targetKeys.has(api.key(f))],['unlabelled',()=>true]]) {
  document.getElementById(id).onclick=()=>{const next=[...frames.keys()].map(i=>(index+1+i)%frames.length).find(i=>predicate(frames[i])&&!labels[api.key(frames[i])]);if(next!==undefined){index=next;show();}};
}
clips.onchange=()=>{index=frames.findIndex(f=>f.clip===clips.value);show();};
document.getElementById('zoom').onclick=()=>{const native=canvas.style.width!=='1920px';canvas.style.width=native?'1920px':'100%';document.getElementById('zoom').textContent=native?'Fit width':'Native size';};
function download(text,name) {
  const url=URL.createObjectURL(new Blob([text],{type:'application/json'})),a=document.createElement('a');
  a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.getElementById('export').onclick=async()=> {
  await writes;
  if(readOnly) {download(JSON.stringify({storage_key:storageKey,...recoveryRaw,validated_labels:Object.values(labels)},null,2),'ball-truth-recovery.json');recoveryExported=true;}
  else {try{await locked(()=>refreshStored());download(api.serialize(Object.values(labels),frames),'ball-human-truth-v2.jsonl');}catch(e){failClosed(e);show();}}
};
function importPlan(rows, legacy) {
  const counts={new:0,changed:0,unchanged:0,would_downgrade_confirmed:0,replace_confirmed:0,newer_locally:0,stale:0};
  for(const row of rows) {
    const old=labels[api.key(row)];
    const changed=!!old && store.values(old)!==store.values(row);
    counts[!old?'new':changed?'changed':'unchanged']++;
    if(changed && row.updated_at<old.updated_at)counts.stale++;
    if(changed && confirmed(old)) {
      counts.replace_confirmed++;
      if(row.updated_at<old.updated_at)counts.newer_locally++;
    }
    if(confirmed(old)&&(!confirmed(row)||legacy.has(api.key(row))))counts.would_downgrade_confirmed++;
  }
  return counts;
}
document.getElementById('import').onchange=async e=> {
  try {
    const text=await e.target.files[0].text(), rows=api.parse(text,frames);
    const legacy=new Set(text.split(/\r?\n/).filter(s=>s.trim()).map(s=>JSON.parse(s)).filter(r=>!('match_ball' in r)||r.schema_version===1).map(api.key));
    await enqueue(()=> {
      if(!readOnly) refreshStored();
      const counts=importPlan(rows,legacy);
      const summary=`Import: ${counts.new} new, ${counts.changed} changed, ${counts.unchanged} unchanged, ${counts.would_downgrade_confirmed} would-downgrade-confirmed; would replace ${counts.replace_confirmed} confirmed decisions (${counts.newer_locally} of them newer locally). ${counts.stale} STALE changed rows; keep stored rows unless replacement is explicitly approved.`;
      document.getElementById('import-summary').textContent=summary;
      if(readOnly) {
        if(!recoveryExported) {status.textContent='Export the recovery backup before re-importing.';return;}
        if(!window.confirm(summary+' Replace unreadable v2 storage with these validated rows?'))return;
        // Do not overwrite storage that changed after the recovery backup.
        if(localStorage.getItem(storageKey)!==recoveryRaw.v2)throw new Error('Storage changed since recovery export. Export a fresh backup and re-import.');
      } else if((counts.replace_confirmed || counts.stale) && !window.confirm(summary+' Replace confirmed reviews and/or stale imported rows? Cancel keeps stored decisions exactly; OK explicitly replaces and restamps the changed rows.')) {
        status.textContent='Import cancelled; confirmed reviews preserved.';return;
      }
      const recovering=readOnly;
      if(recovering)state=store.empty();
      const time=store.clock(state);
      for(const row of rows) {
        const key=api.key(row);
        if(recovering||store.values(state.labels[key])!==store.values(row))state.labels[key]=put(row,time);
      }
      // This is a validated, explicit recovery/import, not an edit through save().
      persist();readOnly=false;recoveryExported=false;safety.hidden=true;
      document.getElementById('export').textContent='Export JSONL';
      rebuildQueue();show();status.textContent='Import saved. '+summary;
    });
  } catch(error) {status.textContent='Import rejected: '+error.message;}
  finally {e.target.value='';}
};
window.addEventListener('storage',e=> {
  if(e.key===legacyKey) {enqueue(()=>checkLegacyHash());return;}
  if(e.key!==storageKey&&e.key!==null)return;
  if(readOnly)return;
  enqueue(()=>{if(readOnly)return;refreshStored();persist();show();status.textContent='labels changed in another tab';});
});
document.addEventListener('keydown',e=> {
  if(['SELECT','INPUT'].includes(e.target.tagName))return;
  const key=e.key.toLowerCase();
  if(['arrowright','arrowleft','enter',' ','n','m','c','j','k'].includes(key))e.preventDefault();
  if(['enter',' ','n','m','c'].includes(key)&&readOnly)return;
  if(key==='enter'||key===' ')document.getElementById('accept').click();
  if(key==='n')document.getElementById('none').click();
  if(key==='m')document.getElementById('match').click();
  if(key==='c')document.getElementById('confirm').click();
  if(key==='j'||key==='k')moveClip(key==='j'?1:-1);
  if(key==='arrowright')move(1);if(key==='arrowleft')move(-1);
});
enqueue(async()=> {
  try {
    const raw=localStorage.getItem(storageKey), legacyRaw=localStorage.getItem(legacyKey);
    if(raw!==null && raw!=='')state=store.parse(raw,frames);
    else {
      state=store.fromRows(api.parse(seedRows.map(r=>JSON.stringify(r)).join('\n'),frames));
      // Legacy is bootstrap input only; later reads hash it, never merge it again.
      const legacy=api.parse(legacyRaw||'',frames);
      for(const row of legacy)state.labels[api.key(row)]=row;
      const cleared=JSON.parse(localStorage.getItem(legacyKey+':cleared')||'[]');
      if(!Array.isArray(cleared)||cleared.some(k=>typeof k!=='string'||!(k in byKey)))throw new Error('Invalid legacy cleared-label history');
      for(const key of cleared) {state.deleted[key]=store.clock(state);delete state.labels[key];}
      persist();
    }
    await checkLegacyHash(legacyRaw);
  } catch(error) {failClosed(error);}
  initialized=true;show();
});
