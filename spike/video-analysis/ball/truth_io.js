/* Shared browser/Node JSONL contract; no unchecked or default-negative labels. */
(function (root) {
  function key(row) { return `${row.clip}|${row.t.toFixed(6)}`; }
  function validate(row, frames) {
    if (!row || ['clip','t','visible','x','y'].some(k=>!(k in row)) || Object.keys(row).some(k=>!['clip','t','visible','x','y','source_accepted','accepted_source','accepted_score'].includes(k)) ||
        typeof row.clip !== 'string' || !Number.isFinite(row.t) || typeof row.visible !== 'boolean')
      throw new Error('Expected {clip,t,x,y,visible}');
    const frame = frames.find(f => key(f) === key(row));
    if (!frame) throw new Error('Unknown clip/time');
    if (row.visible) {
      if (!Number.isFinite(row.x) || !Number.isFinite(row.y) || row.x < 0 || row.y < 0 ||
          row.x >= frame.source_size[0] || row.y >= frame.source_size[1])
        throw new Error('Coordinates must be within source frame');
    } else if (row.x !== null || row.y !== null) throw new Error('Invisible coordinates must be null');
    if ('source_accepted' in row && typeof row.source_accepted !== 'boolean') throw new Error('source_accepted must be boolean');
    if(row.source_accepted) {
      if(!row.visible || typeof row.accepted_source !== 'string' || !row.accepted_source || !Number.isFinite(row.accepted_score) || row.accepted_score < 0 || row.accepted_score > 1) throw new Error('Accepted suggestion provenance required');
    } else if ('accepted_source' in row || 'accepted_score' in row) throw new Error('Provenance requires acceptance');
    return {...row, t: frame.t};
  }
  function parse(text, frames) {
    const seen = new Set();
    return text.split(/\r?\n/).filter(s => s.trim()).map(line => {
      const row = validate(JSON.parse(line), frames), id = key(row);
      if (seen.has(id)) throw new Error('Duplicate clip/time');
      seen.add(id); return row;
    });
  }
  function serialize(rows, frames) {
    const checked = parse(rows.map(r => JSON.stringify(r)).join('\n'), frames);
    checked.sort((a,b) => a.clip.localeCompare(b.clip) || a.t-b.t);
    return checked.map(r => JSON.stringify(r)).join('\n') + (checked.length ? '\n' : '');
  }
  const api = {key, validate, parse, serialize};
  if (typeof module !== 'undefined') module.exports = api;
  else root.BallTruth = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
