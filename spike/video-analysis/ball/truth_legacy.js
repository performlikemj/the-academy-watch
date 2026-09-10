/* Legacy reconciliation metadata is separate from the unchanged v2 label store. */
(function(root) {
  const fallbackMessage="The old click page changed after this page started, but this page can't tell which frames. Export from it, import here, check, then Dismiss.";
  function hash(raw) {
    let value=0xcbf29ce484222325n;
    for(const byte of new TextEncoder().encode(JSON.stringify(raw)))value=BigInt.asUintN(64,(value^BigInt(byte))*0x100000001b3n);
    return 'fnv1a64-v1:'+value.toString(16).padStart(16,'0');
  }
  // SHA-256 only upgrades build-11 hash baselines; works without WebCrypto.
  function sha256(text) {
    const primes=[];for(let n=2;primes.length<64;n++)if(primes.every(p=>n%p))primes.push(n);
    const frac=x=>Math.floor((x-Math.floor(x))*4294967296)|0;
    const constants=primes.map(p=>frac(Math.cbrt(p))), h=primes.slice(0,8).map(p=>frac(Math.sqrt(p)));
    const bytes=new TextEncoder().encode(text), size=Math.ceil((bytes.length+9)/64)*64;
    const padded=new Uint8Array(size);padded.set(bytes);padded[bytes.length]=128;
    const view=new DataView(padded.buffer), bits=bytes.length*8;
    view.setUint32(size-8,Math.floor(bits/4294967296));view.setUint32(size-4,bits>>>0);
    const rotate=(n,b)=>(n>>>b)|(n<<(32-b));
    for(let offset=0;offset<size;offset+=64) {
      const w=new Int32Array(64);
      for(let i=0;i<16;i++)w[i]=view.getInt32(offset+i*4);
      for(let i=16;i<64;i++) {
        const x=w[i-15],y=w[i-2];
        w[i]=(w[i-16]+(rotate(x,7)^rotate(x,18)^(x>>>3))+w[i-7]+(rotate(y,17)^rotate(y,19)^(y>>>10)))|0;
      }
      let [a,b,c,d,e,f,g,j]=h;
      for(let i=0;i<64;i++) {
        const t1=(j+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^(~e&g))+constants[i]+w[i])|0;
        const t2=((rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&b)^(a&c)^(b&c)))|0;
        j=g;g=f;f=e;e=(d+t1)|0;d=c;c=b;b=a;a=(t1+t2)|0;
      }
      [a,b,c,d,e,f,g,j].forEach((v,i)=>h[i]=(h[i]+v)|0);
    }
    return h.map(v=>(v>>>0).toString(16).padStart(8,'0')).join('');
  }
  function point(row) {return row?{visible:row.visible,x:row.x,y:row.y}:null;}
  function equal(a,b) {
    if(!a||!b)return !a&&!b;
    return a.visible===b.visible && (!a.visible || (Math.abs(a.x-b.x)<=1e-6 && Math.abs(a.y-b.y)<=1e-6));
  }
  function create(key,legacyKey,frames,oldHashKey) {
    let failed=false;
    const current=()=>localStorage.getItem(legacyKey);
    const rows=raw=>Object.fromEntries(BallTruth.parse(raw||'',frames).map(r=>[BallTruth.key(r),r]));
    function write(base) {
      try {localStorage.setItem(key,JSON.stringify(base));failed=false;}
      catch (_) {
        // Hash-only mode retains the OLD baseline on a failed per-key choice.
        try {localStorage.setItem(key,hash(base.raw));failed=false;} catch (_) {failed=true;}
      }
    }
    function rebase(raw=current()) {write({kind:'ball-legacy-raw-v1',raw,taken_at:Date.now(),kept:{}});}
    function baseline() {
      let value=localStorage.getItem(key);
      if(value===null && oldHashKey) {
        value=localStorage.getItem(oldHashKey);
        // Freeze the old hash once, without fighting build-12 metadata writers.
        if(value!==null)try {localStorage.setItem(key,value);} catch (_) {failed=true;}
      }
      let base;try {base=JSON.parse(value);} catch (_) {}
      if(base?.kind==='ball-legacy-raw-v1' && (base.raw===null||typeof base.raw==='string') && Number.isFinite(base.taken_at) && base.kept && typeof base.kept==='object')return base;
      return value;
    }
    function check(state) {
      const raw=current();let base=baseline();
      if(base===null) {rebase(raw);base=baseline();}
      if(typeof base==='string') {
        const matches=base===hash(raw) || (/^[a-f0-9]{64}$/.test(base) && base===sha256(JSON.stringify(raw)));
        if(!matches || failed) {
          // Once history is unknown, only explicit Dismiss may acknowledge it.
          if(!base.startsWith('unresolved-v1:'))try {localStorage.setItem(key,'unresolved-v1:'+base);} catch (_) {}
          return {fallback:true,keys:[],raw};
        }
        rebase(raw);base=baseline();
        if(typeof base==='string')return {fallback:failed,keys:[],raw};
      }
      if(!base || failed)return {fallback:true,keys:[],raw};
      if(base.raw===raw)return {fallback:false,keys:[],raw};
      try {
        const before=rows(base.raw), after=rows(raw), keys=[];
        for(const key of new Set([...Object.keys(before),...Object.keys(after)])) {
          const value=point(after[key]);
          if(equal(point(before[key]),value))continue;
          if(Object.hasOwn(base.kept,key) && equal(base.kept[key],value))continue;
          if(value?equal(point(state.labels[key]),value):!state.labels[key]&&Object.hasOwn(state.deleted,key))continue;
          keys.push({key,value,row:after[key]||null});
        }
        keys.sort((a,b)=>a.key.localeCompare(b.key));
        if(!keys.length)rebase(raw);
        return {fallback:false,keys,raw};
      } catch (_) {return {fallback:true,keys:[],raw};}
    }
    function keep(key,value) {
      const base=baseline();
      if(base && typeof base==='object') {base.kept[key]=value;write(base);}
    }
    return {check,rebase,keep,rows,current};
  }
  root.BallLegacy={create,point,equal,hash,sha256,fallbackMessage};
})(globalThis);
