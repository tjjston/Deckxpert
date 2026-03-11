<?php
session_start();

ob_start();
include "HostFiles/Redirector.php";
include "Libraries/HTTPLibraries.php";
include_once "WriteLog.php";
ob_end_clean();

function FailAndRedirect(string $message): void
{
  http_response_code(400);
  $safeMessage = htmlspecialchars($message, ENT_QUOTES);
  echo "<!doctype html><html><head><meta charset='utf-8'><title>Sim Replay Error</title></head><body style='font-family:system-ui,-apple-system,sans-serif;background:#111;color:#eee;padding:18px;'><h3 style='margin-top:0;'>Sim Replay Error</h3><p>{$safeMessage}</p></body></html>";
  exit;
}

function TrimString(mixed $value): string
{
  return trim(strval($value ?? ""));
}

function ResolvePhpCliBinary(): string
{
  $envPhp = TrimString(getenv("PHP_BIN"));
  if ($envPhp !== "" && is_executable($envPhp)) return $envPhp;

  $phpBinary = defined("PHP_BINARY") ? TrimString(PHP_BINARY) : "";
  if (
    $phpBinary !== ""
    && is_executable($phpBinary)
    && preg_match('/php/i', basename($phpBinary)) === 1
  ) {
    return $phpBinary;
  }

  $pathCandidates = ["/usr/bin/php", "/usr/local/bin/php"];
  foreach ($pathCandidates as $candidate) {
    if (is_executable($candidate)) return $candidate;
  }

  $nameCandidates = ["php", "php8.4", "php8.3", "php8.2", "php8.1", "php8.0", "php7.4"];
  if (function_exists("shell_exec")) {
    foreach ($nameCandidates as $name) {
      $resolved = TrimString(shell_exec("command -v " . escapeshellarg($name) . " 2>/dev/null"));
      if ($resolved !== "") return $resolved;
    }
  }

  return "";
}

function LoadDeckMap(string $path): array
{
  if (!file_exists($path)) return [];
  $json = file_get_contents($path);
  if ($json === false) return [];
  $decoded = json_decode($json, true);
  if (!is_array($decoded)) return [];
  $deckMap = [];
  foreach ($decoded as $entry) {
    if (!is_array($entry)) continue;
    $deckId = TrimString($entry["deck_id"] ?? "");
    if ($deckId === "") continue;
    $deckMap[$deckId] = $entry;
  }
  return $deckMap;
}

function PushCardCopies(array &$cards, mixed $cardId, mixed $count): void
{
  $id = TrimString($cardId);
  $copies = max(0, intval($count ?? 0));
  if ($id === "" || $copies <= 0) return;
  for ($i = 0; $i < $copies; ++$i) {
    $cards[] = $id;
  }
}

function DeckEntryToHeadlessString(array $deckEntry): string
{
  $swudb = $deckEntry["swudb"] ?? null;
  if (!is_array($swudb)) {
    throw new RuntimeException("Deck is missing SWUDB payload.");
  }

  $material = [];
  $leader = $swudb["leader"] ?? null;
  $base = $swudb["base"] ?? null;
  if (is_array($leader)) {
    PushCardCopies($material, $leader["id"] ?? "", max(1, intval($leader["count"] ?? 1)));
  }
  if (is_array($base)) {
    PushCardCopies($material, $base["id"] ?? "", max(1, intval($base["count"] ?? 1)));
  }

  if (count($material) < 2) {
    throw new RuntimeException("Deck material must include leader and base.");
  }

  $main = [];
  $deckCards = $swudb["deck"] ?? [];
  if (!is_array($deckCards)) $deckCards = [];
  foreach ($deckCards as $card) {
    if (!is_array($card)) continue;
    PushCardCopies($main, $card["id"] ?? "", $card["count"] ?? 0);
  }
  if (count($main) === 0) {
    throw new RuntimeException("Deck has no main deck cards.");
  }

  return implode(" ", $material) . "\n" . implode(" ", $main);
}

function DecodeRunnerPayload(string $stdout, string $stderr): array
{
  $tryDecode = function (string $text): array {
    $text = trim($text);
    if ($text === "") return [];
    $decoded = json_decode($text, true);
    if (is_array($decoded)) return $decoded;
    $firstBrace = strpos($text, "{");
    if ($firstBrace === false) return [];
    $decoded = json_decode(substr($text, $firstBrace), true);
    if (!is_array($decoded)) return [];
    return $decoded;
  };

  $fromStdout = $tryDecode($stdout);
  if (count($fromStdout) > 0) return $fromStdout;
  return $tryDecode($stderr);
}

function ToAbsolutePath(string $path, string $baseDir): string
{
  $path = TrimString($path);
  if ($path === "") return "";
  if (str_starts_with($path, "/")) return $path;
  if (str_starts_with($path, "./")) $path = substr($path, 2);
  return rtrim($baseDir, "/") . "/" . ltrim($path, "/");
}

$userId = TrimString($_SESSION["userid"] ?? "");
if ($userId === "") FailAndRedirect("You must be logged in to generate bot replays.");

$deckAId = TrimString(TryPOST("deckA", TryGet("deckA", "")));
$deckBId = TrimString(TryPOST("deckB", TryGet("deckB", "")));
if ($deckAId === "" || $deckBId === "") {
  FailAndRedirect("Select both Deck A and Deck B.");
}

$policy = strtolower(TrimString(TryPOST("policy", TryGet("policy", "heuristic"))));
$allowedPolicies = ["heuristic", "random_legal", "random_non_pass", "first_non_pass", "mcts"];
if (!in_array($policy, $allowedPolicies, true)) $policy = "heuristic";

$seedInput = TrimString(TryPOST("seed", TryGet("seed", "")));
if ($seedInput === "" || !preg_match('/^-?\d+$/', $seedInput)) {
  $seed = random_int(1, 2147483647);
} else {
  $seed = intval($seedInput);
  if ($seed === 0) $seed = random_int(1, 2147483647);
}

$maxActionsInput = TrimString(TryPOST("maxActions", TryGet("maxActions", TryPOST("max_actions", TryGet("max_actions", "")))));
$maxActions = 4000;
if ($maxActionsInput !== "" && preg_match('/^\d+$/', $maxActionsInput)) {
  $parsedMaxActions = intval($maxActionsInput);
  if ($parsedMaxActions > 0) {
    $maxActions = max(50, min(4000, $parsedMaxActions));
  }
}

$deckMap = LoadDeckMap(__DIR__ . "/sim_harness/data/decks.json");
if (!isset($deckMap[$deckAId]) || !isset($deckMap[$deckBId])) {
  FailAndRedirect("One or both selected decks are unavailable.");
}

try {
  $deckAText = DeckEntryToHeadlessString($deckMap[$deckAId]);
  $deckBText = DeckEntryToHeadlessString($deckMap[$deckBId]);
} catch (Throwable $e) {
  FailAndRedirect("Failed to build decks for simulation: " . $e->getMessage());
}

$phpBin = ResolvePhpCliBinary();
if ($phpBin === "") FailAndRedirect("PHP CLI binary not found. Install php-cli or set PHP_BIN.");

$runnerPath = __DIR__ . "/sim_harness/php_match_runner.php";
if (!file_exists($runnerPath)) FailAndRedirect("Simulation runner script was not found.");

$runnerRuntimeDir = __DIR__ . "/sim_harness/runtime";
if (!file_exists($runnerRuntimeDir) && !mkdir($runnerRuntimeDir, 0777, true)) {
  FailAndRedirect("Unable to create simulation runtime directory.");
}
$runnerCwd = __DIR__;

$matchId = intval(round(microtime(true) * 1000)) + random_int(0, 999);
$command = [
  $phpBin,
  $runnerPath,
  "--seed",
  strval($seed),
  "--deck-a-b64",
  base64_encode($deckAText),
  "--deck-b-b64",
  base64_encode($deckBText),
  "--match-id",
  strval($matchId),
  "--policy",
  $policy,
  "--max-actions",
  strval($maxActions),
  "--replay-only",
];
if ($policy === "mcts") {
  $command[] = "--mcts-iterations";
  $command[] = "24";
  $command[] = "--mcts-max-depth";
  $command[] = "18";
}

$descriptors = [
  1 => ["pipe", "w"],
  2 => ["pipe", "w"],
];
$env = getenv();
if (!is_array($env)) $env = [];
$env["XDEBUG_MODE"] = "off";
$env["SIM_RUNNER_BASE_DIR"] = "sim_harness/runtime";
$process = proc_open($command, $descriptors, $pipes, $runnerCwd, $env);
if (!is_resource($process)) {
  FailAndRedirect("Unable to start simulation process.");
}

$stdout = stream_get_contents($pipes[1]);
fclose($pipes[1]);
$stderr = stream_get_contents($pipes[2]);
fclose($pipes[2]);
$exitCode = proc_close($process);

if ($exitCode !== 0) {
  $summary = TrimString($stderr);
  if ($summary === "") $summary = TrimString($stdout);
  if ($summary !== "" && strlen($summary) > 300) $summary = substr($summary, 0, 300) . "...";
  FailAndRedirect("Bot simulation failed (exit {$exitCode}). " . ($summary !== "" ? $summary : "No output."));
}

$payload = DecodeRunnerPayload(strval($stdout), strval($stderr));
if (count($payload) === 0) {
  FailAndRedirect("Simulation returned invalid output.");
}

$replayInfo = $payload["replay"] ?? [];
$origPath = ToAbsolutePath(strval($replayInfo["orig_gamestate_path"] ?? ""), __DIR__);
$commandPath = ToAbsolutePath(strval($replayInfo["commandfile_path"] ?? ""), __DIR__);
if ($origPath === "" || !file_exists($origPath)) {
  FailAndRedirect("Simulation did not produce an original gamestate replay artifact.");
}
if ($commandPath === "" || !file_exists($commandPath)) {
  FailAndRedirect("Simulation did not produce a replay command artifact.");
}

$replaysRoot = "./Replays/" . $userId . "/";
if (!file_exists($replaysRoot) && !mkdir($replaysRoot, 0777, true)) {
  FailAndRedirect("Unable to create user replay directory.");
}

$counterPath = $replaysRoot . "counter.txt";
$counter = 1;
if (file_exists($counterPath)) {
  $counter = max(1, intval(trim(strval(file_get_contents($counterPath)))));
}

$replayNumber = $counter;
$targetDir = $replaysRoot . $replayNumber . "/";
while (file_exists($targetDir)) {
  ++$replayNumber;
  $targetDir = $replaysRoot . $replayNumber . "/";
}
if (!mkdir($targetDir, 0777, true)) {
  FailAndRedirect("Unable to create replay folder.");
}

if (!copy($origPath, $targetDir . "origGamestate.txt")) {
  FailAndRedirect("Failed to copy original gamestate into replay folder.");
}
if (!copy($commandPath, $targetDir . "replayCommands.txt")) {
  FailAndRedirect("Failed to copy replay commands into replay folder.");
}

$metadata = [
  "created_at_ms" => intval(round(microtime(true) * 1000)),
  "source" => "sim_harness",
  "deck_a_id" => $deckAId,
  "deck_b_id" => $deckBId,
  "deck_a_name" => TrimString($deckMap[$deckAId]["swudb"]["metadata"]["name"] ?? $deckAId),
  "deck_b_name" => TrimString($deckMap[$deckBId]["swudb"]["metadata"]["name"] ?? $deckBId),
  "policy" => $policy,
  "seed" => $seed,
  "max_actions" => $maxActions,
  "winner" => intval($payload["winner"] ?? 0),
  "turns" => intval($payload["turns"] ?? 0),
  "illegal_actions" => intval($payload["stats"]["illegal_actions"] ?? 0),
];
file_put_contents($targetDir . "metadata.json", json_encode($metadata, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));

file_put_contents($counterPath, strval($replayNumber + 1));

header("Location: CreateReplayGame.php?replayNumber=" . $replayNumber);
exit;
