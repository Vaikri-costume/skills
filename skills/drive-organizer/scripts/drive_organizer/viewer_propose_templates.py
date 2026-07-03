"""drive_organizer.viewer_propose_templates — HTML/CSS/JS template strings for the proposal-review viewer, split out of viewer_propose.py (pure structural move, no behavior change)."""


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

_STATIC_REVIEW_HTML_TEMPLATE = """<!doctype html><meta charset="utf-8"><title>Drive Organizer — static review</title>
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
