"""drive_organizer.viewer_propose — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import os
import re
import sqlite3
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    PARA_ROOTS,
    _atomic_write,
    _effective_viewer_page_size,
)


_VIEWER_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Drive Organiser — Proposals</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         font-size: 13px; background: #f4f5f7; color: #1a1a1a; }

  /* Header */
  #header { background: #1e2126; color: #e8e8e8; padding: 10px 20px;
            display: flex; align-items: center; gap: 16px; position: sticky;
            top: 0; z-index: 100; }
  #header h1 { font-size: 15px; font-weight: 600; flex: 1; }
  #progress-label { font-size: 13px; color: #aaa; white-space: nowrap; }
  #submit-btn { background: #2ea44f; color: #fff; border: none; border-radius: 5px;
                padding: 7px 18px; font-size: 13px; font-weight: 600; cursor: pointer; }
  #submit-btn:disabled { background: #444; color: #888; cursor: default; }
  #submit-btn:hover:not(:disabled) { background: #2c9b49; }

  /* Page tabs */
  #tabs { background: #2a2f38; padding: 6px 20px 0; display: flex; gap: 4px;
          overflow-x: auto; position: sticky; top: 44px; z-index: 99; }
  .tab { padding: 6px 14px; border-radius: 5px 5px 0 0; cursor: pointer;
         color: #aaa; background: #1e2126; font-size: 12px; white-space: nowrap;
         border: 1px solid #3a3f48; border-bottom: none; }
  .tab.active { background: #f4f5f7; color: #1a1a1a; font-weight: 600; }
  .tab:hover:not(.active) { background: #2e3440; }

  /* Page content */
  .page { display: none; padding: 16px 20px; }
  .page.active { display: block; }

  .page-actions { margin-bottom: 10px; }
  .approve-all-btn { background: #e6f4ea; border: 1px solid #34a853; color: #1a6b2e;
                     border-radius: 4px; padding: 5px 14px; cursor: pointer;
                     font-size: 12px; font-weight: 600; }
  .approve-all-btn:hover { background: #d0edda; }

  /* Table */
  table { width: 100%; border-collapse: collapse; background: #fff;
          border-radius: 7px; overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  thead th { background: #f0f2f5; font-weight: 600; padding: 8px 10px;
             text-align: left; font-size: 12px; color: #555;
             border-bottom: 1px solid #dde1e7; }
  tbody tr { border-bottom: 1px solid #eef0f3; }
  tbody tr:last-child { border-bottom: none; }
  tbody tr.approved  { background: #e8f5e9; }
  tbody tr.rejected  { background: #fce8e6; }
  tbody tr.flagged   { background: #fff8e1; }
  tbody tr.inbox     { background: #f3e5f5; }
  tbody tr.delete    { background: #ffebee; }
  td { padding: 7px 10px; vertical-align: middle; }
  td.num  { color: #888; width: 36px; text-align: right; }
  td.from { color: #777; font-size: 11px; max-width: 120px;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  td.orig { max-width: 180px; overflow: hidden; text-overflow: ellipsis;
            white-space: nowrap; font-family: monospace; font-size: 11px; }
  td.arrow { color: #bbb; width: 18px; text-align: center; }
  td.dest-cell { min-width: 270px; }
  td.newname { min-width: 180px; }
  td.actions { width: 115px; white-space: nowrap; }

  /* Path builder — 3 free-text segments with autocomplete */
  .path-builder { display: flex; align-items: center; gap: 2px; }
  .path-builder .seg { padding: 3px 5px; border: 1px solid #ccc; border-radius: 4px;
                        font-size: 12px; min-width: 0; background: #fff; }
  .path-builder .seg.seg1 { flex: 2.5; min-width: 90px; }
  .path-builder .seg.seg2 { flex: 1.8; min-width: 55px; }
  .path-builder .seg.seg3 { flex: 1.2; min-width: 40px; }
  .path-builder .sep { color: #bbb; font-size: 13px; flex-shrink: 0; padding: 0 1px; }

  /* New filename input */
  input.name-input { padding: 3px 6px; border: 1px solid #ccc; border-radius: 4px;
                     font-size: 12px; width: 100%; }

  /* Status buttons */
  .status-btn { border: 1px solid transparent; border-radius: 4px; padding: 3px 9px;
                cursor: pointer; font-size: 13px; background: #f0f0f0;
                color: #888; transition: background .1s; }
  .status-btn.approve { border-color: #34a853; }
  .status-btn.approve.active { background: #34a853; color: #fff; }
  .status-btn.reject  { border-color: #ea4335; }
  .status-btn.reject.active  { background: #ea4335; color: #fff; }
  .status-btn.flag    { border-color: #f9ab00; }
  .status-btn.flag.active    { background: #f9ab00; color: #fff; }
  .status-btn.inbox   { border-color: #9c27b0; }
  .status-btn.inbox.active   { background: #9c27b0; color: #fff; }
  .status-btn.delete  { border-color: #c62828; }
  .status-btn.delete.active  { background: #c62828; color: #fff; }
  .status-btn:hover { filter: brightness(0.95); }

  /* Post-submit banner */
  #submitted-banner { display: none; background: #e8f5e9; border: 1px solid #34a853;
                      border-radius: 7px; padding: 20px 24px; margin: 30px auto;
                      max-width: 500px; text-align: center; font-size: 15px;
                      color: #1a6b2e; font-weight: 600; }

  /* Group header rows — show destination grouping in the table */
  tr.group-header td { background: #eef3f8; color: #2c3e50; font-weight: 600;
                       padding: 8px 12px; font-size: 12px; border-top: 2px solid #c3d4e2;
                       border-bottom: 1px solid #c3d4e2; }
  tr.group-header .group-path { font-family: monospace; }
  tr.group-header .group-count { color: #6a7c91; margin-left: 8px; font-weight: 400; }
  tr.group-header.inbox td { background: #f3e5f5; color: #6a1b7a; border-top-color: #ce93d8; border-bottom-color: #ce93d8; }
  .approve-group-btn { background: #e6f4ea; border: 1px solid #34a853; color: #1a6b2e;
                       border-radius: 4px; padding: 2px 10px; cursor: pointer; font-size: 11px;
                       font-weight: 600; margin-left: 12px; }
  .approve-group-btn:hover { background: #d0edda; }
</style>
</head>
<body>

<div id="header">
  <h1 id="header-title">Drive Organiser — Proposals</h1>
  <span id="progress-label">0 / 0 approved</span>
  <button id="submit-btn" disabled onclick="submitAll()">Submit 0</button>
</div>

<datalist id="voc-1"></datalist>
<datalist id="voc-2"></datalist>
<datalist id="voc-3"></datalist>
<div id="tabs"></div>
<div id="pages"></div>
<div id="submitted-banner"></div>

<script>
// ---------- Data ----------
const VOCAB = __VOCAB_JSON__;
const PROPOSALS = __PROPOSALS_JSON__;
const PAGE_SIZE = __PAGE_SIZE__;

// per-row state: { status, seg1, seg2, seg3, newName }
// status values: 'unset' | 'approved' | 'rejected' | 'inbox' | 'delete' | 'flagged'
// rejected = I got it wrong, reclassify using context
// inbox    = user needs to open it manually (EPS etc), confirmed _Inbox
const rowState = {};
const PROPOSAL_BY_ID = {};

PROPOSALS.forEach(p => {
  PROPOSAL_BY_ID[p.id] = p;
  rowState[p.id] = {
    status:  'unset',
    seg1:    p.seg1 || '_Inbox',
    seg2:    p.seg2 || '',
    seg3:    p.seg3 || '',
    newName: p.new_filename || p.filename,
  };
});

// ---------- Path helpers ----------
function destPath(id) {
  const st = rowState[id];
  return [slugify(st.seg1), slugify(st.seg2), slugifyPath(st.seg3)].filter(Boolean).join('/');
}

function isStagingPath(path) {
  // Single shared predicate for "this destination is a staging root, not a real
  // routed folder" — empty or any underscore-prefixed root (_Inbox, _To Delete,
  // _Duplicates, ...). Used by inferCategory AND the inbox row-styling so they
  // can never disagree.
  return !path || path.startsWith('_');
}

function inferCategory(path) {
  // para_category is the file's TOP-LEVEL GROUPING — the first segment of the
  // destination path (e.g. WORK/Acme/finance -> WORK). Staging roots (_Inbox,
  // Archive) return themselves. (This is a registry column only; routing is by
  // para_subfolder. The old fixed Areas/Resources/Projects vocab was wrong.)
  if (isStagingPath(path)) return path || '_Inbox';
  return path.split('/')[0];
}

// ---------- Rendering ----------

function buildRow(p, globalIdx) {
  const st = rowState[p.id];
  const trClass = st.status === 'unset' ? '' : st.status;
  return `
<tr id="row-${p.id}" class="${trClass}">
  <td class="num">${globalIdx + 1}</td>
  <td class="from" title="${escHtml(p.current_path || '')}">${escHtml((p.current_path || '').split('/').slice(-2,-1)[0] || '')}</td>
  <td class="orig" title="${escHtml(p.filename)}">${escHtml(p.filename)}</td>
  <td class="arrow">→</td>
  <td class="dest-cell">
    <div class="path-builder">
      <input class="seg seg1" id="s1-${p.id}" type="text" list="voc-1"
             value="${escHtml(st.seg1)}" placeholder="folder"
             oninput="onSeg(${p.id})">
      <span class="sep">/</span>
      <input class="seg seg2" id="s2-${p.id}" type="text" list="voc-2"
             value="${escHtml(st.seg2)}" placeholder="sub"
             oninput="onSeg(${p.id})">
      <span class="sep">/</span>
      <input class="seg seg3" id="s3-${p.id}" type="text" list="voc-3"
             value="${escHtml(st.seg3)}" placeholder=""
             oninput="onSeg(${p.id})">
    </div>
  </td>
  <td class="newname">
    <input class="name-input" id="name-${p.id}" type="text"
           value="${escHtml(st.newName)}"
           oninput="onNameChange(${p.id}, this.value)">
  </td>
  <td class="actions">
    <button class="status-btn approve${st.status==='approved'?' active':''}"
            onclick="setStatus(${p.id},'approved')" title="Approve — move to proposed destination">✓</button>
    <button class="status-btn reject${st.status==='rejected'?' active':''}"
            onclick="setStatus(${p.id},'rejected')" title="Wrong — Claude will reclassify">✗</button>
    <button class="status-btn flag${st.status==='flagged'?' active':''}"
            onclick="setStatus(${p.id},'flagged')" title="No idea — Claude will peek and repropose">?</button>
    <button class="status-btn inbox${st.status==='inbox'?' active':''}"
            onclick="setStatus(${p.id},'inbox')" title="Inbox — I need to open this myself">📥</button>
    <button class="status-btn delete${st.status==='delete'?' active':''}"
            onclick="setStatus(${p.id},'delete')" title="Move to Archive/_To Delete (not permanently deleted)">🗑</button>
  </td>
</tr>`;
}

function buildGroupHeader(path, ids, isInbox) {
  const cls = 'group-header' + (isInbox ? ' inbox' : '');
  const safePath = escHtml(path || '(no destination)');
  const count = ids.length;
  const idsAttr = escHtml(JSON.stringify(ids));
  return `
<tr class="${cls}">
  <td colspan="7">
    → <span class="group-path">${safePath}</span>
    <span class="group-count">(${count} file${count === 1 ? '' : 's'})</span>
    <button class="approve-group-btn" onclick='approveGroup(${idsAttr})'>Approve group</button>
  </td>
</tr>`;
}

function buildPage(pageIdx) {
  const start = pageIdx * PAGE_SIZE;
  const slice = PROPOSALS.slice(start, start + PAGE_SIZE);

  // Walk the slice and emit group headers when para_subfolder changes
  let body = '';
  let i = 0;
  while (i < slice.length) {
    const groupPath = slice[i].para_subfolder || '';
    let j = i;
    while (j < slice.length && (slice[j].para_subfolder || '') === groupPath) j++;
    const isInbox = isStagingPath(groupPath);
    const groupIds = [];
    for (let k = i; k < j; k++) groupIds.push(slice[k].id);
    body += buildGroupHeader(groupPath, groupIds, isInbox);
    for (let k = i; k < j; k++) {
      body += buildRow(slice[k], start + k);
    }
    i = j;
  }

  return `
<div class="page" id="page-${pageIdx}">
  <div class="page-actions">
    <button class="approve-all-btn" onclick="approveAll(${pageIdx})">Approve all on this page</button>
  </div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>From</th><th>Original filename</th><th></th>
        <th>Destination</th><th>New filename</th>
        <th title="✓ approve  ✗ reclassify  ? peek+repropose  📥 manual inbox">Action</th>
      </tr>
    </thead>
    <tbody id="tbody-${pageIdx}">${body}</tbody>
  </table>
</div>`;
}

function approveGroup(ids) {
  (ids || []).forEach(id => {
    if (rowState[id]) {
      rowState[id].status = 'approved';
      refreshRow(id);
    }
  });
  updateAll();
}

function init() {
  // Populate autocomplete datalists from vocab
  [1, 2, 3].forEach(pos => {
    const dl = document.getElementById(`voc-${pos}`);
    if (!dl) return;
    (VOCAB[String(pos)] || []).forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      dl.appendChild(opt);
    });
  });

  const numPages = Math.ceil(PROPOSALS.length / PAGE_SIZE);
  const tabsEl   = document.getElementById('tabs');
  const pagesEl  = document.getElementById('pages');
  document.getElementById('header-title').textContent =
    `Drive Organiser — Proposals (${PROPOSALS.length} files)`;

  for (let i = 0; i < numPages; i++) {
    const tab = document.createElement('div');
    tab.className = 'tab' + (i === 0 ? ' active' : '');
    tab.id = `tab-${i}`;
    tab.onclick = () => switchPage(i);
    tabsEl.appendChild(tab);
    pagesEl.innerHTML += buildPage(i);
  }
  updateAll();
  switchPage(0);
}

let currentPage = 0;
function switchPage(idx) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`page-${idx}`).classList.add('active');
  document.getElementById(`tab-${idx}`).classList.add('active');
  currentPage = idx;
}

function updateAll() {
  const numPages = Math.ceil(PROPOSALS.length / PAGE_SIZE);
  let totalApproved = 0;
  for (let i = 0; i < numPages; i++) {
    const start = i * PAGE_SIZE;
    const slice = PROPOSALS.slice(start, start + PAGE_SIZE);
    const pageReviewed = slice.filter(p => ['approved','rejected','inbox','delete','flagged'].includes(rowState[p.id].status)).length;
    totalApproved += pageReviewed;
    const tab = document.getElementById(`tab-${i}`);
    if (tab) tab.textContent = `${i+1}  ${pageReviewed}/${slice.length}`;
  }
  document.getElementById('progress-label').textContent =
    `${totalApproved} / ${PROPOSALS.length} reviewed`;
  const btn = document.getElementById('submit-btn');
  btn.disabled = totalApproved === 0;
  btn.textContent = `Submit ${totalApproved}`;
}

// ---------- State mutations ----------
function setStatus(id, newStatus) {
  const st = rowState[id];
  // Toggle off if already that status
  st.status = (st.status === newStatus) ? 'unset' : newStatus;
  refreshRow(id);
  updateAll();
}

function addToDatalist(pos, val) {
  if (!val) return;
  const dl = document.getElementById(`voc-${pos}`);
  if (!dl) return;
  if (!Array.from(dl.options).some(o => o.value === val)) {
    const opt = document.createElement('option');
    opt.value = val;
    dl.appendChild(opt);
  }
}

function slugify(s) {
  // Normalise a single path segment (seg1/seg2): trim, collapse internal whitespace, and
  // strip any embedded '/' so a single segment can never change the destination depth.
  return String(s == null ? '' : s)
    .replace(/\//g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

function slugifyPath(s) {
  // Normalise the seg3 TAIL, which legitimately holds a multi-segment path (Q3/Q4, e.g.
  // "Financials/Bills" or "PROJECT/Scripts" when the classifier returned a 4+-segment
  // para_subfolder). Sanitise each component but PRESERVE the '/' separators — slugify()
  // would fold them to spaces and collapse the depth, corrupting the destination.
  return String(s == null ? '' : s)
    .split('/').map(slugify).filter(Boolean).join('/');
}

function onSeg(id) {
  const st = rowState[id];
  st.seg1 = slugify((document.getElementById(`s1-${id}`) || {value: ''}).value);
  st.seg2 = slugify((document.getElementById(`s2-${id}`) || {value: ''}).value);
  st.seg3 = slugifyPath((document.getElementById(`s3-${id}`) || {value: ''}).value);
  addToDatalist(1, st.seg1);
  addToDatalist(2, st.seg2);
  addToDatalist(3, st.seg3);
}
function onNameChange(id, val) {
  const trimmed = String(val == null ? '' : val).trim();
  const orig = (PROPOSAL_BY_ID[id] || {}).filename || '';
  rowState[id].newName = trimmed || orig;
}

function approveAll(pageIdx) {
  const start = pageIdx * PAGE_SIZE;
  const slice = PROPOSALS.slice(start, start + PAGE_SIZE);
  slice.forEach(p => { rowState[p.id].status = 'approved'; refreshRow(p.id); });
  updateAll();
}

function refreshRow(id) {
  const tr = document.getElementById(`row-${id}`);
  if (!tr) return;
  const st = rowState[id];
  tr.className = st.status === 'unset' ? '' : st.status;
  const approveBtn = tr.querySelector('.status-btn.approve');
  const rejectBtn  = tr.querySelector('.status-btn.reject');
  const flagBtn    = tr.querySelector('.status-btn.flag');
  if (approveBtn) approveBtn.className = 'status-btn approve' + (st.status==='approved'?' active':'');
  if (rejectBtn)  rejectBtn.className  = 'status-btn reject'  + (st.status==='rejected'?' active':'');
  if (flagBtn)    flagBtn.className    = 'status-btn flag'     + (st.status==='flagged'?' active':'');
  const inboxBtn  = tr.querySelector('.status-btn.inbox');
  if (inboxBtn)   inboxBtn.className   = 'status-btn inbox'    + (st.status==='inbox'?' active':'');
  const deleteBtn = tr.querySelector('.status-btn.delete');
  if (deleteBtn)  deleteBtn.className  = 'status-btn delete'   + (st.status==='delete'?' active':'');
}

// ---------- Submit ----------
function submitAll() {
  const output = [];
  const flaggedIds = [];
  const skippedIds = [];
  let unset = 0;
  PROPOSALS.forEach(p => {
    const st = rowState[p.id];
    if (st.status === 'approved') {
      const path = destPath(p.id);
      output.push({
        id:             p.id,
        current_path:   p.current_path,
        filename:       p.filename,
        is_image:       p.is_image,
        para_subfolder: path,
        new_filename:   st.newName || p.filename,
        vision_desc:    p.vision_desc || null,
        file_date:      p.file_date || null,
        reason:         p.reason || null,
        action:         'approved',
      });
    } else if (st.status === 'rejected') {
      // Keep original proposal — Claude will reclassify before executing
      output.push({
        id:             p.id,
        current_path:   p.current_path,
        filename:       p.filename,
        is_image:       p.is_image,
        para_subfolder: p.para_subfolder || null,
        new_filename:   p.new_filename || p.filename,
        vision_desc:    p.vision_desc || null,
        file_date:      p.file_date || null,
        reason:         p.reason || null,
        action:         'rejected',
      });
    } else if (st.status === 'inbox') {
      // User explicitly confirmed: needs manual review, send to _Inbox
      output.push({
        id:             p.id,
        current_path:   p.current_path,
        filename:       p.filename,
        is_image:       p.is_image,
        para_subfolder: '_Inbox',
        new_filename:   p.filename,
        vision_desc:    p.vision_desc || null,
        file_date:      p.file_date || null,
        reason:         'manual review',
        action:         'inbox',
      });
    } else if (st.status === 'delete') {
      output.push({
        id:             p.id,
        current_path:   p.current_path,
        filename:       p.filename,
        is_image:       p.is_image,
        para_subfolder: 'Archive/_To Delete',
        new_filename:   p.filename,
        vision_desc:    p.vision_desc || null,
        file_date:      p.file_date || null,
        reason:         'marked for deletion',
        action:         'delete',
      });
    } else if (st.status === 'flagged') {
      flaggedIds.push(p.id);
    } else {
      unset++;
      skippedIds.push(p.id);
    }
  });

  fetch('/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved: output, flagged: flaggedIds, skipped: skippedIds }),
  })
  .then(r => r.json())
  .then(resp => {
    document.getElementById('tabs').style.display = 'none';
    document.getElementById('pages').style.display = 'none';
    const banner = document.getElementById('submitted-banner');
    banner.style.display = 'block';
    const deleteCount = output.filter(r => r.action === 'delete').length;
    let msg = `✓ Submitted ${output.length} proposals.`;
    if (deleteCount > 0) msg += ` ${deleteCount} marked for deletion (moved to Archive/_To Delete).`;
    if (flaggedIds.length > 0) msg += ` ${flaggedIds.length} flagged for later review.`;
    if (unset > 0) msg += ` ${unset} unset rows skipped.`;
    msg += ` You can close this window and return to Claude.`;
    banner.textContent = msg;
  })
  .catch(err => alert('Submit failed: ' + err));
}

function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

window.onload = init;
</script>
</body>
</html>"""

APPROVED_JSON_PATH = Path.home() / ".claude" / "drive-organizer" / "proposals_approved.json"


def _para_path_segments(para_subfolder: str) -> tuple[str, str, str]:
    """Split a stored subfolder path into up to 3 segments for the path-builder viewer."""
    parts = (para_subfolder or "").split("/", 2)
    return (
        parts[0] if len(parts) > 0 else "_Inbox",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
    )


def _persist_vocab_from_approvals(db_path: str, approved: list) -> None:
    """Learn new path-vocab segments from approved proposal destinations.

    Inserts or increments `path_vocab` rows for each non-staging destination
    segment so the viewer's autocomplete reflects newly-seen paths.  Extracted
    from the HTTP handler so it can be called from process-return's learning
    loop or any future code path without going through the browser viewer.
    """
    if not approved or not db_path:
        return
    try:
        with sqlite3.connect(db_path) as _db:
            for entry in approved:
                subfolder = entry.get("para_subfolder", "")
                parts = subfolder.split("/", 2) if subfolder else []
                # Skip staging destinations entirely — they are not routing
                # vocab. That means a leading '_' (e.g. '_Inbox') AND any path
                # whose first segment is a PARA_ROOT (e.g. 'Archive/_To Delete',
                # the delete destination, which does NOT start with '_'); without
                # the latter check 'Archive' / '_To Delete' would be learned as
                # autocomplete destinations the next viewer round offers.
                if not subfolder or subfolder.startswith("_") or (parts and parts[0] in PARA_ROOTS):
                    continue
                for pos, seg in enumerate(parts, 1):
                    if seg:
                        _db.execute(
                            """INSERT INTO path_vocab (segment, position, use_count) VALUES (?,?,1)
                               ON CONFLICT(segment, position) DO UPDATE SET use_count = use_count + 1""",
                            (seg, pos),
                        )
    except Exception as e:
        print(f"Warning: could not save vocab: {e}", flush=True)


def _persist_flagged_status(db_path: str, flagged_ids: list) -> bool:
    """Write status='flagged' for the given file IDs in the SQLite registry.

    Extracted from the HTTP handler so the same update can be driven from
    process-return or any future non-HTTP code path.  Prints a success line
    on write (mutually exclusive with the warning line) so callers can branch
    on exactly one outcome.

    Returns True if the write succeeded (or there was nothing to write),
    False if the DB update failed — so callers can detect an un-persisted flag
    and react (e.g. warn the user to patch manually from proposals_flagged.json).
    """
    if not flagged_ids or not db_path:
        if flagged_ids and not db_path:
            # Files WERE flagged but the registry path was unavailable at viewer
            # launch (db absent). Emit the same warning shape so the executor reads
            # this as the flag-write-failed case (and applies the manual patch from
            # proposals_flagged.json) rather than the no-files-flagged case — those
            # flagged files would otherwise reappear as pending next round.
            print("Warning: could not mark flagged in DB: registry not found at viewer launch "
                  "(patch status='flagged' manually from proposals_flagged.json).", flush=True)
            return False
        return True
    try:
        placeholders = ",".join("?" * len(flagged_ids))
        with sqlite3.connect(db_path) as db:
            db.execute(
                f"UPDATE files SET status='flagged' WHERE id IN ({placeholders})",
                flagged_ids,
            )
        # Success line printed ONLY on a successful write — so the
        # success and warning lines are mutually exclusive (the executor
        # can branch on exactly one).
        print(f"{len(flagged_ids)} files marked flagged in registry.", flush=True)
        return True
    except Exception as e:
        print(f"Warning: could not mark flagged in DB: {e}", flush=True)
        return False


class _SilentHandler(BaseHTTPRequestHandler):
    """HTTP handler for the viewer; suppresses access logs."""

    _proposals: list = []
    _shutdown_event: threading.Event = None
    _db_path: str = None
    _vocab: dict = {}

    def log_message(self, format, *args):
        pass  # suppress access logs

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            proposals = self.__class__._proposals

            # Enrich proposals with derived keys for the viewer
            viewer_proposals = []
            for p in proposals:
                seg1, seg2, seg3 = _para_path_segments(p.get("para_subfolder", ""))
                vp = dict(p)
                vp["seg1"] = seg1
                vp["seg2"] = seg2
                vp["seg3"] = seg3
                viewer_proposals.append(vp)

            html = _VIEWER_HTML_TEMPLATE
            # Substitute the non-data placeholder first; do the proposal-data
            # replacement LAST so proposal text containing a literal placeholder
            # token can't be clobbered by a later replace().
            html = html.replace("__VOCAB_JSON__", json.dumps(self.__class__._vocab))
            html = html.replace("__PROPOSALS_JSON__", json.dumps(viewer_proposals))
            html = html.replace("__PAGE_SIZE__", str(_effective_viewer_page_size(paths_config._EFFECTIVE_ROOT)))
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/submit":
            self.send_response(404)
            self.end_headers()
            return

        # Parse Content-Length defensively: a malformed header must not crash
        # the handler, and an oversized body must not be read unbounded.
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_response(400)
            self.end_headers()
            return
        if length < 0:
            self.send_response(400)
            self.end_headers()
            return
        MAX_BODY = 64 * 1024 * 1024  # 64 MB cap
        if length > MAX_BODY:
            self.send_response(413)
            self.end_headers()
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        # Support both old flat-array format and new {approved, flagged} format
        if isinstance(payload, list):
            approved = payload
            flagged_ids = []
            skipped_ids = []
        else:
            approved = payload.get("approved", [])
            flagged_ids = payload.get("flagged", [])
            skipped_ids = payload.get("skipped", [])

        # Reject an empty submission rather than overwriting prior approvals
        # with nothing — an accidental/duplicate POST must not truncate output.
        if not approved and not flagged_ids:
            resp = json.dumps({"ok": False, "error": "empty submission"}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        # Persist both output files. A failure here (disk full, permissions, read-only
        # mount) must NOT crash the handler with a bare traceback and then fall through
        # to the success response + shutdown — that would tell the user their review was
        # saved when it was lost. Catch it, report it in the browser response AND on
        # stderr, and DON'T shut the server down so they can retry the submit.
        try:
            APPROVED_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
            # Write proposals_approved.json UNCONDITIONALLY (even an empty list):
            # process-return reads it every round, and a guarded skip on an
            # empty-approved-but-flagged submit would leave a STALE prior-round file the
            # consumer mistakes for this round's. An empty list is the correct signal —
            # execute then prints "Approved list is empty."
            _atomic_write(APPROVED_JSON_PATH, json.dumps(approved, indent=2))
            # Persist the EXACT flagged-ID set to a sidecar (the precise list
            # process-return's warning-branch fallback reads — never inferred by
            # set-difference, which catches unreviewed 'unset' rows too). Written
            # UNCONDITIONALLY (including []) so a flag-less submit CLEARS any prior-round
            # file instead of leaving stale IDs for the next round.
            _atomic_write(
                APPROVED_JSON_PATH.parent / "proposals_flagged.json",
                json.dumps(flagged_ids, indent=2),
            )
        except OSError as e:
            print(f"ERROR: could not write review output ({e}); submit NOT saved — "
                  f"resolve the disk/permission problem and re-submit.", file=sys.stderr, flush=True)
            err = json.dumps({"ok": False, "error": f"could not write output: {e}"}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
            return  # leave the server running so the user can retry

        # Surface deliberately-unreviewed ('unset') rows explicitly so downstream
        # knows which files were skipped rather than silently dropping them.
        if skipped_ids:
            print(
                f"{len(skipped_ids)} unreviewed files skipped (not written to "
                f"proposals_approved.json): ids {skipped_ids}",
                flush=True,
            )

        # Vocab-save and flag-write are data-layer operations; delegate to
        # module-level functions so the same logic is reachable from process-return
        # or any future non-HTTP path without coupling it to this transport layer.
        db_path = self.__class__._db_path
        _persist_vocab_from_approvals(db_path, approved)
        if not _persist_flagged_status(db_path, flagged_ids):
            print("Warning: flagged-status write failed in HTTP handler — "
                  "patch status='flagged' manually from proposals_flagged.json.", flush=True)

        try:
            resp = json.dumps({"ok": True, "path": str(APPROVED_JSON_PATH)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

            print(f"\nApproved proposals written to: {APPROVED_JSON_PATH}", flush=True)
            print("Server shutting down.", flush=True)
        finally:
            # Signal shutdown in a separate thread so response can be sent first.
            # In a finally so an unhandled exception in the response-send path
            # doesn't leave the server running indefinitely.
            if self.__class__._shutdown_event:
                threading.Timer(0.5, self.__class__._shutdown_event.set).start()


def _cowork_or_headless() -> bool:
    """True when the localhost browser viewer cannot be reached — a Cowork/remote
    session or an explicitly-headless run. The localhost HTTP viewer (port 5002/5003)
    is unreachable from Cowork (the user's browser is not on this host), so scan should
    fall back to the static review file instead of starting a server nobody can open.
    Signalled by DRIVE_ORG_HEADLESS=1, or any Cowork environment marker."""
    if os.environ.get("DRIVE_ORG_HEADLESS", "").strip().lower() in ("1", "true", "yes"):
        return True
    return any(os.environ.get(v) for v in ("CLAUDE_COWORK", "COWORK", "CLAUDE_CODE_COWORK"))


def _emit_static_review(proposals: list) -> Path:
    """Cowork-reachable fallback for the localhost viewer: write a self-contained,
    editable HTML review file (no server, no localhost POST) PLUS a pre-filled
    proposals_approved.json (every file defaulted to 'approved' at its proposed
    destination). The user reviews/edits in the HTML and clicks Download to produce an
    updated approved.json, OR edits the pre-filled JSON directly, then runs
    process-return. Returns the HTML path. The approved entry schema matches what the
    browser viewer POSTs (id / current_path / para_subfolder / new_filename / action),
    so the downstream consumer is identical — only the transport differs."""
    out_dir = APPROVED_JSON_PATH.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pre-fill proposals_approved.json (all approved) so "accept everything" needs no
    # browser at all — the user can run process-return immediately, or edit first.
    prefilled = []
    for p in proposals:
        prefilled.append({
            "id": p.get("id"),
            "current_path": p.get("current_path") or p.get("original_path"),
            "para_subfolder": p.get("para_subfolder", ""),
            "new_filename": p.get("new_filename") or p.get("filename"),
            "action": "approved",
            "file_date": p.get("file_date"),
            "vision_desc": p.get("vision_desc"),
        })
    _atomic_write(APPROVED_JSON_PATH, json.dumps(prefilled, indent=2))

    # Self-contained editable HTML — the Download button builds the same
    # {approved, flagged, skipped} payload the localhost viewer POSTs, as a client-side
    # Blob the user saves over proposals_approved.json. No network, so it works wherever
    # the file can be opened (Cowork file preview, a copied-out browser, etc.).
    review_html = out_dir / "proposals_review.html"
    rows = json.dumps(proposals)
    appr_path_js = json.dumps(str(APPROVED_JSON_PATH))
    html = """<!doctype html><meta charset="utf-8"><title>Drive Organizer — static review</title>
<style>body{font:14px system-ui,sans-serif;margin:1.5rem;max-width:1100px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 6px;vertical-align:top}
th{background:#f3f3f3;text-align:left}select,input{font:inherit;width:100%;box-sizing:border-box}
.path{color:#555;font-size:12px;word-break:break-all}button{font:inherit;padding:.5rem 1rem;margin:.5rem 0}
.hint{background:#fffbe6;border:1px solid #e6d27a;padding:.6rem .8rem;border-radius:4px}</style>
<h2>Drive Organizer — static review (Cowork / headless)</h2>
<div class="hint">The localhost viewer is unreachable here. Review below, then <b>Download approved.json</b>
and save it over:<br><code id="ap"></code><br>then run <code>process-return</code>.
A pre-filled <code>proposals_approved.json</code> (everything approved) was already written there —
if you just want to accept all, skip this file and run <code>process-return</code> now.</div>
<button onclick="dl()">⬇ Download approved.json</button>
<table id="t"><thead><tr><th>#</th><th>File</th><th>Action</th><th>Destination</th><th>New filename</th><th>Why</th></tr></thead><tbody></tbody></table>
<script>
const P=__ROWS__, AP=__AP__;document.getElementById('ap').textContent=AP;
const tb=document.querySelector('#t tbody');
P.forEach((p,i)=>{const tr=document.createElement('tr');
const cp=p.current_path||p.original_path||'';
tr.innerHTML=`<td>${i+1}</td><td class=path>${cp.replace(/</g,'&lt;')}</td>
<td><select data-i=${i} class=act><option value=approved selected>approve</option>
<option value=rejected>reject</option><option value=inbox>inbox</option>
<option value=flagged>flag</option><option value=skip>skip (leave unreviewed — not moved)</option></select></td>
<td><input data-i=${i} class=dest value="${(p.para_subfolder||'').replace(/"/g,'&quot;')}"></td>
<td><input data-i=${i} class=fn value="${(p.new_filename||p.filename||'').replace(/"/g,'&quot;')}"></td>
<td>${(p.reason||'').replace(/</g,'&lt;')}</td>`;tb.appendChild(tr);});
function dl(){const approved=[],flagged=[],skipped=[];
P.forEach((p,i)=>{const act=document.querySelector(`.act[data-i="${i}"]`).value;
const dest=document.querySelector(`.dest[data-i="${i}"]`).value;
const fn=document.querySelector(`.fn[data-i="${i}"]`).value;
if(act==='flagged'){flagged.push(p.id);return;}
if(act==='skip'){skipped.push(p.id);return;}
approved.push({id:p.id,current_path:p.current_path||p.original_path,para_subfolder:dest,
new_filename:fn,action:act,reason:p.reason||'',file_date:p.file_date,vision_desc:p.vision_desc});});
const blob=new Blob([JSON.stringify({approved,flagged,skipped},null,2)],{type:'application/json'});
const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='proposals_approved.json';a.click();}
</script>"""
    html = html.replace("__ROWS__", rows).replace("__AP__", appr_path_js)
    _atomic_write(review_html, html)
    return review_html


def cmd_generate_viewer(args):
    from drive_organizer.classify_propose import _bubble_sort_proposals
    from drive_organizer.entities_rules import _read_entities
    proposals_path = Path(args.proposals)
    if not proposals_path.exists():
        sys.exit(f"Error: proposals file not found: {proposals_path}")

    with open(proposals_path, encoding="utf-8") as f:
        proposals = json.load(f)

    if not proposals:
        sys.exit("Error: proposals JSON is empty.")

    # Bubble-sort by destination so files going to the same leaf appear together
    proposals = _bubble_sort_proposals(proposals)

    # Cowork-reachable fallback: if asked for --static, or a Cowork/headless session is
    # detected, emit a static editable review file instead of a localhost server nobody
    # on this host can open.
    if getattr(args, "static", False) or _cowork_or_headless():
        review_html = _emit_static_review(proposals)
        print("Static review mode (localhost viewer not reachable here).")
        print(f"  Review + edit:        {review_html}")
        print(f"  Pre-filled approvals: {APPROVED_JSON_PATH}  ({len(proposals)} files, all 'approved')")
        print("  Edit in the HTML and Download, or edit the JSON directly, then run process-return.")
        print("  (To force the localhost server instead, re-run without --static and unset DRIVE_ORG_HEADLESS.)")
        return

    port = int(args.port) if args.port else 5002

    # Load path vocab from registry (+ built-in structural defaults)
    # Level 1 is seeded from .tidy-rules.json — never hardcoded here.
    # Level 2 = universal subfolder *types*; level 3 = common depth-3 structural names.
    # This is a curated seed list hand-aligned with subfolder-templates.json's
    # subfolder_definitions — it is NOT read from that file at runtime (autocomplete must
    # work before any templates are loaded), so it is only a convenience seed: the live,
    # authoritative vocabulary comes from the registry's actually-used path segments
    # (queried below), which always reflect the real taxonomy even as the templates grow.
    # Personal ENTITY names (people, joint owners, etc.) are NOT hardcoded here — they
    # are seeded per-drive from entities.json / the registry's used segments below, so a
    # shared install ships only generic types, never any individual's identity.
    BUILTIN_VOCAB: dict[int, list[str]] = {
        1: [],
        2: ["Schedules", "Docs", "References", "Legal", "Financials",
            "Templates", "Planning", "Admin", "Notes", "Reports",
            "Academic Papers", "Archived", "Deliverables"],
        3: ["Bills", "Invoices", "Receipts", "Bank Statements", "Tax Documents",
            "Expense Reports", "Payment Summaries", "Advances",
            "Contracts", "Agreements", "Backups", "Code", "Output"],
    }
    # NOTE: this is a small UNIVERSAL seed only. Any user's real, domain-specific
    # vocabulary reaches autocomplete from the registry's actually-used path segments
    # (path_vocab, queried below) and from entities.json — it is NOT hardcoded here, so
    # the shipped skill ships no individual's taxonomy.
    vocab: dict[int, list[str]] = {1: [], 2: [], 3: []}
    if paths_config.REGISTRY_DB.exists():
        try:
            with sqlite3.connect(str(paths_config.REGISTRY_DB)) as _db:
                _db.row_factory = sqlite3.Row
                for row in _db.execute(
                    "SELECT segment, position FROM path_vocab ORDER BY use_count DESC"
                ).fetchall():
                    pos = row["position"]
                    if pos in vocab:
                        vocab[pos].append(row["segment"])
        except (sqlite3.DatabaseError, OSError) as e:
            print(f"WARNING: could not read path_vocab from registry "
                  f"({type(e).__name__}: {e}); proposal-path autocomplete "
                  f"may be incomplete.", file=sys.stderr)
    # Seed level-1 directly from .tidy-rules.json (source of truth for top-level names)
    rules_file = paths_config._EFFECTIVE_ROOT / ".tidy-rules.json"
    if rules_file.exists():
        try:
            _rules_data = json.loads(rules_file.read_text(encoding="utf-8"))
            _seen_l1 = set(vocab[1])
            for _rule in _rules_data.get("rules", []):
                _top = _rule.get("folderName", "").split("/")[0].strip()
                if _top and _top not in _seen_l1:
                    vocab[1].append(_top)
                    _seen_l1.add(_top)
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: could not seed vocab[1] from {rules_file} "
                  f"({type(e).__name__}: {e}); level-1 autocomplete may be "
                  f"incomplete.", file=sys.stderr)
    # Seed entity names (people / joint owners / orgs) from this drive's entities.json —
    # the per-drive source of truth for identities. Replaces the formerly-hardcoded
    # personal names so a shared install carries none, yet a configured drive still
    # autocompletes its own entities. Entities sit at the "thing inside" depth (level 2).
    _seen_l2 = set(vocab[2])
    for _ent in _read_entities().keys():
        if _ent and _ent not in _seen_l2:
            vocab[2].append(_ent)
            _seen_l2.add(_ent)
    for pos in [2, 3]:
        seen = set(vocab[pos])
        for v in BUILTIN_VOCAB[pos]:
            if v not in seen:
                vocab[pos].append(v)
                seen.add(v)

    shutdown_event = threading.Event()
    _SilentHandler._proposals = proposals
    _SilentHandler._shutdown_event = shutdown_event
    if not paths_config.REGISTRY_DB.exists():
        print(
            "WARNING: Registry DB not found — flagged decisions submitted via viewer will be "
            "saved to proposals_flagged.json but NOT written to the registry. "
            "Run `organizer.py scan` to create the registry first, then re-open the viewer.",
            file=sys.stderr
        )
    _SilentHandler._db_path = str(paths_config.REGISTRY_DB) if paths_config.REGISTRY_DB.exists() else None
    _SilentHandler._vocab = {str(k): v for k, v in vocab.items()}

    import errno as _errno
    try:
        server = HTTPServer(("127.0.0.1", port), _SilentHandler)
    except OSError as e:
        if e.errno == _errno.EADDRINUSE:
            sys.exit(
                f"Error: port {port} is already in use. "
                f"Try another --port (e.g. --port {port + 1})."
            )
        raise
    server.timeout = 1.0

    server_thread = threading.Thread(target=_serve_until, args=(server, shutdown_event), daemon=True)
    server_thread.start()

    url = f"http://localhost:{port}/"
    print(f"Viewer running at {url}")
    print(f"Proposals: {len(proposals)} files")
    print(f"Approved output will be written to: {APPROVED_JSON_PATH}")
    print("Press Ctrl+C to stop.")

    if not getattr(args, "no_open", False):
        webbrowser.open(url)

    try:
        shutdown_event.wait()
    except KeyboardInterrupt:
        print("\nInterrupted — shutting down.")
    finally:
        server.shutdown()


def _serve_until(server: HTTPServer, stop_event: threading.Event):
    """Run the server, checking stop_event each timeout cycle."""
    while not stop_event.is_set():
        try:
            server.handle_request()
        except Exception as e:
            # A single handler exception must not kill the serve loop, or the
            # viewer would die mid-review and lose unsubmitted approvals.
            print(f"Warning: request handler error: {e}", flush=True)


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------
