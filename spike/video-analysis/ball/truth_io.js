/* Shared browser/Node JSONL contract; no unchecked or default-negative labels. */
(function (root) {
  function key(row) { return `${row.clip}|${row.t.toFixed(6)}`; }
  function validate(row, frames) {
    if (!row || Object.keys(row).sort().join(',') !== 'clip,t,visible,x,y' ||
        typeof row.clip !== 'string' || !Number.isFinite(row.t) || typeof row.visible !== 'boolean')
      throw new Error('Expected {clip,t,x,y,visible}');
    const frame = frames.find(f => key(f) === key(row));
    if (!frame) throw new Error('Unknown clip/time');
    if (row.visible) {
      if (!Number.isFinite(row.x) || !Number.isFinite(row.y) || row.x < 0 || row.y < 0 ||
          row.x >= frame.source_size[0] || row.y >= frame.source_size[1])
        throw new Error('Coordinates must be within source frame');
    } else if (row.x !== null || row.y !== null) throw new Error('Invisible coordinates must be null');
    return {clip: row.clip, t: frame.t, x: row.x, y: row.y, visible: row.visible};
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
