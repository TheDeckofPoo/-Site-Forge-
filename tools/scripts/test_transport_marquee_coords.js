#!/usr/bin/env node
/**
 * Transport marquee screen↔world coordinate regression.
 *
 * Mirrors canvasPointFromEvent in dashboard/transport-build.js:
 *   client → canvas rect → +scroll → /zoom → world
 *
 * Marquee left/top are world coords on a layer that shares scale(z)
 * with #tb-nodes (see applyViewportZoom). Hit-testing uses the same world space.
 */
'use strict';

function canvasPointFromEvent(ev, canvas, zoom) {
  const rect = canvas.getBoundingClientRect();
  const z = Math.max(0.05, Number(zoom) || 1);
  return {
    x: (ev.clientX - rect.left + canvas.scrollLeft) / z,
    y: (ev.clientY - rect.top + canvas.scrollTop) / z,
  };
}

function worldToContentCss(pt, zoom) {
  const z = Math.max(0.05, Number(zoom) || 1);
  return { x: (Number(pt?.x) || 0) * z, y: (Number(pt?.y) || 0) * z };
}

/** Synthetic canvas stub — no DOM required. */
function makeCanvas({ left, top, scrollLeft, scrollTop }) {
  return {
    scrollLeft,
    scrollTop,
    getBoundingClientRect() {
      return { left, top, right: left + 800, bottom: top + 600, width: 800, height: 600 };
    },
  };
}

function approxEq(a, b, eps = 1e-9) {
  return Math.abs(a - b) <= eps;
}

const cases = [
  {
    name: '100% zoom / origin',
    canvas: { left: 100, top: 50, scrollLeft: 0, scrollTop: 0 },
    zoom: 1,
    client: { clientX: 250, clientY: 150 },
    expect: { x: 150, y: 100 },
  },
  {
    name: 'zoomed in (2x)',
    canvas: { left: 0, top: 0, scrollLeft: 0, scrollTop: 0 },
    zoom: 2,
    client: { clientX: 200, clientY: 100 },
    expect: { x: 100, y: 50 },
  },
  {
    name: 'zoomed out (0.5x)',
    canvas: { left: 0, top: 0, scrollLeft: 0, scrollTop: 0 },
    zoom: 0.5,
    client: { clientX: 100, clientY: 50 },
    expect: { x: 200, y: 100 },
  },
  {
    name: 'panned X (scrollLeft)',
    canvas: { left: 40, top: 20, scrollLeft: 300, scrollTop: 0 },
    zoom: 1,
    client: { clientX: 140, clientY: 120 },
    expect: { x: 400, y: 100 },
  },
  {
    name: 'panned Y (scrollTop)',
    canvas: { left: 0, top: 0, scrollLeft: 0, scrollTop: 250 },
    zoom: 1,
    client: { clientX: 80, clientY: 50 },
    expect: { x: 80, y: 300 },
  },
  {
    name: 'panned X+Y + zoom',
    canvas: { left: 10, top: 10, scrollLeft: 100, scrollTop: 200 },
    zoom: 2,
    client: { clientX: 210, clientY: 310 },
    expect: { x: 150, y: 250 },
  },
  {
    name: 'fit-view deep zoom-out',
    canvas: { left: 0, top: 0, scrollLeft: 500, scrollTop: 400 },
    zoom: 0.05,
    client: { clientX: 25, clientY: 20 },
    expect: { x: 10500, y: 8400 },
  },
];

let failed = 0;
for (const c of cases) {
  const canvas = makeCanvas(c.canvas);
  const got = canvasPointFromEvent(c.client, canvas, c.zoom);
  const ok = approxEq(got.x, c.expect.x) && approxEq(got.y, c.expect.y);
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${c.name}: got (${got.x}, ${got.y}) expect (${c.expect.x}, ${c.expect.y})`);
  if (!ok) failed += 1;

  // Round-trip: world → content CSS → must equal (client - rect + scroll)
  const css = worldToContentCss(got, c.zoom);
  const contentX = c.client.clientX - c.canvas.left + c.canvas.scrollLeft;
  const contentY = c.client.clientY - c.canvas.top + c.canvas.scrollTop;
  const rt = approxEq(css.x, contentX) && approxEq(css.y, contentY);
  console.log(`         round-trip content CSS [${rt ? 'PASS' : 'FAIL'}] (${css.x}, ${css.y})`);
  if (!rt) failed += 1;
}

// Marquee placement invariant: box.left/top are world coords; scaled layer
// places the visual edge under the cursor at any zoom.
function marqueeStartsUnderCursor(client, canvasSpec, zoom) {
  const canvas = makeCanvas(canvasSpec);
  const world = canvasPointFromEvent(client, canvas, zoom);
  // Visual position of marquee origin in viewport CSS px:
  // contentCss = world * zoom; viewport = contentCss - scroll + rect
  const content = worldToContentCss(world, zoom);
  const visualX = canvasSpec.left + (content.x - canvasSpec.scrollLeft);
  const visualY = canvasSpec.top + (content.y - canvasSpec.scrollTop);
  return approxEq(visualX, client.clientX) && approxEq(visualY, client.clientY);
}

for (const c of cases) {
  const ok = marqueeStartsUnderCursor(c.client, c.canvas, c.zoom);
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] marquee-under-cursor @ ${c.name}`);
  if (!ok) failed += 1;
}

if (typeof module !== 'undefined') {
  module.exports = { canvasPointFromEvent, worldToContentCss, marqueeStartsUnderCursor };
}

if (failed) {
  console.error(`FAIL — ${failed} marquee coordinate case(s)`);
  process.exit(1);
}
console.log(`PASS — ${cases.length} transform + ${cases.length} under-cursor checks`);
process.exit(0);
