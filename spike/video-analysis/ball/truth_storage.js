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
  // The second argument is the value already in storage. Equal timestamps
  // rank confirmed > explicit clear > unconfirmed; remaining row ties keep
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
      if(row.updated_at<time || (row.updated_at===time && !BallTruth.confirmed(row))) delete result.labels[key];
      else if(row.updated_at===time) delete result.deleted[key]; // Also safe for build-10 readers.
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
  root.BallStorage={empty,fromRows,parse,merge,serialize,clock,values};
})(globalThis);
