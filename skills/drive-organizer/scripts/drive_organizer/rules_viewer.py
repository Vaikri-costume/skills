"""drive_organizer.rules_viewer — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    IMAGE_EXTS,
    RAW_EXTS,
    _CLUSTER_LABEL,
    _CLUSTER_ORDER,
    _effective_viewer_page_size,
    _reset_caches,
    _settings_for_viewer,
    _write_user_config,
)
from drive_organizer.content_peek import (
    get_db,
)
from drive_organizer.classify_propose import (
    _auto_classify_entry,
    _build_rules_index,
)
from drive_organizer.entities_rules import (
    _aggregate_rules,
    _apply_area_changes,
    _conflicts_for,
    _coverage_gaps,
    _edit_rule_across_occurrences,
    _merge_entities,
    _promotion_plan,
    _read_entities,
    _rename_entity,
    _write_entities,
)
from drive_organizer.cleanup_reconcile import (
    _active_groupings,
    cmd_reconcile,
)
from drive_organizer.viewer_propose import (
    _serve_until,
)


_RULES_VIEWER_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Drive Organizer — Rules</title>
<style>
 :root{--bg:#0f1115;--card:#1a1d24;--mut:#8b93a7;--fg:#e7ebf3;--acc:#6ea8fe;--warn:#f0a35e;--bad:#e06c75;--ok:#7ec699;--line:#2a2f3a;--input:#11141b;--bar:#0f1115f2;--chip:#232735;--tagbg:#272c38}
 @media (prefers-color-scheme: light){:root{--bg:#f6f7f9;--card:#ffffff;--mut:#5c6473;--fg:#1a1d24;--acc:#2563eb;--warn:#b4690e;--bad:#c0392b;--ok:#2e7d52;--line:#dfe3ea;--input:#ffffff;--bar:#f6f7f9f2;--chip:#eceff3;--tagbg:#e7ebf2}}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;background:var(--bar);backdrop-filter:blur(6px);border-bottom:1px solid var(--line);padding:12px 18px;z-index:5}
 h1{font-size:16px;margin:0 0 6px} .sub{color:var(--mut);font-size:12px}
 .areas{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:8px}
 .chip{background:var(--chip);border:1px solid var(--line);border-radius:14px;padding:2px 10px;font-size:12px;display:flex;gap:6px;align-items:center}
 .chip button{background:none;border:none;color:var(--mut);cursor:pointer;font-size:12px}
 button{cursor:pointer} .btn{background:var(--acc);color:#06101f;border:none;border-radius:6px;padding:6px 12px;font-weight:600}
 .btn.ghost{background:var(--chip);color:var(--fg);border:1px solid var(--line)} .btn.sm{padding:3px 8px;font-size:12px} .btn.warn{color:var(--warn)} .btn.bad{color:var(--bad)}
 main{padding:14px 18px;max-width:1100px;margin:0 auto}
 .cluster{margin:18px 0 6px;font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--acc);border-bottom:1px solid var(--line);padding-bottom:4px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:10px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:11px 12px}
 .card h3{margin:0;font-size:15px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
 .tag{font-size:10px;border-radius:10px;padding:1px 7px;background:var(--tagbg);color:var(--mut)} .tag.rethink{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}
 .tag.dead{background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad)} .tag.lock{background:color-mix(in srgb,var(--ok) 18%,transparent);color:var(--ok)} .tag.inf{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}
 .meta{margin:7px 0;display:grid;grid-template-columns:auto 1fr;gap:4px 8px;align-items:center;font-size:12px}
 .meta label{color:var(--mut)} input,select,textarea{background:var(--input);border:1px solid var(--line);color:var(--fg);border-radius:5px;padding:4px 6px;font:inherit;width:100%}
 textarea{resize:vertical;min-height:34px} .occ{font-size:11px;color:var(--mut);margin:6px 0;border-left:2px solid var(--line);padding-left:8px}
 .occ b{color:var(--fg);font-weight:600} .conflict{font-size:11px;color:var(--warn);margin-top:5px} .row{display:flex;gap:6px;margin-top:7px;flex-wrap:wrap}
 .pager{display:flex;gap:6px;align-items:center;justify-content:center;margin:16px 0} .pager span{color:var(--mut)}
 .tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:8px}
 .tools input{width:auto;min-width:220px} #testout,#planout{font-size:12px;color:var(--ok);margin-left:6px}
 .gaps{margin-top:8px;font-size:12px;color:var(--warn)} dialog{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:10px}
 .legend{margin-top:8px;font-size:12px} .legend summary{cursor:pointer;color:var(--acc)} .legendbody{color:var(--mut);margin-top:6px;padding:8px 10px;background:var(--input);border:1px solid var(--line);border-radius:8px} .legendbody ul{margin:4px 0 8px 0;padding-left:18px} .legendbody b{color:var(--fg)} .legendbody i{color:var(--acc)}
 .savebar{position:sticky;bottom:0;background:var(--bar);border-top:1px solid var(--line);padding:10px 18px;display:flex;gap:12px;align-items:center;justify-content:flex-end}
 .pill{font-size:11px;background:var(--tagbg);border-radius:10px;padding:1px 8px;color:var(--mut)}
 .bulkbar{position:sticky;top:0;z-index:6;background:var(--bar);border-bottom:1px solid var(--line);padding:8px 18px;display:flex;gap:10px;align-items:center}
 .planline{font-size:11px;color:var(--warn)} h3 .bulk{accent-color:var(--acc);margin-right:2px}
 #diff{max-width:560px;width:90%} #diffbody{max-height:50vh;overflow:auto} .diffrow{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:4px 0;border-bottom:1px solid var(--line);font-size:13px}
</style></head><body>
<header>
 <h1>Drive Organizer — Rules viewer / editor</h1>
 <div class="sub" id="sub"></div>
 <div class="areas" id="areas"></div>
 <div class="tools">
   <span class="pill">Test a file</span><input id="testfile" placeholder="paste a filename, e.g. invoice_acme.pdf">
   <button class="btn sm ghost" onclick="testFile()">where would it go?</button><span id="testout"></span>
 </div>
 <div class="gaps" id="gaps"></div>
 <details class="legend"><summary>What goes where?</summary>
  <div class="legendbody">
   <b>type</b> — which cluster an entity belongs to:
   <ul>
    <li><b>area</b> — a top-level grouping (WORK, PERSONAL…)</li>
    <li><b>project</b> — a project folder (carries a filename tag / production period)</li>
    <li><b>person</b> — a person or name (give their other names under <i>aliases</i>)</li>
    <li><b>category</b> — a functional subfolder reused across the tree (Bills, Docs, Scripts…)</li>
    <li><b>policy</b> — an entity whose rule is a <i>behaviour</i> (e.g. group files by event/date)</li>
    <li><b>atomic</b> — a whole folder treated as one locked unit, never opened file-by-file</li>
   </ul>
   <b>aliases</b> — other spellings/names that should route to this same entity (e.g. <i>Bob</i> → Robert).<br>
   <b>relation</b> — how it relates to you or another entity, free text (collaborator, client, partner…).<br>
   <b>behaviour</b> — the specific routing behaviour, if any (e.g. <i>event-group</i>). This is different from the <i>policy</i> type: type says "this entity is a behaviour rule", behaviour says "what the rule does".<br>
   <b>notes</b> — anything else worth recording about the rule.
  </div>
 </details>
 <details class="legend" id="settingspanel"><summary>⚙ Settings</summary>
  <div class="legendbody">
   <div class="meta" style="grid-template-columns:auto 1fr;max-width:560px">
    <label title="Let classification agents open file CONTENTS (text/PDF). Off → classify from the pre-extracted snippet + name/path/rules only.">peek (read file contents)</label>
    <span><input type="checkbox" id="set_peek" style="width:auto"></span>
    <label title="Let classification agents SEE images. Off → route images by name/path/rules + EXIF date.">vision (see images)</label>
    <span><input type="checkbox" id="set_vision" style="width:auto"></span>
    <label title="Mark deterministic W1 fast-path matches auto_approved so you may skip the viewer for them (still audited in auto-routed.csv). Default off.">auto-approve W1 fast-path</label>
    <span><input type="checkbox" id="set_autoapprove" style="width:auto"></span>
    <label title="Never open these extensions — route by name/path/rules only. Comma-separated, e.g. .mov, .raw">skip file types</label>
    <input id="set_skiptypes" placeholder=".mov, .raw">
    <label title="Never open files larger than this many MB — route by name/path/rules only. Blank = no cap.">skip files over (MB)</label>
    <input id="set_skipmb" type="number" min="0" step="1" placeholder="(no cap)">
    <label title="Extra words that mark a file as a &quot;variant&quot; for merge-candidate grouping (e.g. legal: executed, redlined; screenwriting: draft, revision). Extends the built-in list (v2/final/copy/highlighted/annotated/marked) — does not replace it. Comma-separated.">variant tokens (extra)</label>
    <input id="set_varianttokens" placeholder="e.g. executed, redlined">
    <label title="Classification fan-out batch size — how many files each classification sub-agent works at once. Blank = default (25).">classify batch size</label>
    <input id="set_batchsize" type="number" min="1" step="1" placeholder="25 (default)">
    <label title="Days of padding added to each side of a project's date_range when a file's date widens it. Blank = default (30).">period buffer (days)</label>
    <input id="set_bufferdays" type="number" min="1" step="1" placeholder="30 (default)">
    <label title="Max characters extracted per file for the content-peek text snippet used in classification. Blank = default (300).">content peek chars</label>
    <input id="set_peekchars" type="number" min="1" step="1" placeholder="300 (default)">
    <label title="Seconds to wait for a cloud-only (online-not-downloaded) file to finish downloading before skipping it for this pass. Overridden per-run by the DRIVE_ORG_DL_TIMEOUT env var when set. Blank = default (30).">download poll timeout (s)</label>
    <input id="set_dltimeout" type="number" min="0" step="1" placeholder="30 (default)">
    <label title="Inbox size (organizer.py inbox-list → count) at which to run the periodic arbiter reclamation sweep. Soft guideline, not a hard gate. Blank = default (100).">inbox arbiter trigger</label>
    <input id="set_arbitertrigger" type="number" min="1" step="1" placeholder="100 (default)">
    <label title="Max files per scan/propose/bootstrap batch. Overridden per-run by --limit when passed. Blank = default (250).">scan file limit</label>
    <input id="set_scanfilelimit" type="number" min="1" step="1" placeholder="250 (default)">
    <label title="Max cumulative GB per scan/download-batch batch. Overridden per-run by --limit-gb when passed. Blank = default (20).">scan GB limit</label>
    <input id="set_scangblimit" type="number" min="0" step="0.1" placeholder="20 (default)">
    <label title="Earliest date a file's date is trusted to widen a project's date_range — anything before this is treated as unreliable/pre-digital noise and ignored. Blank = default (1990-01-01).">date floor</label>
    <input id="set_datefloor" type="date">
    <label title="How many days into the future (from now) a file's date is still trusted — anything further out is treated as a clock/metadata error and ignored. Blank = default (365).">date ceiling (days from now)</label>
    <input id="set_dateceilingdays" type="number" min="1" step="1" placeholder="365 (default)">
    <label title="Rows per page in this rules viewer and the proposal-review viewer. Does not affect the entity cap (fixed at 250). Blank = default (25).">viewer page size</label>
    <input id="set_viewerpagesize" type="number" min="1" step="1" placeholder="25 (default)">
    <label title="Extra folder NAMES treated as atomic units (never descended, proposed whole) — e.g. a proprietary device-export folder name specific to your drive. Extends the shipped signature list (node_modules/.git/venv/OSCAR_Data/Backups.backupdb/etc.) — does not replace it. Comma-separated.">atomic folder names (extra)</label>
    <input id="set_atomicdirs" placeholder="e.g. MyDeviceExport">
    <label title="Extra folder-name SUFFIXES treated as atomic-unit bundles (like .app/.framework/.xcodeproj) — e.g. a proprietary bundle extension specific to your drive. Extends the shipped list — does not replace it. Comma-separated, include the leading dot.">atomic folder suffixes (extra)</label>
    <input id="set_atomicsuffixes" placeholder="e.g. .mybundle">
   </div>
   <div class="row"><button class="btn sm" onclick="saveSettings()">Save settings</button><span id="set_out" style="font-size:12px;color:var(--ok)"></span></div>
  </div>
 </details>
</header>
<div id="bulkbar" class="bulkbar" style="display:none">
 <span id="bulkn" class="pill">0 selected</span>
 <select onchange="bulkType(this.value);this.value=''"><option value="">set type…</option><option>area</option><option>project</option><option>person</option><option>category</option><option>policy</option><option>atomic</option><option>unknown</option></select>
 <button class="btn sm ghost warn" onclick="bulkRethink()">rethink selected</button>
 <button class="btn sm ghost bad" onclick="bulkDelete()">delete selected</button>
 <button class="btn sm ghost" onclick="bulkClear()">clear selection</button>
</div>
<main id="main"></main>
<dialog id="diff"><h3>Pending changes</h3><div id="diffbody"></div><div style="text-align:right;margin-top:10px"><button class="btn ghost" onclick="document.getElementById('diff').close()">close</button></div></dialog>
<div class="savebar">
 <span class="pill" id="dirty">0 unsaved changes</span>
 <button class="btn ghost" onclick="preview()">Preview changes</button>
 <button class="btn ghost" onclick="location.reload()">Discard all</button>
 <button class="btn ghost" onclick="apply()" title="write changes now and keep the editor open">Apply (keep open)</button>
 <button class="btn" onclick="save()">Save &amp; close</button>
</div>
<script>
let DATA = __DATA__;   // reassigned by apply() on keep-open refresh — must be `let`, not `const`
const PAGE = __PAGE_SIZE__, CAP = 250;
const TYPE_HELP={area:'top-level grouping',project:'a project (has a filename tag/period)',person:'a person / name',category:'a functional subfolder (Bills, Docs…)',policy:'a behaviour rule (e.g. event-grouping)',atomic:'a locked whole-folder unit (never descended)',unknown:'not yet classified — please set'};
let changes = {entities:{}, rule_edits:{}, deletes:{}, rethink:{}, renames:{}, merges:{}, areas:{add:[],rename:[],remove:[]}};
let pages = {}; // cluster -> current page
function dirtyCount(){return Object.keys(changes.entities).length+Object.keys(changes.rule_edits).length+Object.keys(changes.deletes).length+Object.keys(changes.rethink).length+Object.keys(changes.renames).length+Object.keys(changes.merges).length+changes.areas.add.length+changes.areas.rename.length+changes.areas.remove.length;}
function markDirty(){document.getElementById('dirty').textContent=dirtyCount()+' unsaved change(s)';}
function byType(){const m={};for(const e of DATA.entities){(m[e.entity_type]=m[e.entity_type]||[]).push(e);}return m;}
function esc(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
// For values dropped INTO a single-quoted JS string inside an onclick="..." attribute:
// backslash-escape \ and ' for the JS-string layer FIRST, then HTML-escape for the
// attribute layer. Plain esc() would emit &#39; which the HTML parser decodes back to
// a bare ' before the JS runs — breaking the call (or allowing injection) on names
// like "O'Brien". jsq() survives both layers.
function jsq(s){return esc(String(s==null?'':s).replace(/\\/g,'\\\\').replace(/'/g,"\\'"));}

function renderAreas(){
 const el=document.getElementById('areas');el.innerHTML='<span class="pill">Areas</span>';
 DATA.areas.forEach(a=>{const c=document.createElement('span');c.className='chip';
   c.innerHTML=`${esc(a)} <button title="rename" onclick="renameArea('${jsq(a)}')">✎</button><button title="remove" onclick="removeArea('${jsq(a)}')">✕</button>`;el.appendChild(c);});
 const add=document.createElement('button');add.className='btn sm ghost';add.textContent='+ area';add.onclick=addArea;el.appendChild(add);
}
function addArea(){const n=prompt('New area name (will be ALL-CAPS):');if(n){const u=n.toUpperCase();if(DATA.areas.indexOf(u)>=0)return;changes.areas.add.push(u);DATA.areas.push(u);renderAreas();markDirty();}}
function renameArea(a){const n=prompt('Rename '+a+' to:',a);if(n){const i=DATA.areas.indexOf(a);if(i<0)return;changes.areas.rename.push({old:a,new:n.toUpperCase()});DATA.areas[i]=n.toUpperCase();renderAreas();markDirty();}}
function removeArea(a){if(confirm('Remove area '+a+'? (refused if it still has files)')){changes.areas.remove.push(a);DATA.areas=DATA.areas.filter(x=>x!=a);renderAreas();markDirty();}}

let selected=new Set();
function card(e){
 const conf=DATA.conflicts[e.occurrences[0]?.dest]||[];
 const occ=e.occurrences.map(o=>`<div class="occ"><b>${esc(o.parent||'(root)')}/${esc(o.folderName)}</b> — ${esc(o.signal||'(no signal)')}</div>`).join('');
 const tags=[]; if(e.locked)tags.push('<span class="tag lock">locked</span>');
 if(e.dead&&e.occurrences.length)tags.push('<span class="tag dead">0 routed</span>');
 if(e.type_inferred)tags.push('<span class="tag inf">type?</span>');
 if(e.review||changes.rethink[e.entity])tags.push('<span class="tag rethink">rethink</span>');
 const types=['area','project','person','category','policy','atomic','unknown'];
 const ck=selected.has(e.entity)?'checked':'';
 return `<div class="card" data-e="${esc(e.entity)}">
  <h3><input type="checkbox" class="bulk" ${ck} onchange="toggleSel('${jsq(e.entity)}',this.checked)" title="select for bulk action"> ${esc(e.entity)} ${tags.join(' ')} <span class="tag">${e.usage_count} files</span></h3>
  <div class="meta">
   <label title="Which cluster this entity belongs to. See the 'What goes where' legend at the top.">type</label><select onchange="metaEdit('${jsq(e.entity)}','entity_type',this.value)">${types.map(t=>`<option value="${t}" ${t==e.entity_type?'selected':''}>${t} — ${TYPE_HELP[t]}</option>`).join('')}</select>
   <label title="Other names this same thing is known by, so they auto-route to it.">aliases</label><input value="${esc((e.aliases||[]).join(', '))}" placeholder="other names, e.g. Bob, R.S." onchange="metaEdit('${jsq(e.entity)}','aliases',this.value.split(',').map(s=>s.trim()).filter(Boolean))">
   <label title="How this entity relates to you or to another entity (free text).">relation</label><input value="${esc(e.relation||'')}" placeholder="e.g. collaborator, client, partner, employer" onchange="metaEdit('${jsq(e.entity)}','relation',this.value)">
   <label title="A routing behaviour for this entity's files (optional). Distinct from the 'policy' type: this is the specific rule. Recognised: 'event-group' files this entity's dated files into date-derived subfolders (YYYY/Month YY). Any other text is just a note.">behaviour</label><input value="${esc(e.policy||'')}" placeholder="e.g. event-group (group photos by date/event)" onchange="metaEdit('${jsq(e.entity)}','policy',this.value)">
   <label title="Free notes — what this rule is for, or why it exists.">notes</label><input value="${esc(e.notes||'')}" placeholder="free notes, e.g. 'primary contact for Project X'" onchange="metaEdit('${jsq(e.entity)}','notes',this.value)">
   <label title="Date range this entity's dated files fall in (optional). Routes loose dated files (bills, statements, photos) to this entity by date — generalised off projects-only. Leave both blank to clear.">date range</label><span style="display:flex;gap:4px"><input type="date" value="${esc((e.date_range||{}).start||'')}" onchange="drEdit('${jsq(e.entity)}','start',this.value)"><input type="date" value="${esc((e.date_range||{}).end||'')}" onchange="drEdit('${jsq(e.entity)}','end',this.value)"></span>
   <label title="Canonical tag inserted into new_filename for files routed to this entity, so classification doesn't need to re-infer the issuer/person name from content every round — same purpose as a project's filename_tag, just entity-level.">filename tag</label><input value="${esc(e.filename_tag||'')}" placeholder="e.g. ChaseBank, JaneDoe" onchange="metaEdit('${jsq(e.entity)}','filename_tag',this.value)">
   <label title="Overrides the global 4-character minimum for this entity's own folder-name tokens to become auto-classify matches (optional). Set to 3 for short names like IBM/BBC/ADM that would otherwise never auto-route. Leave blank for the default (4).">min token len</label><input type="number" min="1" value="${e.min_token_len||''}" placeholder="4 (default)" onchange="metaEdit('${jsq(e.entity)}','min_token_len',this.value===''?'':parseInt(this.value,10))">
   <label title="Override the global auto-approve setting for this entity's W1 fast-path matches. Inherit = use the Settings-panel global. Always = auto-approve this entity's matches even if the global is off. Never = never auto-approve this entity's matches even if the global is on.">auto-approve</label><select onchange="metaEdit('${jsq(e.entity)}','auto_approve',this.value===''?'':this.value==='true')"><option value="" ${e.auto_approve==null?'selected':''}>inherit global</option><option value="true" ${e.auto_approve===true?'selected':''}>always approve</option><option value="false" ${e.auto_approve===false?'selected':''}>never approve</option></select>
  </div>
  ${occ}
  ${conf.length?`<div class="conflict">⚠ overlaps: ${conf.map(c=>esc(c.with)+' ['+c.shared.join(',')+']').join('; ')}</div>`:''}
  ${e.occurrences.length?`<label class="sub">signal (applies to all ${e.occurrences.length} folder(s))</label>
  <textarea onchange="signalEdit('${jsq(e.entity)}',this.value)">${esc(e.occurrences[0]?.signal||'')}</textarea>`:''}
  <div class="row">
   <button class="btn sm ghost" onclick="planMove('${jsq(e.entity)}')" title="dry-run a move up/down a level">move a level…</button>
   <button class="btn sm ghost" onclick="renameEntity('${jsq(e.entity)}')" title="rename this entity (rule + folder + registry)">rename</button>
   <button class="btn sm ghost" onclick="mergeEntity('${jsq(e.entity)}')" title="fold this into another entity as an alias">merge…</button>
   <button class="btn sm ghost warn" onclick="rethinkEntity('${jsq(e.entity)}')" title="flag for re-inference — keeps the rule, marks it to reconsider (≠ delete)">rethink</button>
   <button class="btn sm ghost bad" onclick="delEntity('${jsq(e.entity)}')" title="remove the routing rule (files/folders are NOT deleted)">delete</button>
   <span id="plan-${esc(e.entity)}" class="planline"></span>
  </div>
 </div>`;
}
function render(){
 document.getElementById('sub').textContent=`${DATA.root} — ${DATA.entities.length} entities (showing up to ${CAP}), ${PAGE}/page`;
 renderAreas();
 const gaps=DATA.coverage_gaps||[]; const SHOWN=12; const capped=gaps.length>=100;
 document.getElementById('gaps').innerHTML=gaps.length?`coverage gaps (folders with files, no rule) — showing ${Math.min(SHOWN,gaps.length)} of ${gaps.length}${capped?'+ (capped at 100 — there may be more)':''}: ${gaps.slice(0,SHOWN).map(esc).join(', ')}${gaps.length>SHOWN?' …':''}`:'';
 const m=byType();const main=document.getElementById('main');main.innerHTML='';
 for(const t of DATA.cluster_order){const ents=(m[t]||[]).slice(0,CAP);if(!ents.length)continue;
   pages[t]=pages[t]||0;const start=pages[t]*PAGE;const show=ents.slice(start,start+PAGE);
   const h=document.createElement('div');h.className='cluster';h.textContent=`${DATA.cluster_label[t]||t} (${ents.length})`;main.appendChild(h);
   const g=document.createElement('div');g.className='grid';g.innerHTML=show.map(card).join('');main.appendChild(g);
   if(ents.length>PAGE){const p=document.createElement('div');p.className='pager';
     p.innerHTML=`<button class="btn sm ghost" onclick="flip('${t}',-1)">‹</button><span>page ${pages[t]+1}/${Math.ceil(ents.length/PAGE)}</span><button class="btn sm ghost" onclick="flip('${t}',1)">›</button>`;main.appendChild(p);}
 }
 renderBulk();markDirty();
 renderSettings();
}
function renderSettings(){
 const s=DATA.settings||{};
 document.getElementById('set_peek').checked = s.peek!==false;
 document.getElementById('set_vision').checked = s.vision!==false;
 document.getElementById('set_autoapprove').checked = !!s.auto_approve;
 document.getElementById('set_skiptypes').value = (s.skip_types||[]).join(', ');
 document.getElementById('set_skipmb').value = (s.skip_over_mb==null?'':s.skip_over_mb);
 document.getElementById('set_varianttokens').value = (s.variant_tokens||[]).join(', ');
 document.getElementById('set_batchsize').value = (s.classify_batch_size==null?'':s.classify_batch_size);
 document.getElementById('set_bufferdays').value = (s.period_buffer_days==null?'':s.period_buffer_days);
 document.getElementById('set_peekchars').value = (s.content_peek_chars==null?'':s.content_peek_chars);
 document.getElementById('set_dltimeout').value = (s.download_poll_timeout==null?'':s.download_poll_timeout);
 document.getElementById('set_arbitertrigger').value = (s.inbox_arbiter_trigger==null?'':s.inbox_arbiter_trigger);
 document.getElementById('set_scanfilelimit').value = (s.scan_file_limit==null?'':s.scan_file_limit);
 document.getElementById('set_scangblimit').value = (s.scan_gb_limit==null?'':s.scan_gb_limit);
 document.getElementById('set_datefloor').value = (s.date_floor==null?'':s.date_floor);
 document.getElementById('set_dateceilingdays').value = (s.date_ceiling_days==null?'':s.date_ceiling_days);
 document.getElementById('set_viewerpagesize').value = (s.viewer_page_size==null?'':s.viewer_page_size);
 const ase=s.atomic_signatures_extra||{};
 document.getElementById('set_atomicdirs').value = (ase.dir_names||[]).join(', ');
 document.getElementById('set_atomicsuffixes').value = (ase.suffixes||[]).join(', ');
}
function saveSettings(){
 const out=document.getElementById('set_out'); out.textContent='saving…';
 const mb=document.getElementById('set_skipmb').value.trim();
 const batchSize=document.getElementById('set_batchsize').value.trim();
 const bufferDays=document.getElementById('set_bufferdays').value.trim();
 const peekChars=document.getElementById('set_peekchars').value.trim();
 const dlTimeout=document.getElementById('set_dltimeout').value.trim();
 const arbiterTrigger=document.getElementById('set_arbitertrigger').value.trim();
 const scanFileLimit=document.getElementById('set_scanfilelimit').value.trim();
 const scanGbLimit=document.getElementById('set_scangblimit').value.trim();
 const dateFloor=document.getElementById('set_datefloor').value.trim();
 const dateCeilingDays=document.getElementById('set_dateceilingdays').value.trim();
 const viewerPageSize=document.getElementById('set_viewerpagesize').value.trim();
 const atomicDirs=document.getElementById('set_atomicdirs').value.split(',').map(s=>s.trim()).filter(Boolean);
 const atomicSuffixes=document.getElementById('set_atomicsuffixes').value.split(',').map(s=>s.trim()).filter(Boolean);
 const settings={
   peek: document.getElementById('set_peek').checked,
   vision: document.getElementById('set_vision').checked,
   auto_approve: document.getElementById('set_autoapprove').checked,
   skip_types: document.getElementById('set_skiptypes').value,
   skip_over_mb: mb===''?null:Number(mb),
   variant_tokens: document.getElementById('set_varianttokens').value,
   classify_batch_size: batchSize===''?null:Number(batchSize),
   period_buffer_days: bufferDays===''?null:Number(bufferDays),
   content_peek_chars: peekChars===''?null:Number(peekChars),
   download_poll_timeout: dlTimeout===''?null:Number(dlTimeout),
   inbox_arbiter_trigger: arbiterTrigger===''?null:Number(arbiterTrigger),
   scan_file_limit: scanFileLimit===''?null:Number(scanFileLimit),
   scan_gb_limit: scanGbLimit===''?null:Number(scanGbLimit),
   date_floor: dateFloor===''?null:dateFloor,
   date_ceiling_days: dateCeilingDays===''?null:Number(dateCeilingDays),
   viewer_page_size: viewerPageSize===''?null:Number(viewerPageSize),
   atomic_signatures_extra: (atomicDirs.length||atomicSuffixes.length)?{dir_names:atomicDirs,suffixes:atomicSuffixes}:null,
 };
 fetch('/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({settings})})
  .then(r=>r.json()).then(d=>{
    if(d.ok){DATA.settings=d.settings;renderSettings();out.textContent='saved ✓';setTimeout(()=>out.textContent='',2500);}
    else{out.style.color='var(--bad)';out.textContent='error: '+(d.error||'failed');}
  }).catch(e=>{out.style.color='var(--bad)';out.textContent='error: '+e;});
}
function flip(t,d){const m=byType();const n=Math.ceil(Math.min(m[t].length,CAP)/PAGE);pages[t]=Math.max(0,Math.min(n-1,pages[t]+d));render();}
function metaEdit(e,k,v){changes.entities[e]=changes.entities[e]||{};changes.entities[e][k]=v;markDirty();}
function drEdit(ent,which,val){
 const cur=(changes.entities[ent]&&changes.entities[ent].date_range)||((DATA.entities.find(x=>x.entity===ent)||{}).date_range)||{};
 const dr={start:cur.start||'',end:cur.end||''}; dr[which]=val;
 changes.entities[ent]=changes.entities[ent]||{};
 changes.entities[ent].date_range=(dr.start||dr.end)?{start:dr.start,end:dr.end}:null;
 markDirty();
}
function signalEdit(e,v){changes.rule_edits[e]={entity:e,description:v};markDirty();}
function delEntity(e){if(confirm('Delete the routing rule for "'+e+'" everywhere? (files/folders are NOT deleted)')){changes.deletes[e]=true;markDirty();render();}}
function rethinkEntity(e){changes.rethink[e]=true;markDirty();render();}
function renameEntity(e){const n=prompt('Rename "'+e+'" to (renames the rule, the on-disk folder, and registry rows):',e);if(n&&n!=e){changes.renames[e]={entity:e,new_name:n};markDirty();render();}}
function mergeEntity(e){const d=prompt('Fold "'+e+'" INTO which entity? (its name becomes an alias of that one, its rule is removed)');if(d&&d!==e){changes.merges[e]={src:e,dst:d};markDirty();render();}}
// bulk
function toggleSel(e,on){on?selected.add(e):selected.delete(e);renderBulk();}
function renderBulk(){const b=document.getElementById('bulkbar');if(!selected.size){b.style.display='none';return;}
 b.style.display='flex';b.querySelector('#bulkn').textContent=selected.size+' selected';}
function bulkType(v){if(!v)return;selected.forEach(e=>metaEdit(e,'entity_type',v));render();}
function bulkRethink(){selected.forEach(e=>changes.rethink[e]=true);markDirty();render();}
function bulkDelete(){if(confirm('Delete rules for '+selected.size+' selected entities?')){selected.forEach(e=>changes.deletes[e]=true);selected.clear();markDirty();render();}}
function bulkClear(){selected.clear();render();}
async function testFile(){const fn=document.getElementById('testfile').value;if(!fn)return;
 const r=await fetch('/test',{method:'POST',body:JSON.stringify({filename:fn})});const j=await r.json();
 document.getElementById('testout').textContent=j.dest?`→ ${j.dest} (${j.reason})`:j.reason;}
async function planMove(e){const tgt=prompt('Promote/move "'+e+'" under which parent? (blank = top-level area)');if(tgt===null)return;
 const r=await fetch('/plan',{method:'POST',body:JSON.stringify({entity:e,target_parent:tgt})});const j=await r.json();
 document.getElementById('plan-'+e).textContent='DRY-RUN preview (not wired to Apply/Save — see plan.note for how to perform this move): '+(j.steps||[]).map(s=>`${s.move_folder.from}→${s.move_folder.to} (${s.registry_rows_to_update} rows)`).join('; ');}
// preview / diff + per-change undo
function pendingList(){const out=[];
 for(const[e,m]of Object.entries(changes.entities))out.push({k:'entities',e,label:`${e}: set ${Object.keys(m).join(', ')}`});
 for(const e of Object.keys(changes.rule_edits))out.push({k:'rule_edits',e,label:`${e}: edit signal`});
 for(const e of Object.keys(changes.deletes))out.push({k:'deletes',e,label:`${e}: DELETE rule`});
 for(const e of Object.keys(changes.rethink))out.push({k:'rethink',e,label:`${e}: rethink (re-infer)`});
 for(const e of Object.keys(changes.renames))out.push({k:'renames',e,label:`${e} → ${changes.renames[e].new_name}`});
 for(const e of Object.keys(changes.merges))out.push({k:'merges',e,label:`${e} ⤳ merge into ${changes.merges[e].dst}`});
 changes.areas.add.forEach((a,i)=>out.push({k:'areas.add',e:i,label:`area + ${a}`}));
 changes.areas.rename.forEach((a,i)=>out.push({k:'areas.rename',e:i,label:`area ${a.old} → ${a.new}`}));
 changes.areas.remove.forEach((a,i)=>out.push({k:'areas.remove',e:i,label:`area − ${a}`}));
 return out;}
function undo(k,e){if(k.startsWith('areas.')){const sub=k.split('.')[1];changes.areas[sub].splice(e,1);}else{delete changes[k][e];}preview();render();}
function preview(){const l=pendingList();const dlg=document.getElementById('diff');
 dlg.querySelector('#diffbody').innerHTML=l.length?l.map(x=>`<div class="diffrow"><span>${esc(x.label)}</span><button class="btn sm ghost" onclick="undo('${jsq(x.k)}','${jsq(x.e)}')">undo</button></div>`).join(''):'<i>no pending changes</i>';
 if(!dlg.open)dlg.showModal();}
function payload(extra){return Object.assign({entities:changes.entities,rule_edits:Object.values(changes.rule_edits),deletes:Object.keys(changes.deletes),rethink:Object.keys(changes.rethink),renames:Object.values(changes.renames),merges:Object.values(changes.merges),areas:changes.areas},extra||{});}
function clearChanges(){changes={entities:{},rule_edits:{},deletes:{},rethink:{},renames:{},merges:{},areas:{add:[],rename:[],remove:[]}};selected.clear();}
async function apply(){const r=await fetch('/apply',{method:'POST',body:JSON.stringify(payload())});const j=await r.json();
 if(r.ok&&j.ok){const d=document.getElementById('diff');if(d.open)d.close();
   if(j.data)DATA=j.data;
   clearChanges();render();
   document.getElementById('dirty').textContent='applied ✓ — kept open';}
 else{document.getElementById('dirty').textContent='apply failed: '+((j&&j.error)||('HTTP '+r.status));}}
async function save(){const r=await fetch('/save',{method:'POST',body:JSON.stringify(payload())});const j=await r.json();
 document.body.innerHTML='<main style="padding:20px"><h1>Saved</h1><pre>'+esc(JSON.stringify(j.results,null,2))+'</pre><p>You can close this tab.</p></main>';}
render();
</script></body></html>"""


class _RulesHandler(BaseHTTPRequestHandler):
    """Serves the rules viewer/editor and applies edits on submit."""
    _root: Path = None

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self._send(404, {"error": "not found"})
            return
        root = self.__class__._root
        # Two tree walks here (_aggregate_rules for the entity view, _build_rules_index
        # for conflicts/coverage). Kept separate on purpose: they are independent concerns
        # reused at other call sites (the W1 matcher, /test, cmd_reconcile), and merging
        # them into one shared walk would couple the matcher's hot path to the viewer's
        # display logic. The cost is two .tidy-rules.json walks PER PAGE LOAD of a manual,
        # localhost-only viewer the user opens a handful of times — not a production hot
        # path — so the clarity of two single-purpose helpers wins over de-duping the walk.
        agg = _aggregate_rules(root)
        index, dest_set = _build_rules_index(root)
        payload = {
            "root": str(root),
            "areas": sorted(_active_groupings()),
            "entities": agg,
            "conflicts": _conflicts_for(index),
            "coverage_gaps": _coverage_gaps(root, dest_set),
            "cluster_order": _CLUSTER_ORDER,
            "cluster_label": _CLUSTER_LABEL,
            "settings": _settings_for_viewer(root),
        }
        data_js = json.dumps(payload).replace("</", "<\\/")
        html = _RULES_VIEWER_HTML.replace("__DATA__", data_js)
        html = html.replace("__PAGE_SIZE__", str(_effective_viewer_page_size(root)))
        self._send(200, html, "text/html; charset=utf-8")

    _MAX_BODY = 8 * 1024 * 1024  # cap request body at 8 MiB

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send(400, {"error": "bad content-length"}); return
        if length < 0 or length > self._MAX_BODY:
            self._send(400, {"error": "body too large"}); return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "bad json"}); return
        root = self.__class__._root

        if self.path == "/config":
            # Settings panel: merge the submitted user-editable config keys into
            # <root>/.organizer/config.json and return the new effective settings. Separate
            # from /save and /apply (which handle rule/entity edits) so saving settings never
            # touches the rule set and vice-versa.
            try:
                new_settings = _write_user_config(payload.get("settings") or {}, root)
            except Exception as e:
                self._send(500, {"error": f"could not write settings: {e}"}); return
            self._send(200, {"ok": True, "settings": new_settings})
            return

        if self.path == "/test":
            # test-a-file: run the W1 matcher on a pasted filename (read-only)
            index, dest_set = _build_rules_index(root)
            entry = {"filename": payload.get("filename", ""),
                     "current_path": str(root / payload.get("filename", "")),
                     "is_image": False, "extension": ""}
            dest, reason = _auto_classify_entry(entry, root, index, dest_set)
            self._send(200, {"dest": dest, "reason": reason or "no deterministic match — would go to the classifier"})
            return

        if self.path == "/plan":
            agg = {e["entity"]: e for e in _aggregate_rules(root)}
            ent = agg.get(payload.get("entity"))
            if not ent:
                self._send(404, {"error": "unknown entity"}); return
            self._send(200, _promotion_plan(root, ent["entity"], ent["occurrences"],
                                            payload.get("target_parent", "")))
            return

        if self.path in ("/save", "/apply"):
            keepalive = (self.path == "/apply") or bool(payload.get("keepalive"))
            META_KEYS = ("entity_type", "locked", "aliases", "relation", "policy", "notes", "review", "date_range", "filename_tag", "min_token_len", "auto_approve")
            agg = {e["entity"]: e for e in _aggregate_rules(root)}
            results = {"meta": 0, "rule_edits": 0, "deletes": 0, "rethink": 0,
                       "renames": [], "merges": [], "areas": None}
            cur = _read_entities(root)
            # entity metadata -> entities.json (merge per-key; clear emptied keys)
            meta_in = payload.get("entities") or {}
            for name, m in meta_in.items():
                base = dict(cur.get(name, {}))
                for k in META_KEYS:
                    if k not in m:
                        continue
                    v = m[k]
                    if v in (None, "", [], {}):
                        base.pop(k, None)
                    else:
                        base[k] = v
                if base:
                    cur[name] = base
                elif name in cur:
                    del cur[name]
                results["meta"] += 1
            # rethink: flag an entity for re-inference (distinct from delete)
            for name in payload.get("rethink") or []:
                cur.setdefault(name, {})["review"] = True
                results["rethink"] += 1
            if meta_in or payload.get("rethink"):
                _write_entities(root, cur)
            # signal/description edits across occurrences (areas may need rule creation)
            for ed in payload.get("rule_edits") or []:
                ent = agg.get(ed.get("entity"))
                if ent:
                    is_area = ent.get("entity_type") == "area" or ent.get("synthetic_area")
                    results["rule_edits"] += _edit_rule_across_occurrences(
                        root, ent["entity"], ent["occurrences"],
                        new_description=ed.get("description"), create_if_missing=is_area)
            # delete a rule everywhere
            for name in payload.get("deletes") or []:
                ent = agg.get(name)
                if ent:
                    results["deletes"] += _edit_rule_across_occurrences(
                        root, ent["entity"], ent["occurrences"], delete=True)
            # rename an entity (rule + on-disk folder + registry)
            for rn in payload.get("renames") or []:
                ent = agg.get(rn.get("entity"))
                if ent and rn.get("new_name"):
                    results["renames"].append(_rename_entity(
                        root, ent["entity"], ent["occurrences"], rn["new_name"], apply=True))
            # merge an entity into another (fold as alias + delete its rules)
            for mg in payload.get("merges") or []:
                ent = agg.get(mg.get("src"))
                if ent and mg.get("dst"):
                    results["merges"].append(_merge_entities(root, ent, mg["dst"]))
            # area changes
            ac = payload.get("areas")
            if ac and (ac.get("add") or ac.get("rename") or ac.get("remove")):
                results["areas"] = _apply_area_changes(
                    root, ac.get("add"), ac.get("rename"), ac.get("remove"))

            resp = {"ok": True, "results": results}
            if keepalive:
                _reset_caches()
                index, dest_set = _build_rules_index(root)
                resp["data"] = {
                    "root": str(root), "areas": sorted(_active_groupings()),
                    "entities": _aggregate_rules(root), "conflicts": _conflicts_for(index),
                    "coverage_gaps": _coverage_gaps(root, dest_set),
                    "cluster_order": _CLUSTER_ORDER, "cluster_label": _CLUSTER_LABEL,
                    # Include settings so the JS (which does DATA=j.data; renderSettings())
                    # keeps the Settings-panel checkboxes populated after a keep-open apply —
                    # omitting it left DATA.settings undefined and unchecked every box.
                    "settings": _settings_for_viewer(root),
                }
            self._send(200, resp)
            if not keepalive and self.server is not None:
                # Flush the response to the client BEFORE signalling shutdown, so the
                # stop event can't race the client's read of the save confirmation.
                try:
                    self.wfile.flush()
                except (OSError, ValueError):
                    pass
                self.server._stop_event.set()
            return

        self._send(404, {"error": "not found"})


def cmd_inbox_list(args):
    """List every file currently sitting in _Inbox (organized there, awaiting a real home)
    as JSON: {count, arbiter_trigger, files:[{id, filename, current_path, file_date, is_image,
    is_raw}]}. Feeds the periodic arbiter sweep (SKILL.md: when count reaches the configured
    trigger, re-judge ALL of them against the now-larger rule set — files inboxed in earlier
    rounds may now be placeable). `arbiter_trigger` is the effective threshold — config.json's
    `inbox_arbiter_trigger` when valid, else 100 (see paths_config._effective_inbox_arbiter_trigger)
    — so the orchestrator reads the configured soft-guideline count dynamically instead of a
    hardcoded value in SKILL.md's prose."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, filename, current_path, file_date FROM files "
        "WHERE status='organized' AND (para_subfolder='_Inbox' OR para_subfolder LIKE '\\_Inbox/%' ESCAPE '\\') "
        "ORDER BY id"
    ).fetchall()
    conn.close()
    # is_image uses IMAGE_EXTS only (NOT IMAGE_EXTS | RAW_EXTS): the arbiter consumes this
    # field as a vision-readability gate (arbiter-prompt.md: "use it to apply the vision/peek
    # capability gates") and, unlike propose's entry dict, has no separate RAW block to fall
    # back on.  RAW is permanently un-vision-readable (file-type-routing.md "RAW-never-vision"
    # rule), so it must present is_image=False here or the arbiter would attempt vision on a
    # RAW file.  is_raw is a SEPARATE flag the arbiter uses for RAW-specific handling; the
    # server already applied the RAW vision-block before dispatch so the arbiter must NOT
    # re-apply it.
    out = {"count": len(rows),
           "arbiter_trigger": paths_config._effective_inbox_arbiter_trigger(),
           "files": [{"id": r["id"], "filename": r["filename"], "current_path": r["current_path"],
                      "file_date": r["file_date"],
                      "is_image": Path(r["filename"]).suffix.lower() in IMAGE_EXTS,
                      "is_raw": Path(r["filename"]).suffix.lower() in RAW_EXTS}
                     for r in rows]}
    print(json.dumps(out, indent=2))


def cmd_rules_viewer(args):
    """Launch the browser rules viewer/editor on the aggregated rule set."""
    root = Path(paths_config._EFFECTIVE_ROOT)
    port = int(getattr(args, "port", None) or 5003)
    _RulesHandler._root = root
    server = HTTPServer(("127.0.0.1", port), _RulesHandler)
    server.timeout = 1.0
    server._stop_event = threading.Event()
    t = threading.Thread(target=_serve_until, args=(server, server._stop_event), daemon=True)
    t.start()
    url = f"http://localhost:{port}/"
    n = len(_aggregate_rules(root))
    print(f"Rules viewer running at {url}")
    print(f"{n} entities across {len(_active_groupings())} areas. Submit in the browser to save + stop.")
    if not getattr(args, "no_open", False):
        webbrowser.open(url)
    try:
        server._stop_event.wait()
    except KeyboardInterrupt:
        print("\nInterrupted — shutting down.")
    finally:
        server.shutdown()


# ---------------------------------------------------------------------------
# W3 — Bootstrap rules-builder: reverse-engineer rules from a drive's existing
# organisation. Atomic-units are detected + approved + LOCKED first (never
# descended). Then every unruled folder with files is sampled and emitted for
# Claude's inference; the proposals are reviewed in the W2 viewer and written
# back. Two modes: cold-start (whole taxonomy) and audit (unruled + drift).
# ---------------------------------------------------------------------------
