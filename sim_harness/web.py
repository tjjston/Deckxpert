from __future__ import annotations

import json
import subprocess
import shutil
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import cli

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
<label>Seed</label><input id=\"matchSeed\" type=\"number\" value=\"123\"/>
<label>Max actions (optional safety cap)</label><input id=\"matchMaxActions\" type=\"number\" placeholder=\"unlimited\"/>
<button onclick=\"runSingleMatch()\">Run Match</button><div id=\"matchMsg\" class=\"muted\"></div></div>

<div class=\"card\"><h3>Settings</h3><div id=\"settings\" class=\"muted\"></div></div>
</aside><main>
<div class=\"grid\">
<div class=\"card\"><h3>Decks</h3><table><thead><tr><th>ID</th><th>Pool</th><th>Name</th><th>Cards</th><th></th></tr></thead><tbody id=\"decksTbody\"></tbody></table></div>
<div class=\"card\"><h3>Simulations</h3><table><thead><tr><th>ID</th><th>Candidate</th><th>Winrate</th><th>Games</th><th></th></tr></thead><tbody id=\"simsTbody\"></tbody></table></div>
</div>
<div class=\"card\"><h3>Simulation Analysis</h3><pre id=\"analysis\">Select a simulation to inspect analysis.</pre></div>
<div class=\"card\"><h3>Deck JSON Viewer (SWUDB)</h3><pre id=\"deckView\">Select a deck to view SWUDB JSON.</pre></div>
<div class=\"card\"><h3>Single Match Timeline</h3><pre id=\"matchSummary\">Run a single match to see turn-by-turn legality.</pre><table><thead><tr><th>Step</th><th>Round</th><th>Phase</th><th>Player</th><th>Action</th><th>Card</th><th>Legal?</th><th>Effects</th></tr></thead><tbody id=\"matchTbody\"></tbody></table></div>
</main></div>
<script>
async function api(path, opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});const t=await r.text();let d={};try{d=t?JSON.parse(t):{}}catch{d={raw:t}}if(!r.ok)throw new Error(d.error||t||r.statusText);return d;}
async function refreshAll(){const s=await api('/api/state');renderDecks(s.decks);renderSims(s.simulations);renderCandidates(s.decks);renderMatchDecks(s.decks);document.getElementById('settings').textContent=JSON.stringify(s.settings,null,2);}
function fill(sel,decks,filter){sel.innerHTML='';decks.filter(filter).forEach(d=>{const o=document.createElement('option');o.value=d.deck_id;o.textContent=`${d.deck_id} :: ${d.name}`;sel.appendChild(o);});}
function renderCandidates(decks){fill(document.getElementById('candidate'),decks,d=>d.pool==='candidate');}
function renderMatchDecks(decks){fill(document.getElementById('deckA'),decks,_=>true);fill(document.getElementById('deckB'),decks,_=>true);}
function renderDecks(decks){const tb=document.getElementById('decksTbody');tb.innerHTML='';decks.forEach(d=>{const tr=document.createElement('tr');tr.innerHTML=`<td>${d.deck_id}</td><td>${d.pool}</td><td>${d.name}</td><td>${d.deck_size}</td><td><button onclick=\"showDeck('${d.deck_id}')\">View</button></td>`;tb.appendChild(tr);});}
function renderSims(sims){const tb=document.getElementById('simsTbody');tb.innerHTML='';sims.forEach(s=>{const tr=document.createElement('tr');const wr=((s.overall?.win_rate||0)*100).toFixed(2)+'%';tr.innerHTML=`<td>${s.sim_id}</td><td>${s.candidate_deck_id}</td><td>${wr}</td><td>${s.overall?.games||0}</td><td><button onclick=\"showSim('${s.sim_id}')\">Analyze</button></td>`;tb.appendChild(tr);});}
async function uploadDeck(){const msg=document.getElementById('uploadMsg');msg.textContent='Uploading...';try{await api('/api/decks',{method:'POST',body:JSON.stringify({deck_id:document.getElementById('deckId').value||null,pool:document.getElementById('pool').value,swudb:JSON.parse(document.getElementById('deckJson').value)})});msg.textContent='Uploaded';await refreshAll();}catch(e){msg.textContent='Error: '+e.message;}}
async function createSimulation(){const msg=document.getElementById('simMsg');msg.textContent='Running...';try{const out=await api('/api/simulations',{method:'POST',body:JSON.stringify({candidate:document.getElementById('candidate').value,opponents:document.getElementById('opponents').value,games:parseInt(document.getElementById('games').value||'20',10),seed:parseInt(document.getElementById('seed').value||'42',10),workers:parseInt(document.getElementById('workers').value||'4',10),php_script:document.getElementById('phpScript').value||null,sim_id:document.getElementById('simId').value||null})});msg.textContent='Created '+out.sim_id;await refreshAll();await showSim(out.sim_id);}catch(e){msg.textContent='Error: '+e.message;}}
async function showDeck(id){const d=await api('/api/decks/'+encodeURIComponent(id));document.getElementById('deckView').textContent=JSON.stringify(d.swudb,null,2);}
async function showSim(id){const d=await api('/api/simulations/'+encodeURIComponent(id)+'/analysis');document.getElementById('analysis').textContent=d.text;}
async function runSingleMatch(){const msg=document.getElementById('matchMsg');msg.textContent='Running match...';try{const d=await api('/api/match/run',{method:'POST',body:JSON.stringify({deck_a_id:document.getElementById('deckA').value,deck_b_id:document.getElementById('deckB').value,seed:parseInt(document.getElementById('matchSeed').value||'123',10),max_actions:document.getElementById('matchMaxActions').value})});msg.textContent='Done';document.getElementById('matchSummary').textContent=JSON.stringify(d.summary,null,2);const tb=document.getElementById('matchTbody');tb.innerHTML='';(d.events||[]).forEach(e=>{const tr=document.createElement('tr');const ok=e.apply_ok?'<span class="ok">ok</span>':'<span class="bad">illegal</span>';const eff=e.effects?.['player_'+e.player]||{};tr.innerHTML=`<td>${e.step}</td><td>${e.round}</td><td>${e.phase}</td><td>${e.player}</td><td>${e.action?.type||''}</td><td>${e.card?.id||''} (c:${e.card?.cost??''}, t:${e.card?.type||''})</td><td>${ok}</td><td>resΔ:${eff.resources_available_delta??''}, handΔ:${eff.hand_count_delta??''}, deckΔ:${eff.deck_count_delta??''}, discardΔ:${eff.discard_count_delta??''}</td>`;tb.appendChild(tr);});}catch(e){msg.textContent='Error: '+e.message;}}
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


def _run_single_match(deck_a: cli.DeckRecord, deck_b: cli.DeckRecord, seed: int, max_actions: int | None = None) -> dict[str, Any]:
    php_bin = shutil.which("php")
    if php_bin is None:
        raise ValueError(
            "PHP CLI binary was not found on PATH. Install PHP CLI or add it to PATH, then retry."
        )

    cmd = [
        php_bin,
        "sim_harness/php_match_runner.php",
        "--seed",
        str(seed),
        "--deck-a",
        _deck_to_runner_string(deck_a.swudb),
        "--deck-b",
        _deck_to_runner_string(deck_b.swudb),
        "--match-id",
        str(uuid.uuid4().int % 1_000_000),
    ]
    if max_actions is not None:
        cmd.extend(["--max-actions", str(max_actions)])
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ValueError(f"PHP runner failed: {stderr or 'unknown error'}") from exc

    return json.loads(proc.stdout)


class SimWebHandler(BaseHTTPRequestHandler):
    server_version = "DeckxpertSimUI/2.0"

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
            if path == "/":
                self._send_html(INDEX_HTML)
                return
            if path == "/api/state":
                decks = cli._load_decks()
                sims = cli._load_sims()
                self._send_json({
                    "decks": [_deck_to_json(d) for d in decks],
                    "simulations": sims,
                    "settings": {
                        "data_dir": str(cli.DATA_DIR),
                        "decks_file": str(cli.DECKS_FILE),
                        "sims_file": str(cli.SIMS_FILE),
                        "cwd": str(Path.cwd()),
                        "php_bin": shutil.which("php") or "not_found",
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
                max_actions_raw = payload.get("max_actions")
                max_actions: int | None = None
                if max_actions_raw not in {None, ""}:
                    max_actions = max(1, int(max_actions_raw))
                match = _run_single_match(deck_a, deck_b, seed, max_actions)
                self._send_json({
                    "ok": True,
                    "summary": {
                        "match_id": match.get("match_id"),
                        "winner": match.get("winner"),
                        "turns": match.get("turns"),
                        "events": match.get("stats", {}).get("events", 0),
                        "illegal_actions": match.get("stats", {}).get("illegal_actions", 0),
                        "game_over": match.get("stats", {}).get("game_over", False),
                    },
                    "events": match.get("events", []),
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
