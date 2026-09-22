#!/usr/bin/env node
/**
 * Transport area-assign batch contract — save/render once for N ids.
 *
 * Mirrors moveNodesToArea topology + persist coalescing without DOM.
 * Proves bulk assign does not call save/render per id.
 */
'use strict';

function inboundWires(area, toId) {
  return (area.wires || []).filter((w) => w.to === toId);
}

function syncDownstreamFromWires(area) {
  const byId = Object.fromEntries((area.nodes || []).map((n) => [n.id, n]));
  (area.nodes || []).forEach((n) => {
    const w = (area.wires || []).find((x) => x.from === n.id);
    if (!w) {
      if (!n.downstream) n.downstream = '';
      return;
    }
    const dst = byId[w.to];
    n.downstream = dst ? String(dst.conveyorTag || '').trim() : (n.downstream || '');
  });
}

function syncWiresFromDownstream(area) {
  (area.nodes || []).forEach((n) => {
    const ds = String(n.downstream || '').trim();
    if (!ds) return;
    const dst = (area.nodes || []).find(
      (x) => String(x.conveyorTag || '').trim().toUpperCase() === ds.toUpperCase()
    );
    if (!dst || dst.id === n.id) return;
    if ((area.wires || []).some((w) => w.from === n.id && w.to === dst.id)) return;
    area.wires = area.wires || [];
    area.wires.push({ id: `w_${n.id}_${dst.id}`, from: n.id, to: dst.id });
  });
}

/** Minimal batch kernel matching dashboard/transport-build.js moveNodesToArea. */
function moveNodesToArea(state, ids, destAreaId, opts, counters) {
  const o = opts || {};
  const dest = state.areas.find((a) => a.id === destAreaId);
  if (!dest) return { moved: 0 };
  const idList = [...new Set((ids || []).filter(Boolean).map(String))];
  const bySrc = new Map();
  for (const nodeId of idList) {
    let found = null;
    for (const a of state.areas) {
      const node = (a.nodes || []).find((n) => n.id === nodeId);
      if (node) {
        found = { node, srcArea: a, nodeId };
        break;
      }
    }
    if (!found || found.srcArea.id === destAreaId) continue;
    if (!bySrc.has(found.srcArea)) bySrc.set(found.srcArea, []);
    bySrc.get(found.srcArea).push(found);
  }
  if (!bySrc.size) return { moved: 0 };

  const movedNodes = [];
  const touched = new Set([dest]);
  bySrc.forEach((items, srcArea) => {
    touched.add(srcArea);
    syncDownstreamFromWires(srcArea);
    const removeIds = new Set(items.map((it) => it.nodeId));
    items.forEach(({ node, nodeId }) => {
      const keptDownstream = String(node.downstream || '').trim();
      const myTag = String(node.conveyorTag || '').trim();
      inboundWires(srcArea, nodeId).forEach((w) => {
        const src = (srcArea.nodes || []).find((n) => n.id === w.from);
        if (src && myTag) src.downstream = myTag;
      });
      node.downstream = keptDownstream;
      movedNodes.push(node);
    });
    srcArea.nodes = (srcArea.nodes || []).filter((n) => !removeIds.has(n.id));
    srcArea.wires = (srcArea.wires || []).filter(
      (w) => !removeIds.has(w.from) && !removeIds.has(w.to)
    );
  });
  dest.nodes = dest.nodes || [];
  movedNodes.forEach((n) => dest.nodes.push(n));
  touched.forEach((a) => {
    syncDownstreamFromWires(a);
    syncWiresFromDownstream(a);
    counters.invalidate += 1;
  });

  if (!o.skipSave) {
    counters.save += 1;
  }
  if (!o.skipRender) {
    counters.render += 1;
  }
  counters.n = movedNodes.length;
  return { moved: movedNodes.length, n: movedNodes.length };
}

function moveNodeToArea(state, nodeId, destAreaId, opts, counters) {
  return moveNodesToArea(state, [nodeId], destAreaId, opts, counters);
}

function fixture() {
  const nodes = [
    { id: 'n1', conveyorTag: 'P100', downstream: 'P102' },
    { id: 'n2', conveyorTag: 'P102', downstream: 'P104' },
    { id: 'n3', conveyorTag: 'P104', downstream: '' },
    { id: 'n4', conveyorTag: 'P200', downstream: '' },
    { id: 'n5', conveyorTag: 'P202', downstream: '' },
  ];
  return {
    areas: [
      {
        id: 'a',
        name: 'ModuleA',
        nodes: nodes.slice(0, 3),
        wires: [
          { id: 'w1', from: 'n1', to: 'n2' },
          { id: 'w2', from: 'n2', to: 'n3' },
        ],
      },
      {
        id: 'b',
        name: 'ModuleB',
        nodes: nodes.slice(3),
        wires: [],
      },
    ],
  };
}

let failed = 0;
function check(name, cond, detail) {
  const ok = !!cond;
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failed += 1;
}

console.log('=== transport area-assign batch ===');

{
  const state = fixture();
  const counters = { save: 0, render: 0, invalidate: 0, n: 0 };
  const ids = ['n1', 'n2', 'n3'];
  // Naive per-id path (what we must NOT do in production callers)
  ids.forEach((id) => moveNodeToArea(state, id, 'b', {}, counters));
  check('naive per-id save count equals N moved', counters.save === 3, `save=${counters.save}`);
  check('naive per-id render count equals N moved', counters.render === 3, `render=${counters.render}`);
}

{
  const state = fixture();
  const counters = { save: 0, render: 0, invalidate: 0, n: 0 };
  const ids = ['n1', 'n2', 'n3'];
  moveNodesToArea(state, ids, 'b', {}, counters);
  check('batch save once', counters.save === 1, `save=${counters.save}`);
  check('batch render once', counters.render === 1, `render=${counters.render}`);
  check('batch moved n=3', counters.n === 3, `n=${counters.n}`);
  const b = state.areas.find((a) => a.id === 'b');
  const a = state.areas.find((a) => a.id === 'a');
  check('three movers + two residents in ModuleB', (b.nodes || []).length === 5, `b=${(b.nodes || []).length}`);
  check('ModuleA empty', (a.nodes || []).length === 0, `a=${(a.nodes || []).length}`);
  const byTag = Object.fromEntries((b.nodes || []).map((n) => [n.conveyorTag, n]));
  check('P100.downstream preserved', byTag.P100.downstream === 'P102');
  check('P102.downstream preserved', byTag.P102.downstream === 'P104');
}

{
  const state = fixture();
  const counters = { save: 0, render: 0, invalidate: 0, n: 0 };
  moveNodesToArea(state, ['n2'], 'b', { skipSave: true, skipRender: true }, counters);
  check('skipSave/skipRender zero persist', counters.save === 0 && counters.render === 0,
    `save=${counters.save} render=${counters.render}`);
  const p100 = state.areas[0].nodes.find((n) => n.id === 'n1');
  const p102 = state.areas[1].nodes.find((n) => n.id === 'n2');
  check('cross-area upstream tag kept', p100 && p100.downstream === 'P102');
  check('moved node keeps downstream', p102 && p102.downstream === 'P104');
}

if (typeof module !== 'undefined') {
  module.exports = { moveNodesToArea, moveNodeToArea };
}

if (failed) {
  console.error(`FAIL — ${failed} area-assign batch check(s)`);
  process.exit(1);
}
console.log('PASS — area-assign batch checks');
process.exit(0);
