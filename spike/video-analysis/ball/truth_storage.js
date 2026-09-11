/* Atomic v2 storage envelope: validated labels plus timestamped clear records. */
(function(root) {
  function stable(value) {
    if (Array.isArray(value)) return '['+value.map(stable).join(',')+']';
    if (value && typeof value === 'object') return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')+'}';
    return JSON.stringify(value);
  }
  function empty() { return {labels:{}, deleted:{}}; }
  function fromRows(rows) { return {labels:Object.fromEntries(rows.map(r=>[BallTruth.key(r),r])),deleted:{}}; }
  function parse(text, frames) {
    if (!text?.trim()) throw new Error('v2 storage is empty or was removed');
    let value;
    try { value=JSON.parse(text); } catch (_) { return fromRows(BallTruth.parse(text,frames)); }
    if (value?.kind !== 'ball-truth-v2') return fromRows(BallTruth.parse(text,frames));
    if (Object.keys(value).some(k=>!['kind','labels','deleted'].includes(k)) || !Array.isArray(value.labels) || !value.deleted || Array.isArray(value.deleted) || typeof value.deleted !== 'object') throw new Error('Invalid v2 storage envelope');
    const state=fromRows(BallTruth.parse(value.labels.map(r=>JSON.stringify(r)).join('\n'),frames));
    const allowed=new Set(frames.map(BallTruth.key));
    for(const [key,time] of Object.entries(value.deleted)) {
      if (!allowed.has(key) || !Number.isSafeInteger(time) || time<0) throw new Error('Invalid cleared-label history');
      state.deleted[key]=time;
    }
    return merge(empty(),state);
  }
  // A bad envelope must not discard independent, readable decisions. Salvage
  // never writes storage; the page stays read-only until explicit recovery.
  function salvage(text,frames) {
    const state=empty(), unreadable=[];
    let value;
    try {value=JSON.parse(text);} catch (_) {
      return {state,unreadable:[{key:'storage',reason:'not parseable JSON'}],parseable:false};
    }
    if(!value || typeof value!=='object' || Array.isArray(value))return {state,unreadable:[{key:'storage',reason:'Invalid v2 envelope'}],parseable:true};
    if(value.kind!=='ball-truth-v2')unreadable.push({key:'storage',reason:'Invalid envelope kind'});
    for(const key of Object.keys(value))if(!['kind','labels','deleted'].includes(key))unreadable.push({key,reason:'Unknown envelope field'});
    const seen=new Set();
    if(Array.isArray(value.labels))value.labels.forEach((row,i)=> {
      let key='row '+(i+1);
      try {
        if(typeof row?.clip==='string' && Number.isFinite(row.t))key=BallTruth.key(row);
        const valid=BallTruth.validate(row,frames);
        key=BallTruth.key(valid);
        if(seen.has(key)) {delete state.labels[key];throw new Error('Duplicate label key');}
        seen.add(key);state.labels[key]=valid;
      } catch(error) {unreadable.push({key,reason:error.message});}
    });
    else unreadable.push({key:'labels',reason:'Expected a label array'});
    const allowed=new Set(frames.map(BallTruth.key));
    if(value.deleted && typeof value.deleted==='object' && !Array.isArray(value.deleted)) {
      for(const [key,time] of Object.entries(value.deleted)) {
        if(allowed.has(key) && Number.isSafeInteger(time) && time>=0)state.deleted[key]=time;
        else unreadable.push({key,reason:'Invalid clear key or timestamp'});
      }
    } else unreadable.push({key:'deleted',reason:'Expected clear history'});
    return {state:merge(empty(),state),unreadable,parseable:true};
  }
  // One ordering for clear versus edit in merges and imports. Equal-time rows
  // remain a policy choice: import may apply an equal row, merge keeps storage
  // (with confirmation priority) because it reconciles concurrent snapshots.
  function compareDecision(aTime,aClear,bTime,bClear) {
    return aTime-bTime || Number(aClear)-Number(bClear);
  }
  function readImport(text,frames,key) {
    let value;try {value=JSON.parse(text);} catch (_) {}
    if(value && (value.kind==='ball-truth-recovery' || Array.isArray(value.validated_labels))) {
      if(value.storage_key!==key)throw new Error('Recovery backup belongs to another kit');
      let deleted=value.validated_clears;
      if(deleted===undefined) {
        try {deleted=parse(value.v2,frames).deleted;} catch (_) {deleted={};}
      }
      return parse(stable({kind:'ball-truth-v2',labels:value.validated_labels,deleted}),frames);
    }
    return fromRows(BallTruth.parse(text,frames));
  }
  // The second argument is the value already in storage. Equal timestamps
  // rank explicit clear > any edit; remaining row ties keep
  // storage. Conflicting confirmed ties notify the UI without changing schema.
  function merge(local,stored,onConflict=()=>{}) {
    const result={labels:{...local.labels},deleted:{...local.deleted}};
    for(const [key,row] of Object.entries(stored.labels)) {
      const old=result.labels[key];
      if(!old || row.updated_at>old.updated_at) result.labels[key]=row;
      else if(row.updated_at===old.updated_at) {
        const a=BallTruth.confirmed(old), b=BallTruth.confirmed(row);
        if(a && b && values(old)!==values(row)) onConflict(key,old,row);
        if(b || !a) result.labels[key]=row;
      }
    }
    for(const [key,time] of Object.entries(stored.deleted)) result.deleted[key]=Math.max(time,result.deleted[key]??-1);
    for(const [key,time] of Object.entries(result.deleted)) {
      const row=result.labels[key];
      if(!row)continue;
      if(compareDecision(row.updated_at,false,time,true)<0) delete result.labels[key];
    }
    return result;
  }
  function serialize(state) {
    return stable({kind:'ball-truth-v2',labels:Object.keys(state.labels).sort().map(k=>state.labels[k]),deleted:state.deleted});
  }
  function clock(state) {
    return Math.max(Date.now(), ...Object.values(state.labels).map(r=>r.updated_at+1), ...Object.values(state.deleted).map(t=>t+1));
  }
  function values(row) {
    if (!row) return null;
    const {updated_at,...value}=row;
    return stable(value);
  }
  root.BallStorage={compareDecision,readImport,empty,fromRows,parse,salvage,merge,serialize,clock,values};
})(globalThis);
