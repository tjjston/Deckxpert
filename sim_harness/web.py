from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import cli
from . import runner

INDEX_HTML = """<!doctype html>
<html lang=\"en\"><head>
<meta charset=\"utf-8\"/><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>
<title>Deckxpert Simulation UI</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}header{padding:14px 18px;background:#111827;border-bottom:1px solid #334155}h1{margin:0;font-size:20px}
.wrap{display:grid;grid-template-columns:340px 1fr;min-height:calc(100vh - 52px)}aside{border-right:1px solid #334155;padding:14px}main{padding:14px}
.card{background:#111827;border:1px solid #334155;border-radius:10px;padding:12px;margin-bottom:12px}label{display:block;margin:8px 0 4px;font-size:12px;color:#94a3b8}
input,select,textarea,button{width:100%;box-sizing:border-box;margin-bottom:8px;border-radius:8px;border:1px solid #334155;background:#0b1220;color:#e2e8f0;padding:8px}
textarea{min-height:120px;font-family:ui-monospace,monospace}button{background:#1d4ed8;border-color:#1d4ed8;cursor:pointer}button:hover{background:#1e40af}
table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #334155;text-align:left;padding:6px;font-size:12px}.grid{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:12px}
.muted{color:#94a3b8;font-size:12px}pre{white-space:pre-wrap;word-break:break-word;background:#020617;border:1px solid #334155;border-radius:8px;padding:10px}
.ok{color:#22c55e}.bad{color:#ef4444}
.cardRef{cursor:pointer;color:#93c5fd;text-decoration:underline}
.boardCell{line-height:1.35}
.boardLine{display:block;margin-top:4px}
.eventLine{margin-bottom:6px}
#cardHover{display:none;position:fixed;z-index:9999;pointer-events:none;background:#020617;border:1px solid #334155;border-radius:10px;padding:8px;box-shadow:0 12px 30px rgba(0,0,0,.45)}
#cardHover img{height:min(46vh,520px);width:auto;display:block;border-radius:8px}
#cardHover .meta{margin-top:6px;font-size:12px;color:#cbd5e1;max-width:260px}
#cardModal{display:none;position:fixed;z-index:10000;inset:0;background:rgba(2,6,23,.88);align-items:center;justify-content:center}
#cardModal.open{display:flex}
#cardModal img{max-width:96vw;max-height:94vh;border-radius:12px;border:1px solid #334155;box-shadow:0 20px 40px rgba(0,0,0,.6)}
#cardModalClose{position:fixed;top:14px;right:16px;width:auto;padding:6px 10px;border-radius:8px;background:#111827;border:1px solid #334155;color:#e2e8f0;cursor:pointer}
</style></head><body>
<header><h1>Deckxpert Simulation Dashboard</h1></header>
<div class=\"wrap\"><aside>
<div class=\"card\"><h3>Add Deck</h3>
<label>Deck ID (optional)</label><input id=\"deckId\" placeholder=\"my-candidate-v1\"/>
<label>Pool</label><select id=\"pool\"><option>candidate</option><option>meta</option><option>starter</option></select>
<label>SWUDB JSON</label><textarea id=\"deckJson\" placeholder='{"metadata":{"name":"..."},...}'></textarea>
<button onclick=\"uploadDeck()\">Upload Deck</button><div id=\"uploadMsg\" class=\"muted\"></div></div>

<div class=\"card\"><h3>Create Simulation</h3>
<label>Candidate Deck</label><select id=\"candidate\"></select>
<label>Opponent Set</label><select id=\"opponents\"><option>all</option><option>meta</option><option>starter</option></select>
<label>Games per Opponent</label><input id=\"games\" type=\"number\" value=\"20\"/>
<label>Seed</label><input id=\"seed\" type=\"number\" value=\"42\"/>
<label>Workers</label><input id=\"workers\" type=\"number\" value=\"4\"/>
<label>PHP Script</label><input id=\"phpScript\" value=\"sim_harness/php_match_runner.php\"/>
<label>Simulation ID (optional)</label><input id=\"simId\" placeholder=\"sim-my-run\"/>
<button onclick=\"createSimulation()\">Run Simulation</button><div id=\"simMsg\" class=\"muted\"></div></div>

<div class=\"card\"><h3>Follow One Match (Turn-by-turn legality)</h3>
<label>Player A deck</label><select id=\"deckA\"></select>
<label>Player B deck</label><select id=\"deckB\"></select>
<label>Policy</label><select id=\"matchPolicy\"><option value=\"random_legal\">Random legal (uniform, recommended)</option><option value=\"random_non_pass\">Random legal (prefer non-pass)</option><option value=\"first_non_pass\">First non-pass (legacy)</option></select>
<label>Seed</label><input id=\"matchSeed\" type=\"number\" value=\"123\"/>
<button onclick=\"runSingleMatch()\">Run Match</button><div id=\"matchMsg\" class=\"muted\">Runs until game over (or safety cap).</div></div>

<div class=\"card\"><h3>Settings</h3><div id=\"settings\" class=\"muted\"></div></div>
</aside><main>
<div class=\"grid\">
<div class=\"card\"><h3>Decks</h3><table><thead><tr><th>ID</th><th>Pool</th><th>Name</th><th>Cards</th><th></th></tr></thead><tbody id=\"decksTbody\"></tbody></table></div>
<div class=\"card\"><h3>Simulations</h3><table><thead><tr><th>ID</th><th>Candidate</th><th>Winrate</th><th>Games</th><th></th></tr></thead><tbody id=\"simsTbody\"></tbody></table></div>
</div>
<div class=\"card\"><h3>Simulation Analysis</h3><pre id=\"analysis\">Select a simulation to inspect analysis.</pre></div>
<div class=\"card\"><h3>Deck JSON Viewer (SWUDB)</h3><pre id=\"deckView\">Select a deck to view SWUDB JSON.</pre></div>
<div class=\"card\"><h3 style=\"display:flex;justify-content:space-between;align-items:center;gap:8px;\">Single Match Timeline <button id=\"toggleMatchTimelineBtn\" style=\"width:auto;margin:0;padding:4px 10px;\" onclick=\"toggleMatchTimeline()\">Collapse</button></h3><div id=\"matchTimelineBody\"><pre id=\"matchSummary\">Run a single match to see turn-by-turn legality.</pre><div id=\"openingState\" class=\"muted\"></div><div class=\"muted\">Round page: <button onclick=\"prevRoundPage()\">Prev</button> <button onclick=\"nextRoundPage()\">Next</button> <span id=\"roundPageInfo\">-</span> <label style=\"display:inline;margin-left:8px;\"><input style=\"width:auto;\" id=\"showDecisionSteps\" type=\"checkbox\" onchange=\"renderRoundPage()\"/> Show decision prompts</label></div><table><thead><tr><th>Step</th><th>Round</th><th>Phase</th><th>Player</th><th>Kind</th><th>Action</th><th>Card</th><th>Legal?</th><th>Initiative</th><th>P1 Resources</th><th>P2 Resources</th><th>Board State</th></tr></thead><tbody id=\"matchTbody\"></tbody></table></div></div>
<div class=\"card\"><h3>Timeline By Round/Phase</h3><table><thead><tr><th>Round</th><th>Phase</th><th>Steps</th><th>Illegal</th><th>P1 Base HP</th><th>P2 Base HP</th><th>Actions</th></tr></thead><tbody id=\"timelineByPhaseTbody\"></tbody></table></div>
</main></div>
<div id=\"cardHover\"><img id=\"cardHoverImg\" alt=\"Card art\"/><div id=\"cardHoverMeta\" class=\"meta\"></div></div>
<div id=\"cardModal\" onclick=\"closeCardModal()\"><button id=\"cardModalClose\" onclick=\"closeCardModal();event.stopPropagation();\">Close</button><img id=\"cardModalImg\" alt=\"Card art\"/></div>
<script>
const DECISION_TYPES = new Set(['yesno','decision','choose_zone','choose_deck','opt_top','opt_bottom','multi_choose','dynamic_input','hand_top','hand_bottom']);
const TIMELINE_COLLAPSE_KEY = 'deckxpert_match_timeline_collapsed';
let currentMatchEvents = [];
let roundNumbers = [];
let currentRoundPage = 0;
let matchTimelineCollapsed = false;
const cardArtCache = new Map();

async function api(path, opts={}){
  const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});
  const t=await r.text();let d={};
  try{d=t?JSON.parse(t):{}}catch{d={raw:t}}
  if(!r.ok)throw new Error(d.error||t||r.statusText);
  return d;
}
async function refreshAll(){const s=await api('/api/state');renderDecks(s.decks);renderSims(s.simulations);renderCandidates(s.decks);renderMatchDecks(s.decks);document.getElementById('settings').textContent=JSON.stringify(s.settings,null,2);}
function setMatchTimelineCollapsed(collapsed){
  matchTimelineCollapsed=Boolean(collapsed);
  const body=document.getElementById('matchTimelineBody');
  const btn=document.getElementById('toggleMatchTimelineBtn');
  if(!body||!btn)return;
  body.style.display=matchTimelineCollapsed?'none':'block';
  btn.textContent=matchTimelineCollapsed?'Expand':'Collapse';
  try{localStorage.setItem(TIMELINE_COLLAPSE_KEY,matchTimelineCollapsed?'1':'0');}catch(_e){}
}
function toggleMatchTimeline(){setMatchTimelineCollapsed(!matchTimelineCollapsed);}
function initUiState(){
  let collapsed=false;
  try{collapsed=localStorage.getItem(TIMELINE_COLLAPSE_KEY)==='1';}catch(_e){}
  setMatchTimelineCollapsed(collapsed);
}
function fill(sel,decks,filter){sel.innerHTML='';decks.filter(filter).forEach(d=>{const o=document.createElement('option');o.value=d.deck_id;o.textContent=`${d.deck_id} :: ${d.name}`;sel.appendChild(o);});}
function renderCandidates(decks){fill(document.getElementById('candidate'),decks,d=>d.pool==='candidate');}
function renderMatchDecks(decks){fill(document.getElementById('deckA'),decks,_=>true);fill(document.getElementById('deckB'),decks,_=>true);}
function renderDecks(decks){const tb=document.getElementById('decksTbody');tb.innerHTML='';decks.forEach(d=>{const tr=document.createElement('tr');tr.innerHTML=`<td>${d.deck_id}</td><td>${d.pool}</td><td>${d.name}</td><td>${d.deck_size}</td><td><button onclick=\"showDeck('${d.deck_id}')\">View</button></td>`;tb.appendChild(tr);});}
function renderSims(sims){const tb=document.getElementById('simsTbody');tb.innerHTML='';sims.forEach(s=>{const tr=document.createElement('tr');const wr=((s.overall?.win_rate||0)*100).toFixed(2)+'%';tr.innerHTML=`<td>${s.sim_id}</td><td>${s.candidate_deck_id}</td><td>${wr}</td><td>${s.overall?.games||0}</td><td><button onclick=\"showSim('${s.sim_id}')\">Analyze</button></td>`;tb.appendChild(tr);});}
async function uploadDeck(){const msg=document.getElementById('uploadMsg');msg.textContent='Uploading...';try{await api('/api/decks',{method:'POST',body:JSON.stringify({deck_id:document.getElementById('deckId').value||null,pool:document.getElementById('pool').value,swudb:JSON.parse(document.getElementById('deckJson').value)})});msg.textContent='Uploaded';await refreshAll();}catch(e){msg.textContent='Error: '+e.message;}}
async function createSimulation(){const msg=document.getElementById('simMsg');msg.textContent='Running...';try{const out=await api('/api/simulations',{method:'POST',body:JSON.stringify({candidate:document.getElementById('candidate').value,opponents:document.getElementById('opponents').value,games:parseInt(document.getElementById('games').value||'20',10),seed:parseInt(document.getElementById('seed').value||'42',10),workers:parseInt(document.getElementById('workers').value||'4',10),php_script:document.getElementById('phpScript').value||null,sim_id:document.getElementById('simId').value||null})});msg.textContent='Created '+out.sim_id;await refreshAll();await showSim(out.sim_id);}catch(e){msg.textContent='Error: '+e.message;}}
async function showDeck(id){const d=await api('/api/decks/'+encodeURIComponent(id));document.getElementById('deckView').textContent=JSON.stringify(d.swudb,null,2);}
async function showSim(id){const d=await api('/api/simulations/'+encodeURIComponent(id)+'/analysis');document.getElementById('analysis').textContent=d.text;}

function isRenderableEvent(e){return !!e && typeof e==='object' && Number.isFinite(Number(e.step));}
function isDecisionEvent(e){const t=String(e?.action?.type||'');return Boolean(e?.is_decision) || DECISION_TYPES.has(t);}
function filteredEvents(events){return (events||[]).filter(isRenderableEvent);}
function normalizeCardId(v){return String(v||'').trim();}
function buildCardArtCandidates(cardId,rawId){
  const ids=[normalizeCardId(rawId),normalizeCardId(cardId)].filter(Boolean);
  const out=[];
  ids.forEach(id=>{
    // Prefer full-card portrait assets; keep square/cropped concat art as fallback.
    out.push(`/WebpImages2/${id}.webp`);
    out.push(`/WebpImages/${id}.webp`);
    out.push(`/RecentlyImplemented/${id}.webp`);
    out.push(`/UnimplementedCards/${id}.webp`);
    out.push(`/concat/${id}.webp`);
  });
  return [...new Set(out)];
}
function loadImage(url){
  return new Promise((resolve,reject)=>{
    const img=new Image();
    img.onload=()=>resolve(url);
    img.onerror=()=>reject(new Error('missing'));
    img.src=url;
  });
}
async function resolveCardArt(cardId,rawId){
  const key=`${normalizeCardId(rawId)}|${normalizeCardId(cardId)}`;
  if(cardArtCache.has(key)) return cardArtCache.get(key);
  const candidates=buildCardArtCandidates(cardId,rawId);
  for(const c of candidates){
    try{
      const ok=await loadImage(c);
      cardArtCache.set(key,ok);
      return ok;
    }catch(_e){}
  }
  cardArtCache.set(key,'');
  return '';
}
function moveCardHover(ev){
  const box=document.getElementById('cardHover');
  const x=Math.min(window.innerWidth-320, ev.clientX+18);
  const y=Math.min(window.innerHeight-540, ev.clientY+18);
  box.style.left=`${Math.max(8,x)}px`;
  box.style.top=`${Math.max(8,y)}px`;
}
async function showCardHover(ev,cardId,rawId,cost,type){
  const id=normalizeCardId(cardId);
  if(!id) return;
  const src=await resolveCardArt(id,rawId);
  if(!src) return;
  const box=document.getElementById('cardHover');
  document.getElementById('cardHoverImg').src=src;
  document.getElementById('cardHoverMeta').textContent=`${id}${rawId&&rawId!==id?` (${rawId})`:''} | c:${cost??''} t:${type??''}`;
  box.style.display='block';
  moveCardHover(ev);
}
function hideCardHover(){document.getElementById('cardHover').style.display='none';}
async function openCardModal(cardId,rawId,cost,type){
  const id=normalizeCardId(cardId);
  if(!id) return;
  const src=await resolveCardArt(id,rawId);
  if(!src) return;
  document.getElementById('cardModalImg').src=src;
  document.getElementById('cardModalImg').title=`${id}${rawId&&rawId!==id?` (${rawId})`:''} | c:${cost??''} t:${type??''}`;
  document.getElementById('cardModal').classList.add('open');
}
function closeCardModal(){document.getElementById('cardModal').classList.remove('open');}

function renderTimelineByPhase(events){
  const tb=document.getElementById('timelineByPhaseTbody');tb.innerHTML='';
  const grouped=new Map();
  filteredEvents(events).forEach(e=>{
    const k=`${e.round}::${e.phase}`;
    if(!grouped.has(k)){grouped.set(k,{round:e.round,phase:e.phase,steps:0,illegal:0,p1Start:null,p1End:null,p2Start:null,p2End:null,actions:{}});}
    const g=grouped.get(k);
    g.steps+=1;
    if(!e.apply_ok)g.illegal+=1;
    const p1b=e.phase_state_begin?.player_1?.base?.health;
    const p1e=e.phase_state_end?.player_1?.base?.health;
    const p2b=e.phase_state_begin?.player_2?.base?.health;
    const p2e=e.phase_state_end?.player_2?.base?.health;
    if(g.p1Start===null&&p1b!==undefined)g.p1Start=p1b;
    if(p1e!==undefined)g.p1End=p1e;
    if(g.p2Start===null&&p2b!==undefined)g.p2Start=p2b;
    if(p2e!==undefined)g.p2End=p2e;
    const at=e.action?.type||'unknown';
    g.actions[at]=(g.actions[at]||0)+1;
  });
  [...grouped.values()].sort((a,b)=>a.round===b.round?String(a.phase).localeCompare(String(b.phase)):a.round-b.round).forEach(g=>{
    const tr=document.createElement('tr');
    const actions=Object.entries(g.actions).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`${k}:${v}`).join(', ');
    tr.innerHTML=`<td>${g.round}</td><td>${g.phase}</td><td>${g.steps}</td><td>${g.illegal}</td><td>${g.p1Start ?? ''} -> ${g.p1End ?? ''}</td><td>${g.p2Start ?? ''} -> ${g.p2End ?? ''}</td><td>${actions}</td>`;
    tb.appendChild(tr);
  });
}

function renderRoundPage(){
  const tb=document.getElementById('matchTbody');
  const info=document.getElementById('roundPageInfo');
  tb.innerHTML='';
  if(roundNumbers.length===0){info.textContent='No round data';return;}
  if(currentRoundPage<0)currentRoundPage=0;
  if(currentRoundPage>=roundNumbers.length)currentRoundPage=roundNumbers.length-1;
  const showDecisions=document.getElementById('showDecisionSteps').checked;
  const round=roundNumbers[currentRoundPage];
  const rows=filteredEvents(currentMatchEvents).filter(e=>Number(e.round)===Number(round)).filter(e=>showDecisions || !isDecisionEvent(e));
  const fmtCards=(arr,limit=8)=>{
    const vals=(Array.isArray(arr)?arr:[]).map(v=>String(v)).filter(v=>v!=='');
    if(vals.length===0)return '-';
    if(vals.length<=limit)return vals.join(',');
    return vals.slice(0,limit).join(',')+`,+${vals.length-limit}`;
  };
  const fmtMod=(n)=>{
    const v=Number(n||0);
    if(!Number.isFinite(v)||v===0)return '';
    return v>0?`+${v}`:`${v}`;
  };
  const fmtUnit=(u)=>{
    const id=String(u?.id||u?.raw_id||'unit');
    const stance=u?.ready?'R':'X';
    const pNow=Number(u?.current_power??0);
    const hNow=Number(u?.current_hp??0);
    const hMax=Number(u?.max_hp??0);
    const pMod=fmtMod(u?.power_modifier);
    const hMod=fmtMod(u?.hp_modifier);
    const upg=fmtCards(u?.upgrades||[],3);
    const dmg=Number(u?.damage_taken??0);
    return `${id}(${stance}) pwr:${pNow}${pMod?`(${pMod})`:''} hp:${hNow}/${hMax}${hMod?`(${hMod})`:''}${dmg>0?` dmg:${dmg}`:''}${upg!=='-'?` upg:[${upg}]`:''}`;
  };
  const fmtUnitList=(arr,limit=3)=>{
    const units=Array.isArray(arr)?arr:[];
    if(units.length===0)return '-';
    const shown=units.slice(0,limit).map(fmtUnit);
    if(units.length>limit) shown.push(`+${units.length-limit} more`);
    return shown.join(' ; ');
  };
  const fmtActionDetails=(d)=>{
    if(!d||typeof d!=='object') return '';
    const bits=[];
    const follow=d.follow_up_prompt;
    if(follow && typeof follow==='object'){
      const t=String(follow.text||'').trim();
      const p=Number(follow.player||0);
      const ph=String(follow.phase||'');
      bits.push(`Prompt: P${p||'?'} ${ph}${t?` - ${t}`:''}`);
    }
    const wdChecks=(Array.isArray(d.when_defeated_checks)?d.when_defeated_checks:[]).slice(0,3).map(x=>{
      const has=Boolean(x.has_when_defeated);
      const likely=Boolean(x.likely_triggered);
      const unit=String(x.unit_id||x.unit_raw_id||'unit');
      const p=Number(x.player||0);
      const status=!has?'no when-defeated text':(likely?'likely prompted':'no prompt seen');
      return `P${p} ${unit}: ${status}`;
    });
    if(wdChecks.length) bits.push(`When Defeated: ${wdChecks.join(' ; ')}`);
    const stateChanges=(Array.isArray(d.player_state_changes)?d.player_state_changes:[]).map(x=>{
      const parts=[];
      const add=(label,val)=>{
        const n=Number(val||0);
        if(!Number.isFinite(n) || n===0) return;
        parts.push(`${label}${n>0?`+${n}`:`${n}`}`);
      };
      add('hp ',x.base_hp_delta);
      add('hand ',x.hand_delta);
      add('deck ',x.deck_delta);
      add('discard ',x.discard_delta);
      add('resAvail ',x.resources_available_delta);
      add('resSpent ',x.resources_spent_delta);
      add('resTotal ',x.resource_cards_total_delta);
      add('resReady ',x.resource_cards_ready_delta);
      add('resExh ',x.resource_cards_exhausted_delta);
      add('active ',x.active_units_delta);
      add('ready ',x.ready_units_delta);
      add('exhausted ',x.exhausted_units_delta);
      const forceBefore=Boolean(x.force_before);
      const forceAfter=Boolean(x.force_after);
      if(forceBefore!==forceAfter){
        parts.push(`force ${forceBefore?'on':'off'}->${forceAfter?'on':'off'}`);
      }
      if(parts.length===0) return '';
      return `P${x.player}: ${parts.join(', ')}`;
    }).filter(Boolean);
    if(stateChanges.length) bits.push(`State: ${stateChanges.join(' ; ')}`);
    const base=(Array.isArray(d.base_damage)?d.base_damage:[]).map(x=>`P${x.player} base -${x.amount} (${x.before_hp}->${x.after_hp})`);
    if(base.length) bits.push(`Base: ${base.join(' ; ')}`);
    const unitDmg=(Array.isArray(d.unit_damage)?d.unit_damage:[]).slice(0,3).map(x=>`P${x.player} ${x.unit_id} -${x.damage} (${x.before_hp}->${x.after_hp})`);
    if(unitDmg.length) bits.push(`Unit dmg: ${unitDmg.join(' ; ')}`);
    const defeated=(Array.isArray(d.unit_defeated)?d.unit_defeated:[]).slice(0,3).map(x=>`P${x.player} ${x.unit_id}`);
    if(defeated.length) bits.push(`Defeated: ${defeated.join(', ')}`);
    const deployed=(Array.isArray(d.unit_deployed)?d.unit_deployed:[]).slice(0,3).map(x=>`P${x.player} ${x.unit_id} [${x.current_power}/${x.current_hp}]`);
    if(deployed.length) bits.push(`Deployed: ${deployed.join(' ; ')}`);
    const upg=(Array.isArray(d.unit_upgrade_changes)?d.unit_upgrade_changes:[]).slice(0,3).map(x=>`P${x.player} ${x.unit_id} [${fmtCards(x.before||[],2)} -> ${fmtCards(x.after||[],2)}]`);
    if(upg.length) bits.push(`Upgrades: ${upg.join(' ; ')}`);
    const stat=(Array.isArray(d.unit_stat_changes)?d.unit_stat_changes:[]).slice(0,3).map(x=>`P${x.player} ${x.unit_id} pwr ${x.power?.before}->${x.power?.after}, hp ${x.max_hp?.before}->${x.max_hp?.after}`);
    if(stat.length) bits.push(`Stats: ${stat.join(' ; ')}`);
    return bits.join(' | ');
  };
  const fmtRes=(pb,pe)=>{
    const rb=pb?.resources||{};
    const re=pe?.resources||{};
    const beforeAvail = rb.available ?? '';
    const afterAvail = re.available ?? '';
    const beforeSpent = rb.spent ?? '';
    const afterSpent = re.spent ?? '';
    const beforeReady = rb.ready_cards ?? rb.spendable ?? '';
    const afterReady = re.ready_cards ?? re.spendable ?? '';
    const total = re.total_cards ?? rb.total_cards ?? '';
    const exhausted = re.exhausted_cards ?? '';
    return `avail:${beforeAvail}->${afterAvail}, spent:${beforeSpent}->${afterSpent}, ready:${beforeReady}->${afterReady}, total:${total}, exhausted:${exhausted}`;
  };
  const fmtBoard=(label,phasePlayer,boardPlayer)=>{
    const c=phasePlayer?.counts||{};
    const z=phasePlayer?.zones||{};
    const u=phasePlayer?.units||{};
    const bu=boardPlayer?.units||{};
    const unitDetails=Array.isArray(bu.details)?bu.details:[];
    const hp=boardPlayer?.base_hp ?? phasePlayer?.base?.health ?? '';
    const handCount=boardPlayer?.hand_count ?? c.hand ?? '';
    const handCards=fmtCards(boardPlayer?.hand_cards ?? z.hand,6);
    const active=bu.active_count ?? u.active_count ?? c.active_units ?? '';
    const deckCount=boardPlayer?.deck_count ?? c.deck ?? '';
    const discardCount=boardPlayer?.discard_count ?? c.discard ?? '';
    const forceStatus=boardPlayer?.force?.status || (phasePlayer?.force?.status || 'unavailable');
    const forceTimes=boardPlayer?.force?.times_used_this_phase ?? (phasePlayer?.force?.times_used_this_phase ?? 0);
    const readyUnits=unitDetails.filter(x=>Boolean(x?.ready));
    const exhaustedUnits=unitDetails.filter(x=>Boolean(x?.exhausted));
    return `<span class="boardLine"><strong>${label}</strong> hp:${hp}, force:${forceStatus} (used:${forceTimes}), hand:${handCount}[${handCards}], deck:${deckCount}, discard:${discardCount}, active:${active}, ready:${readyUnits.length}, exhausted:${exhaustedUnits.length}</span><span class="boardLine">units: ${fmtUnitList(unitDetails,3)}</span>`;
  };
  rows.forEach(e=>{
    const tr=document.createElement('tr');
    const ok=e.apply_ok?'<span class="ok">ok</span>':'<span class="bad">illegal</span>';
    const p1b=e.phase_state_begin?.player_1||{};
    const p1=e.phase_state_end?.player_1||{};
    const p2b=e.phase_state_begin?.player_2||{};
    const p2=e.phase_state_end?.player_2||{};
    const p1Board=e.board_state_end?.player_1||{};
    const p2Board=e.board_state_end?.player_2||{};
    const actionType=e.action?.type||'';
    const actionButton=e.action?.buttonInput||'';
    const actionCardRef=(e.action?.cardID ?? '');
    const actionNeedsChoiceLabel=new Set(['yesno','choose_zone','decision','opt_top','opt_bottom','multi_choose','dynamic_input','hand_top','hand_bottom']);
    const actionChoice=(actionButton!=='')
      ? String(actionButton)
      : (actionType==='choose_zone' && actionCardRef!=='' && actionCardRef!==0 ? String(actionCardRef) : '');
    const actionLabel=(actionNeedsChoiceLabel.has(actionType) && actionChoice!=='')?`${actionType}:${actionChoice}`:actionType;
    const kindLabel=isDecisionEvent(e)?'prompt':'gameplay';
    const taken=Number(e.initiative_taken)===1;
    const initiativeLabel=`p${e.initiative_player || '-'}${taken?' (taken)':' (open)'}`;
    const cardId=e.card?.id||'';
    const rawId=e.card?.raw_id||'';
    const cost=e.card?.cost??'';
    const type=e.card?.type||'';
    const cardJson=JSON.stringify(cardId);
    const rawJson=JSON.stringify(rawId);
    const costJson=JSON.stringify(cost);
    const typeJson=JSON.stringify(type);
    const cardCell=cardId
      ? `<span class="cardRef" onmouseenter='showCardHover(event,${cardJson},${rawJson},${costJson},${typeJson})' onmousemove='moveCardHover(event)' onmouseleave='hideCardHover()' onclick='openCardModal(${cardJson},${rawJson},${costJson},${typeJson})'>${cardId}</span> (c:${cost}, t:${type})`
      : `(c:, t:)`;
    const actionDetail=fmtActionDetails(e.action_details);
    tr.innerHTML=`<td>${e.step}</td><td>${e.round}</td><td>${e.phase}</td><td>${e.player}</td><td>${kindLabel}</td><td>${actionLabel}</td><td>${cardCell}</td><td>${ok}</td><td>${initiativeLabel}</td><td>${fmtRes(p1b,p1)}</td><td>${fmtRes(p2b,p2)}</td><td class="boardCell">${actionDetail?`<div class="eventLine muted">${actionDetail}</div>`:''}<div>${fmtBoard('P1',p1,p1Board)}</div><div>${fmtBoard('P2',p2,p2Board)}</div></td>`;
    tb.appendChild(tr);
  });
  info.textContent=`Round ${round} (${currentRoundPage+1}/${roundNumbers.length}) - showing ${rows.length} steps`;
}

function prevRoundPage(){if(roundNumbers.length===0)return;currentRoundPage=Math.max(0,currentRoundPage-1);renderRoundPage();}
function nextRoundPage(){if(roundNumbers.length===0)return;currentRoundPage=Math.min(roundNumbers.length-1,currentRoundPage+1);renderRoundPage();}

async function runSingleMatch(){
  const msg=document.getElementById('matchMsg');
  const opening=document.getElementById('openingState');
  msg.textContent='Running match...';
  opening.textContent='';
  try{
    const d=await api('/api/match/run',{method:'POST',body:JSON.stringify({deck_a_id:document.getElementById('deckA').value,deck_b_id:document.getElementById('deckB').value,policy:document.getElementById('matchPolicy').value,seed:parseInt(document.getElementById('matchSeed').value||'123',10)})});
    msg.textContent='Done';
    document.getElementById('matchSummary').textContent=JSON.stringify(d.summary,null,2);
    document.getElementById('showDecisionSteps').checked=false;
    const o=d.summary?.opening||{};
    const p1=o.player_1||{};
    const p2=o.player_2||{};
    opening.textContent=`Opening snapshot: P1 hand=${p1.hand_count ?? '?'} deck=${p1.deck_count ?? '?'} resources=${p1.resource_cards ?? '?'} | P2 hand=${p2.hand_count ?? '?'} deck=${p2.deck_count ?? '?'} resources=${p2.resource_cards ?? '?'}`;
    currentMatchEvents=filteredEvents(d.events||[]);
    roundNumbers=[...new Set(currentMatchEvents.map(e=>Number(e.round)).filter(n=>Number.isFinite(n)&&n>0))].sort((a,b)=>a-b);
    currentRoundPage=0;
    renderRoundPage();
    renderTimelineByPhase(currentMatchEvents);
  }catch(e){
    msg.textContent='Error: '+e.message;
  }
}

initUiState();
refreshAll();
</script></body></html>
"""


def _deck_to_json(deck: cli.DeckRecord) -> dict[str, Any]:
    return {
        "deck_id": deck.deck_id,
        "pool": deck.pool,
        "name": deck.name,
        "author": deck.author,
        "added_at": deck.added_at,
        "deck_size": sum(int(c.get("count", 0)) for c in deck.swudb.get("deck", [])),
    }


def _simulation_analysis_text(sim: dict[str, Any]) -> str:
    rows = sim.get("opponents", [])
    lines = [
        f"Simulation: {sim['sim_id']}",
        f"Candidate: {sim['candidate_deck_id']} :: {sim['candidate_name']}",
        f"Overall win rate: {sim['overall']['win_rate']:.2%} ({sim['overall']['wins']}/{sim['overall']['games']})",
        "",
        "By tier:",
    ]
    tier_summary: dict[str, dict[str, float]] = {}
    for r in rows:
        tier = r["pool"]
        tier_summary.setdefault(tier, {"wins": 0.0, "games": 0.0})
        tier_summary[tier]["wins"] += float(r["wins"])
        tier_summary[tier]["games"] += float(r["games"])
    for tier, totals in sorted(tier_summary.items()):
        wr = (totals["wins"] / totals["games"]) if totals["games"] else 0.0
        lines.append(f"- {tier}: {wr:.2%} ({int(totals['wins'])}/{int(totals['games'])})")
    return "\n".join(lines)


def _deck_to_runner_string(swudb: dict[str, Any]) -> str:
    material, main = cli._cards_to_expanded_ids(swudb)
    return " ".join(material) + "\n" + " ".join(main)


def _run_single_match(
    deck_a: cli.DeckRecord,
    deck_b: cli.DeckRecord,
    seed: int,
    max_actions: int | None,
    policy: str,
) -> dict[str, Any]:
    php_bin = runner.resolve_php_bin()
    if not php_bin:
        raise RuntimeError(
            "PHP executable not found. Install php-cli or set PHP_BIN to your php binary path."
        )
    deck_a_b64 = base64.b64encode(_deck_to_runner_string(deck_a.swudb).encode("utf-8")).decode("ascii")
    deck_b_b64 = base64.b64encode(_deck_to_runner_string(deck_b.swudb).encode("utf-8")).decode("ascii")
    cmd = [
        php_bin,
        "sim_harness/php_match_runner.php",
        "--seed",
        str(seed),
        "--deck-a-b64",
        deck_a_b64,
        "--deck-b-b64",
        deck_b_b64,
        "--match-id",
        str(uuid.uuid4().int % 1_000_000),
        "--policy",
        policy,
    ]
    if max_actions is not None and int(max_actions) > 0:
        cmd.extend(["--max-actions", str(int(max_actions))])
    env = dict(os.environ)
    env["XDEBUG_MODE"] = "off"
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        concise = _extract_runner_error(stdout, stderr)
        raise RuntimeError(
            "PHP match runner failed "
            f"(exit={proc.returncode}). {concise}"
        )
    return _decode_match_json(stdout, stderr)


def _decode_match_json(stdout: str, stderr: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        raise ValueError(
            "PHP match runner returned empty stdout. "
            f"stderr={stderr[:500] or '<empty>'}"
        )
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    raise ValueError(
        "PHP match runner did not return valid JSON. "
        f"stdout={text[:500]} stderr={stderr[:500] or '<empty>'}"
    )


def _extract_runner_error(stdout: str, stderr: str) -> str:
    for text in (stdout, stderr):
        if not text:
            continue
        try:
            payload = _decode_match_json(text, "")
            if isinstance(payload, dict):
                err = str(payload.get("error", "")).strip()
                msg = str(payload.get("message", "")).strip()
                file = str(payload.get("file", "")).strip()
                line = payload.get("line", "")
                checkpoint = str(payload.get("checkpoint", "")).strip()
                parts: list[str] = []
                if err and msg:
                    parts.append(f"{err}: {msg}")
                elif msg:
                    parts.append(msg)
                elif err:
                    parts.append(err)
                if file:
                    loc = f"{file}:{line}" if str(line).strip() else file
                    parts.append(f"at {loc}")
                if checkpoint:
                    parts.append(f"checkpoint={checkpoint}")
                if parts:
                    return " ".join(parts)
        except Exception:
            pass
    return (
        f"stderr={stderr[:500] or '<empty>'} "
        f"stdout={stdout[:500] or '<empty>'}"
    )


class SimWebHandler(BaseHTTPRequestHandler):
    server_version = "DeckxpertSimUI/2.0"

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        mime, _ = mimetypes.guess_type(str(path))
        if mime is None:
            mime = "application/octet-stream"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static_asset(self, path: str) -> bool:
        rel = Path(path.lstrip("/"))
        if not rel.parts:
            return False
        if ".." in rel.parts:
            return False
        allowed_roots = {"concat", "RecentlyImplemented", "UnimplementedCards", "WebpImages", "WebpImages2", "Images", "crops"}
        if rel.parts[0] not in allowed_roots:
            return False
        file_path = (Path.cwd() / rel).resolve()
        root_path = (Path.cwd() / rel.parts[0]).resolve()
        if root_path not in file_path.parents and file_path != root_path:
            return False
        if not file_path.is_file():
            return False
        self._send_file(file_path)
        return True

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(data.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if self._serve_static_asset(path):
                return
            if path == "/":
                self._send_html(INDEX_HTML)
                return
            if path == "/api/state":
                decks = cli._load_decks()
                sims = cli._load_sims()
                php_bin = runner.resolve_php_bin()
                self._send_json({
                    "decks": [_deck_to_json(d) for d in decks],
                    "simulations": sims,
                    "settings": {
                        "data_dir": str(cli.DATA_DIR),
                        "decks_file": str(cli.DECKS_FILE),
                        "sims_file": str(cli.SIMS_FILE),
                        "cwd": str(Path.cwd()),
                        "php_bin": php_bin,
                        "php_available": bool(php_bin),
                        "php_bin_env": os.environ.get("PHP_BIN", ""),
                    },
                })
                return
            if path.startswith("/api/decks/"):
                deck_id = path.rsplit("/", 1)[-1]
                deck = cli._find_deck(cli._load_decks(), deck_id)
                self._send_json({"deck_id": deck.deck_id, "pool": deck.pool, "swudb": deck.swudb})
                return
            if path.startswith("/api/simulations/") and path.endswith("/analysis"):
                sim_id = path.split("/")[3]
                sim = cli._find_sim(sim_id)
                self._send_json({"sim_id": sim_id, "text": _simulation_analysis_text(sim), "raw": sim})
                return
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if path == "/api/decks":
                payload = self._read_json()
                swudb = payload.get("swudb")
                if not isinstance(swudb, dict):
                    raise ValueError("swudb must be a JSON object")
                cli._validate_swudb_deck(swudb)
                decks = cli._load_decks()
                deck_id = payload.get("deck_id") or uuid.uuid4().hex[:12]
                if any(d.deck_id == deck_id for d in decks):
                    raise ValueError(f"Deck id already exists: {deck_id}")
                pool = str(payload.get("pool") or "candidate")
                if pool not in {"candidate", "meta", "starter"}:
                    raise ValueError("pool must be candidate/meta/starter")
                deck = cli.DeckRecord(deck_id=deck_id, pool=pool, swudb=swudb, added_at=cli._now_iso())
                decks.append(deck)
                cli._save_decks(decks)
                self._send_json({"ok": True, "deck_id": deck.deck_id, "name": deck.name})
                return

            if path == "/api/simulations":
                payload = self._read_json()
                args = type("Args", (), {
                    "candidate": payload.get("candidate"),
                    "opponents": payload.get("opponents", "all"),
                    "games": int(payload.get("games", 20)),
                    "seed": int(payload.get("seed", 42)),
                    "workers": int(payload.get("workers", 4)),
                    "php_script": payload.get("php_script"),
                    "sim_id": payload.get("sim_id"),
                })()
                cli.cmd_sim_create(args)
                sim_id = args.sim_id or cli._load_sims()[-1]["sim_id"]
                self._send_json({"ok": True, "sim_id": sim_id})
                return

            if path == "/api/match/run":
                payload = self._read_json()
                decks = cli._load_decks()
                deck_a = cli._find_deck(decks, str(payload.get("deck_a_id", "")))
                deck_b = cli._find_deck(decks, str(payload.get("deck_b_id", "")))
                seed = int(payload.get("seed", 123))
                max_actions_raw = payload.get("max_actions", None)
                max_actions = None
                if max_actions_raw is not None:
                    parsed = int(max_actions_raw)
                    if parsed > 0:
                        max_actions = parsed
                policy = str(payload.get("policy", "random_legal"))
                if policy not in {"random_non_pass", "random_legal", "first_non_pass"}:
                    raise ValueError("policy must be random_non_pass/random_legal/first_non_pass")
                match = _run_single_match(deck_a, deck_b, seed, max_actions, policy)
                self._send_json({
                    "ok": True,
                    "summary": {
                        "match_id": match.get("match_id"),
                        "seed": match.get("seed"),
                        "winner": match.get("winner"),
                        "turns": match.get("turns"),
                        "deck_a_id": deck_a.deck_id,
                        "deck_a_name": deck_a.name,
                        "deck_b_id": deck_b.deck_id,
                        "deck_b_name": deck_b.name,
                        "policy": match.get("stats", {}).get("policy"),
                        "events": match.get("stats", {}).get("events", 0),
                        "illegal_actions": match.get("stats", {}).get("illegal_actions", 0),
                        "forced_passes": match.get("stats", {}).get("forced_passes", 0),
                        "action_cap": match.get("stats", {}).get("action_cap"),
                        "terminated_reason": match.get("stats", {}).get("terminated_reason", ""),
                        "game_over": match.get("stats", {}).get("game_over", False),
                        "setup": match.get("setup", {}),
                        "opening": match.get("opening", {}),
                        "final_state": match.get("final_state", {}),
                    },
                    "events": match.get("events", []),
                    "round_pages": match.get("round_pages", []),
                })
                return

            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), SimWebHandler)
    print(f"Deckxpert Simulation UI running on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Deckxpert simulation web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.host, args.port)
