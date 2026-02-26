<?php
require_once __DIR__ . "/../Libraries/CoreLibraries.php";
require_once __DIR__ . "/../WriteLog.php";

$options = getopt("", ["seed:", "deck-a:", "deck-b:", "match-id::", "log-format::"]);
$seed = $options["seed"] ?? "0";
$deckA = $options["deck-a"] ?? "deck_a";
$deckB = $options["deck-b"] ?? "deck_b";
$matchID = intval($options["match-id"] ?? 0);
$logFormat = $options["log-format"] ?? "json";

$gameName = "sim_" . $matchID;
$GLOBALS["gameName"] = $gameName;
if(!is_dir("./Games/$gameName")) mkdir("./Games/$gameName", 0700, true);
CreateLog($gameName);

SetMatchSeed($seed, $gameName);
if($logFormat === "json") SetStructuredLogMode(true);

$turn = ["START", "0"];
$GLOBALS["turn"] = $turn;
$rngTurns = 4 + (GetRandom(0, 10));
for($t = 1; $t <= $rngTurns; ++$t) {
  $GLOBALS["turn"] = ["TURN", strval($t)];
  $actor = ($t % 2 == 0) ? 2 : 1;
  WriteLog("Simulated turn $t", $actor, false, "./", false, ["action" => "simulate_turn", "result" => "ok"]);
}
$winner = GetRandom(1, 2);

$response = [
  "match_id" => $matchID,
  "seed" => intval($seed),
  "winner" => $winner,
  "turns" => $rngTurns,
  "deck_a" => $deckA,
  "deck_b" => $deckB,
  "log_path" => LogPath($gameName),
];

echo json_encode($response, JSON_UNESCAPED_SLASHES);
