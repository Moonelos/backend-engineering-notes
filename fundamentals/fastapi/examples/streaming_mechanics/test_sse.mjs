import assert from 'node:assert/strict';
import {events} from './sse.mjs';
const bytes = new TextEncoder().encode(': heartbeat\r\n\r\nid: 42\r\ndata: {"text":\r\ndata: "café"}\r\n\r\n');
for (let split = 0; split <= bytes.length; split++) {
  async function* chunks() { yield bytes.slice(0, split); yield bytes.slice(split); }
  const result = [];
  for await (const event of events(chunks())) result.push(event);
  assert.equal(result.length, 1);
  assert.equal(result[0].id, '42');
  assert.equal(JSON.parse(result[0].data).text, 'café');
}
async function* truncated() { yield new TextEncoder().encode('data: broken'); }
await assert.rejects(async () => { for await (const _ of events(truncated())) {} }, /truncated/);
async function* oversized() { yield new TextEncoder().encode('data: too long\n\n'); }
await assert.rejects(async () => { for await (const _ of events(oversized(), 5)) {} }, /too large/);
console.log('all byte split positions, multiline data, truncation and size bound passed');
