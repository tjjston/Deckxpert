from __future__ import annotations

import base64
import json
import mimetypes
import os
import shlex
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
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
.page{padding:14px}
.card{background:#111827;border:1px solid #334155;border-radius:10px;padding:12px;margin-bottom:12px;overflow:auto}label{display:block;margin:8px 0 4px;font-size:12px;color:#94a3b8}
input,select,textarea,button{width:100%;box-sizing:border-box;margin-bottom:8px;border-radius:8px;border:1px solid #334155;background:#0b1220;color:#e2e8f0;padding:8px}
textarea{min-height:120px;font-family:ui-monospace,monospace}button{background:#1d4ed8;border-color:#1d4ed8;cursor:pointer}button:hover{background:#1e40af}
table{width:max-content;min-width:100%;border-collapse:collapse;table-layout:auto}th,td{border-bottom:1px solid #334155;text-align:left;padding:6px;font-size:12px;vertical-align:top;white-space:nowrap;overflow-wrap:normal;word-break:normal}.grid{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:12px}
.topTiles{display:grid;grid-template-columns:repeat(4,minmax(260px,1fr));gap:12px;align-items:start;margin-bottom:12px}
.mlGrid{display:grid;grid-template-columns:repeat(3,minmax(260px,1fr));gap:12px}
.singleMatchGrid{display:grid;grid-template-columns:minmax(0,2fr) minmax(360px,1fr);gap:12px;align-items:start}
@media (max-width:1400px){.topTiles{grid-template-columns:repeat(2,minmax(260px,1fr))}}
@media (max-width:1200px){.singleMatchGrid{grid-template-columns:1fr}.topTiles{grid-template-columns:1fr}.mlGrid{grid-template-columns:1fr}}
.muted{color:#94a3b8;font-size:12px}pre{white-space:pre;overflow:auto;background:#020617;border:1px solid #334155;border-radius:8px;padding:10px}
.ok{color:#22c55e}.bad{color:#ef4444}
.cardRef{cursor:pointer;color:#93c5fd;text-decoration:underline}
.boardCell{line-height:1.35}
.boardLine{display:block;margin-top:4px}
.moreUnitsHint{cursor:help;text-decoration:underline dotted;color:#93c5fd}
.eventLine{margin-bottom:6px}
#matchTbody td:nth-child(12){min-width:480px}
#validationMatrixTbody td:nth-child(5),#keywordAuditTbody td:nth-child(9){min-width:280px}
.instanceDrop{margin-top:6px}
.instanceDrop summary{cursor:pointer;color:#93c5fd}
.instanceList{margin-top:6px;max-height:220px;overflow:auto;font-size:11px;line-height:1.35}
.instanceLine{padding:2px 0;border-bottom:1px dashed #334155;white-space:nowrap}
.attackTargetAction{display:inline-flex;align-items:center;gap:6px;padding:1px 8px;border-radius:999px;border:1px solid #f59e0b;background:#7c2d12;color:#ffedd5;font-weight:700;letter-spacing:.01em}
.attackTargetAction .attackTargetTag{font-size:10px;text-transform:uppercase;color:#fde68a}
.attackTargetAction .attackTargetValue{font-size:12px;color:#ffffff}
.logBox{min-height:220px;max-height:420px}
#cardHover{display:none;position:fixed;z-index:9999;pointer-events:none;background:#020617;border:1px solid #334155;border-radius:10px;padding:8px;box-shadow:0 12px 30px rgba(0,0,0,.45)}
#cardHover img{height:min(46vh,520px);width:auto;display:block;border-radius:8px}
#cardHover .meta{margin-top:6px;font-size:12px;color:#cbd5e1;max-width:260px}
#cardModal{display:none;position:fixed;z-index:10000;inset:0;background:rgba(2,6,23,.88);align-items:center;justify-content:center}
#cardModal.open{display:flex}
#cardModal img{max-width:96vw;max-height:94vh;border-radius:12px;border:1px solid #334155;box-shadow:0 20px 40px rgba(0,0,0,.6)}
#cardModalClose{position:fixed;top:14px;right:16px;width:auto;padding:6px 10px;border-radius:8px;background:#111827;border:1px solid #334155;color:#e2e8f0;cursor:pointer}
</style></head><body>
<header><h1>Deckxpert Simulation Dashboard</h1></header>
<div class=\"page\">
<div class=\"topTiles\">
<div class=\"card\"><h3>Add Deck</h3>
<label>Deck ID (optional)</label><input id=\"deckId\" placeholder=\"my-candidate-v1\"/>
<label>Pool</label><select id=\"pool\"><option>candidate</option><option>meta</option><option>starter</option></select>
<label>SWUDB JSON</label><textarea id=\"deckJson\" placeholder='{"metadata":{"name":"..."},...}'></textarea>
<button id=\"uploadDeckBtn\" onclick=\"uploadDeck()\">Upload Deck</button>
<button id=\"saveDeckEditBtn\" style=\"display:none;background:#0f766e;border-color:#0f766e\" onclick=\"saveDeckEdit()\">Save Deck Edit</button>
<button id=\"cancelDeckEditBtn\" style=\"display:none;background:#475569;border-color:#475569\" onclick=\"cancelDeckEdit()\">Cancel Edit</button>
<div id=\"uploadMsg\" class=\"muted\"></div></div>

<div class=\"card\"><h3>Follow One Match (Turn-by-turn legality)</h3>
<label>Player A deck</label><select id=\"deckA\"></select>
<label>Player B deck</label><select id=\"deckB\"></select>
<label>Deck Minimum</label><select id=\"matchMinCards\"><option value=\"50\" selected>50 cards</option><option value=\"30\">30 cards</option></select>
<label>Policy</label><select id=\"matchPolicy\"><option value=\"random_legal\">Random legal (uniform, recommended)</option><option value=\"random_non_pass\">Random legal (prefer non-pass)</option><option value=\"first_non_pass\">First non-pass (legacy)</option><option value=\"heuristic\">Heuristic (rule-based)</option><option value=\"mcts\">MCTS starter</option></select>
<label>MCTS Iterations</label><input id=\"matchMctsIterations\" type=\"number\" value=\"16\"/>
<label>MCTS Rollout Depth</label><input id=\"matchMctsDepth\" type=\"number\" value=\"14\"/>
<label>Seed</label><input id=\"matchSeed\" type=\"number\" value=\"123\"/>
<button onclick=\"runSingleMatch()\">Run Match</button><div id=\"matchMsg\" class=\"muted\">Runs until game over (or safety cap).</div></div>

<div class=\"card\"><h3>Create Simulation</h3>
<label>Candidate Deck</label><select id=\"candidate\"></select>
<label>Opponent Set</label><select id=\"opponents\"><option>all</option><option>meta</option><option>starter</option></select>
<label>Deck Minimum</label><select id=\"simMinCards\"><option value=\"50\" selected>50 cards</option><option value=\"30\">30 cards</option></select>
<label>Policy</label><select id=\"simPolicy\"><option value=\"random_legal\">Random legal (uniform)</option><option value=\"random_non_pass\">Random legal (prefer non-pass)</option><option value=\"first_non_pass\">First non-pass (legacy)</option><option value=\"heuristic\">Heuristic (rule-based)</option><option value=\"mcts\">MCTS starter</option></select>
<label>MCTS Iterations</label><input id=\"simMctsIterations\" type=\"number\" value=\"16\"/>
<label>MCTS Rollout Depth</label><input id=\"simMctsDepth\" type=\"number\" value=\"14\"/>
<label>Games per Opponent</label><input id=\"games\" type=\"number\" value=\"20\"/>
<label>Seed</label><input id=\"seed\" type=\"number\" value=\"42\"/>
<label>Workers</label><input id=\"workers\" type=\"number\" value=\"4\"/>
<label>PHP Script</label><input id=\"phpScript\" value=\"sim_harness/php_match_runner.php\"/>
<label>Simulation ID (optional)</label><input id=\"simId\" placeholder=\"sim-my-run\"/>
<button onclick=\"createSimulation()\">Run Simulation</button><div id=\"simMsg\" class=\"muted\"></div></div>

<div class=\"card\"><h3>How To Use (Best Results)</h3>
<div class=\"muted\">
1) Upload decks into pools: your test deck in <code>candidate</code>, benchmarks in <code>meta</code>/<code>starter</code>.<br/>
2) Run <strong>Follow One Match</strong> with <code>heuristic</code> or <code>mcts</code> to confirm engine behavior and legality.<br/>
3) Run <strong>Create Simulation</strong> (or ML Lab <code>sim_shootout</code>) to benchmark random vs heuristic vs mcts on the same seed set.<br/>
4) In <strong>ML Lab</strong>, run <code>rl_collect</code> with policies like <code>heuristic,mcts</code> to build training data.<br/>
5) Run <code>rl_train</code> with <code>device=cuda</code> and GPUs <code>0,1</code> (or a single GPU) to train policy/value checkpoints.<br/>
6) Re-run shootouts and sims to validate win-rate lift and illegal-move stability before using models in deck scoring.<br/>
Backup tip: copy <code>sim_harness/data/decks.json</code> before major runs.
</div>
<pre id=\"howToRuntime\" class=\"muted\">Runtime info loading...</pre>
</div>
</div>
<div class=\"card\"><h3>ML Lab (Async Sims + Training)</h3>
<div id=\"mlInfo\" class=\"muted\">Loading runtime info...</div>
<div class=\"mlGrid\">
<div class=\"card\"><h3>Simulation Job</h3>
<label>Candidate Deck</label><select id=\"mlSimCandidate\"></select>
<label>Mode</label><select id=\"mlSimKind\"><option value=\"sim_create\">sim create</option><option value=\"sim_shootout\">sim shootout</option></select>
<label>Opponents</label><select id=\"mlSimOpponents\"><option>all</option><option>meta</option><option>starter</option></select>
<label>Deck Minimum</label><select id=\"mlSimMinCards\"><option value=\"50\" selected>50 cards</option><option value=\"30\">30 cards</option></select>
<label>Policy (sim create)</label><select id=\"mlSimPolicy\"><option value=\"random_legal\">random_legal</option><option value=\"random_non_pass\">random_non_pass</option><option value=\"first_non_pass\">first_non_pass</option><option value=\"heuristic\">heuristic</option><option value=\"mcts\">mcts</option></select>
<label>Policies (sim shootout, csv)</label><input id=\"mlSimPolicies\" value=\"random_legal,heuristic,mcts\"/>
<label>MCTS Iterations</label><input id=\"mlSimMctsIterations\" type=\"number\" value=\"24\"/>
<label>MCTS Max Depth</label><input id=\"mlSimMctsDepth\" type=\"number\" value=\"18\"/>
<label>Games per Opponent</label><input id=\"mlSimGames\" type=\"number\" value=\"30\"/>
<label>Seed</label><input id=\"mlSimSeed\" type=\"number\" value=\"123\"/>
<label>Workers</label><input id=\"mlSimWorkers\" type=\"number\" value=\"6\"/>
<label>GPU Devices (CUDA_VISIBLE_DEVICES)</label><input id=\"mlSimGpuDevices\" value=\"0,1\"/>
<label>PHP Script (optional)</label><input id=\"mlSimPhpScript\" value=\"sim_harness/php_match_runner.php\"/>
<label>Simulation ID (sim create)</label><input id=\"mlSimId\" placeholder=\"sim-gpu-run\"/>
<label>Shootout Output JSON (optional)</label><input id=\"mlShootoutOutJson\" placeholder=\"sim_harness/data/shootout-latest.json\"/>
<button onclick=\"startMlSimJob()\">Start Sim Job</button><div id=\"mlSimMsg\" class=\"muted\"></div>
</div>
<div class=\"card\"><h3>RL Collect Job</h3>
<label>Candidate Deck</label><select id=\"mlCollectCandidate\"></select>
<label>Opponents</label><select id=\"mlCollectOpponents\"><option>all</option><option>meta</option><option>starter</option></select>
<label>Deck Minimum</label><select id=\"mlCollectMinCards\"><option value=\"50\" selected>50 cards</option><option value=\"30\">30 cards</option></select>
<label>Policies (csv)</label><input id=\"mlCollectPolicies\" value=\"heuristic,mcts\"/>
<label>MCTS Iterations</label><input id=\"mlCollectMctsIterations\" type=\"number\" value=\"24\"/>
<label>MCTS Max Depth</label><input id=\"mlCollectMctsDepth\" type=\"number\" value=\"18\"/>
<label>Games per Opponent</label><input id=\"mlCollectGames\" type=\"number\" value=\"25\"/>
<label>Seed</label><input id=\"mlCollectSeed\" type=\"number\" value=\"123\"/>
<label>Workers</label><input id=\"mlCollectWorkers\" type=\"number\" value=\"6\"/>
<label>Hash Dim</label><input id=\"mlCollectHashDim\" type=\"number\" value=\"256\"/>
<label>GPU Devices (optional)</label><input id=\"mlCollectGpuDevices\" value=\"0,1\"/>
<label>Output Prefix (optional)</label><input id=\"mlCollectOutputPrefix\" placeholder=\"sim_harness/data/rl/my-candidate-gpu\"/>
<button onclick=\"startMlCollectJob()\">Start RL Collect</button><div id=\"mlCollectMsg\" class=\"muted\"></div>
</div>
<div class=\"card\"><h3>RL Train Job</h3>
<label>Dataset JSONL</label><input id=\"mlTrainDataset\" list=\"mlDatasetList\" placeholder=\"sim_harness/data/rl/...jsonl\"/>
<datalist id=\"mlDatasetList\"></datalist>
<label>Vocab JSON</label><input id=\"mlTrainVocab\" list=\"mlVocabList\" placeholder=\"sim_harness/data/rl/...vocab.json\"/>
<datalist id=\"mlVocabList\"></datalist>
<label>Model Output (.pt)</label><input id=\"mlTrainModelOut\" value=\"sim_harness/data/rl/policy_value_latest.pt\"/>
<label>Device</label><select id=\"mlTrainDevice\"><option value=\"auto\">auto</option><option value=\"cuda\">cuda</option><option value=\"cpu\">cpu</option></select>
<label>GPU Devices (CUDA_VISIBLE_DEVICES)</label><input id=\"mlTrainGpuDevices\" value=\"0,1\"/>
<label>Epochs</label><input id=\"mlTrainEpochs\" type=\"number\" value=\"12\"/>
<label>Batch Size</label><input id=\"mlTrainBatchSize\" type=\"number\" value=\"512\"/>
<label>Learning Rate</label><input id=\"mlTrainLr\" value=\"0.001\"/>
<label>Weight Decay</label><input id=\"mlTrainWeightDecay\" value=\"0.00001\"/>
<label>Validation Split</label><input id=\"mlTrainValSplit\" value=\"0.1\"/>
<label>Hidden Dim</label><input id=\"mlTrainHiddenDim\" type=\"number\" value=\"256\"/>
<label>Hidden Layers</label><input id=\"mlTrainHiddenLayers\" type=\"number\" value=\"2\"/>
<label>Dropout</label><input id=\"mlTrainDropout\" value=\"0.1\"/>
<button onclick=\"startMlTrainJob()\">Start RL Train</button><div id=\"mlTrainMsg\" class=\"muted\"></div>
</div>
</div>
<h3>ML Job Queue</h3>
<table><thead><tr><th>ID</th><th>Type</th><th>Status</th><th>GPU</th><th>Started</th><th>Ended</th><th>Exit</th><th></th></tr></thead><tbody id=\"mlJobsTbody\"></tbody></table>
<div class=\"muted\" id=\"mlJobMeta\">Select a job to view full logs.</div>
<pre id=\"mlJobLogs\" class=\"logBox\">No job selected.</pre>
</div>
<div class=\"grid\">
<div class=\"card\"><h3>Decks</h3><table><thead><tr><th>ID</th><th>Pool</th><th>Name</th><th>Cards</th><th></th></tr></thead><tbody id=\"decksTbody\"></tbody></table></div>
<div class=\"card\"><h3>Simulations</h3><table><thead><tr><th>ID</th><th>Candidate</th><th>Winrate</th><th>Games</th><th>Illegal</th><th></th></tr></thead><tbody id=\"simsTbody\"></tbody></table></div>
</div>
<div class=\"card\"><h3>Simulation Analysis</h3><pre id=\"analysis\">Select a simulation to inspect analysis.</pre></div>
<div class=\"card\"><h3>Simulation Illegal Move Audit</h3><div id=\"simIllegalSummary\" class=\"muted\">Select a simulation to inspect illegal move details.</div><table><thead><tr><th>Match</th><th>Opponent</th><th>Step</th><th>Round</th><th>Phase</th><th>Player</th><th>Action</th><th>Card</th><th>Message</th><th>Legal Options</th></tr></thead><tbody id=\"simIllegalTbody\"></tbody></table></div>
<div class=\"card\"><h3>Deck JSON Viewer (SWUDB)</h3><pre id=\"deckView\">Select a deck to view SWUDB JSON.</pre></div>
<div class=\"singleMatchGrid\">
<div class=\"card\"><h3>Single Match Timeline</h3><div style=\"display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;\"><span class=\"muted\">Match JSON</span><button id=\"toggleMatchSummaryBtn\" style=\"width:auto;margin:0;padding:4px 10px;\" onclick=\"toggleMatchSummary()\">Expand JSON</button></div><pre id=\"matchSummary\" style=\"display:none;\">Run a single match to see turn-by-turn legality.</pre><div id=\"openingState\" class=\"muted\"></div><div class=\"muted\">Round page: <button onclick=\"prevRoundPage()\">Prev</button> <button onclick=\"nextRoundPage()\">Next</button> <span id=\"roundPageInfo\">-</span> <label style=\"display:inline;margin-left:8px;\"><input style=\"width:auto;\" id=\"showDecisionSteps\" type=\"checkbox\" onchange=\"renderRoundPage()\"/> Show decision prompts</label></div><table><thead><tr><th>Step</th><th>Round</th><th>Phase</th><th>Player</th><th>Kind</th><th>Action</th><th>Card</th><th>Legal?</th><th>Initiative</th><th>P1 Resources</th><th>P2 Resources</th><th>Board State</th></tr></thead><tbody id=\"matchTbody\"></tbody></table></div>
<div class=\"card\"><h3>Keyword Trigger Audit</h3><table><thead><tr><th>Step</th><th>Round</th><th>Player</th><th>Card</th><th>Keyword</th><th>Triggered</th><th>Correct?</th><th>Turn Action</th><th>Evidence</th></tr></thead><tbody id=\"keywordAuditTbody\"></tbody></table><div class=\"muted\">Tracks keyword cards used in gameplay actions and whether keyword effects were observed in the match log.</div></div>
</div>
<div class=\"card\"><h3>Validation Matrix (Mechanics Seen In Log)</h3><table><thead><tr><th>Mechanic</th><th>Triggered</th><th>Count</th><th>First Step</th><th>Evidence</th></tr></thead><tbody id=\"validationMatrixTbody\"></tbody></table><div class=\"muted\">Flags are inferred from the current match timeline and prompt/effect logs.</div></div>
<div class=\"card\"><h3>Timeline By Round/Phase</h3><table><thead><tr><th>Round</th><th>Phase</th><th>Steps</th><th>Illegal</th><th>P1 Base HP</th><th>P2 Base HP</th><th>Actions</th></tr></thead><tbody id=\"timelineByPhaseTbody\"></tbody></table></div>
</div>
<div id=\"cardHover\"><img id=\"cardHoverImg\" alt=\"Card art\"/><div id=\"cardHoverMeta\" class=\"meta\"></div></div>
<div id=\"cardModal\" onclick=\"closeCardModal()\"><button id=\"cardModalClose\" onclick=\"closeCardModal();event.stopPropagation();\">Close</button><img id=\"cardModalImg\" alt=\"Card art\"/></div>
<script>
const DECISION_TYPES = new Set(['yesno','decision','choose_zone','choose_deck','opt_top','opt_bottom','multi_choose','dynamic_input','hand_top','hand_bottom']);
const SUMMARY_COLLAPSE_KEY = 'deckxpert_match_summary_collapsed';
const MATCH_PREFS_KEY = 'deckxpert_single_match_prefs';
let currentMatchEvents = [];
let roundNumbers = [];
let currentRoundPage = 0;
let matchSummaryCollapsed = true;
const cardArtCache = new Map();
let hoverSession = 0;
let currentMlJobId = '';
let mlRefreshTimer = null;
let editingDeckId = '';

function loadMatchPrefs(){
  try{
    const raw=localStorage.getItem(MATCH_PREFS_KEY);
    if(!raw) return {};
    const obj=JSON.parse(raw);
    return (obj && typeof obj==='object')?obj:{};
  }catch(_e){
    return {};
  }
}
function setSelectValueIfPresent(el,val){
  if(!el) return false;
  const target=String(val??'').trim();
  if(target==='') return false;
  for(const opt of Array.from(el.options||[])){
    if(String(opt.value)===target){
      el.value=target;
      return true;
    }
  }
  return false;
}
function persistMatchPrefs(){
  const payload={
    deck_a_id:document.getElementById('deckA')?.value||'',
    deck_b_id:document.getElementById('deckB')?.value||'',
    min_cards:document.getElementById('matchMinCards')?.value||'',
    policy:document.getElementById('matchPolicy')?.value||'',
    mcts_iterations:document.getElementById('matchMctsIterations')?.value||'',
    mcts_max_depth:document.getElementById('matchMctsDepth')?.value||'',
    seed:document.getElementById('matchSeed')?.value||'',
  };
  try{localStorage.setItem(MATCH_PREFS_KEY,JSON.stringify(payload));}catch(_e){}
}
function initMatchPrefBindings(){
  ['deckA','deckB','matchMinCards','matchPolicy','matchMctsIterations','matchMctsDepth','matchSeed'].forEach(id=>{
    const el=document.getElementById(id);
    if(!el) return;
    el.addEventListener('change',persistMatchPrefs);
  });
}

async function api(path, opts={}){
  const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});
  const t=await r.text();let d={};
  try{d=t?JSON.parse(t):{}}catch{d={raw:t}}
  if(!r.ok)throw new Error(d.error||t||r.statusText);
  return d;
}
async function refreshAll(){
  const s=await api('/api/state');
  renderDecks(s.decks);
  renderSims(s.simulations);
  renderCandidates(s.decks);
  renderMatchDecks(s.decks);
  const rt=document.getElementById('howToRuntime');
  if(rt){
    const set=s.settings||{};
    const lines=[
      `cwd: ${set.cwd||'-'}`,
      `python: ${set.python_executable||'-'}`,
      `php_bin: ${set.php_bin||'-'}`,
      `php_available: ${Boolean(set.php_available)}`,
      `CUDA_VISIBLE_DEVICES: ${set.cuda_visible_devices||'(not set)'}`,
      `decks_file: ${set.decks_file||'-'}`,
      `sims_file: ${set.sims_file||'-'}`,
    ];
    rt.textContent=lines.join('\\n');
  }
  await refreshMlInfo();
  await refreshMlJobs();
}
function setMatchSummaryCollapsed(collapsed){
  matchSummaryCollapsed=Boolean(collapsed);
  const summary=document.getElementById('matchSummary');
  const btn=document.getElementById('toggleMatchSummaryBtn');
  if(!summary||!btn)return;
  summary.style.display=matchSummaryCollapsed?'none':'block';
  btn.textContent=matchSummaryCollapsed?'Expand JSON':'Collapse JSON';
  try{localStorage.setItem(SUMMARY_COLLAPSE_KEY,matchSummaryCollapsed?'1':'0');}catch(_e){}
}
function toggleMatchSummary(){setMatchSummaryCollapsed(!matchSummaryCollapsed);}
function initUiState(){
  let stored=null;
  try{stored=localStorage.getItem(SUMMARY_COLLAPSE_KEY);}catch(_e){}
  const collapsed=(stored===null)?true:(stored==='1');
  setMatchSummaryCollapsed(collapsed);
}
function fill(sel,decks,filter){
  if(!sel) return;
  sel.innerHTML='';
  decks.filter(filter).forEach(d=>{
    const o=document.createElement('option');
    o.value=d.deck_id;
    o.textContent=`${d.deck_id} :: ${d.name}`;
    sel.appendChild(o);
  });
}
function fillCandidateSelect(id,decks){
  const el=document.getElementById(id);
  if(!el) return;
  const prev=el.value||'';
  fill(el,decks,d=>d.pool==='candidate');
  if(!setSelectValueIfPresent(el,prev) && el.options.length>0) el.selectedIndex=0;
}
function renderCandidates(decks){
  ['candidate','mlSimCandidate','mlCollectCandidate'].forEach(id=>fillCandidateSelect(id,decks));
}
function renderMatchDecks(decks){
  const deckA=document.getElementById('deckA');
  const deckB=document.getElementById('deckB');
  const prevA=deckA?.value||'';
  const prevB=deckB?.value||'';
  fill(deckA,decks,_=>true);
  fill(deckB,decks,_=>true);
  const prefs=loadMatchPrefs();
  if(!setSelectValueIfPresent(deckA,prevA)) setSelectValueIfPresent(deckA,prefs.deck_a_id);
  if(!setSelectValueIfPresent(deckB,prevB)) setSelectValueIfPresent(deckB,prefs.deck_b_id);
  setSelectValueIfPresent(document.getElementById('matchMinCards'),prefs.min_cards);
  setSelectValueIfPresent(document.getElementById('matchPolicy'),prefs.policy);
  const mctsIterationsInput=document.getElementById('matchMctsIterations');
  if(mctsIterationsInput && String(prefs.mcts_iterations||'').trim()!=='') mctsIterationsInput.value=String(prefs.mcts_iterations);
  const mctsDepthInput=document.getElementById('matchMctsDepth');
  if(mctsDepthInput && String(prefs.mcts_max_depth||'').trim()!=='') mctsDepthInput.value=String(prefs.mcts_max_depth);
  const seedInput=document.getElementById('matchSeed');
  if(seedInput && String(prefs.seed||'').trim()!=='') seedInput.value=String(prefs.seed);
}
function setDeckEditMode(deckId=''){
  editingDeckId=String(deckId||'').trim();
  const uploadBtn=document.getElementById('uploadDeckBtn');
  const saveBtn=document.getElementById('saveDeckEditBtn');
  const cancelBtn=document.getElementById('cancelDeckEditBtn');
  const deckIdInput=document.getElementById('deckId');
  if(uploadBtn) uploadBtn.style.display=editingDeckId===''?'':'none';
  if(saveBtn) saveBtn.style.display=editingDeckId===''?'none':'';
  if(cancelBtn) cancelBtn.style.display=editingDeckId===''?'none':'';
  if(deckIdInput) deckIdInput.disabled=editingDeckId!=='';
}
function renderDecks(decks){const tb=document.getElementById('decksTbody');tb.innerHTML='';decks.forEach(d=>{const tr=document.createElement('tr');tr.innerHTML=`<td>${d.deck_id}</td><td>${d.pool}</td><td>${d.name}</td><td>${d.deck_size}</td><td><button onclick=\"showDeck('${d.deck_id}')\">View</button> <button onclick=\"editDeck('${d.deck_id}')\" style=\"background:#0f766e;border-color:#0f766e\">Edit</button> <button onclick=\"renameDeck('${d.deck_id}')\" style=\"background:#7c3aed;border-color:#7c3aed\">Rename</button> <button onclick=\"deleteDeck('${d.deck_id}')\" style=\"background:#b91c1c;border-color:#b91c1c\">Remove</button></td>`;tb.appendChild(tr);});}
function renderSims(sims){const tb=document.getElementById('simsTbody');tb.innerHTML='';sims.forEach(s=>{const tr=document.createElement('tr');const wr=((s.overall?.win_rate||0)*100).toFixed(2)+'%';const illegal=Number(s.overall?.illegal_actions||0);tr.innerHTML=`<td>${s.sim_id}</td><td>${s.candidate_deck_id}</td><td>${wr}</td><td>${s.overall?.games||0}</td><td>${illegal}</td><td><button onclick=\"showSim('${s.sim_id}')\">Analyze</button></td>`;tb.appendChild(tr);});}
async function uploadDeck(){
  if(editingDeckId!==''){
    await saveDeckEdit();
    return;
  }
  const msg=document.getElementById('uploadMsg');
  msg.textContent='Uploading...';
  try{
    const raw=document.getElementById('deckJson').value;
    let swudb={};
    try{
      swudb=JSON.parse(raw);
    }catch(parseErr){
      msg.textContent='Error: Invalid JSON. '+parseErr.message;
      return;
    }
    const out=await api('/api/decks',{method:'POST',body:JSON.stringify({deck_id:document.getElementById('deckId').value||null,pool:document.getElementById('pool').value,swudb})});
    const warnings=Array.isArray(out?.warnings)?out.warnings:[];
    msg.textContent=warnings.length?('Uploaded with warning: '+warnings.join(' ')):'Uploaded';
    await refreshAll();
  }catch(e){
    msg.textContent='Error: '+e.message;
  }
}
async function saveDeckEdit(){
  const msg=document.getElementById('uploadMsg');
  if(editingDeckId===''){
    msg.textContent='Error: No deck is selected for editing.';
    return;
  }
  msg.textContent='Saving deck edit...';
  try{
    const raw=document.getElementById('deckJson').value;
    let swudb={};
    try{
      swudb=JSON.parse(raw);
    }catch(parseErr){
      msg.textContent='Error: Invalid JSON. '+parseErr.message;
      return;
    }
    const out=await api('/api/decks/'+encodeURIComponent(editingDeckId),{method:'PUT',body:JSON.stringify({pool:document.getElementById('pool').value,swudb})});
    const warnings=Array.isArray(out?.warnings)?out.warnings:[];
    msg.textContent=warnings.length?('Saved with warning: '+warnings.join(' ')):'Saved changes for '+editingDeckId;
    const editedDeckId=editingDeckId;
    setDeckEditMode('');
    await refreshAll();
    await showDeck(editedDeckId);
  }catch(e){
    msg.textContent='Error: '+e.message;
  }
}
function cancelDeckEdit(){
  setDeckEditMode('');
  const msg=document.getElementById('uploadMsg');
  if(msg) msg.textContent='Edit cancelled.';
}
async function editDeck(id){
  if(!id) return;
  const msg=document.getElementById('uploadMsg');
  msg.textContent='Loading deck...';
  try{
    const d=await api('/api/decks/'+encodeURIComponent(id));
    document.getElementById('deckId').value=String(d.deck_id||id);
    setSelectValueIfPresent(document.getElementById('pool'),d.pool||'candidate');
    document.getElementById('deckJson').value=JSON.stringify(d.swudb||{},null,2);
    setDeckEditMode(id);
    msg.textContent='Editing '+id+'. Update JSON then click \"Save Deck Edit\".';
  }catch(e){
    msg.textContent='Error: '+e.message;
  }
}
async function renameDeck(id){
  if(!id) return;
  const msg=document.getElementById('uploadMsg');
  msg.textContent='Loading deck...';
  try{
    const d=await api('/api/decks/'+encodeURIComponent(id));
    const currentName=String(d?.swudb?.metadata?.name||id);
    const nextName=window.prompt('Rename deck',currentName);
    if(nextName===null){
      msg.textContent='Rename cancelled.';
      return;
    }
    const cleaned=String(nextName).trim();
    if(cleaned===''){
      msg.textContent='Error: Name cannot be blank.';
      return;
    }
    const out=await api('/api/decks/'+encodeURIComponent(id)+'/rename',{method:'POST',body:JSON.stringify({name:cleaned})});
    msg.textContent='Renamed '+id+' to '+String(out?.name||cleaned);
    await refreshAll();
  }catch(e){
    msg.textContent='Error: '+e.message;
  }
}
async function deleteDeck(id){
  if(!id) return;
  const ok=window.confirm(`Delete deck '${id}' from local list?`);
  if(!ok) return;
  const msg=document.getElementById('uploadMsg');
  msg.textContent='Deleting...';
  try{
    await api('/api/decks/'+encodeURIComponent(id),{method:'DELETE'});
    if(editingDeckId===id) setDeckEditMode('');
    msg.textContent='Deleted '+id;
    const deckView=document.getElementById('deckView');
    if(deckView) deckView.textContent='Select a deck to view SWUDB JSON.';
    await refreshAll();
  }catch(e){
    msg.textContent='Error: '+e.message;
  }
}
async function createSimulation(){const msg=document.getElementById('simMsg');msg.textContent='Running...';try{const out=await api('/api/simulations',{method:'POST',body:JSON.stringify({candidate:document.getElementById('candidate').value,opponents:document.getElementById('opponents').value,min_cards:parseInt(document.getElementById('simMinCards').value||'50',10),policy:document.getElementById('simPolicy').value||'random_legal',mcts_iterations:parseInt(document.getElementById('simMctsIterations').value||'16',10),mcts_max_depth:parseInt(document.getElementById('simMctsDepth').value||'14',10),games:parseInt(document.getElementById('games').value||'20',10),seed:parseInt(document.getElementById('seed').value||'42',10),workers:parseInt(document.getElementById('workers').value||'4',10),php_script:document.getElementById('phpScript').value||null,sim_id:document.getElementById('simId').value||null})});msg.textContent='Created '+out.sim_id;await refreshAll();await showSim(out.sim_id);}catch(e){msg.textContent='Error: '+e.message;}}
async function showDeck(id){const d=await api('/api/decks/'+encodeURIComponent(id));document.getElementById('deckView').textContent=JSON.stringify(d.swudb,null,2);}
function renderSimulationIllegalAudit(sim){
  const summary=document.getElementById('simIllegalSummary');
  const tbody=document.getElementById('simIllegalTbody');
  if(!summary||!tbody) return;
  const audit=(sim&&typeof sim==='object'&&sim.illegal_move_audit&&typeof sim.illegal_move_audit==='object')?sim.illegal_move_audit:{};
  const rows=Array.isArray(audit.rows)?audit.rows:[];
  const total=Number(audit.total_illegal_actions||0);
  const matches=Number(audit.matches_with_illegal||0);
  const actionPairs=Object.entries(audit.by_action_type||{}).sort((a,b)=>Number(b[1])-Number(a[1]));
  const topActions=(actionPairs.slice(0,6).map(([k,v])=>`${k}:${v}`).join(', '))||'-';
  summary.textContent=`Illegal actions: ${total} across ${matches} matches | Top action types: ${topActions}`;
  tbody.innerHTML='';
  if(rows.length===0){
    const tr=document.createElement('tr');
    tr.innerHTML='<td colspan=\"10\" class=\"muted\">No illegal moves were recorded for this simulation.</td>';
    tbody.appendChild(tr);
    return;
  }
  rows.forEach(r=>{
    const tr=document.createElement('tr');
    const legal=Object.entries(r.legal_actions_by_type||{}).sort((a,b)=>String(a[0]).localeCompare(String(b[0]))).map(([k,v])=>`${k}:${v}`).join(', ');
    const actionType=String(r.action_type||'');
    const actionChoice=String(r.action_choice||'');
    const actionCell=actionChoice!==''?`${actionType}:${actionChoice}`:actionType;
    tr.innerHTML=`<td>${r.match_id}</td><td>${r.opponent_deck_id}</td><td>${r.step}</td><td>${r.round}</td><td>${r.phase}</td><td>${r.player}</td><td>${actionCell}</td><td>${r.card_id||r.card_raw_id||'-'}</td><td>${r.message||''}</td><td>${legal||'-'}</td>`;
    tbody.appendChild(tr);
  });
}
async function showSim(id){const d=await api('/api/simulations/'+encodeURIComponent(id)+'/analysis');document.getElementById('analysis').textContent=d.text;renderSimulationIllegalAudit(d.raw||{});}

function inputValue(id){return String(document.getElementById(id)?.value||'').trim();}
function inputInt(id,fallback){
  const raw=inputValue(id);
  if(raw==='') return fallback;
  const parsed=parseInt(raw,10);
  return Number.isFinite(parsed)?parsed:fallback;
}
function inputFloat(id,fallback){
  const raw=inputValue(id);
  if(raw==='') return fallback;
  const parsed=parseFloat(raw);
  return Number.isFinite(parsed)?parsed:fallback;
}
function formatLocal(ts){
  const v=String(ts||'').trim();
  if(v==='') return '-';
  const d=new Date(v);
  if(Number.isNaN(d.getTime())) return v;
  return d.toLocaleString();
}
function renderRlArtifactLists(artifacts){
  const ds=document.getElementById('mlDatasetList');
  const vs=document.getElementById('mlVocabList');
  if(ds) ds.innerHTML='';
  if(vs) vs.innerHTML='';
  (Array.isArray(artifacts)?artifacts:[]).forEach(a=>{
    const p=String(a?.path||'');
    if(p==='') return;
    if(ds && p.endsWith('.jsonl')){
      const o=document.createElement('option');
      o.value=p;
      ds.appendChild(o);
    }
    if(vs && p.endsWith('.vocab.json')){
      const o=document.createElement('option');
      o.value=p;
      vs.appendChild(o);
    }
  });
}
function renderMlInfo(info){
  const box=document.getElementById('mlInfo');
  if(!box) return;
  const gpus=Array.isArray(info?.gpus)?info.gpus:[];
  const gpuLine=gpus.length
    ? gpus.map(g=>`GPU ${g.index}: ${g.name} (${g.memory_total_mb} MB)`).join(' | ')
    : String(info?.gpu_error||'No GPUs detected by nvidia-smi');
  const visible=String(info?.cuda_visible_devices||'all');
  const py=String(info?.python_executable||'python');
  box.textContent=`Python: ${py} | CUDA_VISIBLE_DEVICES: ${visible} | ${gpuLine}`;
  renderRlArtifactLists(info?.rl_artifacts||[]);
}
function renderMlJobs(jobs){
  const tb=document.getElementById('mlJobsTbody');
  if(!tb) return;
  tb.innerHTML='';
  const rows=Array.isArray(jobs)?jobs:[];
  if(rows.length===0){
    const tr=document.createElement('tr');
    tr.innerHTML='<td colspan=\"8\" class=\"muted\">No ML jobs yet.</td>';
    tb.appendChild(tr);
    return;
  }
  rows.forEach(j=>{
    const tr=document.createElement('tr');
    const jid=String(j.job_id||'');
    const status=String(j.status||'unknown');
    const gpu=String(j.gpu_devices||'');
    const isActive=(status==='queued' || status==='running' || status==='stopping');
    const stopBtn=isActive?`<button style=\"background:#b91c1c;border-color:#b91c1c\" onclick=\"stopMlJob('${jid}')\">Stop</button>`:'';
    tr.innerHTML=`<td>${jid}</td><td>${j.job_type||''}</td><td>${status}</td><td>${gpu||'-'}</td><td>${formatLocal(j.started_at)}</td><td>${formatLocal(j.ended_at)}</td><td>${j.exit_code===null?'-':j.exit_code}</td><td><button onclick=\"viewMlJob('${jid}')\">View</button> ${stopBtn}</td>`;
    tb.appendChild(tr);
  });
}
async function refreshMlInfo(){
  try{
    const out=await api('/api/ml/info');
    renderMlInfo(out);
  }catch(e){
    const box=document.getElementById('mlInfo');
    if(box) box.textContent='ML info unavailable: '+e.message;
  }
}
async function refreshMlJobs(){
  try{
    const out=await api('/api/ml/jobs');
    renderMlJobs(out.jobs||[]);
    if(currentMlJobId!==''){
      await viewMlJob(currentMlJobId,false);
    }
  }catch(_e){}
}
async function viewMlJob(jobId,focus=true){
  if(!jobId) return;
  try{
    const out=await api('/api/ml/jobs/'+encodeURIComponent(jobId));
    const job=out.job||{};
    currentMlJobId=String(job.job_id||jobId);
    const meta=document.getElementById('mlJobMeta');
    const logs=document.getElementById('mlJobLogs');
    if(meta){
      const cmd=Array.isArray(job.command)?job.command.join(' '):'';
      meta.textContent=`${job.job_id||jobId} | ${job.job_type||''} | status=${job.status||''} | exit=${job.exit_code===null?'-':job.exit_code} | ${cmd}`;
    }
    if(logs){
      const lines=Array.isArray(job.logs)?job.logs:[];
      logs.textContent=lines.join('\\n') || '(no logs yet)';
      if(focus) logs.scrollTop=logs.scrollHeight;
    }
  }catch(e){
    const logs=document.getElementById('mlJobLogs');
    if(logs) logs.textContent='Error loading job '+jobId+': '+e.message;
  }
}
async function launchMlJob(payload,msgId){
  const msg=document.getElementById(msgId);
  if(msg) msg.textContent='Starting job...';
  try{
    const out=await api('/api/ml/jobs',{method:'POST',body:JSON.stringify(payload||{})});
    const job=out.job||{};
    if(msg) msg.textContent=`Started ${job.job_id||''}`;
    await refreshMlJobs();
    if(job.job_id) await viewMlJob(job.job_id);
  }catch(e){
    if(msg) msg.textContent='Error: '+e.message;
  }
}
async function stopMlJob(jobId){
  if(!jobId) return;
  try{
    await api('/api/ml/jobs/'+encodeURIComponent(jobId)+'/stop',{method:'POST',body:'{}'});
    await refreshMlJobs();
    await viewMlJob(jobId,false);
  }catch(e){
    const logs=document.getElementById('mlJobLogs');
    if(logs) logs.textContent='Stop request failed: '+e.message;
  }
}
function startMlSimJob(){
  launchMlJob({
    job_type: inputValue('mlSimKind') || 'sim_create',
    candidate: inputValue('mlSimCandidate'),
    opponents: inputValue('mlSimOpponents') || 'all',
    min_cards: inputInt('mlSimMinCards',50),
    policy: inputValue('mlSimPolicy') || 'random_legal',
    policies: inputValue('mlSimPolicies') || 'random_legal,heuristic,mcts',
    mcts_iterations: inputInt('mlSimMctsIterations',24),
    mcts_max_depth: inputInt('mlSimMctsDepth',18),
    games: inputInt('mlSimGames',30),
    seed: inputInt('mlSimSeed',123),
    workers: inputInt('mlSimWorkers',6),
    gpu_devices: inputValue('mlSimGpuDevices'),
    php_script: inputValue('mlSimPhpScript'),
    sim_id: inputValue('mlSimId'),
    out_json: inputValue('mlShootoutOutJson'),
  },'mlSimMsg');
}
function startMlCollectJob(){
  launchMlJob({
    job_type: 'rl_collect',
    candidate: inputValue('mlCollectCandidate'),
    opponents: inputValue('mlCollectOpponents') || 'all',
    min_cards: inputInt('mlCollectMinCards',50),
    policies: inputValue('mlCollectPolicies') || 'heuristic,mcts',
    mcts_iterations: inputInt('mlCollectMctsIterations',24),
    mcts_max_depth: inputInt('mlCollectMctsDepth',18),
    games: inputInt('mlCollectGames',25),
    seed: inputInt('mlCollectSeed',123),
    workers: inputInt('mlCollectWorkers',6),
    hash_dim: inputInt('mlCollectHashDim',256),
    gpu_devices: inputValue('mlCollectGpuDevices'),
    output_prefix: inputValue('mlCollectOutputPrefix'),
  },'mlCollectMsg');
}
function startMlTrainJob(){
  launchMlJob({
    job_type: 'rl_train',
    dataset: inputValue('mlTrainDataset'),
    vocab: inputValue('mlTrainVocab'),
    model_out: inputValue('mlTrainModelOut'),
    device: inputValue('mlTrainDevice') || 'auto',
    gpu_devices: inputValue('mlTrainGpuDevices'),
    epochs: inputInt('mlTrainEpochs',12),
    batch_size: inputInt('mlTrainBatchSize',512),
    lr: inputFloat('mlTrainLr',0.001),
    weight_decay: inputFloat('mlTrainWeightDecay',0.00001),
    val_split: inputFloat('mlTrainValSplit',0.1),
    hidden_dim: inputInt('mlTrainHiddenDim',256),
    hidden_layers: inputInt('mlTrainHiddenLayers',2),
    dropout: inputFloat('mlTrainDropout',0.1),
  },'mlTrainMsg');
}

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
  const mySession=++hoverSession;
  const id=normalizeCardId(cardId);
  if(!id) return;
  const src=await resolveCardArt(id,rawId);
  if(mySession!==hoverSession) return;
  if(!src) return;
  const box=document.getElementById('cardHover');
  document.getElementById('cardHoverImg').src=src;
  document.getElementById('cardHoverMeta').textContent=`${id}${rawId&&rawId!==id?` (${rawId})`:''} | c:${cost??''} t:${type??''}`;
  box.style.display='block';
  moveCardHover(ev);
}
function hideCardHover(){
  hoverSession+=1;
  const box=document.getElementById('cardHover');
  if(box) box.style.display='none';
}
async function openCardModal(cardId,rawId,cost,type){
  hideCardHover();
  const id=normalizeCardId(cardId);
  if(!id) return;
  const src=await resolveCardArt(id,rawId);
  if(!src) return;
  document.getElementById('cardModalImg').src=src;
  document.getElementById('cardModalImg').title=`${id}${rawId&&rawId!==id?` (${rawId})`:''} | c:${cost??''} t:${type??''}`;
  document.getElementById('cardModal').classList.add('open');
}
function closeCardModal(){document.getElementById('cardModal').classList.remove('open');}

function renderSingleMatchAnalysis(summary, events){
  const el=document.getElementById('analysis');
  if(!el)return;
  const s=summary||{};
  const rows=filteredEvents(events||[]);
  const rounds=[...new Set(rows.map(e=>Number(e.round)).filter(n=>Number.isFinite(n)&&n>0))].sort((a,b)=>a-b);
  const winner=Number(s.winner||0);
  const winnerLabel=winner===1?'Player 1':(winner===2?'Player 2':'None');
  const actionCounts={};
  rows.forEach(e=>{
    const k=String(e?.action?.type||'unknown');
    actionCounts[k]=(actionCounts[k]||0)+1;
  });
  const topActions=Object.entries(actionCounts).sort((a,b)=>b[1]-a[1]).slice(0,8).map(([k,v])=>`${k}:${v}`).join(', ') || '-';
  const last=rows.length?rows[rows.length-1]:null;
  const p1End=last?.phase_state_end?.player_1?.base?.health ?? '';
  const p2End=last?.phase_state_end?.player_2?.base?.health ?? '';
  const policy=String(s.policy||'-');
  const turns=Number(s.turns||0);
  const seed=String(s.seed ?? '-');
  const illegal=Number(s.illegal_actions ?? rows.filter(e=>!e.apply_ok).length);
  const forcedPasses=Number(s.forced_passes ?? 0);
  const noOpFiltered=Number(s.no_op_filtered_actions ?? 0);
  const noOpRetries=Number(s.no_op_action_retries ?? 0);
  const eventsCount=Number(s.events ?? rows.length);
  const deckA=String(s.deck_a_name||s.deck_a_id||'Player A');
  const deckB=String(s.deck_b_name||s.deck_b_id||'Player B');
  const derivedLeaderActionTriggers=rows.reduce((sum,e)=>sum+nonEpicLeaderTriggersFromDetails(actionDetailsOf(e)).length,0);
  const derivedEpicActionTriggers=rows.reduce((sum,e)=>{
    const d=actionDetailsOf(e);
    return sum + (Array.isArray(d?.epic_action_triggers)?d.epic_action_triggers.length:0);
  },0);
  const leaderActionTriggers=rows.length>0 ? derivedLeaderActionTriggers : Number(s.leader_action_triggers ?? 0);
  const epicActionTriggers=rows.length>0 ? derivedEpicActionTriggers : Number(s.epic_action_triggers ?? 0);
  const lines=[
    `Single Match Analysis`,
    `Policy: ${policy} | Seed: ${seed}`,
    `Deck A: ${deckA}`,
    `Deck B: ${deckB}`,
    `Winner: ${winnerLabel}`,
    `Turns: ${turns} | Rounds seen: ${rounds.length} | Events: ${eventsCount}`,
    `Illegal actions: ${illegal} | Forced passes: ${forcedPasses}`,
    `No-op filtered: ${noOpFiltered} | No-op retries: ${noOpRetries}`,
    `Leader action triggers: ${leaderActionTriggers} | Epic action triggers: ${epicActionTriggers}`,
    `Final base HP: P1 ${p1End} | P2 ${p2End}`,
    `Top actions: ${topActions}`,
  ];
  el.textContent=lines.join('\\n');
}

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

function extractPromptText(e){
  const p=e?.action_details?.follow_up_prompt;
  if(!p||typeof p!=='object')return '';
  const txt=String(p.text||'').trim();
  const rawTurn=String(p.raw_turn_parameter||'').trim();
  const rawCtx=String(p.raw_dq_context||'').trim();
  return `${txt} ${rawTurn} ${rawCtx}`.trim().toLowerCase();
}

function isResourceSelectionPrompt(e){
  const prompt=extractPromptText(e);
  if(!prompt) return false;
  const actionType=String(e?.action?.type||'').toLowerCase();
  const cardChoice=String(e?.action?.cardID||'').toUpperCase();
  const looksLikeResourcePrompt=
    prompt.includes('choose a card to resource') ||
    prompt.includes('choose card to resource') ||
    prompt.includes('card to resource') ||
    prompt.includes('choose a card you wish to resource');
  if(!looksLikeResourcePrompt) return false;
  if(cardChoice.startsWith('MYHAND-')) return true;
  return actionType==='choose_zone' || actionType==='multi_choose' || actionType==='pass' || Boolean(e?.is_decision);
}

function detailsJson(e){
  try{return JSON.stringify(e?.action_details||{}).toLowerCase();}catch(_e){return '';}
}

const SHIELD_TOKEN_ID = '8752877738';

function hasCaptureEvidence(e){
  const changes=Array.isArray(e?.action_details?.unit_capture_changes)?e.action_details.unit_capture_changes:[];
  const hasDelta=changes.some(x=>{
    const added=Array.isArray(x?.captured_added)?x.captured_added:[];
    const released=Array.isArray(x?.captured_released)?x.captured_released:[];
    return added.length>0 || released.length>0;
  });
  if(hasDelta) return true;
  const p=extractPromptText(e);
  return p.includes('capture') || p.includes('captured');
}

function isAttackTargetSelection(e,actionType,actionChoice){
  if(String(actionType||'')!=='choose_zone')return false;
  const choice=String(actionChoice||'').toUpperCase();
  if(choice.startsWith('THEIRALLY-')||choice.startsWith('THEIRCHAR-')||choice.startsWith('THEIRUNIT-'))return true;
  const prompt=extractPromptText(e);
  if(prompt.includes('target for the attack')||prompt.includes('target of the attack')||prompt.includes('attack target'))return true;
  const d=detailsJson(e);
  return d.includes('target for the attack')||d.includes('target of the attack');
}

function hasKeywordFlag(e,keyword){
  return Boolean(e?.card?.keywords?.[keyword]);
}

function normalizeCardLikeId(v){
  return String(v||'').trim().toUpperCase();
}

function actionDetailsOf(e){
  return (e && typeof e==='object' && e.action_details && typeof e.action_details==='object') ? e.action_details : {};
}

function nonEpicLeaderTriggersFromDetails(d){
  const details=(d && typeof d==='object') ? d : {};
  const leader=Array.isArray(details?.leader_action_triggers) ? details.leader_action_triggers : [];
  if(leader.length===0) return [];
  const epic=Array.isArray(details?.epic_action_triggers) ? details.epic_action_triggers : [];
  const hasEpic=epic.length>0;
  return leader.filter(t=>{
    const deployFrom=String(t?.deploy_from||'').toUpperCase();
    if(deployFrom==='EPICACTION') return false;
    if(hasEpic && String(t?.trigger||'')==='leader_action_selected') return false;
    return true;
  });
}

function playerStateDelta(e, playerId){
  const d=actionDetailsOf(e);
  const states=Array.isArray(d.player_state_changes)?d.player_state_changes:[];
  return states.find(x=>Number(x?.player)===Number(playerId)) || null;
}

function playerSnapshot(e, playerId, when='end'){
  const root=(when==='begin' ? e?.phase_state_begin : e?.phase_state_end) || {};
  return root[`player_${Number(playerId)}`] || null;
}

function playerActiveUnitCount(e, playerId, when='end'){
  const snap=playerSnapshot(e, playerId, when);
  return Number(snap?.counts?.active_units ?? 0);
}

function unitDetailByUid(e, playerId, uid, when='begin'){
  const snap=playerSnapshot(e, playerId, when);
  const list=Array.isArray(snap?.units?.details)?snap.units.details:[];
  const wanted=String(uid||'');
  if(!wanted) return null;
  for(const u of list){
    if(String(u?.uid||'')===wanted) return u;
  }
  return null;
}

function exhaustedAttackerUid(e){
  const d=actionDetailsOf(e);
  const changes=Array.isArray(d.unit_ready_state_changes)?d.unit_ready_state_changes:[];
  const actor=Number(e?.player||0);
  const hit=changes.find(x=>Number(x?.player)===actor && Boolean(x?.before_ready) && !Boolean(x?.after_ready));
  return String(hit?.unit_uid || '');
}

function classifyExhaustionTransitions(e){
  const d=actionDetailsOf(e);
  const changes=Array.isArray(d.unit_ready_state_changes)?d.unit_ready_state_changes:[];
  const exhausted=changes.filter(x=>Boolean(x?.before_ready) && !Boolean(x?.after_ready));
  const actor=Number(e?.player||0);
  const actionType=String(e?.action?.type||'').toLowerCase();
  const attackUid=actionType==='activate_ally' ? exhaustedAttackerUid(e) : '';
  let attackSelfCount=0;
  let effectCount=0;
  let enemyEffectCount=0;
  exhausted.forEach(ch=>{
    const owner=Number(ch?.player||0);
    const uid=String(ch?.unit_uid||'');
    const actorOwned=owner===actor;
    let isAttackSelf=false;
    if(actionType==='activate_ally' && actorOwned){
      if(attackUid!==''){
        if(uid===attackUid && attackSelfCount===0) isAttackSelf=true;
      } else if(attackSelfCount===0){
        isAttackSelf=true;
      }
    }
    if(isAttackSelf){
      attackSelfCount+=1;
      return;
    }
    effectCount+=1;
    if(!actorOwned) enemyEffectCount+=1;
  });
  return {
    attack_self_count: attackSelfCount,
    effect_count: effectCount,
    enemy_effect_count: enemyEffectCount,
  };
}

function outgoingDamageFromEvent(e, attackerPlayer){
  const d=actionDetailsOf(e);
  const attacker=Number(attackerPlayer||0);
  const unitDamage=Array.isArray(d.unit_damage)?d.unit_damage:[];
  const baseDamage=Array.isArray(d.base_damage)?d.base_damage:[];
  let total=0;
  unitDamage.forEach(x=>{
    if(Number(x?.player)===attacker) return;
    total+=Math.max(0, Number(x?.damage||0));
  });
  baseDamage.forEach(x=>{
    if(Number(x?.player)===attacker) return;
    total+=Math.max(0, Number(x?.amount||0));
  });
  return total;
}

function promptContainsPilotText(e){
  const p=extractPromptText(e);
  return p.includes('play as a pilot or unit') || p.includes('play as pilot') || p.includes('pilot');
}

function isPlayedFromResources(e, keyword){
  const k=String(keyword||'');
  if(!hasKeywordFlag(e,k)) return false;
  const action=String(e?.action?.type||'').toLowerCase();
  if(action!=='play_hand' && action!=='play_character') return false;
  const actor=Number(e?.player||0);
  const s=playerStateDelta(e, actor);
  if(!s) return false;
  const handDelta=Number(s?.hand_delta||0);
  const resTotalDelta=Number(s?.resource_cards_total_delta||0);
  return handDelta===0 && resTotalDelta<0;
}

function looksLikeShieldEvidence(e){
  const d=actionDetailsOf(e);
  const changes=Array.isArray(d.unit_upgrade_changes)?d.unit_upgrade_changes:[];
  for(const ch of changes){
    const added=Array.isArray(ch?.added)?ch.added:[];
    const removed=Array.isArray(ch?.removed)?ch.removed:[];
    const all=added.concat(removed).map(normalizeCardLikeId);
    if(all.includes(normalizeCardLikeId(SHIELD_TOKEN_ID))) return true;
  }
  return false;
}

function shieldUpgradeDelta(e){
  const d=actionDetailsOf(e);
  const changes=Array.isArray(d.unit_upgrade_changes)?d.unit_upgrade_changes:[];
  let applied=0;
  let removed=0;
  changes.forEach(ch=>{
    const added=Array.isArray(ch?.added)?ch.added:[];
    const rem=Array.isArray(ch?.removed)?ch.removed:[];
    added.forEach(x=>{if(normalizeCardLikeId(x)===normalizeCardLikeId(SHIELD_TOKEN_ID)) applied+=1;});
    rem.forEach(x=>{if(normalizeCardLikeId(x)===normalizeCardLikeId(SHIELD_TOKEN_ID)) removed+=1;});
  });
  return {applied, removed};
}

function damagedAfterByUid(e, playerId, unitUid){
  const u=unitDetailByUid(e, playerId, unitUid, 'end');
  return Number(u?.damage_taken||0)>0;
}

function keywordObserved(e,keyword){
  const k=String(keyword||'').toLowerCase();
  const p=extractPromptText(e);
  const action=String(e?.action?.type||'').toLowerCase();
  const d=actionDetailsOf(e);
  const actor=Number(e?.player||0);
  const statChanges=Array.isArray(d.unit_stat_changes)?d.unit_stat_changes:[];
  const defeatedUnits=Array.isArray(d.unit_defeated)?d.unit_defeated:[];
  const upgradedUnits=Array.isArray(d.unit_upgrade_changes)?d.unit_upgrade_changes:[];
  const unitDamage=Array.isArray(d.unit_damage)?d.unit_damage:[];
  const baseDamage=Array.isArray(d.base_damage)?d.base_damage:[];
  const hasAttackPrompt=p.includes('target for the attack') || p.includes('target of the attack') || p.includes('attack target');
  if(!k)return {triggered:false,evidence:''};
  if(isResourceSelectionPrompt(e)) return {triggered:false,evidence:''};
  if((k==='plot' || k==='smuggle') && isPlayedFromResources(e, keyword)){
    return {triggered:true,evidence:`${k} card played from resources`};
  }
  if(k==='shielded' || k==='shield'){
    const shield=shieldUpgradeDelta(e);
    const hit=(shield.applied + shield.removed)>0;
    return {triggered:hit,evidence:hit?`shield tokens changed (+${shield.applied}/-${shield.removed})`:''};
  }
  if(k==='piloting'){
    const hit=hasKeywordFlag(e,'Piloting') && upgradedUnits.length>0 && promptContainsPilotText(e);
    return {triggered:hit,evidence:hit?'pilot mode selected and attached as upgrade':''};
  }
  if(k==='ambush'){
    const hit=hasKeywordFlag(e,'Ambush') && action==='play_hand' && hasAttackPrompt;
    return {triggered:hit,evidence:hit?'ambush attack prompt after deploy':''};
  }
  if(k==='bounty'){
    const hit=hasKeywordFlag(e,'Bounty') && defeatedUnits.length>0;
    return {triggered:hit,evidence:hit?'bounty unit defeated in action resolution':''};
  }
  if(k==='coordinate'){
    const controlled=playerActiveUnitCount(e, actor, 'end');
    const hit=hasKeywordFlag(e,'Coordinate') && controlled>=3 && (statChanges.length>0 || hasCaptureEvidence(e));
    return {triggered:hit,evidence:hit?`coordinate active (${controlled} units), effect resolved`:''};
  }
  if(k==='saboteur'){
    if(!hasKeywordFlag(e,'Saboteur')) return {triggered:false,evidence:''};
    if(action!=='activate_ally' && action!=='choose_zone') return {triggered:false,evidence:''};
    const shield=shieldUpgradeDelta(e);
    const hit=(shield.removed>0) && isAttackTargetSelection(e, action, String(e?.action?.buttonInput||e?.action?.cardID||''));
    return {triggered:hit,evidence:hit?`saboteur removed shield in combat (-${shield.removed})`:''};
  }
  if(k==='restore'){
    const state=(Array.isArray(e?.action_details?.player_state_changes)?e.action_details.player_state_changes:[]);
    const healed=state.some(x=>Number(x?.base_hp_delta||0)>0);
    const hit=hasKeywordFlag(e,'Restore') && healed;
    return {triggered:hit,evidence:hit?'restore healing applied':''};
  }
  if(k==='exploit'){
    const ex=d.exploit_resolution;
    const hasResolution=Boolean(ex && typeof ex==='object');
    if(!hasResolution) return {triggered:false,evidence:''};
    const sel=Number(ex?.selected_count||0);
    const n=Number.isFinite(sel) ? Math.max(0, sel) : 0;
    if(n<=0) return {triggered:false,evidence:''};
    const sacrificed=defeatedUnits.filter(x=>Number(x?.player)===actor).length;
    const hit=sacrificed>0;
    return {triggered:hit,evidence:hit?`exploit resolved with ${sacrificed} defeated unit(s)`:''};
  }
  if(k==='overwhelm'){
    const hit=hasKeywordFlag(e,'Overwhelm') && unitDamage.length>0 && baseDamage.length>0;
    return {triggered:hit,evidence:hit?'combat dealt both unit and base damage':''};
  }
  if(k==='raid'){
    const attackerUid=exhaustedAttackerUid(e);
    const attacker=unitDetailByUid(e, actor, attackerUid, 'begin');
    const basePower=Math.max(0, Number(attacker?.current_power||0));
    const dealt=outgoingDamageFromEvent(e, actor);
    const hit=hasKeywordFlag(e,'Raid') && action==='activate_ally' && dealt>basePower;
    return {triggered:hit,evidence:hit?`raid attack increased damage (${basePower}->${dealt})`:''};
  }
  if(k==='grit'){
    if(!hasKeywordFlag(e,'Grit')) return {triggered:false,evidence:''};
    const cardId=String(e?.card?.id||'');
    const stats=statChanges.filter(x=>
      Number(x?.player)===actor &&
      String(x?.unit_id||'')===cardId &&
      Number(x?.power?.after||0)>Number(x?.power?.before||0)
    );
    for(const s of stats){
      if(damagedAfterByUid(e, actor, String(s?.unit_uid||''))){
        const before=Number(s?.power?.before||0);
        const after=Number(s?.power?.after||0);
        return {triggered:true,evidence:`grit power increased while damaged (${before}->${after})`};
      }
    }
    return {triggered:false,evidence:''};
  }
  if(k==='sentinel' || k==='hidden'){
    return {triggered:false,evidence:''};
  }
  return {triggered:false,evidence:''};
}

function keywordObservedWithContext(events, index, keyword){
  const rows=Array.isArray(events)?events:[];
  const i=Number(index);
  if(!Number.isFinite(i) || i<0 || i>=rows.length) return {triggered:false,evidence:''};
  const e=rows[i];
  const base=keywordObserved(e,keyword);
  if(base.triggered) return base;
  const k=String(keyword||'').toLowerCase();
  const actionType=String(e?.action?.type||'').toLowerCase();
  const actor=Number(e?.player||0);
  if((k==='plot' || k==='smuggle') && isPlayedFromResources(e, keyword)){
    return {triggered:true,evidence:`${k} card played from resources`};
  }
  if(k==='piloting' && hasKeywordFlag(e,'Piloting')){
    for(let j=i;j<rows.length && j<=i+4;j+=1){
      const next=rows[j];
      if(Number(next?.round)!==Number(e?.round)) break;
      if(Number(next?.player)!==actor) continue;
      const upgrades=Array.isArray(next?.action_details?.unit_upgrade_changes)?next.action_details.unit_upgrade_changes:[];
      if(upgrades.length===0) continue;
      const hasPilotPrompt=promptContainsPilotText(next) || promptContainsPilotText(e);
      if(!hasPilotPrompt) continue;
      return {triggered:true,evidence:'pilot mode resolved as upgrade attachment'};
    }
  }
  if(k==='coordinate' && hasKeywordFlag(e,'Coordinate')){
    for(let j=i;j<rows.length && j<=i+4;j+=1){
      const next=rows[j];
      if(Number(next?.round)!==Number(e?.round)) break;
      if(Number(next?.player)!==actor) continue;
      const controlled=playerActiveUnitCount(next, actor, 'end');
      const statChanges=Array.isArray(next?.action_details?.unit_stat_changes)?next.action_details.unit_stat_changes:[];
      if(controlled>=3 && (statChanges.length>0 || hasCaptureEvidence(next))){
        return {triggered:true,evidence:`coordinate active (${controlled} units), effect resolved`};
      }
    }
  }
  if(k==='grit' && hasKeywordFlag(e,'Grit')){
    for(let j=i;j<rows.length && j<=i+4;j+=1){
      const next=rows[j];
      if(Number(next?.round)!==Number(e?.round)) break;
      if(Number(next?.player)!==actor) continue;
      const d=actionDetailsOf(next);
      const stats=Array.isArray(d.unit_stat_changes)?d.unit_stat_changes:[];
      const cardId=String(e?.card?.id||'');
      for(const s of stats){
        if(Number(s?.player)!==actor) continue;
        if(String(s?.unit_id||'')!==cardId) continue;
        const before=Number(s?.power?.before||0);
        const after=Number(s?.power?.after||0);
        if(after<=before) continue;
        if(damagedAfterByUid(next, actor, String(s?.unit_uid||''))){
          return {triggered:true,evidence:`grit power increased while damaged (${before}->${after})`};
        }
      }
    }
  }
  if(k==='exploit' && hasKeywordFlag(e,'Exploit')){
    for(let j=i;j<rows.length && j<=i+5;j+=1){
      const next=rows[j];
      if(Number(next?.round)!==Number(e?.round)) break;
      if(Number(next?.player)!==actor) continue;
      const d=actionDetailsOf(next);
      const ex=d.exploit_resolution;
      if(!ex || typeof ex!=='object') continue;
      const selected=Math.max(0, Number(ex?.selected_count||0));
      if(selected<=0) continue;
      const defeated=Array.isArray(d.unit_defeated)?d.unit_defeated:[];
      const sacrificed=defeated.filter(x=>Number(x?.player)===actor).length;
      if(sacrificed>0){
        return {triggered:true,evidence:`exploit paid by defeating ${sacrificed} unit(s)`};
      }
    }
  }
  if(k==='overwhelm' && hasKeywordFlag(e,'Overwhelm') && actionType==='activate_ally'){
    for(let j=i+1;j<rows.length && j<=i+4;j+=1){
      const next=rows[j];
      if(Number(next?.round)!==Number(e?.round)) break;
      if(Number(next?.player)!==Number(e?.player)) continue;
      const unitDamage=Array.isArray(next?.action_details?.unit_damage)?next.action_details.unit_damage:[];
      const baseDamage=Array.isArray(next?.action_details?.base_damage)?next.action_details.base_damage:[];
      if(unitDamage.length>0 && baseDamage.length>0){
        return {triggered:true,evidence:'overwhelm spillover observed in attack resolution'};
      }
      if(String(next?.action?.type||'').toLowerCase()==='activate_ally') break;
    }
  }
  if(k==='raid' && hasKeywordFlag(e,'Raid') && actionType==='activate_ally'){
    const attackerUid=exhaustedAttackerUid(e);
    const attacker=unitDetailByUid(e, actor, attackerUid, 'begin');
    const basePower=Math.max(0, Number(attacker?.current_power||0));
    for(let j=i+1;j<rows.length && j<=i+3;j+=1){
      const next=rows[j];
      if(Number(next?.round)!==Number(e?.round)) break;
      if(Number(next?.player)!==Number(e?.player)) continue;
      const dealt=outgoingDamageFromEvent(next, actor);
      if(dealt>basePower){
        return {triggered:true,evidence:`raid attack increased damage (${basePower}->${dealt})`};
      }
      if(String(next?.action?.type||'').toLowerCase()==='activate_ally') break;
    }
  }
  if(k==='saboteur' && hasKeywordFlag(e,'Saboteur') && actionType==='activate_ally'){
    for(let j=i+1;j<rows.length && j<=i+4;j+=1){
      const next=rows[j];
      if(Number(next?.round)!==Number(e?.round)) break;
      if(Number(next?.player)!==actor) continue;
      const nextType=String(next?.action?.type||'').toLowerCase();
      const nextChoice=String(next?.action?.buttonInput||next?.action?.cardID||'');
      if(!isAttackTargetSelection(next,nextType,nextChoice)) continue;
      const shield=shieldUpgradeDelta(next);
      const targetHasShielded=Boolean(next?.card?.keywords?.Shielded);
      const targetHasSentinel=Boolean(next?.card?.keywords?.Sentinel);
      if(shield.removed>0 || targetHasShielded || targetHasSentinel){
        if(targetHasSentinel){
          return {triggered:true,evidence:'saboteur attacked sentinel defender'};
        }
        if(shield.removed>0 || targetHasShielded){
          return {triggered:true,evidence:`saboteur attacked shielded defender${shield.removed>0?` (shield removed ${shield.removed})`:''}`};
        }
      }
    }
  }
  if(k==='sentinel'){
    const choice=String(e?.action?.buttonInput||e?.action?.cardID||'').toUpperCase();
    if(actionType==='choose_zone' && choice.startsWith('THEIRALLY-') && hasKeywordFlag(e,'Sentinel') && isAttackTargetSelection(e,actionType,choice)){
      let forced=false;
      const prev=i>0?rows[i-1]:null;
      if(prev && Number(prev?.round)===Number(e?.round) && Number(prev?.player)===Number(e?.player)){
        const prompt=extractPromptText(prev);
        if(prompt.includes('target for the attack') || prompt.includes('target of the attack')){
          const hasBaseOption=prompt.includes('theirchar-');
          const hasAllyOption=prompt.includes('theirally-');
          forced=hasAllyOption && !hasBaseOption;
        }
      }
      return {
        triggered:true,
        evidence:forced
          ? 'sentinel constrained target options (no base target offered)'
          : 'sentinel unit selected as attack target'
      };
    }
  }
  return base;
}

function renderKeywordAudit(events){
  const tb=document.getElementById('keywordAuditTbody');
  if(!tb)return;
  tb.innerHTML='';
  const rows=[];
  const sourceEvents=filteredEvents(events);
  sourceEvents.forEach((e,idx)=>{
    const actionType=String(e?.action?.type||'');
    const actionChoice=String(e?.action?.buttonInput||e?.action?.cardID||'');
    const isAttackTargetStep=isAttackTargetSelection(e,actionType,actionChoice);
    if(isDecisionEvent(e) && !isAttackTargetStep)return;
    const keywords=e?.card?.keywords;
    if(!keywords || typeof keywords!=='object')return;
    const cardId=String(e?.card?.id||'');
    Object.entries(keywords).forEach(([keyword,val])=>{
      if(!val)return;
      const check=keywordObservedWithContext(sourceEvents,idx,keyword);
      if(!check.triggered) return;
      let correctness='yes';
      let correctnessClass='ok';
      if(!e.apply_ok){
        correctness='no';
        correctnessClass='bad';
      }
      rows.push({
        step:e.step,
        round:e.round,
        player:e.player,
        card:cardId,
        keyword:String(keyword),
        triggered:check.triggered,
        correct:correctness,
        correctClass:correctnessClass,
        action:actionType,
        evidence:check.evidence || '-',
      });
    });
  });
  rows.sort((a,b)=>Number(a.step)-Number(b.step));
  if(rows.length===0){
    const tr=document.createElement('tr');
    tr.innerHTML='<td colspan="9" class="muted">No keyword-card gameplay actions found in this match log.</td>';
    tb.appendChild(tr);
    return;
  }
  rows.forEach(r=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${r.step}</td><td>${r.round}</td><td>${r.player}</td><td>${r.card||'-'}</td><td>${r.keyword}</td><td>${r.triggered?'<span class="ok">yes</span>':'<span class="bad">no</span>'}</td><td><span class="${r.correctClass}">${r.correct}</span></td><td>${r.action||'-'}</td><td>${r.evidence}</td>`;
    tb.appendChild(tr);
  });
}

function renderValidationMatrix(events){
  const tb=document.getElementById('validationMatrixTbody');
  if(!tb)return;
  tb.innerHTML='';
  const norm=(s)=>String(s||'').toLowerCase();
  const esc=(s)=>String(s??'').replace(/[&<>"']/g,(m)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const keywordFromLabel=(label)=>{
    const raw=String(label||'');
    if(!raw.toLowerCase().startsWith('keyword:')) return '';
    return raw.slice(8).trim();
  };
  const actionChoiceForEvent=(e)=>{
    const at=String(e?.action?.type||'');
    const ac=String(e?.action?.buttonInput||e?.action?.cardID||'');
    const actionNeedsChoiceLabel=new Set(['yesno','decision','choose_zone','choose_deck','opt_top','opt_bottom','hand_top','hand_bottom','dynamic_input']);
    return (actionNeedsChoiceLabel.has(at) && ac!=='') ? `${at}:${ac}` : at;
  };
  const keywordUniverse=new Set([
    'Ambush','Bounty','Coordinate','Grit','Hidden','Overwhelm','Piloting','Raid','Restore',
    'Saboteur','Sentinel','Shielded','Smuggle','Villainy','Heroism'
  ]);
  (events||[]).forEach(e=>{
    const kw=e?.card?.keywords;
    if(!kw||typeof kw!=='object')return;
    Object.keys(kw).forEach(k=>{
      if(kw[k]) keywordUniverse.add(String(k));
    });
  });
  const hasKeyword=(e,keyword,idx,source)=>{
    if(isResourceSelectionPrompt(e)) return false;
    const k=String(keyword||'');
    const observed=keywordObservedWithContext(source,idx,k);
    return observed.triggered;
  };
  const rows=[
    {
      id:'illegal_moves',
      label:'Illegal Moves',
      match:(e)=>!Boolean(e?.apply_ok)
    },
    {
      id:'disclose_aspects',
      label:'Disclose Aspects',
      match:(e)=>{
        const p=extractPromptText(e);
        const d=detailsJson(e);
        return p.includes('disclose') || d.includes('disclose') || p.includes('aspect') || d.includes('aspect');
      }
    },
    {
      id:'disclose_cards',
      label:'Reveal / Disclose Cards',
      match:(e)=>{
        const p=extractPromptText(e);
        const d=detailsJson(e);
        return p.includes('reveal') || d.includes('reveal') || p.includes('disclose') || d.includes('disclose');
      }
    },
    {
      id:'capture',
      label:'Capture',
      match:(e)=>{
        const p=extractPromptText(e);
        return hasCaptureEvidence(e) || p.includes('capture') || p.includes('captured');
      }
    },
    {
      id:'unit_exhaust_attack_self',
      label:'Attack Exhaust (Self)',
      match:(e)=>{
        const c=classifyExhaustionTransitions(e);
        return c.attack_self_count>0;
      }
    },
    {
      id:'unit_exhaust_effect',
      label:'Effect Exhaust (Card/Ability)',
      match:(e)=>{
        const c=classifyExhaustionTransitions(e);
        return c.effect_count>0;
      }
    },
    {
      id:'unit_exhaust_enemy_effect',
      label:'Enemy Unit Exhausted by Effect',
      match:(e)=>{
        const c=classifyExhaustionTransitions(e);
        return c.enemy_effect_count>0;
      }
    },
    {
      id:'unit_readied',
      label:'Unit Readied Effects',
      match:(e)=>{
        const changes=Array.isArray(e?.action_details?.unit_ready_state_changes)?e.action_details.unit_ready_state_changes:[];
        return changes.some(x=>Boolean(x?.after_ready));
      }
    },
    {
      id:'leader_actions',
      label:'Leader Action Triggers',
      match:(e)=>nonEpicLeaderTriggersFromDetails(actionDetailsOf(e)).length>0
    },
    {
      id:'epic_actions',
      label:'Epic Action Triggers',
      match:(e)=>Array.isArray(e?.action_details?.epic_action_triggers) && e.action_details.epic_action_triggers.length>0
    },
    {id:'shield',label:'Shield / Shielded',match:(e)=>{
      const d=shieldUpgradeDelta(e);
      return (d.applied + d.removed)>0;
    }},
    {id:'saboteur',label:'Saboteur',match:(e,i,src)=>hasKeyword(e,'Saboteur',i,src)},
    {id:'piloting',label:'Piloting',match:(e,i,src)=>hasKeyword(e,'Piloting',i,src)},
    {id:'coordinate',label:'Coordinate',match:(e,i,src)=>hasKeyword(e,'Coordinate',i,src)},
    {id:'ambush',label:'Ambush',match:(e,i,src)=>hasKeyword(e,'Ambush',i,src)},
    {id:'upgrades',label:'Upgrades',match:(e)=>String(e?.card?.type||'')==='Upgrade' || ((e?.action_details?.unit_upgrade_changes||[]).length>0)},
    {id:'plot',label:'Plot',match:(e,i,src)=>hasKeyword(e,'Plot',i,src)},
    {id:'bounty',label:'Bounty',match:(e,i,src)=>hasKeyword(e,'Bounty',i,src)}
  ];
  [...keywordUniverse].sort((a,b)=>a.localeCompare(b)).forEach(k=>{
    const exists=rows.some(r=>r.id===`kw_${norm(k)}` || norm(r.label)===`keyword: ${norm(k)}`);
    if(exists)return;
    rows.push({id:`kw_${norm(k)}`,label:`Keyword: ${k}`,match:(e,i,src)=>hasKeyword(e,k,i,src)});
  });

  const sourceEvents=filteredEvents(events);
  const groupedStepLabels=buildDecisionGroupedStepLabels(sourceEvents);
  rows.forEach(r=>{
    let count=0;
    let firstStep='';
    let evidence='';
    const instances=[];
    sourceEvents.forEach((e,i)=>{
      if(!r.match(e,i,sourceEvents))return;
      count+=1;
      const rawStep=String(e?.step||'');
      const groupedStep=groupedStepLabels.get(Number(e?.step));
      const step=(groupedStep && String(groupedStep)!==rawStep)
        ? `${groupedStep} (raw ${rawStep})`
        : rawStep;
      const round=String(e?.round||'');
      const phase=String(e?.phase||'');
      const player=String(e?.player||'');
      const action=actionChoiceForEvent(e);
      const card=String(e?.card?.id||'');
      let ev='';
      const kw=keywordFromLabel(r.label);
      if(kw!==''){
        const obs=keywordObservedWithContext(sourceEvents,i,kw);
        ev=String(obs?.evidence||'');
      }
      if(ev===''){
        const prompt=extractPromptText(e);
        if(prompt!=='') ev=prompt.slice(0,120);
      }
      instances.push({step,round,phase,player,action,card,evidence:ev});
      if(firstStep===''){
        firstStep=step;
        evidence=`${action}${card?` ${card}`:''}${ev?` | ${ev}`:''}`;
      }
    });
    const tr=document.createElement('tr');
    const triggered=count>0;
    let instanceHtml='-';
    if(instances.length>0){
      const lines=instances.map(ins=>{
        const cardPart=ins.card?` ${esc(ins.card)}`:'';
        const evPart=ins.evidence?` | ${esc(ins.evidence)}`:'';
        return `<div class="instanceLine">Step ${esc(ins.step)} (R${esc(ins.round)} ${esc(ins.phase)}) P${esc(ins.player)} ${esc(ins.action)}${cardPart}${evPart}</div>`;
      }).join('');
      instanceHtml=`${esc(evidence||'-')}<details class="instanceDrop"><summary>Show ${instances.length} trigger instance${instances.length===1?'':'s'}</summary><div class="instanceList">${lines}</div></details>`;
    }
    tr.innerHTML=`<td>${esc(r.label)}</td><td>${triggered?'<span class="ok">yes</span>':'<span class="bad">no</span>'}</td><td>${count}</td><td>${esc(firstStep)}</td><td>${instanceHtml}</td>`;
    tb.appendChild(tr);
  });
}

function alphaSuffix(n){
  let x=Number(n||0);
  if(!Number.isFinite(x) || x<=0) return '';
  let s='';
  while(x>0){
    x-=1;
    s=String.fromCharCode(97 + (x % 26)) + s;
    x=Math.floor(x/26);
  }
  return s;
}

function buildDecisionGroupedStepLabels(events){
  const map=new Map();
  let major=0;
  let promptIndex=0;
  (events||[]).forEach(e=>{
    const step=Number(e?.step);
    if(!Number.isFinite(step)) return;
    if(isDecisionEvent(e)){
      if(major===0){
        major=1;
        promptIndex=0;
      }
      promptIndex+=1;
      map.set(step, `${major}${alphaSuffix(promptIndex)}`);
      return;
    }
    major+=1;
    promptIndex=0;
    map.set(step, String(major));
  });
  return map;
}

function renderRoundPage(){
  const tb=document.getElementById('matchTbody');
  const info=document.getElementById('roundPageInfo');
  hideCardHover();
  tb.innerHTML='';
  if(roundNumbers.length===0){info.textContent='No round data';return;}
  if(currentRoundPage<0)currentRoundPage=0;
  if(currentRoundPage>=roundNumbers.length)currentRoundPage=roundNumbers.length-1;
  const showDecisions=document.getElementById('showDecisionSteps').checked;
  const round=roundNumbers[currentRoundPage];
  const allRows=filteredEvents(currentMatchEvents);
  const groupedStepLabels=buildDecisionGroupedStepLabels(allRows);
  const rows=allRows.filter(e=>Number(e.round)===Number(round)).filter(e=>showDecisions || !isDecisionEvent(e));
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
    const capt=fmtCards(u?.captives||[],3);
    const dmg=Number(u?.damage_taken??0);
    return `${id}(${stance}) pwr:${pNow}${pMod?`(${pMod})`:''} hp:${hNow}/${hMax}${hMod?`(${hMod})`:''}${dmg>0?` dmg:${dmg}`:''}${upg!=='-'?` upg:[${upg}]`:''}${capt!=='-'?` capt:[${capt}]`:''}`;
  };
  const escAttr=(v)=>String(v??'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/'/g,'&#39;');
  const fmtUnitList=(arr,limit=3)=>{
    const units=Array.isArray(arr)?arr:[];
    if(units.length===0)return '-';
    const shown=units.slice(0,limit).map(fmtUnit);
    if(units.length>limit){
      const hidden=units.slice(limit).map(fmtUnit);
      const hiddenTooltip=escAttr(hidden.join(' ; '));
      shown.push(`<span class="moreUnitsHint" title="${hiddenTooltip}">+${units.length-limit} more</span>`);
    }
    return shown.join(' ; ');
  };
  const fmtActionDetails=(d,e)=>{
    if(!d||typeof d!=='object') return '';
    const bits=[];
    const engineMsg=String(e?.message||'').trim();
    if(engineMsg!=='') bits.push(`Engine: ${engineMsg}`);
    if(!Boolean(e?.apply_ok) && e?.legal_actions_by_type && typeof e.legal_actions_by_type==='object'){
      const legalNow=Object.entries(e.legal_actions_by_type).sort((a,b)=>String(a[0]).localeCompare(String(b[0]))).map(([k,v])=>`${k}:${v}`).join(', ');
      if(legalNow!=='') bits.push(`Legal options: ${legalNow}`);
    }
    const actionType=String(e?.action?.type||'').toLowerCase();
    const actor=Number(e?.player||0);
    const playedCard=(e?.card?.id||e?.card?.raw_id||'').toString();
    if(actionType==='activate_ally'){
      const unitDmg=Array.isArray(d.unit_damage)?d.unit_damage:[];
      const baseDmg=Array.isArray(d.base_damage)?d.base_damage:[];
      const enemyUnitHit=unitDmg.find(x=>Number(x?.player)!==actor);
      const enemyBaseHit=baseDmg.find(x=>Number(x?.player)!==actor);
      const attackerName=playedCard || `P${actor} unit`;
      if(enemyUnitHit){
        bits.push(`Attack: ${attackerName} -> P${enemyUnitHit.player} ${enemyUnitHit.unit_id||'unit'} (${enemyUnitHit.damage||0})`);
      } else if(enemyBaseHit){
        bits.push(`Attack: ${attackerName} -> P${enemyBaseHit.player} base (${enemyBaseHit.amount||0})`);
      }
    }
    const follow=d.follow_up_prompt;
    if(follow && typeof follow==='object'){
      const t=String(follow.text||'').trim();
      const p=Number(follow.player||0);
      const ph=String(follow.phase||'');
      bits.push(`Prompt: P${p||'?'} ${ph}${t?` - ${t}`:''}`);
    }
    const exploit=d.exploit_resolution;
    if(exploit && typeof exploit==='object'){
      const p=Number(exploit.player||0);
      const sel=Number(exploit.selected_count||0);
      const selected=Number.isFinite(sel) ? Math.max(0, sel) : 0;
      const t=String(exploit.action_type||'');
      bits.push(`Exploit: P${p||'?'} selected ${selected} unit${selected===1?'':'s'}${t?` via ${t}`:''}`);
    }
    const wdChecks=(Array.isArray(d.when_defeated_checks)?d.when_defeated_checks:[])
      .filter(x=>Boolean(x && x.has_when_defeated))
      .slice(0,3)
      .map(x=>{
        const likely=Boolean(x.likely_triggered);
        const unit=String(x.unit_id||x.unit_raw_id||'unit');
        const p=Number(x.player||0);
        const status=likely?'likely prompted':'no prompt seen';
        return `P${p} ${unit}: ${status}`;
      });
    if(wdChecks.length) bits.push(`When Defeated: ${wdChecks.join(' ; ')}`);
    const resourced=(Array.isArray(d.resourced_cards)?d.resourced_cards:[]).slice(0,5).map(x=>`P${x.player} ${x.card_id||x.card_raw_id||'unknown'}`);
    if(resourced.length) bits.push(`Resourced: ${resourced.join(' ; ')}`);
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
    const readyState=(Array.isArray(d.unit_ready_state_changes)?d.unit_ready_state_changes:[]).slice(0,6);
    const exhausted=readyState.filter(x=>!Boolean(x?.after_ready)).map(x=>`P${x.player} ${x.unit_id} (R->X)`);
    const readied=readyState.filter(x=>Boolean(x?.after_ready)).map(x=>`P${x.player} ${x.unit_id} (X->R)`);
    if(exhausted.length) bits.push(`Exhaust: ${exhausted.join(' ; ')}`);
    if(readied.length) bits.push(`Ready: ${readied.join(' ; ')}`);
    const leaderTriggers=nonEpicLeaderTriggersFromDetails(d).slice(0,4).map(x=>{
      const player=Number(x?.player||0);
      const leader=String(x?.leader_id||x?.leader_raw_id||'leader');
      const trig=String(x?.trigger||'leader_action');
      const from=String(x?.deploy_from||'');
      return `P${player||'?'} ${leader} ${trig}${from?` from:${from}`:''}`;
    });
    if(leaderTriggers.length) bits.push(`Leader: ${leaderTriggers.join(' ; ')}`);
    const epicTriggers=(Array.isArray(d.epic_action_triggers)?d.epic_action_triggers:[]).slice(0,4).map(x=>{
      const player=Number(x?.player||0);
      const leader=String(x?.leader_id||x?.leader_raw_id||'leader');
      return `P${player||'?'} ${leader}`;
    });
    if(epicTriggers.length) bits.push(`Epic: ${epicTriggers.join(' ; ')}`);
    const upg=(Array.isArray(d.unit_upgrade_changes)?d.unit_upgrade_changes:[]).slice(0,3).map(x=>`P${x.player} ${x.unit_id} [${fmtCards(x.before||[],2)} -> ${fmtCards(x.after||[],2)}]`);
    if(upg.length) bits.push(`Upgrades: ${upg.join(' ; ')}`);
    const capture=(Array.isArray(d.unit_capture_changes)?d.unit_capture_changes:[]).slice(0,3).map(x=>{
      const add=fmtCards(x.captured_added||[],2);
      const rel=fmtCards(x.captured_released||[],2);
      if(add!=='-' && rel!=='-') return `P${x.player} ${x.unit_id} captured:[${add}] released:[${rel}]`;
      if(add!=='-') return `P${x.player} ${x.unit_id} captured:[${add}]`;
      if(rel!=='-') return `P${x.player} ${x.unit_id} released:[${rel}]`;
      return `P${x.player} ${x.unit_id} [${fmtCards(x.before||[],2)} -> ${fmtCards(x.after||[],2)}]`;
    });
    if(capture.length) bits.push(`Capture: ${capture.join(' ; ')}`);
    const stat=(Array.isArray(d.unit_stat_changes)?d.unit_stat_changes:[]).slice(0,3).map(x=>`P${x.player} ${x.unit_id} pwr ${x.power?.before}->${x.power?.after}, hp ${x.max_hp?.before}->${x.max_hp?.after}`);
    if(stat.length) bits.push(`Stats: ${stat.join(' ; ')}`);
    const xp=(Array.isArray(d.experience_tokens_given)?d.experience_tokens_given:[]).slice(0,4).map(x=>{
      const n=Number(x?.amount||0);
      const amt=Number.isFinite(n) ? Math.max(0,n) : 0;
      return `P${x.player} ${x.unit_id} +${amt} XP`;
    });
    if(xp.length) bits.push(`Experience: ${xp.join(' ; ')}`);
    const tokenUnits=(Array.isArray(d.token_units_created)?d.token_units_created:[]).slice(0,4).map(x=>`P${x.player} ${x.unit_id}${x?.arena?` (${x.arena})`:''}`);
    if(tokenUnits.length) bits.push(`Token unit created: ${tokenUnits.join(' ; ')}`);
    return bits.join(' | ');
  };
  const fmtRes=(pb,pe)=>{
    const rb=pb?.resources||{};
    const re=pe?.resources||{};
    const beforeReady = rb.ready_cards ?? rb.available ?? rb.spendable ?? '';
    const afterReady = re.ready_cards ?? re.available ?? re.spendable ?? '';
    const beforeExhausted = rb.exhausted_cards ?? rb.spent ?? '';
    const afterExhausted = re.exhausted_cards ?? re.spent ?? '';
    const total = re.total_cards ?? rb.total_cards ?? '';
    return `ready:${beforeReady}->${afterReady}, exhausted:${beforeExhausted}->${afterExhausted}, total:${total}`;
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
    const capturedHolders=unitDetails.filter(x=>Array.isArray(x?.captives) && x.captives.length>0);
    const capturedTotal=capturedHolders.reduce((n,u)=>n + (Array.isArray(u?.captives)?u.captives.length:0),0);
    const capturedShown=capturedHolders.slice(0,3).map(u=>`${String(u?.id||u?.raw_id||'unit')}:[${fmtCards(u?.captives||[],4)}]`);
    let capturedSummary='-';
    if(capturedShown.length>0){
      capturedSummary=capturedShown.join(' ; ');
      if(capturedHolders.length>3){
        const hidden=capturedHolders.slice(3).map(u=>`${String(u?.id||u?.raw_id||'unit')}:[${fmtCards(u?.captives||[],4)}]`);
        capturedSummary += ` ; <span class="moreUnitsHint" title="${escAttr(hidden.join(' ; '))}">+${capturedHolders.length-3} more holders</span>`;
      }
    }
    return `<span class="boardLine"><strong>${label}</strong> hp:${hp}, force:${forceStatus} (used:${forceTimes}), hand:${handCount}[${handCards}], deck:${deckCount}, discard:${discardCount}, active:${active}, ready:${readyUnits.length}, exhausted:${exhaustedUnits.length}, captured:${capturedTotal}</span><span class="boardLine">units: ${fmtUnitList(unitDetails,3)}</span><span class="boardLine">captured: ${capturedSummary}</span>`;
  };
  rows.forEach(e=>{
    const tr=document.createElement('tr');
    const rawStep=String(e.step ?? '');
    const groupedStep=groupedStepLabels.get(Number(e.step));
    const stepLabel=(groupedStep && String(groupedStep)!==rawStep)
      ? `${groupedStep} <span class="muted">(raw ${rawStep})</span>`
      : (groupedStep || rawStep);
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
    const attackTarget=isAttackTargetSelection(e,actionType,actionChoice);
    const actionCell=attackTarget
      ? `<span class="attackTargetAction"><span class="attackTargetTag">attack target</span><span class="attackTargetValue">${actionChoice||actionLabel}</span></span>`
      : actionLabel;
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
    const actionDetail=fmtActionDetails(e.action_details,e);
    tr.innerHTML=`<td title="raw step ${e.step}">${stepLabel}</td><td>${e.round}</td><td>${e.phase}</td><td>${e.player}</td><td>${kindLabel}</td><td>${actionCell}</td><td>${cardCell}</td><td>${ok}</td><td>${initiativeLabel}</td><td>${fmtRes(p1b,p1)}</td><td>${fmtRes(p2b,p2)}</td><td class="boardCell">${actionDetail?`<div class="eventLine muted">${actionDetail}</div>`:''}<div>${fmtBoard('P1',p1,p1Board)}</div><div>${fmtBoard('P2',p2,p2Board)}</div></td>`;
    tb.appendChild(tr);
  });
  info.textContent=`Round ${round} (${currentRoundPage+1}/${roundNumbers.length}) - showing ${rows.length} steps`;
}

function prevRoundPage(){if(roundNumbers.length===0)return;currentRoundPage=Math.max(0,currentRoundPage-1);renderRoundPage();}
function nextRoundPage(){if(roundNumbers.length===0)return;currentRoundPage=Math.min(roundNumbers.length-1,currentRoundPage+1);renderRoundPage();}

async function runSingleMatch(){
  const msg=document.getElementById('matchMsg');
  const opening=document.getElementById('openingState');
  hideCardHover();
  persistMatchPrefs();
  msg.textContent='Running match...';
  opening.textContent='';
  try{
    const d=await api('/api/match/run',{method:'POST',body:JSON.stringify({deck_a_id:document.getElementById('deckA').value,deck_b_id:document.getElementById('deckB').value,min_cards:parseInt(document.getElementById('matchMinCards').value||'50',10),policy:document.getElementById('matchPolicy').value,mcts_iterations:parseInt(document.getElementById('matchMctsIterations').value||'16',10),mcts_max_depth:parseInt(document.getElementById('matchMctsDepth').value||'14',10),seed:parseInt(document.getElementById('matchSeed').value||'123',10)})});
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
    renderSingleMatchAnalysis(d.summary,currentMatchEvents);
    renderKeywordAudit(currentMatchEvents);
    renderValidationMatrix(currentMatchEvents);
    renderTimelineByPhase(currentMatchEvents);
  }catch(e){
    msg.textContent='Error: '+e.message;
    document.getElementById('analysis').textContent='Single Match Analysis unavailable due to match run error.';
    renderKeywordAudit([]);
    renderValidationMatrix([]);
  }
}

initUiState();
initMatchPrefBindings();
window.addEventListener('blur', hideCardHover);
window.addEventListener('scroll', hideCardHover, {passive:true});
window.addEventListener('resize', hideCardHover);
document.addEventListener('mouseleave', hideCardHover);
document.addEventListener('visibilitychange', ()=>{if(document.hidden) hideCardHover();});
refreshAll();
if(mlRefreshTimer===null){
  mlRefreshTimer=setInterval(()=>{refreshMlJobs();},2000);
}
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
    overall = sim.get("overall", {})
    audit = sim.get("illegal_move_audit", {})
    illegal_actions = int(overall.get("illegal_actions", audit.get("total_illegal_actions", 0)))
    matches_with_illegal = int(overall.get("matches_with_illegal", audit.get("matches_with_illegal", 0)))
    by_action = audit.get("by_action_type", {})
    top_illegal_actions = "-"
    if isinstance(by_action, dict) and by_action:
        top_illegal_actions = ", ".join(
            f"{k}:{v}" for k, v in sorted(by_action.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[:6]
        )
    lines = [
        f"Simulation: {sim['sim_id']}",
        f"Candidate: {sim['candidate_deck_id']} :: {sim['candidate_name']}",
        f"Policy: {sim.get('policy', 'random_legal')}",
        f"Overall win rate: {sim['overall']['win_rate']:.2%} ({sim['overall']['wins']}/{sim['overall']['games']})",
        f"Illegal actions: {illegal_actions} across {matches_with_illegal} matches",
        f"Top illegal action types: {top_illegal_actions}",
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
    mcts_iterations: int | None = None,
    mcts_max_depth: int | None = None,
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
    if mcts_iterations is not None and int(mcts_iterations) > 0:
        cmd.extend(["--mcts-iterations", str(int(mcts_iterations))])
    if mcts_max_depth is not None and int(mcts_max_depth) > 0:
        cmd.extend(["--mcts-max-depth", str(int(mcts_max_depth))])
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_int_field(payload: dict[str, Any], field: str, default: int, minimum: int | None = None) -> int:
    raw = payload.get(field, default)
    value = int(raw)
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return value


def _parse_float_field(payload: dict[str, Any], field: str, default: float, minimum: float | None = None) -> float:
    raw = payload.get(field, default)
    value = float(raw)
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return value


def _optional_text(payload: dict[str, Any], field: str) -> str | None:
    value = str(payload.get(field, "")).strip()
    return value if value else None


def _gpu_env_updates(payload: dict[str, Any]) -> dict[str, str]:
    updates: dict[str, str] = {}
    gpu_devices = _optional_text(payload, "gpu_devices")
    if gpu_devices:
        updates["CUDA_VISIBLE_DEVICES"] = gpu_devices
        updates["NVIDIA_VISIBLE_DEVICES"] = gpu_devices
    return updates


def _build_ml_job_command(payload: dict[str, Any]) -> tuple[str, list[str], dict[str, str]]:
    job_type = str(payload.get("job_type", "")).strip()
    if not job_type:
        raise ValueError("job_type is required")
    python_bin = str(os.environ.get("PYTHON_BIN", "")).strip() or sys.executable
    cmd = [python_bin, "-m", "sim_harness.cli"]
    env_updates = _gpu_env_updates(payload)

    if job_type == "sim_create":
        candidate = str(payload.get("candidate", "")).strip()
        if not candidate:
            raise ValueError("candidate is required for sim_create")
        opponents = str(payload.get("opponents", "all")).strip()
        if opponents not in {"all", "meta", "starter"}:
            raise ValueError("opponents must be all/meta/starter")
        min_cards = cli._coerce_min_cards(payload.get("min_cards", cli.DEFAULT_MIN_DECK_SIZE))
        policy = str(payload.get("policy", "random_legal")).strip()
        if policy not in cli.SUPPORTED_POLICIES:
            allowed = ", ".join(cli.SUPPORTED_POLICIES)
            raise ValueError(f"policy must be one of: {allowed}")
        games = _parse_int_field(payload, "games", 20, minimum=1)
        seed = _parse_int_field(payload, "seed", 42)
        workers = _parse_int_field(payload, "workers", 4, minimum=1)
        mcts_iterations = _parse_int_field(payload, "mcts_iterations", 16, minimum=1)
        mcts_max_depth = _parse_int_field(payload, "mcts_max_depth", 14, minimum=1)
        cmd.extend([
            "sim",
            "create",
            "--candidate",
            candidate,
            "--opponents",
            opponents,
            "--min-cards",
            str(min_cards),
            "--policy",
            policy,
            "--games",
            str(games),
            "--seed",
            str(seed),
            "--workers",
            str(workers),
            "--mcts-iterations",
            str(mcts_iterations),
            "--mcts-max-depth",
            str(mcts_max_depth),
        ])
        php_script = _optional_text(payload, "php_script")
        if php_script:
            cmd.extend(["--php-script", php_script])
        sim_id = _optional_text(payload, "sim_id")
        if sim_id:
            cmd.extend(["--sim-id", sim_id])
        return job_type, cmd, env_updates

    if job_type == "sim_shootout":
        candidate = str(payload.get("candidate", "")).strip()
        if not candidate:
            raise ValueError("candidate is required for sim_shootout")
        opponents = str(payload.get("opponents", "all")).strip()
        if opponents not in {"all", "meta", "starter"}:
            raise ValueError("opponents must be all/meta/starter")
        min_cards = cli._coerce_min_cards(payload.get("min_cards", cli.DEFAULT_MIN_DECK_SIZE))
        games = _parse_int_field(payload, "games", 30, minimum=1)
        seed = _parse_int_field(payload, "seed", 123)
        workers = _parse_int_field(payload, "workers", 6, minimum=1)
        mcts_iterations = _parse_int_field(payload, "mcts_iterations", 24, minimum=1)
        mcts_max_depth = _parse_int_field(payload, "mcts_max_depth", 18, minimum=1)
        policies = str(payload.get("policies", "random_legal,heuristic,mcts")).strip()
        cli._parse_policy_list(policies)
        cmd.extend([
            "sim",
            "shootout",
            "--candidate",
            candidate,
            "--opponents",
            opponents,
            "--min-cards",
            str(min_cards),
            "--games",
            str(games),
            "--seed",
            str(seed),
            "--workers",
            str(workers),
            "--policies",
            policies,
            "--mcts-iterations",
            str(mcts_iterations),
            "--mcts-max-depth",
            str(mcts_max_depth),
        ])
        php_script = _optional_text(payload, "php_script")
        if php_script:
            cmd.extend(["--php-script", php_script])
        out_json = _optional_text(payload, "out_json")
        if out_json:
            cmd.extend(["--out-json", out_json])
        return job_type, cmd, env_updates

    if job_type == "rl_collect":
        candidate = str(payload.get("candidate", "")).strip()
        if not candidate:
            raise ValueError("candidate is required for rl_collect")
        opponents = str(payload.get("opponents", "all")).strip()
        if opponents not in {"all", "meta", "starter"}:
            raise ValueError("opponents must be all/meta/starter")
        min_cards = cli._coerce_min_cards(payload.get("min_cards", cli.DEFAULT_MIN_DECK_SIZE))
        games = _parse_int_field(payload, "games", 25, minimum=1)
        seed = _parse_int_field(payload, "seed", 123)
        workers = _parse_int_field(payload, "workers", 6, minimum=1)
        mcts_iterations = _parse_int_field(payload, "mcts_iterations", 24, minimum=1)
        mcts_max_depth = _parse_int_field(payload, "mcts_max_depth", 18, minimum=1)
        hash_dim = _parse_int_field(payload, "hash_dim", 256, minimum=8)
        policies = str(payload.get("policies", "heuristic,mcts")).strip()
        cli._parse_policy_list(policies)
        cmd.extend([
            "rl",
            "collect",
            "--candidate",
            candidate,
            "--opponents",
            opponents,
            "--min-cards",
            str(min_cards),
            "--games",
            str(games),
            "--seed",
            str(seed),
            "--workers",
            str(workers),
            "--policies",
            policies,
            "--mcts-iterations",
            str(mcts_iterations),
            "--mcts-max-depth",
            str(mcts_max_depth),
            "--hash-dim",
            str(hash_dim),
        ])
        output_prefix = _optional_text(payload, "output_prefix")
        if output_prefix:
            cmd.extend(["--output-prefix", output_prefix])
        php_script = _optional_text(payload, "php_script")
        if php_script:
            cmd.extend(["--php-script", php_script])
        return job_type, cmd, env_updates

    if job_type == "rl_train":
        dataset = str(payload.get("dataset", "")).strip()
        vocab = str(payload.get("vocab", "")).strip()
        model_out = str(payload.get("model_out", "")).strip()
        if not dataset:
            raise ValueError("dataset is required for rl_train")
        if not vocab:
            raise ValueError("vocab is required for rl_train")
        if not model_out:
            raise ValueError("model_out is required for rl_train")
        epochs = _parse_int_field(payload, "epochs", 12, minimum=1)
        batch_size = _parse_int_field(payload, "batch_size", 512, minimum=1)
        hidden_dim = _parse_int_field(payload, "hidden_dim", 256, minimum=16)
        hidden_layers = _parse_int_field(payload, "hidden_layers", 2, minimum=1)
        seed = _parse_int_field(payload, "seed", 42)
        lr = _parse_float_field(payload, "lr", 1e-3, minimum=0.0)
        weight_decay = _parse_float_field(payload, "weight_decay", 1e-5, minimum=0.0)
        val_split = _parse_float_field(payload, "val_split", 0.1, minimum=0.0)
        dropout = _parse_float_field(payload, "dropout", 0.1, minimum=0.0)
        value_loss_weight = _parse_float_field(payload, "value_loss_weight", 1.0, minimum=0.0)
        device = str(payload.get("device", "auto")).strip().lower() or "auto"
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto/cpu/cuda")
        cmd.extend([
            "rl",
            "train",
            "--dataset",
            dataset,
            "--vocab",
            vocab,
            "--model-out",
            model_out,
            "--epochs",
            str(epochs),
            "--batch-size",
            str(batch_size),
            "--lr",
            str(lr),
            "--weight-decay",
            str(weight_decay),
            "--val-split",
            str(val_split),
            "--hidden-dim",
            str(hidden_dim),
            "--hidden-layers",
            str(hidden_layers),
            "--dropout",
            str(dropout),
            "--value-loss-weight",
            str(value_loss_weight),
            "--seed",
            str(seed),
            "--device",
            device,
        ])
        return job_type, cmd, env_updates

    raise ValueError(
        "job_type must be one of: sim_create, sim_shootout, rl_collect, rl_train"
    )


def _detect_gpus() -> tuple[list[dict[str, Any]], str]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return [], "nvidia-smi not found in this container."
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return [], err or "nvidia-smi returned a non-zero exit code."
    rows: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        text = line.strip()
        if not text:
            continue
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < 4:
            continue
        rows.append(
            {
                "index": parts[0],
                "name": parts[1],
                "memory_total_mb": parts[2],
                "driver_version": parts[3],
            }
        )
    return rows, ""


def _list_rl_artifacts(limit: int = 200) -> list[dict[str, Any]]:
    base = cli.DATA_DIR / "rl"
    if not base.exists():
        return []
    allowed_suffixes = {".jsonl", ".pt", ".pth"}
    artifacts: list[dict[str, Any]] = []
    files = sorted(base.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        if not path.is_file():
            continue
        name = path.name
        if path.suffix.lower() not in allowed_suffixes and not name.endswith(".vocab.json") and not name.endswith(".meta.json"):
            continue
        stat = path.stat()
        artifacts.append(
            {
                "path": str(path),
                "name": name,
                "size_bytes": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
        if len(artifacts) >= limit:
            break
    return artifacts


class MlJobManager:
    def __init__(self, max_jobs: int = 80, max_log_lines: int = 4000) -> None:
        self._max_jobs = int(max_jobs)
        self._max_log_lines = int(max_log_lines)
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []

    def _snapshot(self, job: dict[str, Any], include_logs: bool = False, tail: int = 800) -> dict[str, Any]:
        payload = {
            "job_id": job["job_id"],
            "job_type": job["job_type"],
            "status": job["status"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "started_at": job["started_at"],
            "ended_at": job["ended_at"],
            "exit_code": job["exit_code"],
            "pid": job["pid"],
            "error": job["error"],
            "command": list(job["command"]),
            "gpu_devices": job.get("gpu_devices", ""),
            "stop_requested": bool(job.get("stop_requested", False)),
        }
        if include_logs:
            logs = job.get("logs", [])
            if tail > 0:
                payload["logs"] = list(logs[-tail:])
            else:
                payload["logs"] = list(logs)
        return payload

    def _append_log_locked(self, job: dict[str, Any], line: str) -> None:
        logs = job.setdefault("logs", [])
        logs.append(line)
        over = len(logs) - self._max_log_lines
        if over > 0:
            del logs[:over]

    def _prune_locked(self) -> None:
        active = {"queued", "running", "stopping"}
        while len(self._order) > self._max_jobs:
            oldest = self._order[0]
            job = self._jobs.get(oldest)
            if not job:
                self._order.pop(0)
                continue
            if str(job.get("status")) in active:
                break
            self._order.pop(0)
            self._jobs.pop(oldest, None)

    def create(self, job_type: str, command: list[str], env_updates: dict[str, str]) -> dict[str, Any]:
        if not command:
            raise ValueError("job command cannot be empty")
        now = _now_iso()
        job_id = f"job-{uuid.uuid4().hex[:10]}"
        record: dict[str, Any] = {
            "job_id": job_id,
            "job_type": job_type,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "started_at": "",
            "ended_at": "",
            "exit_code": None,
            "pid": None,
            "error": "",
            "command": list(command),
            "env_updates": dict(env_updates),
            "gpu_devices": env_updates.get("CUDA_VISIBLE_DEVICES", ""),
            "stop_requested": False,
            "logs": [f"$ {' '.join(shlex.quote(part) for part in command)}"],
            "_proc": None,
        }
        with self._lock:
            self._jobs[job_id] = record
            self._order.append(job_id)
            self._prune_locked()
        threading.Thread(target=self._run, args=(job_id,), daemon=True).start()
        with self._lock:
            return self._snapshot(self._jobs[job_id], include_logs=False)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if job["status"] != "queued":
                return
            job["status"] = "running"
            job["started_at"] = _now_iso()
            job["updated_at"] = job["started_at"]
            command = list(job["command"])
            env_updates = dict(job.get("env_updates", {}))
        env = dict(os.environ)
        env.update(env_updates)
        env["PYTHONUNBUFFERED"] = "1"
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(Path.cwd()),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                job["_proc"] = proc
                job["pid"] = int(proc.pid)
                job["updated_at"] = _now_iso()
            if proc.stdout is not None:
                for raw in proc.stdout:
                    line = raw.rstrip("\r\n")
                    with self._lock:
                        job = self._jobs.get(job_id)
                        if not job:
                            break
                        self._append_log_locked(job, line)
                        job["updated_at"] = _now_iso()
                        should_stop = bool(job.get("stop_requested"))
                    if should_stop and proc.poll() is None:
                        try:
                            proc.terminate()
                        except Exception:  # noqa: BLE001
                            pass
            code = proc.wait()
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                job["exit_code"] = int(code)
                if bool(job.get("stop_requested")):
                    job["status"] = "stopped"
                else:
                    job["status"] = "succeeded" if int(code) == 0 else "failed"
                job["ended_at"] = _now_iso()
                job["updated_at"] = job["ended_at"]
                job["_proc"] = None
                self._prune_locked()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                job["status"] = "failed"
                job["error"] = str(exc)
                self._append_log_locked(job, f"[runner_error] {exc}")
                job["exit_code"] = -1
                job["ended_at"] = _now_iso()
                job["updated_at"] = job["ended_at"]
                job["_proc"] = None
                self._prune_locked()
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(self._order)
            ids.reverse()
            return [self._snapshot(self._jobs[job_id], include_logs=False) for job_id in ids if job_id in self._jobs]

    def get(self, job_id: str, include_logs: bool = True) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            return self._snapshot(job, include_logs=include_logs)

    def stop(self, job_id: str) -> dict[str, Any]:
        proc: subprocess.Popen[str] | None = None
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            status = str(job.get("status", ""))
            if status in {"succeeded", "failed", "stopped"}:
                return self._snapshot(job, include_logs=False)
            job["stop_requested"] = True
            job["updated_at"] = _now_iso()
            if status == "queued":
                job["status"] = "stopped"
                job["ended_at"] = job["updated_at"]
                job["exit_code"] = -15
            else:
                job["status"] = "stopping"
                proc = job.get("_proc")
            snapshot = self._snapshot(job, include_logs=False)
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        return snapshot


ML_JOB_MANAGER = MlJobManager()


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
                        "python_executable": sys.executable,
                        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
                        "deck_min_cards_default": cli.DEFAULT_MIN_DECK_SIZE,
                        "deck_min_cards_options": sorted(cli.SUPPORTED_MIN_DECK_SIZES),
                    },
                })
                return
            if path == "/api/ml/info":
                gpus, gpu_error = _detect_gpus()
                self._send_json(
                    {
                        "python_executable": sys.executable,
                        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
                        "gpus": gpus,
                        "gpu_error": gpu_error,
                        "rl_artifacts": _list_rl_artifacts(),
                    }
                )
                return
            if path == "/api/ml/jobs":
                self._send_json({"jobs": ML_JOB_MANAGER.list()})
                return
            if path.startswith("/api/ml/jobs/"):
                job_id = path[len("/api/ml/jobs/") :].strip("/")
                if not job_id:
                    raise ValueError("job id is required")
                try:
                    job = ML_JOB_MANAGER.get(job_id, include_logs=True)
                except KeyError as exc:
                    raise ValueError(f"Unknown job id: {job_id}") from exc
                self._send_json({"job": job})
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
            if path == "/api/ml/jobs":
                payload = self._read_json()
                job_type, command, env_updates = _build_ml_job_command(payload)
                job = ML_JOB_MANAGER.create(job_type=job_type, command=command, env_updates=env_updates)
                self._send_json({"ok": True, "job": job})
                return
            if path.startswith("/api/ml/jobs/") and path.endswith("/stop"):
                job_id = path[len("/api/ml/jobs/") : -len("/stop")].strip("/")
                if not job_id:
                    raise ValueError("job id is required")
                try:
                    job = ML_JOB_MANAGER.stop(job_id)
                except KeyError as exc:
                    raise ValueError(f"Unknown job id: {job_id}") from exc
                self._send_json({"ok": True, "job": job})
                return
            if path.startswith("/api/decks/") and path.endswith("/rename"):
                deck_id = path[len("/api/decks/") : -len("/rename")].strip("/")
                if not deck_id:
                    raise ValueError("deck id is required")
                payload = self._read_json()
                name = str(payload.get("name", "")).strip()
                if not name:
                    raise ValueError("name is required")
                author_raw = payload.get("author")
                author = None if author_raw is None else str(author_raw)
                updated = cli._rename_deck(deck_id, name=name, author=author)
                self._send_json({"ok": True, "deck_id": updated.deck_id, "name": updated.name, "author": updated.author})
                return
            if path == "/api/decks":
                payload = self._read_json()
                swudb = payload.get("swudb")
                if not isinstance(swudb, dict):
                    raise ValueError("swudb must be a JSON object")
                swudb, warnings = cli._normalize_swudb_deck(swudb)
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
                self._send_json({"ok": True, "deck_id": deck.deck_id, "name": deck.name, "warnings": warnings})
                return

            if path == "/api/simulations":
                payload = self._read_json()
                policy = str(payload.get("policy", "random_legal"))
                if policy not in {"random_non_pass", "random_legal", "first_non_pass", "heuristic", "mcts"}:
                    raise ValueError("policy must be random_non_pass/random_legal/first_non_pass/heuristic/mcts")
                args = type("Args", (), {
                    "candidate": payload.get("candidate"),
                    "opponents": payload.get("opponents", "all"),
                    "min_cards": cli._coerce_min_cards(payload.get("min_cards", cli.DEFAULT_MIN_DECK_SIZE)),
                    "policy": policy,
                    "mcts_iterations": int(payload.get("mcts_iterations", 16)),
                    "mcts_max_depth": int(payload.get("mcts_max_depth", 14)),
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
                min_cards = cli._coerce_min_cards(payload.get("min_cards", cli.DEFAULT_MIN_DECK_SIZE))
                cli._assert_min_deck_size(deck_a.swudb, min_cards, f"Deck '{deck_a.deck_id}'")
                cli._assert_min_deck_size(deck_b.swudb, min_cards, f"Deck '{deck_b.deck_id}'")
                seed = int(payload.get("seed", 123))
                max_actions_raw = payload.get("max_actions", None)
                max_actions = None
                if max_actions_raw is not None:
                    parsed = int(max_actions_raw)
                    if parsed > 0:
                        max_actions = parsed
                policy = str(payload.get("policy", "random_legal"))
                if policy not in {"random_non_pass", "random_legal", "first_non_pass", "heuristic", "mcts"}:
                    raise ValueError("policy must be random_non_pass/random_legal/first_non_pass/heuristic/mcts")
                mcts_iterations = payload.get("mcts_iterations", 16)
                mcts_max_depth = payload.get("mcts_max_depth", 14)
                match = _run_single_match(
                    deck_a,
                    deck_b,
                    seed,
                    max_actions,
                    policy,
                    mcts_iterations=int(mcts_iterations) if mcts_iterations is not None else None,
                    mcts_max_depth=int(mcts_max_depth) if mcts_max_depth is not None else None,
                )
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
                        "min_cards": min_cards,
                        "policy": match.get("stats", {}).get("policy"),
                        "events": match.get("stats", {}).get("events", 0),
                        "illegal_actions": match.get("stats", {}).get("illegal_actions", 0),
                        "forced_passes": match.get("stats", {}).get("forced_passes", 0),
                        "leader_action_triggers": match.get("stats", {}).get("leader_action_triggers", 0),
                        "epic_action_triggers": match.get("stats", {}).get("epic_action_triggers", 0),
                        "mcts_iterations": match.get("stats", {}).get("mcts_iterations", 0),
                        "mcts_max_depth": match.get("stats", {}).get("mcts_max_depth", 0),
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

    def do_PUT(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if path.startswith("/api/decks/"):
                deck_id = path.rsplit("/", 1)[-1]
                if not deck_id:
                    raise ValueError("deck id is required")
                payload = self._read_json()
                swudb = payload.get("swudb")
                if not isinstance(swudb, dict):
                    raise ValueError("swudb must be a JSON object")
                swudb, warnings = cli._normalize_swudb_deck(swudb)
                cli._validate_swudb_deck(swudb)
                pool_raw = payload.get("pool", None)
                pool = None
                if pool_raw is not None:
                    pool = str(pool_raw).strip()
                    if pool not in {"candidate", "meta", "starter"}:
                        raise ValueError("pool must be candidate/meta/starter")
                updated = cli._update_deck(deck_id, swudb=swudb, pool=pool)
                self._send_json({"ok": True, "deck_id": updated.deck_id, "name": updated.name, "pool": updated.pool, "warnings": warnings})
                return
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if path.startswith("/api/decks/"):
                deck_id = path.rsplit("/", 1)[-1]
                if not deck_id:
                    raise ValueError("deck id is required")
                removed = cli._delete_deck(deck_id)
                self._send_json({"ok": True, "deck_id": removed.deck_id, "name": removed.name})
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
