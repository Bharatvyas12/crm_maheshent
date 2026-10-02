// Generates the PWA PNG icons so the repository does not depend on a binary asset pipeline.
// Run with: node scripts/generate-icons.mjs
import { deflateSync } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, '..', 'public', 'icons');
mkdirSync(outDir, { recursive: true });

const BG = [29, 78, 216];
const FG = [255, 255, 255];

const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i += 1) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, 'ascii');
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crc]);
}

function encodePng(size, pixels) {
  const raw = Buffer.alloc(size * (size * 4 + 1));
  for (let y = 0; y < size; y += 1) {
    raw[y * (size * 4 + 1)] = 0;
    pixels.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0))
  ]);
}

/** Clock glyph drawn analytically with 2x2 supersampling. `scale` shrinks it for the maskable safe zone. */
function insideGlyph(px, py, size, scale) {
  const cx = size / 2;
  const cy = size / 2;
  const unit = size * scale;
  const ringR = unit * 0.34;
  const ringT = unit * 0.062;
  const handW = unit * 0.05;
  const dist = Math.hypot(px - cx, py - cy);

  if (Math.abs(dist - ringR) <= ringT / 2) return true;

  // Minute hand pointing up.
  if (Math.abs(px - cx) <= handW / 2 && py <= cy && py >= cy - ringR + ringT * 0.6) return true;
  // Hour hand pointing right.
  if (Math.abs(py - cy) <= handW / 2 && px >= cx && px <= cx + ringR - ringT * 0.6) return true;

  return false;
}

function render(size, scale) {
  const px = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let hits = 0;
      for (let sy = 0; sy < 2; sy += 1) {
        for (let sx = 0; sx < 2; sx += 1) {
          if (insideGlyph(x + 0.25 + sx * 0.5, y + 0.25 + sy * 0.5, size, scale)) hits += 1;
        }
      }
      const alpha = hits / 4;
      const i = (y * size + x) * 4;
      px[i] = Math.round(BG[0] * (1 - alpha) + FG[0] * alpha);
      px[i + 1] = Math.round(BG[1] * (1 - alpha) + FG[1] * alpha);
      px[i + 2] = Math.round(BG[2] * (1 - alpha) + FG[2] * alpha);
      px[i + 3] = 255;
    }
  }
  return encodePng(size, px);
}

const targets = [
  ['icon-192.png', 192, 1.0],
  ['icon-512.png', 512, 1.0],
  ['icon-maskable-192.png', 192, 0.62],
  ['icon-maskable-512.png', 512, 0.62]
];

for (const [name, size, scale] of targets) {
  writeFileSync(resolve(outDir, name), render(size, scale));
  console.log('wrote', name);
}