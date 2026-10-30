// Bounded parser for this lesson's LF/CRLF UTF-8 SSE contract.
export async function* events(chunks, maxChars = 65536) {
  const decoder = new TextDecoder('utf-8', {fatal: true});
  let carry = '';
  function parse(record) {
    let type = 'message', id = null;
    const data = [];
    for (const line of record.split(/\r?\n/)) {
      if (!line || line.startsWith(':')) continue;
      const colon = line.indexOf(':');
      const field = colon < 0 ? line : line.slice(0, colon);
      let value = colon < 0 ? '' : line.slice(colon + 1);
      if (value.startsWith(' ')) value = value.slice(1);
      if (field === 'data') data.push(value);
      else if (field === 'event') type = value;
      else if (field === 'id' && !value.includes('\0')) id = value;
    }
    return data.length ? {type, id, data: data.join('\n')} : null;
  }
  for await (const bytes of chunks) {
    carry += decoder.decode(bytes, {stream: true});
    let match;
    while ((match = /\r?\n\r?\n/.exec(carry))) {
      if (match.index > maxChars) throw new Error('event too large');
      const event = parse(carry.slice(0, match.index));
      carry = carry.slice(match.index + match[0].length);
      if (event) yield event;
    }
    if (carry.length > maxChars) throw new Error('event too large');
  }
  carry += decoder.decode();
  if (carry.length) throw new Error('truncated event');
}
