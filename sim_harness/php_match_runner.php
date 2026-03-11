<?php

declare(strict_types=1);

error_reporting(0);
ini_set('display_errors', '0');
ini_set('display_startup_errors', '0');
if (!defined('HEADLESS_SIM')) define('HEADLESS_SIM', true);

$GLOBALS['__runner_finished'] = false;
$GLOBALS['__runner_checkpoint'] = 'boot';
$GLOBALS['__runner_last_action'] = null;

set_exception_handler(function (Throwable $e): void {
  $GLOBALS['__runner_finished'] = true;
  $payload = [
    'error' => 'unhandled_exception',
    'message' => $e->getMessage(),
    'file' => $e->getFile(),
    'line' => $e->getLine(),
  ];
  $json = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
  if ($json === false) $json = '{"error":"unhandled_exception","message":"json_encode_failed"}';
  file_put_contents('php://stderr', $json . PHP_EOL);
  echo $json;
  exit(255);
});

register_shutdown_function(function (): void {
  $err = error_get_last();
  if ($err === null) return;
  $fatalTypes = [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR];
  if (!in_array($err['type'] ?? 0, $fatalTypes, true)) return;
  $GLOBALS['__runner_finished'] = true;
  $payload = [
    'error' => 'fatal_error',
    'message' => strval($err['message'] ?? 'unknown'),
    'file' => strval($err['file'] ?? ''),
    'line' => intval($err['line'] ?? 0),
  ];
  $json = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
  if ($json === false) $json = '{"error":"fatal_error","message":"json_encode_failed"}';
  file_put_contents('php://stderr', $json . PHP_EOL);
  echo $json;
});

register_shutdown_function(function (): void {
  if (($GLOBALS['__runner_finished'] ?? false) === true) return;
  $payload = [
    'error' => 'premature_exit',
    'message' => 'Runner exited before emitting final payload.',
    'checkpoint' => strval($GLOBALS['__runner_checkpoint'] ?? 'unknown'),
    'current_round' => intval($GLOBALS['currentRound'] ?? 0),
    'current_player' => intval($GLOBALS['currentPlayer'] ?? 0),
    'turn' => $GLOBALS['turn'] ?? [],
    'last_action' => $GLOBALS['__runner_last_action'] ?? null,
  ];
  $json = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
  if ($json === false) $json = '{"error":"premature_exit","message":"json_encode_failed"}';
  file_put_contents('php://stderr', $json . PHP_EOL);
  echo $json;
});

require_once __DIR__ . '/../Engine/HeadlessEngine.php';
$GLOBALS['__runner_checkpoint'] = 'required_engine';

$options = getopt('', ['seed:', 'deck-a:', 'deck-b:', 'deck-a-b64:', 'deck-b-b64:', 'match-id:', 'log-format:', 'max-actions:', 'policy:', 'mcts-iterations:', 'mcts-max-depth:', 'replay-only']);
$seed = intval($options['seed'] ?? 0);
$deckAInput = strval($options['deck-a'] ?? 'deck_a');
$deckBInput = strval($options['deck-b'] ?? 'deck_b');
$deckAB64 = $options['deck-a-b64'] ?? null;
$deckBB64 = $options['deck-b-b64'] ?? null;
if (is_string($deckAB64) && $deckAB64 !== '') {
  $decoded = base64_decode($deckAB64, true);
  if ($decoded !== false) $deckAInput = $decoded;
}
if (is_string($deckBB64) && $deckBB64 !== '') {
  $decoded = base64_decode($deckBB64, true);
  if ($decoded !== false) $deckBInput = $decoded;
}
$matchID = intval($options['match-id'] ?? 0);
$logFormat = $options['log-format'] ?? 'json';
$maxActions = max(0, intval($options['max-actions'] ?? 0));
$hardActionCap = 20000;
$actionCap = $maxActions > 0 ? min($maxActions, $hardActionCap) : $hardActionCap;
$replayOnly = array_key_exists('replay-only', $options);
$includeDetailedEvents = !$replayOnly;
$policy = strtolower(trim(strval($options['policy'] ?? 'random_legal')));
$mctsIterations = max(1, min(128, intval($options['mcts-iterations'] ?? 16)));
$mctsMaxDepth = max(1, min(120, intval($options['mcts-max-depth'] ?? 14)));
$mctsConfig = [
  'iterations' => $mctsIterations,
  'max_depth' => $mctsMaxDepth,
];
if (!in_array($policy, ['random_non_pass', 'random_legal', 'first_non_pass', 'heuristic', 'mcts'], true)) {
  $policy = 'random_legal';
}

$runnerBaseDir = trim(strval(getenv('SIM_RUNNER_BASE_DIR') ?: '.'));
if ($runnerBaseDir === '') $runnerBaseDir = '.';
$runnerBaseDir = rtrim($runnerBaseDir, "/\\");
if ($runnerBaseDir === '') $runnerBaseDir = '.';
$gamesRoot = $runnerBaseDir . '/Games';
if (!is_dir($gamesRoot)) @mkdir($gamesRoot, 0777, true);

$deckA = normalizeDecklistForHeadless($deckAInput);
$deckB = normalizeDecklistForHeadless($deckBInput);
$unknownDeckCardIds = [];

function toEngineCardId(string $cardId, array &$unknownSetIds): string
{
  $trimmed = trim($cardId);
  if ($trimmed === '') return $trimmed;
  if (!str_contains($trimmed, '_')) return $trimmed;
  $mapped = strval(UUIDLookup($trimmed));
  if ($mapped !== '') return $mapped;
  $unknownSetIds[$trimmed] = true;
  return $trimmed;
}

function normalizeDeckCardIds(array $deck, array &$unknownSetIds): array
{
  $material = [];
  foreach (array_values(array_map('strval', $deck['material'] ?? [])) as $cardId) {
    $material[] = toEngineCardId($cardId, $unknownSetIds);
  }

  $main = [];
  foreach (array_values(array_map('strval', $deck['main'] ?? [])) as $cardId) {
    $main[] = toEngineCardId($cardId, $unknownSetIds);
  }

  return ['material' => $material, 'main' => $main];
}

$deckA = normalizeDeckCardIds($deckA, $unknownDeckCardIds);
$deckB = normalizeDeckCardIds($deckB, $unknownDeckCardIds);
if (count($unknownDeckCardIds) > 0) {
  $unknownList = implode(', ', array_keys($unknownDeckCardIds));
  $setCodes = [];
  foreach (array_keys($unknownDeckCardIds) as $id) {
    $parts = explode('_', strval($id), 2);
    if (count($parts) === 2 && $parts[0] !== '') $setCodes[$parts[0]] = true;
  }
  $setList = implode(', ', array_keys($setCodes));
  $suffix = $setList !== '' ? " (unsupported set codes in this engine build: $setList)" : "";
  throw new InvalidArgumentException("Unknown set card IDs (no UUID mapping): $unknownList$suffix");
}
$GLOBALS['__runner_checkpoint'] = 'normalized_decks';

$simGameName = 'sim_' . $matchID;
$gameName = $simGameName;
$GLOBALS['gameName'] = $simGameName;
if (!is_dir("$gamesRoot/$simGameName")) mkdir("$gamesRoot/$simGameName", 0777, true);
CreateLog($simGameName, $runnerBaseDir . '/');
SetMatchSeed(strval($seed));
if ($logFormat === 'json') SetStructuredLogMode(true);

initHeadlessGame($deckA, $deckB, $seed);
$gameName = $simGameName;
$GLOBALS['gameName'] = $simGameName;
$GLOBALS['__runner_checkpoint'] = 'initialized_game';
$openingState = phaseSnapshot();
$replayOrigGamestatePath = "$gamesRoot/$simGameName/origgamestate.txt";
$replayCommandfilePath = "$gamesRoot/$simGameName/commandfile.txt";
$oldFilename = $filename ?? null;
$oldPlayerID = $playerID ?? null;
$filename = $replayOrigGamestatePath;
$playerID = 1;
ob_start();
include __DIR__ . '/../WriteGamestate.php';
ob_end_clean();
if ($oldFilename === null) unset($filename);
else $filename = $oldFilename;
if ($oldPlayerID === null) unset($playerID);
else $playerID = $oldPlayerID;

function actionEntropyKey(int $playerId, array $action): string
{
  $resolvedCard = resolveCardReferenceRaw($playerId, $action);
  return implode('|', [
    strval($action['type'] ?? ''),
    strval($action['mode'] ?? ''),
    strval($action['buttonInput'] ?? ''),
    strval($action['cardID'] ?? ''),
    strval($action['chkCount'] ?? ''),
    json_encode($action['chkInput'] ?? '', JSON_UNESCAPED_SLASHES),
    strval($action['inputText'] ?? ''),
    $resolvedCard,
  ]);
}

function deterministicChoiceIndex(array $actions, int $seed, int $step, int $playerId, int $round, string $phase, string $policy): int
{
  $actionKeys = [];
  foreach ($actions as $action) {
    $actionKeys[] = actionEntropyKey($playerId, $action);
  }
  $entropy = implode('|', [
    strval($seed),
    strval($step),
    strval($playerId),
    strval($round),
    $phase,
    $policy,
    strval(count($actions)),
    hash('sha256', implode('||', $actionKeys)),
  ]);
  $hash = hash('sha256', $entropy);
  $sampleRaw = hexdec(substr($hash, 0, 8));
  $sample = is_numeric($sampleRaw) ? intval($sampleRaw) : 0;
  $count = max(1, intval(count($actions)));
  return intval($sample % $count);
}

function normalizedPromptContext(): string
{
  $dqState = $GLOBALS['dqState'] ?? [];
  $turn = $GLOBALS['turn'] ?? [];
  $ctx = strval($dqState[4] ?? '');
  if ($ctx === '' || $ctx === '-' || $ctx === '<-') {
    $ctx = strval($turn[2] ?? '');
  }
  $ctx = strtolower(str_replace('_', ' ', trim($ctx)));
  $ctx = preg_replace('/\s+/', ' ', $ctx) ?? $ctx;
  return trim($ctx);
}

function shouldPreferNonPassForPrompt(string $phase): bool
{
  if ($phase !== 'MAYCHOOSEMULTIZONE' && $phase !== 'CHOOSEMULTIZONE') return false;
  $ctx = normalizedPromptContext();
  if ($ctx === '') return false;
  // Exploit is an additional-cost selection. Passing here can make a "play" action no-op
  // when the card only becomes payable after selecting units to exploit.
  return str_contains($ctx, 'exploit');
}

function isPromptPhaseForSearch(string $phase): bool
{
  return in_array($phase, [
    'YESNO',
    'CHOOSEMULTIZONE',
    'MAYCHOOSEMULTIZONE',
    'CHOOSECARD',
    'MAYCHOOSECARD',
    'CHOOSEOPTION',
    'MAYCHOOSEOPTION',
    'BUTTONINPUT',
    'BUTTONINPUTNOPASS',
    'CHOOSEDECK',
    'MAYCHOOSEDECK',
    'HANDTOPBOTTOM',
    'DYNPITCH',
  ], true);
}

function heuristicActionScore(array $action, int $playerId, array $snapshot, string $phase): float
{
  $type = strval($action['type'] ?? '');
  $opponentId = $playerId === 1 ? 2 : 1;
  $self = $snapshot['player_' . $playerId] ?? [];
  $opp = $snapshot['player_' . $opponentId] ?? [];
  $myResources = intval($self['resources']['available'] ?? 0);
  $myUnits = intval($self['counts']['active_units'] ?? 0);
  $oppUnits = intval($opp['counts']['active_units'] ?? 0);
  $myBaseHp = intval($self['base']['health'] ?? 0);
  $oppBaseHp = intval($opp['base']['health'] ?? 0);
  $phaseUpper = strtoupper($phase);

  if ($type === 'pass') {
    $score = -260.0;
    if ($myResources <= 0) $score += 120.0;
    if ($phaseUpper !== 'M') $score += 45.0;
    if ($myUnits <= 0) $score += 25.0;
    return $score;
  }

  $score = 0.0;
  switch ($type) {
    case 'play_character':
      $score += 90.0;
      break;
    case 'play_hand':
      $score += 70.0;
      break;
    case 'activate_ally':
      $score += 64.0;
      break;
    case 'play_combat_chain':
      $score += 60.0;
      break;
    case 'activate_item':
    case 'activate_aura':
    case 'play_arsenal':
      $score += 46.0;
      break;
    case 'choose_zone':
    case 'multi_choose':
    case 'decision':
    case 'yesno':
      $score += 16.0;
      break;
    case 'claim_initiative':
      $score += 18.0;
      break;
    default:
      $score += 8.0;
      break;
  }

  if ($phaseUpper === 'M' && ($type === 'play_hand' || $type === 'activate_ally' || $type === 'play_character')) {
    $score += 8.0;
  }
  if ($oppUnits > $myUnits && ($type === 'activate_ally' || $type === 'play_hand' || $type === 'play_character')) {
    $score += 11.0;
  }

  if ($type === 'claim_initiative') {
    if ($myResources <= 1) $score += 20.0;
    else $score -= 12.0;
    if ($myUnits <= 0) $score += 10.0;
  }

  if ($type === 'choose_zone') {
    $target = strval($action['cardID'] ?? '');
    if (preg_match('/^THEIRALLY-\d+$/', $target) === 1) {
      // Prefer lines that point interaction at enemy board pieces.
      $score += 22.0;
    } else if (preg_match('/^MYALLY-\d+$/', $target) === 1) {
      $score -= 2.0;
      $ctx = normalizedPromptContext();
      if (str_contains($ctx, 'exploit')) $score += 18.0;
    }
  }

  if ($type === 'yesno') {
    $button = strtoupper(strval($action['buttonInput'] ?? ''));
    if ($button === 'YES') $score += 2.0;
    if ($button === 'NO') $score -= 2.0;
  }

  $rawCardId = resolveCardReferenceRaw($playerId, $action);
  if ($rawCardId !== '') {
    $cost = max(0, intval(CardCost($rawCardId)));
    $score += floatval(min($cost, $myResources)) * 3.1;
    $score += floatval(max(0, $cost - $myResources)) * -0.9;

    if (DefinedTypesContains($rawCardId, 'Unit', $playerId)) $score += 12.0;
    if (DefinedTypesContains($rawCardId, 'Event', $playerId)) $score += 9.0;
    if (DefinedTypesContains($rawCardId, 'Upgrade', $playerId)) $score += 4.0;

    if (HasKeyword($rawCardId, 'Ambush', $playerId, -1)) $score += 9.0;
    if (HasKeyword($rawCardId, 'Sentinel', $playerId, -1)) $score += 8.0;
    if (HasKeyword($rawCardId, 'Restore', $playerId, -1)) $score += 5.0;
    if (HasKeyword($rawCardId, 'Saboteur', $playerId, -1)) $score += 4.0;
    if (HasKeyword($rawCardId, 'Overwhelm', $playerId, -1)) $score += 4.0;
  }

  // Light strategic pressure: if ahead on base HP, initiative becomes slightly better.
  $hpDiff = $myBaseHp - $oppBaseHp;
  if ($type === 'claim_initiative' && $hpDiff > 0) $score += 3.0;

  return $score;
}

function chooseHeuristicAction(
  array $legalActions,
  int $seed,
  int $step,
  int $playerId,
  int $round,
  string $phase,
  array $snapshot
): ?array {
  if (count($legalActions) === 0) return null;
  if (count($snapshot) === 0) $snapshot = phaseSnapshot();

  $bestScore = -INF;
  $bestActions = [];
  foreach ($legalActions as $action) {
    $score = heuristicActionScore($action, $playerId, $snapshot, $phase);
    if ($score > $bestScore + 1e-9) {
      $bestScore = $score;
      $bestActions = [$action];
    } else if (abs($score - $bestScore) <= 1e-9) {
      $bestActions[] = $action;
    }
  }

  if (count($bestActions) === 1) return $bestActions[0];
  $choiceIndex = deterministicChoiceIndex($bestActions, $seed, $step, $playerId, $round, $phase, 'heuristic');
  return $bestActions[$choiceIndex] ?? $bestActions[0];
}

function chooseMctsRolloutAction(
  array $legalActions,
  int $seed,
  int $iteration,
  int $ply,
  int $playerId,
  int $round,
  string $phase,
  array $snapshot
): ?array {
  if (count($legalActions) === 0) return null;

  // Keep the first rollout plies slightly informed; deeper plies stay pseudo-random.
  if ($ply < 2) {
    $heuristic = chooseHeuristicAction(
      $legalActions,
      $seed + ($iteration * 101) + $ply,
      $ply + 1,
      $playerId,
      $round,
      $phase,
      $snapshot
    );
    if ($heuristic !== null) return $heuristic;
  }

  $nonPass = array_values(array_filter(
    $legalActions,
    static fn(array $action): bool => strval($action['type'] ?? '') !== 'pass'
  ));
  $candidates = $legalActions;
  if (count($nonPass) > 0 && ($phase === 'M' || shouldPreferNonPassForPrompt($phase))) {
    $candidates = $nonPass;
  }

  $choiceIndex = deterministicChoiceIndex(
    $candidates,
    $seed + ($iteration * 65537),
    $ply + 1,
    $playerId,
    $round,
    $phase,
    'mcts_rollout'
  );
  return $candidates[$choiceIndex] ?? $candidates[0];
}

function mctsEvaluateSnapshotForPlayer(array $snapshot, int $rootPlayerId, int $depth, int $maxDepth): float
{
  $winner = baseWinnerFromSnapshot($snapshot);
  if ($winner === $rootPlayerId) return 1.0;
  if ($winner !== 0) return 0.0;

  $opponentId = $rootPlayerId === 1 ? 2 : 1;
  $self = $snapshot['player_' . $rootPlayerId] ?? [];
  $opp = $snapshot['player_' . $opponentId] ?? [];

  $myHp = intval($self['base']['health'] ?? 0);
  $oppHp = intval($opp['base']['health'] ?? 0);
  $myUnits = intval($self['counts']['active_units'] ?? 0);
  $oppUnits = intval($opp['counts']['active_units'] ?? 0);
  $myRes = intval($self['resources']['available'] ?? 0);
  $oppRes = intval($opp['resources']['available'] ?? 0);

  $hpTerm = ($myHp - $oppHp) / 30.0;
  $unitTerm = ($myUnits - $oppUnits) / 8.0;
  $resTerm = ($myRes - $oppRes) / 8.0;
  $depthPenalty = ($maxDepth > 0 ? min(1.0, max(0.0, $depth / $maxDepth)) : 0.0) * 0.03;

  $score = 0.5 + (0.32 * $hpTerm) + (0.14 * $unitTerm) + (0.06 * $resTerm) - $depthPenalty;
  if ($score < 0.0) return 0.0;
  if ($score > 1.0) return 1.0;
  return $score;
}

function simulateMctsRollout(int $rootPlayerId, int $seed, int $iteration, int $maxDepth): float
{
  $noLegalActionStreak = 0;

  for ($ply = 0; $ply < $maxDepth; ++$ply) {
    $snapshot = phaseSnapshot();
    $winner = baseWinnerFromSnapshot($snapshot);
    if ($winner !== 0) return $winner === $rootPlayerId ? 1.0 : 0.0;
    if (boolval(IsGameOver())) {
      return mctsEvaluateSnapshotForPlayer($snapshot, $rootPlayerId, $ply, $maxDepth);
    }

    $turnSnapshot = $GLOBALS['turn'] ?? ['-', '0'];
    $phase = strval($turnSnapshot[0] ?? '-');
    $round = intval($GLOBALS['currentRound'] ?? 1);
    $turnPlayer = intval($turnSnapshot[1] ?? 0);
    $priorityPlayer = intval($GLOBALS['currentPlayer'] ?? 0);
    $resolved = resolveActingPlayerAndLegalActions($turnPlayer, $priorityPlayer);
    $playerId = intval($resolved['player_id'] ?? ($turnPlayer > 0 ? $turnPlayer : 1));
    $legalActions = is_array($resolved['actions'] ?? null) ? $resolved['actions'] : [];

    if (count($legalActions) === 0) {
      $noLegalActionStreak++;
      if ($noLegalActionStreak >= 2) {
        return mctsEvaluateSnapshotForPlayer($snapshot, $rootPlayerId, $ply, $maxDepth);
      }
      continue;
    }
    $noLegalActionStreak = 0;

    $chosen = chooseMctsRolloutAction($legalActions, $seed, $iteration, $ply, $playerId, $round, $phase, $snapshot);
    if ($chosen === null) {
      return mctsEvaluateSnapshotForPlayer($snapshot, $rootPlayerId, $ply, $maxDepth);
    }

    $result = applyAction($playerId, $chosen);
    if (boolval($result['ok'] ?? false)) continue;

    // Rollout safety: try pass before terminating this playout.
    $passAction = findPassAction($legalActions);
    if ($passAction === null) {
      return mctsEvaluateSnapshotForPlayer(phaseSnapshot(), $rootPlayerId, $ply, $maxDepth);
    }
    $passResult = applyAction($playerId, $passAction);
    if (!boolval($passResult['ok'] ?? false)) {
      return mctsEvaluateSnapshotForPlayer(phaseSnapshot(), $rootPlayerId, $ply, $maxDepth);
    }
  }

  return mctsEvaluateSnapshotForPlayer(phaseSnapshot(), $rootPlayerId, $maxDepth, $maxDepth);
}

function chooseMctsAction(
  array $legalActions,
  int $seed,
  int $step,
  int $playerId,
  int $round,
  string $phase,
  array $snapshot,
  array $mctsConfig
): ?array {
  if (count($legalActions) === 0) return null;
  if (count($legalActions) === 1) return $legalActions[0];

  $iterations = max(1, intval($mctsConfig['iterations'] ?? 16));
  $maxDepth = max(1, intval($mctsConfig['max_depth'] ?? 14));

  $rootSnapshot = headlessCaptureGamestateSnapshot();
  $children = [];
  foreach ($legalActions as $action) {
    $key = json_encode($action, JSON_UNESCAPED_SLASHES);
    $children[$key] = [
      'action' => $action,
      'visits' => 0,
      'value' => 0.0,
    ];
  }

  $totalVisits = 0;
  $exploration = 1.2;

  for ($iter = 0; $iter < $iterations; ++$iter) {
    headlessRestoreGamestateSnapshot($rootSnapshot);

    $selectedKey = '';
    $unvisited = [];
    foreach ($children as $key => $child) {
      if (intval($child['visits']) === 0) $unvisited[$key] = $child['action'];
    }

    if (count($unvisited) > 0) {
      $candidate = chooseHeuristicAction(
        array_values($unvisited),
        $seed + $iter,
        $step + $iter,
        $playerId,
        $round,
        $phase,
        $snapshot
      );
      if ($candidate === null) {
        $candidate = array_values($unvisited)[0];
      }
      $selectedKey = json_encode($candidate, JSON_UNESCAPED_SLASHES);
      if (!isset($children[$selectedKey])) {
        $selectedKey = array_key_first($unvisited);
      }
    } else {
      $bestScore = -INF;
      foreach ($children as $key => $child) {
        $visits = max(1, intval($child['visits']));
        $avg = floatval($child['value']) / $visits;
        $ucb = $avg + $exploration * sqrt(log(max(1, $totalVisits)) / $visits);
        $jitterRaw = hexdec(substr(hash('sha256', $key . '|' . $seed . '|' . $iter), 0, 6));
        $jitter = (is_numeric($jitterRaw) ? floatval($jitterRaw) : 0.0) / 1000000000.0;
        $score = $ucb + $jitter;
        if ($score > $bestScore) {
          $bestScore = $score;
          $selectedKey = $key;
        }
      }
    }

    if ($selectedKey === '' || !isset($children[$selectedKey])) continue;

    $rootAction = $children[$selectedKey]['action'];
    $applyRoot = applyAction($playerId, $rootAction);
    if (!boolval($applyRoot['ok'] ?? false)) {
      $reward = 0.0;
    } else {
      $reward = simulateMctsRollout($playerId, $seed + $step, $iter, $maxDepth);
    }

    $children[$selectedKey]['visits'] = intval($children[$selectedKey]['visits']) + 1;
    $children[$selectedKey]['value'] = floatval($children[$selectedKey]['value']) + $reward;
    $totalVisits++;
  }

  headlessRestoreGamestateSnapshot($rootSnapshot);

  $bestAction = $legalActions[0];
  $bestVisits = -1;
  $bestAvg = -INF;
  foreach ($children as $child) {
    $visits = intval($child['visits']);
    $avg = $visits > 0 ? (floatval($child['value']) / $visits) : -INF;
    if ($visits > $bestVisits || ($visits === $bestVisits && $avg > $bestAvg)) {
      $bestVisits = $visits;
      $bestAvg = $avg;
      $bestAction = $child['action'];
    }
  }
  return $bestAction;
}

function chooseAction(
  array $legalActions,
  int $seed,
  int $step,
  int $playerId,
  int $round,
  string $phase,
  string $policy,
  array $snapshot = [],
  array $policyConfig = []
): ?array {
  if (count($legalActions) === 0) return null;
  if (count($snapshot) === 0) $snapshot = phaseSnapshot();

  if ($policy === 'mcts') {
    // Prompt-heavy phases have low branching and immediate tactical answers;
    // use heuristic there to keep MCTS budget focused on meaningful action phases.
    if (isPromptPhaseForSearch($phase) || count($legalActions) <= 2) {
      return chooseHeuristicAction($legalActions, $seed, $step, $playerId, $round, $phase, $snapshot);
    }
    $mctsConfig = is_array($policyConfig['mcts'] ?? null) ? $policyConfig['mcts'] : [];
    return chooseMctsAction($legalActions, $seed, $step, $playerId, $round, $phase, $snapshot, $mctsConfig);
  }

  if ($policy === 'heuristic') {
    return chooseHeuristicAction($legalActions, $seed, $step, $playerId, $round, $phase, $snapshot);
  }

  if ($policy === 'first_non_pass') {
    foreach ($legalActions as $action) {
      if (($action['type'] ?? '') !== 'pass') return $action;
    }
    return $legalActions[0];
  }

  $candidates = $legalActions;
  $nonPass = array_values(array_filter(
    $legalActions,
    static fn(array $action): bool => strval($action['type'] ?? '') !== 'pass'
  ));

  if ($policy === 'random_non_pass') {
    if (count($nonPass) > 0) $candidates = $nonPass;
  }
  // Prevent degenerate "double-pass to end round" loops in main phase.
  // Keep random_legal behavior everywhere else.
  if ($policy === 'random_legal' && $phase === 'M' && count($nonPass) > 0) {
    $candidates = $nonPass;
  } else if ($policy === 'random_legal' && count($nonPass) > 0 && shouldPreferNonPassForPrompt($phase)) {
    $candidates = $nonPass;
  }

  $choiceIndex = deterministicChoiceIndex($candidates, $seed, $step, $playerId, $round, $phase, $policy);
  return $candidates[$choiceIndex] ?? $candidates[0];
}

function snapshotFingerprint(array $snapshot): string
{
  $json = json_encode($snapshot, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
  if ($json === false) return hash('sha256', serialize($snapshot));
  return hash('sha256', $json);
}

function gameplayNoOpCandidate(array $action): bool
{
  $type = strval($action['type'] ?? '');
  if ($type === '') return false;
  if ($type === 'play_character') return true;
  if ($type === 'arsenal') return true;
  if (str_starts_with($type, 'play_')) return true;
  if (str_starts_with($type, 'activate_')) return true;
  return false;
}

function isNoOpResolvedAction(array $before, array $after, array $action, bool $ok): bool
{
  if (!$ok) return false;
  if (!gameplayNoOpCandidate($action)) return false;
  return snapshotFingerprint($before) === snapshotFingerprint($after);
}

function legalActionTypeSummary(array $legalActions): array
{
  $summary = [];
  foreach ($legalActions as $action) {
    $type = strval($action['type'] ?? 'unknown');
    $summary[$type] = intval($summary[$type] ?? 0) + 1;
  }
  ksort($summary);
  return $summary;
}

function findPassAction(array $legalActions): ?array
{
  foreach ($legalActions as $action) {
    if (strval($action['type'] ?? '') === 'pass') return $action;
  }
  return null;
}

function resolveActingPlayerAndLegalActions(int $turnPlayer, int $priorityPlayer): array
{
  $candidates = [];
  if ($turnPlayer > 0) $candidates[] = $turnPlayer;
  if ($priorityPlayer > 0 && !in_array($priorityPlayer, $candidates, true)) $candidates[] = $priorityPlayer;
  foreach ([1, 2] as $pid) {
    if (!in_array($pid, $candidates, true)) $candidates[] = $pid;
  }

  foreach ($candidates as $pid) {
    $actions = getLegalActions($pid);
    if (count($actions) > 0) {
      return ['player_id' => $pid, 'actions' => $actions];
    }
  }

  $fallback = intval($candidates[0] ?? 1);
  return ['player_id' => $fallback, 'actions' => []];
}

function isDecisionLikeAction(array $action): bool
{
  $decisionTypes = [
    'yesno',
    'decision',
    'choose_zone',
    'choose_deck',
    'opt_top',
    'opt_bottom',
    'multi_choose',
    'dynamic_input',
    'hand_top',
    'hand_bottom',
  ];
  $type = strval($action['type'] ?? '');
  return in_array($type, $decisionTypes, true);
}

function groupedEventsByRound(array $events): array
{
  $pages = [];
  foreach ($events as $event) {
    if (!is_array($event)) continue;
    $round = intval($event['round'] ?? 0);
    if ($round <= 0) continue;
    if (!isset($pages[$round])) {
      $pages[$round] = [
        'round' => $round,
        'start_step' => intval($event['step'] ?? 0),
        'end_step' => intval($event['step'] ?? 0),
        'total_steps' => 0,
        'decision_steps' => 0,
        'gameplay_steps' => 0,
        'phases' => [],
        'events' => [],
      ];
    }
    $pages[$round]['end_step'] = intval($event['step'] ?? $pages[$round]['end_step']);
    $pages[$round]['total_steps']++;
    if (boolval($event['is_decision'] ?? false)) $pages[$round]['decision_steps']++;
    else $pages[$round]['gameplay_steps']++;
    $phase = strval($event['phase'] ?? '-');
    $pages[$round]['phases'][$phase] = intval($pages[$round]['phases'][$phase] ?? 0) + 1;
    $pages[$round]['events'][] = $event;
  }
  ksort($pages, SORT_NUMERIC);
  return array_values($pages);
}

function sanitizeReplayToken(mixed $value): string
{
  return str_replace(["\r", "\n"], '', strval($value ?? ''));
}

function formatReplayCommandLine(int $playerId, array $action): string
{
  $mode = intval($action['mode'] ?? 0);
  $buttonInput = sanitizeReplayToken($action['buttonInput'] ?? '');
  $cardID = sanitizeReplayToken($action['cardID'] ?? '');
  $chkCount = max(0, intval($action['chkCount'] ?? 0));
  $chkInputRaw = $action['chkInput'] ?? [];
  if (!is_array($chkInputRaw)) $chkInputRaw = [];
  $chkInput = [];
  foreach ($chkInputRaw as $value) {
    $chkInput[] = sanitizeReplayToken($value);
  }
  return $playerId . ' ' . $mode . ' ' . $buttonInput . ' ' . $cardID . ' ' . $chkCount . ' ' . implode('|', $chkInput);
}

function resolveCardReferenceRaw(int $playerId, array $action): string
{
  $type = strval($action['type'] ?? '');
  $cardID = $action['cardID'] ?? 0;
  $cardIDStr = strval($cardID);

  if ($type === 'play_hand') {
    $hand = &GetHand($playerId);
    return strval($hand[intval($cardID)] ?? '');
  }
  if ($type === 'play_character') {
    $character = &GetPlayerCharacter($playerId);
    return strval($character[intval($cardID)] ?? '');
  }
  if ($type === 'play_arsenal') {
    $arsenal = &GetArsenal($playerId);
    return strval($arsenal[intval($cardID)] ?? '');
  }
  if ($type === 'play_resource') {
    $resources = &GetResourceCards($playerId);
    return strval($resources[intval($cardID)] ?? '');
  }
  if ($type === 'play_item' || $type === 'activate_item') {
    $items = &GetItems($playerId);
    return strval($items[intval($cardID)] ?? '');
  }
  if ($type === 'play_ally' || $type === 'activate_ally') {
    $allies = &GetAllies($playerId);
    return strval($allies[intval($cardID)] ?? '');
  }
  if ($type === 'play_aura' || $type === 'activate_aura') {
    $auras = &GetAuras($playerId);
    return strval($auras[intval($cardID)] ?? '');
  }
  if ($cardIDStr !== '' && str_contains($cardIDStr, '-')) {
    return strval(GetMZCard($playerId, $cardIDStr));
  }
  if ($type === 'choose_zone') {
    $targetRef = strval($cardID);
    if (preg_match('/^(MYALLY|THEIRALLY)-(\d+)$/', $targetRef, $matches) === 1) {
      $zone = strval($matches[1] ?? '');
      $index = intval($matches[2] ?? -1);
      if ($index < 0) return '';
      $targetPlayer = $zone === 'MYALLY' ? $playerId : ($playerId === 1 ? 2 : 1);
      $allies = &GetAllies($targetPlayer);
      return strval($allies[$index] ?? '');
    }
  }
  if ($type === 'arsenal') return strval($cardID);
  return '';
}

function displayCardId(string $rawCardId): string
{
  if ($rawCardId === '') return '';
  $mapped = strval(CardIDLookup($rawCardId));
  if ($mapped !== '') return $mapped;
  return $rawCardId;
}

function cardKeywordFlags(string $rawCardId, int $playerId): array
{
  if ($rawCardId === '') return [];
  $keywords = [
    'Smuggle',
    'Raid',
    'Grit',
    'Restore',
    'Bounty',
    'Overwhelm',
    'Saboteur',
    'Shielded',
    'Sentinel',
    'Ambush',
    'Coordinate',
    'Exploit',
    'Piloting',
    'Hidden',
    'Plot',
  ];
  $flags = [];
  foreach ($keywords as $keyword) {
    $hasKeyword = false;
    try {
      $hasKeyword = boolval(HasKeyword($rawCardId, $keyword, $playerId, -1));
    } catch (Throwable $t) {
      $hasKeyword = false;
    }
    $flags[$keyword] = $hasKeyword;
  }
  return $flags;
}

function buildUnitDetail(int $playerId, array $allies, int $index): ?array
{
  $rawCardId = strval($allies[$index] ?? '');
  if ($rawCardId === '') return null;

  $ally = new Ally('MYALLY-' . $index, $playerId);
  $arenaOverride = strval($allies[$index + 15] ?? 'NA');
  $arena = $arenaOverride !== 'NA' ? $arenaOverride : strval(CardArenas($rawCardId));
  $arenaUpper = strtoupper($arena);
  if ($arenaUpper === 'GROUND') $arenaUpper = 'LAND';
  if ($arenaUpper !== 'SPACE') $arenaUpper = 'LAND';

  $isReady = !$ally->IsExhausted();
  $printedPower = intval(CardPower($rawCardId));
  $currentPower = intval($ally->CurrentPower());
  $printedHp = intval(CardHP($rawCardId));
  $maxHp = intval($ally->MaxHealth());
  $damageTaken = intval($ally->Damage());
  $currentHp = intval($ally->Health());
  $upgrades = array_values(array_map('strval', $ally->GetUpgrades()));
  $captives = array_values(array_map('strval', $ally->GetCaptives()));

  return [
    'raw_id' => $rawCardId,
    'unique_id' => strval($allies[$index + 5] ?? ''),
    'arena' => $arenaUpper,
    'ready' => boolval($isReady),
    'exhausted' => boolval(!$isReady),
    'damage_taken' => $damageTaken,
    'current_hp' => $currentHp,
    'max_hp' => $maxHp,
    'printed_hp' => $printedHp,
    'hp_modifier' => $maxHp - $printedHp,
    'current_power' => $currentPower,
    'printed_power' => $printedPower,
    'power_modifier' => $currentPower - $printedPower,
    'counters' => intval($allies[$index + 6] ?? 0),
    'times_attacked' => intval($allies[$index + 10] ?? 0),
    'owner' => intval($allies[$index + 11] ?? $playerId),
    'turns_in_play' => intval($allies[$index + 12] ?? 0),
    'from' => strval($allies[$index + 16] ?? ''),
    'is_leader' => boolval($ally->IsLeader()),
    'upgrades' => $upgrades,
    'is_upgraded' => count($upgrades) > 0,
    'captives' => $captives,
    'has_captive' => count($captives) > 0,
  ];
}

function unitDetailMapByUnique(array $details): array
{
  $map = [];
  foreach ($details as $detail) {
    if (!is_array($detail)) continue;
    $uid = strval($detail['unique_id'] ?? '');
    if ($uid === '') continue;
    $map[$uid] = $detail;
  }
  return $map;
}

function allyArenaState(int $playerId): array
{
  global $p1Allies, $p2Allies;
  $allies = ($playerId === 1 ? $p1Allies : $p2Allies);
  $landAll = [];
  $landReady = [];
  $landExhausted = [];
  $landDetailAll = [];
  $landDetailReady = [];
  $landDetailExhausted = [];
  $spaceAll = [];
  $spaceReady = [];
  $spaceExhausted = [];
  $spaceDetailAll = [];
  $spaceDetailReady = [];
  $spaceDetailExhausted = [];
  for ($i = 0; $i < count($allies); $i += AllyPieces()) {
    $detail = buildUnitDetail($playerId, $allies, $i);
    if ($detail === null) continue;
    $cardId = strval($detail['raw_id'] ?? '');
    $isReady = boolval($detail['ready'] ?? false);
    if (strval($detail['arena'] ?? 'LAND') === 'SPACE') {
      $spaceAll[] = $cardId;
      $spaceDetailAll[] = $detail;
      if ($isReady) $spaceReady[] = $cardId;
      else $spaceExhausted[] = $cardId;
      if ($isReady) $spaceDetailReady[] = $detail;
      else $spaceDetailExhausted[] = $detail;
    } else {
      $landAll[] = $cardId;
      $landDetailAll[] = $detail;
      if ($isReady) $landReady[] = $cardId;
      else $landExhausted[] = $cardId;
      if ($isReady) $landDetailReady[] = $detail;
      else $landDetailExhausted[] = $detail;
    }
  }
  return [
    'land' => [
      'all' => $landAll,
      'ready' => $landReady,
      'exhausted' => $landExhausted,
      'details' => [
        'all' => $landDetailAll,
        'ready' => $landDetailReady,
        'exhausted' => $landDetailExhausted,
      ],
    ],
    'space' => [
      'all' => $spaceAll,
      'ready' => $spaceReady,
      'exhausted' => $spaceExhausted,
      'details' => [
        'all' => $spaceDetailAll,
        'ready' => $spaceDetailReady,
        'exhausted' => $spaceDetailExhausted,
      ],
    ],
  ];
}

function allyArenaCardIds(int $playerId): array
{
  $state = allyArenaState($playerId);
  return [
    'land' => $state['land']['all'],
    'space' => $state['space']['all'],
  ];
}

function zoneCardCount(array $zone, int $pieces): int
{
  if ($pieces <= 1) return count($zone);
  return intdiv(count($zone), $pieces);
}

function resourceCardStats(int $playerId): array
{
  $resourceCards = &GetResourceCards($playerId);
  $ready = 0;
  $exhausted = 0;
  $ids = [];
  for ($i = 0; $i < count($resourceCards); $i += ResourcePieces()) {
    $ids[] = strval($resourceCards[$i] ?? '');
    $isExhausted = strval($resourceCards[$i + 4] ?? '0') === '1';
    if ($isExhausted) $exhausted++;
    else $ready++;
  }
  return [
    'ids' => $ids,
    'total' => zoneCardCount($resourceCards, ResourcePieces()),
    'ready' => $ready,
    'exhausted' => $exhausted,
  ];
}

function remainingBaseHealth(int $playerId): int
{
  global $playerHealths;
  $damageTaken = intval($playerHealths[$playerId - 1] ?? 0);
  $character = &GetPlayerCharacter($playerId);
  $baseCard = strval($character[0] ?? '');
  $maxHealth = $baseCard !== '' ? intval(CardHP($baseCard)) : 30;
  if ($maxHealth <= 0) $maxHealth = 30;
  $remaining = $maxHealth - $damageTaken;
  return $remaining > 0 ? $remaining : 0;
}

function playerPhaseSnapshot(int $playerId): array
{
  DoGamestateUpdate();
  global $playerHealths, $p1Hand, $p1Deck, $p1Discard, $p2Hand, $p2Deck, $p2Discard;
  global $CS_NumTimesUsedTheForce;
  $hand = ($playerId === 1 ? $p1Hand : $p2Hand);
  $deck = ($playerId === 1 ? $p1Deck : $p2Deck);
  $discard = ($playerId === 1 ? $p1Discard : $p2Discard);
  $resources = &GetResources($playerId);
  $resourceStats = resourceCardStats($playerId);
  $forceAvailable = HasTheForce($playerId);
  $forceTimesUsed = intval(GetClassState($playerId, $CS_NumTimesUsedTheForce));
  $arenaState = allyArenaState($playerId);
  $landAll = $arenaState['land']['all'];
  $spaceAll = $arenaState['space']['all'];
  $landReady = $arenaState['land']['ready'];
  $spaceReady = $arenaState['space']['ready'];
  $landExhausted = $arenaState['land']['exhausted'];
  $spaceExhausted = $arenaState['space']['exhausted'];
  $landDetailAll = $arenaState['land']['details']['all'];
  $spaceDetailAll = $arenaState['space']['details']['all'];
  $landDetailReady = $arenaState['land']['details']['ready'];
  $spaceDetailReady = $arenaState['space']['details']['ready'];
  $landDetailExhausted = $arenaState['land']['details']['exhausted'];
  $spaceDetailExhausted = $arenaState['space']['details']['exhausted'];
  $allUnitDetails = array_merge($landDetailAll, $spaceDetailAll);
  $handCount = zoneCardCount($hand, HandPieces());
  $deckCount = zoneCardCount($deck, DeckPieces());
  $discardCount = zoneCardCount($discard, DiscardPieces());
  $landCount = count($landAll);
  $spaceCount = count($spaceAll);
  $activeUnitCount = count($landReady) + count($spaceReady);

  return [
    'resources' => [
      'raw' => $resources,
      // SWU spendability is represented by ready/exhausted resource cards.
      // Keep these aligned with what users expect to see in the timeline.
      'available' => intval($resourceStats['ready']),
      'spent' => intval($resourceStats['exhausted']),
      // Preserve engine pool counters for debugging.
      'pool_available' => intval($resources[0] ?? 0),
      'pool_spent' => intval($resources[1] ?? 0),
      'total_cards' => intval($resourceStats['total']),
      'ready_cards' => intval($resourceStats['ready']),
      'exhausted_cards' => intval($resourceStats['exhausted']),
      'spendable' => intval($resourceStats['ready']),
    ],
    'base' => [
      // Expose user-facing remaining base HP (not internal damage-taken counter).
      'health' => remainingBaseHealth($playerId),
      'damage_taken' => intval($playerHealths[$playerId - 1] ?? 0),
    ],
    'force' => [
      'available' => boolval($forceAvailable),
      'status' => $forceAvailable ? 'available' : 'unavailable',
      'times_used_this_phase' => $forceTimesUsed,
    ],
    'counts' => [
      'hand' => $handCount,
      'deck' => $deckCount,
      'discard' => $discardCount,
      'land_arena' => $landCount,
      'space_arena' => $spaceCount,
      'active_units' => $activeUnitCount,
    ],
    'zones' => [
      'hand' => $hand,
      'deck' => $deck,
      'discard' => $discard,
      'resources' => $resourceStats['ids'],
      'land_arena' => $landAll,
      'space_arena' => $spaceAll,
      'land_ready' => $landReady,
      'space_ready' => $spaceReady,
      'land_exhausted' => $landExhausted,
      'space_exhausted' => $spaceExhausted,
    ],
    'units' => [
      'active_count' => $activeUnitCount,
      'details' => $allUnitDetails,
      'detail_map' => unitDetailMapByUnique($allUnitDetails),
      'land' => [
        'all' => $landAll,
        'ready' => $landReady,
        'exhausted' => $landExhausted,
        'details' => [
          'all' => $landDetailAll,
          'ready' => $landDetailReady,
          'exhausted' => $landDetailExhausted,
        ],
      ],
      'space' => [
        'all' => $spaceAll,
        'ready' => $spaceReady,
        'exhausted' => $spaceExhausted,
        'details' => [
          'all' => $spaceDetailAll,
          'ready' => $spaceDetailReady,
          'exhausted' => $spaceDetailExhausted,
        ],
      ],
    ],
  ];
}

function phaseSnapshot(): array
{
  $turn = $GLOBALS['turn'] ?? [];
  $dqState = $GLOBALS['dqState'] ?? [];
  $decisionQueue = $GLOBALS['decisionQueue'] ?? [];
  return [
    'meta' => [
      'turn_phase' => strval($turn[0] ?? ''),
      'turn_player' => intval($turn[1] ?? 0),
      'turn_parameter' => strval($turn[2] ?? ''),
      'dq_context' => strval($dqState[4] ?? ''),
      'dq_phase' => strval($decisionQueue[0] ?? ''),
      'dq_player' => intval($decisionQueue[1] ?? 0),
    ],
    'player_1' => playerPhaseSnapshot(1),
    'player_2' => playerPhaseSnapshot(2),
  ];
}

function baseWinnerFromSnapshot(array $snapshot): int
{
  $p1Hp = intval($snapshot['player_1']['base']['health'] ?? 0);
  $p2Hp = intval($snapshot['player_2']['base']['health'] ?? 0);
  if ($p1Hp <= 0 && $p2Hp <= 0) return 0;
  if ($p1Hp <= 0) return 2;
  if ($p2Hp <= 0) return 1;
  return 0;
}

function isBaseZeroGameOver(array $snapshot): bool
{
  return baseWinnerFromSnapshot($snapshot) !== 0;
}

function numericDelta(int $before, int $after): int
{
  return $after - $before;
}

function normalizePromptText(string $text): string
{
  $t = trim($text);
  if ($t === '' || $t === '-' || $t === '<-') return '';
  $t = str_replace('_', ' ', $t);
  $t = preg_replace('/\s+/', ' ', $t) ?? $t;
  return trim($t);
}

function deriveEffects(array $before, array $after): array
{
  $effects = [];
  foreach (['player_1', 'player_2'] as $playerKey) {
    $b = $before[$playerKey];
    $a = $after[$playerKey];
    $p1 = $after['player_1'];
    $p2 = $after['player_2'];
    $effects[$playerKey] = [
      // Absolute board snapshot (compat for older UI renderers).
      'p1_hp' => intval($p1['base']['health']),
      'p2_hp' => intval($p2['base']['health']),
      'p1_hand' => intval($p1['counts']['hand']),
      'p2_hand' => intval($p2['counts']['hand']),
      'p1_deck' => intval($p1['counts']['deck']),
      'p2_deck' => intval($p2['counts']['deck']),
      'p1_discard' => intval($p1['counts']['discard']),
      'p2_discard' => intval($p2['counts']['discard']),
      'p1_land' => intval($p1['counts']['land_arena']),
      'p2_land' => intval($p2['counts']['land_arena']),
      'p1_space' => intval($p1['counts']['space_arena']),
      'p2_space' => intval($p2['counts']['space_arena']),
      'p1_resources_total' => intval($p1['resources']['total_cards']),
      'p2_resources_total' => intval($p2['resources']['total_cards']),
      'p1_resources_available' => intval($p1['resources']['available']),
      'p2_resources_available' => intval($p2['resources']['available']),
      'p1_resources_spent' => intval($p1['resources']['spent']),
      'p2_resources_spent' => intval($p2['resources']['spent']),
      'p1_resources_ready' => intval($p1['resources']['ready_cards']),
      'p2_resources_ready' => intval($p2['resources']['ready_cards']),
      'p1_resources_exhausted' => intval($p1['resources']['exhausted_cards']),
      'p2_resources_exhausted' => intval($p2['resources']['exhausted_cards']),
      'p1_active_units' => intval($p1['counts']['active_units'] ?? 0),
      'p2_active_units' => intval($p2['counts']['active_units'] ?? 0),
      // Legacy "Effects" columns in older UI builds consume *_d fields.
      // Keep these as live per-player totals (not deltas) so board state persists row-to-row.
      'hp_d' => intval($a['base']['health']),
      'res_d' => intval($a['resources']['available']),
      'spent_d' => intval($a['resources']['spent']),
      'hand_d' => zoneCardCount($a['zones']['hand'], HandPieces()),
      'deck_d' => zoneCardCount($a['zones']['deck'], DeckPieces()),
      'discard_d' => zoneCardCount($a['zones']['discard'], DiscardPieces()),
      'land_d' => count($a['zones']['land_arena']),
      'space_d' => count($a['zones']['space_arena']),
      'resources_available_delta' => numericDelta(intval($b['resources']['available']), intval($a['resources']['available'])),
      'resources_spent_delta' => numericDelta(intval($b['resources']['spent']), intval($a['resources']['spent'])),
      'resource_cards_total_delta' => numericDelta(intval($b['resources']['total_cards']), intval($a['resources']['total_cards'])),
      'resource_cards_ready_delta' => numericDelta(intval($b['resources']['ready_cards']), intval($a['resources']['ready_cards'])),
      'resource_cards_exhausted_delta' => numericDelta(intval($b['resources']['exhausted_cards']), intval($a['resources']['exhausted_cards'])),
      'base_health_delta' => numericDelta(intval($b['base']['health']), intval($a['base']['health'])),
      'hand_count_delta' => numericDelta(zoneCardCount($b['zones']['hand'], HandPieces()), zoneCardCount($a['zones']['hand'], HandPieces())),
      'deck_count_delta' => numericDelta(zoneCardCount($b['zones']['deck'], DeckPieces()), zoneCardCount($a['zones']['deck'], DeckPieces())),
      'discard_count_delta' => numericDelta(zoneCardCount($b['zones']['discard'], DiscardPieces()), zoneCardCount($a['zones']['discard'], DiscardPieces())),
      'land_arena_count_delta' => numericDelta(count($b['zones']['land_arena']), count($a['zones']['land_arena'])),
      'space_arena_count_delta' => numericDelta(count($b['zones']['space_arena']), count($a['zones']['space_arena'])),
    ];
  }
  return $effects;
}

function displayZoneCardIds(array $zone): array
{
  $out = [];
  foreach ($zone as $rawCardId) {
    $raw = strval($rawCardId);
    if ($raw === '') continue;
    $out[] = displayCardId($raw);
  }
  return $out;
}

function displayUnitDetails(array $details): array
{
  $out = [];
  foreach ($details as $detail) {
    if (!is_array($detail)) continue;
    $rawCardId = strval($detail['raw_id'] ?? '');
    if ($rawCardId === '') continue;
    $upgradesRaw = array_values(array_map('strval', $detail['upgrades'] ?? []));
    $captivesRaw = array_values(array_map('strval', $detail['captives'] ?? []));
    $out[] = [
      'id' => displayCardId($rawCardId),
      'raw_id' => $rawCardId,
      'uid' => strval($detail['unique_id'] ?? ''),
      'arena' => strval($detail['arena'] ?? ''),
      'ready' => boolval($detail['ready'] ?? false),
      'exhausted' => boolval($detail['exhausted'] ?? false),
      'damage_taken' => intval($detail['damage_taken'] ?? 0),
      'current_hp' => intval($detail['current_hp'] ?? 0),
      'max_hp' => intval($detail['max_hp'] ?? 0),
      'printed_hp' => intval($detail['printed_hp'] ?? 0),
      'hp_modifier' => intval($detail['hp_modifier'] ?? 0),
      'current_power' => intval($detail['current_power'] ?? 0),
      'printed_power' => intval($detail['printed_power'] ?? 0),
      'power_modifier' => intval($detail['power_modifier'] ?? 0),
      'counters' => intval($detail['counters'] ?? 0),
      'times_attacked' => intval($detail['times_attacked'] ?? 0),
      'owner' => intval($detail['owner'] ?? 0),
      'turns_in_play' => intval($detail['turns_in_play'] ?? 0),
      'from' => strval($detail['from'] ?? ''),
      'is_leader' => boolval($detail['is_leader'] ?? false),
      'is_upgraded' => boolval($detail['is_upgraded'] ?? false),
      'upgrades' => displayZoneCardIds($upgradesRaw),
      'upgrades_raw' => $upgradesRaw,
      'has_captive' => boolval($detail['has_captive'] ?? false),
      'captives' => displayZoneCardIds($captivesRaw),
      'captives_raw' => $captivesRaw,
    ];
  }
  return $out;
}

function unitDetailsMapFromSnapshot(array $playerSnapshot): array
{
  $details = $playerSnapshot['units']['detail_map'] ?? [];
  if (is_array($details) && count($details) > 0) return $details;
  return unitDetailMapByUnique($playerSnapshot['units']['details'] ?? []);
}

function cardCounts(array $rawCardIds): array
{
  $counts = [];
  foreach ($rawCardIds as $rawCardId) {
    $raw = strval($rawCardId);
    if ($raw === '') continue;
    $counts[$raw] = intval($counts[$raw] ?? 0) + 1;
  }
  return $counts;
}

function addedCardsBetweenZones(array $beforeCardIds, array $afterCardIds): array
{
  $beforeCounts = cardCounts($beforeCardIds);
  $afterCounts = cardCounts($afterCardIds);
  $added = [];
  foreach ($afterCounts as $rawCardId => $afterCount) {
    $beforeCount = intval($beforeCounts[$rawCardId] ?? 0);
    $extra = $afterCount - $beforeCount;
    for ($i = 0; $i < $extra; ++$i) {
      $added[] = $rawCardId;
    }
  }
  return $added;
}

function summarizeActionDetails(array $before, array $after, array $action = [], int $actingPlayer = 0, string $actionCardRaw = ''): array
{
  $details = [
    'base_damage' => [],
    'unit_damage' => [],
    'unit_defeated' => [],
    'unit_deployed' => [],
    'unit_ready_state_changes' => [],
    'unit_upgrade_changes' => [],
    'unit_capture_changes' => [],
    'unit_stat_changes' => [],
    'experience_tokens_given' => [],
    'token_units_created' => [],
    'resourced_cards' => [],
    'player_state_changes' => [],
    'follow_up_prompt' => null,
    'when_defeated_checks' => [],
    'exploit_resolution' => null,
    'leader_action_triggers' => [],
    'epic_action_triggers' => [],
  ];

  foreach ([1, 2] as $playerId) {
    $key = 'player_' . $playerId;
    $beforePlayer = $before[$key] ?? [];
    $afterPlayer = $after[$key] ?? [];

    $beforeHand = zoneCardCount($beforePlayer['zones']['hand'] ?? [], HandPieces());
    $afterHand = zoneCardCount($afterPlayer['zones']['hand'] ?? [], HandPieces());
    $beforeDeck = zoneCardCount($beforePlayer['zones']['deck'] ?? [], DeckPieces());
    $afterDeck = zoneCardCount($afterPlayer['zones']['deck'] ?? [], DeckPieces());
    $beforeDiscard = zoneCardCount($beforePlayer['zones']['discard'] ?? [], DiscardPieces());
    $afterDiscard = zoneCardCount($afterPlayer['zones']['discard'] ?? [], DiscardPieces());
    $beforeLand = count($beforePlayer['zones']['land_arena'] ?? []);
    $afterLand = count($afterPlayer['zones']['land_arena'] ?? []);
    $beforeSpace = count($beforePlayer['zones']['space_arena'] ?? []);
    $afterSpace = count($afterPlayer['zones']['space_arena'] ?? []);
    $beforeReadyUnits = count($beforePlayer['zones']['land_ready'] ?? []) + count($beforePlayer['zones']['space_ready'] ?? []);
    $afterReadyUnits = count($afterPlayer['zones']['land_ready'] ?? []) + count($afterPlayer['zones']['space_ready'] ?? []);
    $beforeExhaustedUnits = count($beforePlayer['zones']['land_exhausted'] ?? []) + count($beforePlayer['zones']['space_exhausted'] ?? []);
    $afterExhaustedUnits = count($afterPlayer['zones']['land_exhausted'] ?? []) + count($afterPlayer['zones']['space_exhausted'] ?? []);
    $beforeActive = intval($beforePlayer['counts']['active_units'] ?? 0);
    $afterActive = intval($afterPlayer['counts']['active_units'] ?? 0);
    $beforeResAvail = intval($beforePlayer['resources']['available'] ?? 0);
    $afterResAvail = intval($afterPlayer['resources']['available'] ?? 0);
    $beforeResSpent = intval($beforePlayer['resources']['spent'] ?? 0);
    $afterResSpent = intval($afterPlayer['resources']['spent'] ?? 0);
    $beforeResTotal = intval($beforePlayer['resources']['total_cards'] ?? 0);
    $afterResTotal = intval($afterPlayer['resources']['total_cards'] ?? 0);
    $beforeResReady = intval($beforePlayer['resources']['ready_cards'] ?? 0);
    $afterResReady = intval($afterPlayer['resources']['ready_cards'] ?? 0);
    $beforeResExhausted = intval($beforePlayer['resources']['exhausted_cards'] ?? 0);
    $afterResExhausted = intval($afterPlayer['resources']['exhausted_cards'] ?? 0);
    $beforeResCards = array_values(array_map('strval', $beforePlayer['zones']['resources'] ?? []));
    $afterResCards = array_values(array_map('strval', $afterPlayer['zones']['resources'] ?? []));
    $beforeForce = boolval($beforePlayer['force']['available'] ?? false);
    $afterForce = boolval($afterPlayer['force']['available'] ?? false);

    $beforeHp = intval($beforePlayer['base']['health'] ?? 0);
    $afterHp = intval($afterPlayer['base']['health'] ?? 0);
    $stateChange = [
      'player' => $playerId,
      'base_hp_delta' => $afterHp - $beforeHp,
      'hand_delta' => $afterHand - $beforeHand,
      'deck_delta' => $afterDeck - $beforeDeck,
      'discard_delta' => $afterDiscard - $beforeDiscard,
      'land_units_delta' => $afterLand - $beforeLand,
      'space_units_delta' => $afterSpace - $beforeSpace,
      'active_units_delta' => $afterActive - $beforeActive,
      'ready_units_delta' => $afterReadyUnits - $beforeReadyUnits,
      'exhausted_units_delta' => $afterExhaustedUnits - $beforeExhaustedUnits,
      'resources_available_delta' => $afterResAvail - $beforeResAvail,
      'resources_spent_delta' => $afterResSpent - $beforeResSpent,
      'resource_cards_total_delta' => $afterResTotal - $beforeResTotal,
      'resource_cards_ready_delta' => $afterResReady - $beforeResReady,
      'resource_cards_exhausted_delta' => $afterResExhausted - $beforeResExhausted,
      'force_before' => $beforeForce,
      'force_after' => $afterForce,
    ];
    $hasStateChange = false;
    foreach ($stateChange as $k => $v) {
      if ($k === 'player') continue;
      if ($k === 'force_before' || $k === 'force_after') continue;
      if (intval($v) !== 0) {
        $hasStateChange = true;
        break;
      }
    }
    if (!$hasStateChange && $beforeForce !== $afterForce) $hasStateChange = true;
    if ($hasStateChange) $details['player_state_changes'][] = $stateChange;

    $newResourceCards = addedCardsBetweenZones($beforeResCards, $afterResCards);
    foreach ($newResourceCards as $rawCardId) {
      $raw = strval($rawCardId);
      if ($raw === '') continue;
      $details['resourced_cards'][] = [
        'player' => $playerId,
        'card_raw_id' => $raw,
        'card_id' => displayCardId($raw),
      ];
    }

    if ($afterHp < $beforeHp) {
      $details['base_damage'][] = [
        'player' => $playerId,
        'amount' => $beforeHp - $afterHp,
        'before_hp' => $beforeHp,
        'after_hp' => $afterHp,
      ];
    }

    $beforeUnits = unitDetailsMapFromSnapshot($beforePlayer);
    $afterUnits = unitDetailsMapFromSnapshot($afterPlayer);

    foreach ($beforeUnits as $uid => $beforeUnit) {
      if (!is_array($beforeUnit)) continue;
      $afterUnit = $afterUnits[$uid] ?? null;
      $unitDisplay = displayCardId(strval($beforeUnit['raw_id'] ?? ''));
      if ($afterUnit === null || !is_array($afterUnit)) {
        $rawId = strval($beforeUnit['raw_id'] ?? '');
        $details['unit_defeated'][] = [
          'player' => $playerId,
          'unit_uid' => strval($uid),
          'unit_id' => $unitDisplay,
          'unit_raw_id' => $rawId,
          'arena' => strval($beforeUnit['arena'] ?? ''),
          'before_hp' => intval($beforeUnit['current_hp'] ?? 0),
          'has_when_defeated' => ($rawId !== '' ? boolval(HasWhenDestroyed($rawId)) : false),
        ];
        continue;
      }

      $beforeDamage = intval($beforeUnit['damage_taken'] ?? 0);
      $afterDamage = intval($afterUnit['damage_taken'] ?? 0);
      if ($afterDamage > $beforeDamage) {
        $details['unit_damage'][] = [
          'player' => $playerId,
          'unit_uid' => strval($uid),
          'unit_id' => $unitDisplay,
          'unit_raw_id' => strval($beforeUnit['raw_id'] ?? ''),
          'damage' => $afterDamage - $beforeDamage,
          'before_hp' => intval($beforeUnit['current_hp'] ?? 0),
          'after_hp' => intval($afterUnit['current_hp'] ?? 0),
          'upgrades' => displayZoneCardIds(array_values(array_map('strval', $afterUnit['upgrades'] ?? []))),
        ];
      }

      $beforeUpgradesRaw = array_values(array_map('strval', $beforeUnit['upgrades'] ?? []));
      $afterUpgradesRaw = array_values(array_map('strval', $afterUnit['upgrades'] ?? []));
      $beforeUpgrades = $beforeUpgradesRaw;
      $afterUpgrades = $afterUpgradesRaw;
      sort($beforeUpgrades);
      sort($afterUpgrades);
      if ($beforeUpgrades !== $afterUpgrades) {
        $addedUpgradesRaw = addedCardsBetweenZones($beforeUpgradesRaw, $afterUpgradesRaw);
        $removedUpgradesRaw = addedCardsBetweenZones($afterUpgradesRaw, $beforeUpgradesRaw);
        $details['unit_upgrade_changes'][] = [
          'player' => $playerId,
          'unit_uid' => strval($uid),
          'unit_id' => $unitDisplay,
          'unit_raw_id' => strval($beforeUnit['raw_id'] ?? ''),
          'before' => displayZoneCardIds($beforeUpgrades),
          'after' => displayZoneCardIds($afterUpgrades),
          'added' => displayZoneCardIds($addedUpgradesRaw),
          'removed' => displayZoneCardIds($removedUpgradesRaw),
        ];
        $experienceAddedRaw = array_values(array_filter(
          $addedUpgradesRaw,
          static fn(string $raw): bool => $raw === '2007868442'
        ));
        if (count($experienceAddedRaw) > 0) {
          $details['experience_tokens_given'][] = [
            'player' => $playerId,
            'unit_uid' => strval($uid),
            'unit_id' => $unitDisplay,
            'unit_raw_id' => strval($beforeUnit['raw_id'] ?? ''),
            'amount' => count($experienceAddedRaw),
            'token_ids' => displayZoneCardIds($experienceAddedRaw),
          ];
        }
      }

      $beforeReadyState = boolval($beforeUnit['ready'] ?? false);
      $afterReadyState = boolval($afterUnit['ready'] ?? false);
      if ($beforeReadyState !== $afterReadyState) {
        $details['unit_ready_state_changes'][] = [
          'player' => $playerId,
          'unit_uid' => strval($uid),
          'unit_id' => $unitDisplay,
          'unit_raw_id' => strval($beforeUnit['raw_id'] ?? ''),
          'arena' => strval($afterUnit['arena'] ?? $beforeUnit['arena'] ?? ''),
          'before_ready' => $beforeReadyState,
          'after_ready' => $afterReadyState,
          'before_exhausted' => !$beforeReadyState,
          'after_exhausted' => !$afterReadyState,
          'change' => $afterReadyState ? 'readied' : 'exhausted',
        ];
      }

      $beforeCaptives = array_values(array_map('strval', $beforeUnit['captives'] ?? []));
      $afterCaptives = array_values(array_map('strval', $afterUnit['captives'] ?? []));
      sort($beforeCaptives);
      sort($afterCaptives);
      if ($beforeCaptives !== $afterCaptives) {
        $capturedAdded = array_values(array_diff($afterCaptives, $beforeCaptives));
        $capturedReleased = array_values(array_diff($beforeCaptives, $afterCaptives));
        $details['unit_capture_changes'][] = [
          'player' => $playerId,
          'unit_uid' => strval($uid),
          'unit_id' => $unitDisplay,
          'unit_raw_id' => strval($beforeUnit['raw_id'] ?? ''),
          'before' => displayZoneCardIds($beforeCaptives),
          'after' => displayZoneCardIds($afterCaptives),
          'captured_added' => displayZoneCardIds($capturedAdded),
          'captured_released' => displayZoneCardIds($capturedReleased),
        ];
      }

      $beforePower = intval($beforeUnit['current_power'] ?? 0);
      $afterPower = intval($afterUnit['current_power'] ?? 0);
      $beforeMaxHp = intval($beforeUnit['max_hp'] ?? 0);
      $afterMaxHp = intval($afterUnit['max_hp'] ?? 0);
      if ($beforePower !== $afterPower || $beforeMaxHp !== $afterMaxHp) {
        $details['unit_stat_changes'][] = [
          'player' => $playerId,
          'unit_uid' => strval($uid),
          'unit_id' => $unitDisplay,
          'unit_raw_id' => strval($beforeUnit['raw_id'] ?? ''),
          'power' => ['before' => $beforePower, 'after' => $afterPower],
          'max_hp' => ['before' => $beforeMaxHp, 'after' => $afterMaxHp],
        ];
      }
    }

    foreach ($afterUnits as $uid => $afterUnit) {
      if (!is_array($afterUnit)) continue;
      if (isset($beforeUnits[$uid])) continue;
      $rawCardId = strval($afterUnit['raw_id'] ?? '');
      $details['unit_deployed'][] = [
        'player' => $playerId,
        'unit_uid' => strval($uid),
        'unit_id' => displayCardId($rawCardId),
        'unit_raw_id' => $rawCardId,
        'arena' => strval($afterUnit['arena'] ?? ''),
        'from' => strval($afterUnit['from'] ?? ''),
        'is_leader' => boolval($afterUnit['is_leader'] ?? false),
        'ready' => boolval($afterUnit['ready'] ?? false),
        'current_power' => intval($afterUnit['current_power'] ?? 0),
        'current_hp' => intval($afterUnit['current_hp'] ?? 0),
        'max_hp' => intval($afterUnit['max_hp'] ?? 0),
        'upgrades' => displayZoneCardIds(array_values(array_map('strval', $afterUnit['upgrades'] ?? []))),
      ];
      if ($rawCardId !== '' && IsToken($rawCardId)) {
        $details['token_units_created'][] = [
          'player' => $playerId,
          'unit_uid' => strval($uid),
          'unit_id' => displayCardId($rawCardId),
          'unit_raw_id' => $rawCardId,
          'arena' => strval($afterUnit['arena'] ?? ''),
        ];
      }
    }
  }

  $afterMeta = $after['meta'] ?? [];
  $afterPhase = strval($afterMeta['turn_phase'] ?? '');
  $promptPhases = [
    'YESNO',
    'CHOOSEMULTIZONE',
    'MAYCHOOSEMULTIZONE',
    'CHOOSECARD',
    'MAYCHOOSECARD',
    'CHOOSEOPTION',
    'MAYCHOOSEOPTION',
    'BUTTONINPUT',
    'BUTTONINPUTNOPASS',
  ];
  if (in_array($afterPhase, $promptPhases, true)) {
    $turnText = normalizePromptText(strval($afterMeta['turn_parameter'] ?? ''));
    $ctxText = normalizePromptText(strval($afterMeta['dq_context'] ?? ''));
    $promptText = $ctxText !== '' ? $ctxText : $turnText;
    $details['follow_up_prompt'] = [
      'phase' => $afterPhase,
      'player' => intval($afterMeta['turn_player'] ?? 0),
      'text' => $promptText,
      'raw_turn_parameter' => strval($afterMeta['turn_parameter'] ?? ''),
      'raw_dq_context' => strval($afterMeta['dq_context'] ?? ''),
    ];
  }

  $followPrompt = $details['follow_up_prompt'];
  foreach ($details['unit_defeated'] as $defeated) {
    if (!is_array($defeated)) continue;
    $owner = intval($defeated['player'] ?? 0);
    $hasWhenDefeated = boolval($defeated['has_when_defeated'] ?? false);
    $promptForOwner = false;
    if (is_array($followPrompt)) {
      $promptForOwner = intval($followPrompt['player'] ?? 0) === $owner;
    }
    $details['when_defeated_checks'][] = [
      'player' => $owner,
      'unit_id' => strval($defeated['unit_id'] ?? ''),
      'unit_raw_id' => strval($defeated['unit_raw_id'] ?? ''),
      'has_when_defeated' => $hasWhenDefeated,
      'follow_up_prompt_for_owner' => $promptForOwner,
      'follow_up_prompt_phase' => is_array($followPrompt) ? strval($followPrompt['phase'] ?? '') : '',
      'follow_up_prompt_text' => is_array($followPrompt) ? strval($followPrompt['text'] ?? '') : '',
      // "likely_triggered" is conservative: optional prompt exists for defeated unit's owner.
      'likely_triggered' => $hasWhenDefeated && $promptForOwner,
    ];
  }

  $actionType = strval($action['type'] ?? '');
  $actionButton = strval($action['buttonInput'] ?? '');
  $actionMode = intval($action['mode'] ?? 0);
  $actionCardIsLeader = ($actionCardRaw !== '' ? boolval(CardIDIsLeader($actionCardRaw)) : false);
  $actionCardId = ($actionCardRaw !== '' ? displayCardId($actionCardRaw) : '');
  $beforeMeta = $before['meta'] ?? [];
  $beforePromptText = trim(
    normalizePromptText(strval($beforeMeta['dq_context'] ?? '')) . ' ' .
    normalizePromptText(strval($beforeMeta['turn_parameter'] ?? ''))
  );
  $beforePhase = strval($beforeMeta['turn_phase'] ?? '');
  $beforePromptLower = strtolower($beforePromptText);
  if (($beforePhase === 'MAYCHOOSEMULTIZONE' || $beforePhase === 'CHOOSEMULTIZONE') && str_contains($beforePromptLower, 'exploit')) {
    $selectedCount = 0;
    if ($actionType === 'choose_zone' && strval($action['cardID'] ?? '') !== '') {
      $selectedCount = 1;
    } elseif ($actionType === 'multi_choose') {
      $selectedCount = max(0, intval($action['chkCount'] ?? 0));
    }
    $details['exploit_resolution'] = [
      'player' => $actingPlayer,
      'selected_count' => $selectedCount,
      'action_type' => $actionType,
      'prompt' => $beforePromptText,
    ];
  }

  $pendingLeaderActionTrigger = null;
  if ($actionType === 'play_character' && $actionCardIsLeader) {
    $pendingLeaderActionTrigger = [
      'player' => $actingPlayer,
      'leader_id' => $actionCardId,
      'leader_raw_id' => $actionCardRaw,
      'action_type' => $actionType,
      'mode' => $actionMode,
      'button_input' => $actionButton,
      'before_prompt' => $beforePromptText,
      'trigger' => 'leader_action_selected',
    ];
  }

  $epicTriggeredThisAction = false;
  foreach ($details['unit_deployed'] as $deployed) {
    if (!is_array($deployed)) continue;
    if (!boolval($deployed['is_leader'] ?? false)) continue;
    $deployFrom = strtoupper(strval($deployed['from'] ?? ''));
    if ($deployFrom === 'EPICACTION') {
      $epicTriggeredThisAction = true;
      $details['epic_action_triggers'][] = [
        'player' => intval($deployed['player'] ?? 0),
        'leader_id' => strval($deployed['unit_id'] ?? ''),
        'leader_raw_id' => strval($deployed['unit_raw_id'] ?? ''),
        'action_type' => $actionType,
        'mode' => $actionMode,
        'button_input' => $actionButton,
        'trigger' => 'leader_epic_action_deploy',
      ];
      continue;
    }
    $details['leader_action_triggers'][] = [
      'player' => intval($deployed['player'] ?? 0),
      'leader_id' => strval($deployed['unit_id'] ?? ''),
      'leader_raw_id' => strval($deployed['unit_raw_id'] ?? ''),
      'action_type' => $actionType,
      'mode' => $actionMode,
      'button_input' => $actionButton,
      'trigger' => 'leader_deployed',
      'deploy_from' => $deployFrom,
    ];
  }

  if (is_array($pendingLeaderActionTrigger) && !$epicTriggeredThisAction) {
    $details['leader_action_triggers'][] = $pendingLeaderActionTrigger;
  }

  return $details;
}

function boardStateSummary(array $snapshot): array
{
  $out = [];
  foreach (['player_1', 'player_2'] as $playerKey) {
    $p = $snapshot[$playerKey] ?? [];
    $zones = $p['zones'] ?? [];
    $resources = $p['resources'] ?? [];
    $counts = $p['counts'] ?? [];
    $units = $p['units'] ?? [];
    $out[$playerKey] = [
      'base_hp' => intval($p['base']['health'] ?? 0),
      'damage_taken' => intval($p['base']['damage_taken'] ?? 0),
      'force' => [
        'available' => boolval($p['force']['available'] ?? false),
        'status' => strval($p['force']['status'] ?? 'unavailable'),
        'times_used_this_phase' => intval($p['force']['times_used_this_phase'] ?? 0),
      ],
      'hand_count' => intval($counts['hand'] ?? 0),
      'hand_cards' => displayZoneCardIds($zones['hand'] ?? []),
      'resources' => [
        'available' => intval($resources['available'] ?? 0),
        'spent' => intval($resources['spent'] ?? 0),
        'total' => intval($resources['total_cards'] ?? 0),
        'ready' => intval($resources['ready_cards'] ?? 0),
        'exhausted' => intval($resources['exhausted_cards'] ?? 0),
      ],
      'units' => [
        'active_count' => intval($units['active_count'] ?? 0),
        'land' => displayZoneCardIds($zones['land_arena'] ?? []),
        'space' => displayZoneCardIds($zones['space_arena'] ?? []),
        'land_ready' => displayZoneCardIds($zones['land_ready'] ?? []),
        'space_ready' => displayZoneCardIds($zones['space_ready'] ?? []),
        'land_exhausted' => displayZoneCardIds($zones['land_exhausted'] ?? []),
        'space_exhausted' => displayZoneCardIds($zones['space_exhausted'] ?? []),
        'details' => displayUnitDetails($units['details'] ?? []),
        'land_details' => [
          'all' => displayUnitDetails($units['land']['details']['all'] ?? []),
          'ready' => displayUnitDetails($units['land']['details']['ready'] ?? []),
          'exhausted' => displayUnitDetails($units['land']['details']['exhausted'] ?? []),
        ],
        'space_details' => [
          'all' => displayUnitDetails($units['space']['details']['all'] ?? []),
          'ready' => displayUnitDetails($units['space']['details']['ready'] ?? []),
          'exhausted' => displayUnitDetails($units['space']['details']['exhausted'] ?? []),
        ],
      ],
      'deck_count' => intval($counts['deck'] ?? 0),
      'discard_count' => intval($counts['discard'] ?? 0),
    ];
  }
  return $out;
}

$events = [];
$executedActionCount = 0;
$illegalActions = 0;
$forcedPasses = 0;
$noOpFilteredActions = 0;
$noOpActionRetries = 0;
$repeatChosenCount = 0;
$lastChosenStableKey = '';
$terminatedReason = '';
$noLegalActionStreak = 0;
$noOpBlacklistByState = [];
$replayCommands = [];

for ($step = 1; $step <= $actionCap; ++$step) {
  $GLOBALS['__runner_checkpoint'] = 'loop_step_' . $step;
  $preStepSnapshot = phaseSnapshot();
  if (isBaseZeroGameOver($preStepSnapshot)) break;

  $turnSnapshot = $GLOBALS['turn'] ?? ['-', '0'];
  $phase = strval($turnSnapshot[0] ?? '-');
  $round = intval($GLOBALS['currentRound'] ?? 1);
  $turnPlayer = intval($turnSnapshot[1] ?? 0);
  $priorityPlayer = intval($GLOBALS['currentPlayer'] ?? 0);
  $resolvedActing = resolveActingPlayerAndLegalActions($turnPlayer, $priorityPlayer);
  $playerId = intval($resolvedActing['player_id'] ?? ($turnPlayer > 0 ? $turnPlayer : 1));
  $legalActions = is_array($resolvedActing['actions'] ?? null) ? $resolvedActing['actions'] : [];

  $phaseBegin = phaseSnapshot();

  if (count($legalActions) === 0) {
    $noLegalActionStreak++;
    if ($noLegalActionStreak >= 3) {
      $terminatedReason = 'no_legal_actions';
      break;
    }
    continue;
  }
  $noLegalActionStreak = 0;

  $stateFingerprint = snapshotFingerprint($phaseBegin);
  if (!isset($noOpBlacklistByState[$stateFingerprint])) {
    $noOpBlacklistByState[$stateFingerprint] = [];
  }
  $attemptedNoOpKeys = [];
  $chosen = null;
  $chosenCardRefRawBefore = '';
  $result = ['ok' => false, 'message' => ''];
  $ok = false;
  $phaseEnd = $phaseBegin;

  while (true) {
    $candidateActions = array_values(array_filter(
      $legalActions,
      static function (array $action) use ($stateFingerprint, $noOpBlacklistByState, $attemptedNoOpKeys): bool {
        $key = json_encode($action, JSON_UNESCAPED_SLASHES);
        if (isset($noOpBlacklistByState[$stateFingerprint][$key])) return false;
        if (isset($attemptedNoOpKeys[$key])) return false;
        return true;
      }
    ));
    if (count($candidateActions) === 0) {
      $candidateActions = array_values(array_filter(
        $legalActions,
        static function (array $action) use ($attemptedNoOpKeys): bool {
          $key = json_encode($action, JSON_UNESCAPED_SLASHES);
          return !isset($attemptedNoOpKeys[$key]);
        }
      ));
    }
    if (count($candidateActions) === 0) {
      $candidateActions = $legalActions;
    }

    $chosen = chooseAction(
      $candidateActions,
      $seed,
      $step,
      $playerId,
      $round,
      $phase,
      $policy,
      $phaseBegin,
      ['mcts' => $mctsConfig]
    );
    if ($chosen === null) break;

    // Prevent pathological loops where one always-legal action is repeatedly chosen.
    $chosenStableKey = json_encode($chosen, JSON_UNESCAPED_SLASHES);
    if ($chosenStableKey === $lastChosenStableKey) $repeatChosenCount++;
    else $repeatChosenCount = 1;
    $lastChosenStableKey = $chosenStableKey;

    if ($repeatChosenCount >= 6) {
      $passAction = findPassAction($candidateActions);
      if ($passAction !== null) {
        $chosen = $passAction;
        $forcedPasses++;
        $repeatChosenCount = 0;
        $chosenStableKey = json_encode($chosen, JSON_UNESCAPED_SLASHES);
        $lastChosenStableKey = $chosenStableKey;
      }
    }

    // Resolve card reference before applyAction mutates zones (hand/resources/board).
    $chosenCardRefRawBefore = resolveCardReferenceRaw($playerId, $chosen);

    $GLOBALS['gameName'] = $gameName;
    $GLOBALS['__runner_last_action'] = [
      'step' => $step,
      'round' => $round,
      'phase' => $phase,
      'player' => $playerId,
      'action' => $chosen,
    ];
    $result = applyAction($playerId, $chosen);
    $ok = boolval($result['ok'] ?? false);
    $phaseEnd = phaseSnapshot();

    // Illegal-at-apply can happen when hidden/stateful legality differs between selection time
    // and apply-time validation. Retry another candidate in the same step so illegal probes do
    // not consume an action slot in the timeline when alternatives exist.
    if (!$ok) {
      $noOpBlacklistByState[$stateFingerprint][$chosenStableKey] = true;
      $attemptedNoOpKeys[$chosenStableKey] = true;

      $turnSnapshotNow = $GLOBALS['turn'] ?? ['-', '0'];
      $turnPlayerNow = intval($turnSnapshotNow[1] ?? 0);
      $priorityPlayerNow = intval($GLOBALS['currentPlayer'] ?? 0);
      $resolvedNow = resolveActingPlayerAndLegalActions($turnPlayerNow, $priorityPlayerNow);
      $preferredPlayerNow = intval($resolvedNow['player_id'] ?? $playerId);
      $legalActions = is_array($resolvedNow['actions'] ?? null) ? $resolvedNow['actions'] : [];

      if ($preferredPlayerNow !== $playerId && count($legalActions) > 0) {
        $playerId = $preferredPlayerNow;
        // Action candidates are player-specific; reset attempted probes when actor changes.
        $attemptedNoOpKeys = [];
        continue;
      }

      if (count($legalActions) > 0) {
        $hasUnattemptedAlternative = false;
        foreach ($legalActions as $candidate) {
          $candidateKey = json_encode($candidate, JSON_UNESCAPED_SLASHES);
          if (!isset($attemptedNoOpKeys[$candidateKey])) {
            $hasUnattemptedAlternative = true;
            break;
          }
        }
        if ($hasUnattemptedAlternative) {
          continue;
        }
      }

      // Turn-boundary safety: if the active player changed under us, retry using the other player
      // in the same step before recording a hard illegal.
      $otherPlayerId = $playerId === 1 ? 2 : 1;
      $otherLegalActions = getLegalActions($otherPlayerId);
      if (count($otherLegalActions) > 0) {
        $playerId = $otherPlayerId;
        $legalActions = $otherLegalActions;
        // attemptedNoOpKeys are per-player action probes for this state; switching players should reset.
        $attemptedNoOpKeys = [];
        continue;
      }

      // No recoverable alternative found; keep the illegal event for diagnosis.
      break;
    }

    if (!isNoOpResolvedAction($phaseBegin, $phaseEnd, $chosen, $ok)) {
      break;
    }

    $noOpFilteredActions++;
    $noOpActionRetries++;
    $noOpBlacklistByState[$stateFingerprint][$chosenStableKey] = true;
    $attemptedNoOpKeys[$chosenStableKey] = true;
    if (count($attemptedNoOpKeys) >= count($legalActions)) {
      $result['message'] = trim(strval($result['message'] ?? '') . ' no_op_action_reverted');
      break;
    }
  }

  if ($chosen === null) break;
  $executedActionCount++;
  if (!$ok) $illegalActions++;
  else $replayCommands[] = formatReplayCommandLine($playerId, $chosen);

  $cardRefRaw = $chosenCardRefRawBefore;
  $cardRef = displayCardId($cardRefRaw);
  $cardCost = $cardRefRaw !== '' ? intval(CardCost($cardRefRaw)) : null;
  $cardType = $cardRefRaw !== '' ? strval(DefinedCardType($cardRefRaw)) : '';

  if ($includeDetailedEvents) {
    $effects = deriveEffects($phaseBegin, $phaseEnd);
    $actionDetails = summarizeActionDetails($phaseBegin, $phaseEnd, $chosen, $playerId, $cardRefRaw);
    $openingHandP1 = zoneCardCount($openingState['player_1']['zones']['hand'] ?? [], HandPieces());
    $openingHandP2 = zoneCardCount($openingState['player_2']['zones']['hand'] ?? [], HandPieces());
    $effects['player_1']['opening_hand_count'] = $openingHandP1;
    $effects['player_2']['opening_hand_count'] = $openingHandP2;

    $event = [
      'step' => $step,
      'round' => $round,
      'phase' => $phase,
      'player' => $playerId,
      'action' => $chosen,
      'is_decision' => isDecisionLikeAction($chosen),
      'card' => [
        'id' => $cardRef,
        'raw_id' => $cardRefRaw,
        'cost' => $cardCost,
        'type' => $cardType,
        'keywords' => ($cardRefRaw !== '' ? cardKeywordFlags($cardRefRaw, $playerId) : []),
      ],
      'legal_actions' => $legalActions,
      'legal_action_count' => count($legalActions),
      'legal_actions_by_type' => legalActionTypeSummary($legalActions),
      'apply_ok' => $ok,
      'message' => strval($result['message'] ?? ''),
      'next_player' => intval($GLOBALS['currentPlayer'] ?? $playerId),
      'next_phase' => strval(($GLOBALS['turn'][0] ?? '-')),
      'initiative_player' => intval($GLOBALS['initiativePlayer'] ?? 0),
      'initiative_taken' => intval($GLOBALS['initiativeTaken'] ?? 0),
      'phase_state_begin' => $phaseBegin,
      'phase_state_end' => $phaseEnd,
      'board_state_begin' => boardStateSummary($phaseBegin),
      'board_state_end' => boardStateSummary($phaseEnd),
      'action_details' => $actionDetails,
      'effects' => $effects,
    ];
    $events[] = $event;
  }

  $GLOBALS['gameName'] = $gameName;
  WriteLog('Sim step ' . $step, $playerId, false, $runnerBaseDir . '/', !$ok, [
    'action' => 'engine_apply_action',
    'result' => $ok ? 'ok' : 'illegal',
    'action_type' => strval($chosen['type'] ?? ''),
    'mode' => intval($chosen['mode'] ?? 0),
    'card' => $cardRef,
    'round' => $round,
    'phase' => $phase,
    'policy' => $policy,
    'extra' => [
      'card_cost' => $cardCost,
      'card_type' => $cardType,
      'resources_available' => $phaseBegin['player_' . $playerId]['resources']['available'] ?? null,
    ],
  ]);
}

if ($terminatedReason === '' && $executedActionCount >= $actionCap) {
  $terminatedReason = 'action_cap_reached';
}
$replayCommandfileBody = '';
if (count($replayCommands) > 0) {
  $replayCommandfileBody = implode("\r\n", $replayCommands) . "\r\n";
}
file_put_contents($replayCommandfilePath, $replayCommandfileBody);
$GLOBALS['__runner_checkpoint'] = 'building_response';

$finalState = phaseSnapshot();
$winner = baseWinnerFromSnapshot($finalState);
$gameOver = $winner === 1 || $winner === 2;
if (!$gameOver && boolval(IsGameOver()) && $terminatedReason === '') {
  $terminatedReason = 'engine_game_over_without_base_zero';
}
$turns = intval($GLOBALS['currentRound'] ?? 0);
$roundPages = $includeDetailedEvents ? groupedEventsByRound($events) : [];
$leaderActionTriggerCount = 0;
$epicActionTriggerCount = 0;
if ($includeDetailedEvents) {
  foreach ($events as $evt) {
    if (!is_array($evt)) continue;
    $d = $evt['action_details'] ?? null;
    if (!is_array($d)) continue;
    $leaderActionTriggerCount += is_array($d['leader_action_triggers'] ?? null) ? count($d['leader_action_triggers']) : 0;
    $epicActionTriggerCount += is_array($d['epic_action_triggers'] ?? null) ? count($d['epic_action_triggers']) : 0;
  }
}

$response = [
  'match_id' => $matchID,
  'seed' => $seed,
  'winner' => $winner,
  'turns' => $turns,
  'deck_a' => $deckAInput,
  'deck_b' => $deckBInput,
  'log_path' => LogPath($gameName, $runnerBaseDir . '/'),
  'stats' => [
    'events' => $executedActionCount,
    'illegal_actions' => $illegalActions,
    'game_over' => $gameOver,
    'policy' => $policy,
    'forced_passes' => $forcedPasses,
    'no_op_filtered_actions' => $noOpFilteredActions,
    'no_op_action_retries' => $noOpActionRetries,
    'leader_action_triggers' => $leaderActionTriggerCount,
    'epic_action_triggers' => $epicActionTriggerCount,
    'max_actions_requested' => $maxActions,
    'action_cap' => $actionCap,
    'terminated_reason' => $terminatedReason,
    'mcts_iterations' => ($policy === 'mcts' ? $mctsIterations : 0),
    'mcts_max_depth' => ($policy === 'mcts' ? $mctsMaxDepth : 0),
  ],
  'setup' => [
    'starting_round' => intval($GLOBALS['currentRound'] ?? 1),
    'initiative_player' => intval($GLOBALS['initiativePlayer'] ?? 0),
    'initiative_taken' => intval($GLOBALS['initiativeTaken'] ?? 0),
  ],
  'opening' => [
    'player_1' => [
      'hand_count' => zoneCardCount($openingState['player_1']['zones']['hand'] ?? [], HandPieces()),
      'deck_count' => zoneCardCount($openingState['player_1']['zones']['deck'] ?? [], DeckPieces()),
      'resource_cards' => intval($openingState['player_1']['resources']['total_cards'] ?? 0),
    ],
    'player_2' => [
      'hand_count' => zoneCardCount($openingState['player_2']['zones']['hand'] ?? [], HandPieces()),
      'deck_count' => zoneCardCount($openingState['player_2']['zones']['deck'] ?? [], DeckPieces()),
      'resource_cards' => intval($openingState['player_2']['resources']['total_cards'] ?? 0),
    ],
  ],
  'final_state' => ($includeDetailedEvents ? $finalState : (object)[]),
  'events' => ($includeDetailedEvents ? $events : []),
  'round_pages' => ($includeDetailedEvents ? $roundPages : []),
  'replay' => [
    'orig_gamestate_path' => $replayOrigGamestatePath,
    'commandfile_path' => $replayCommandfilePath,
    'command_count' => count($replayCommands),
    'had_illegal_actions' => $illegalActions > 0,
  ],
];

$json = json_encode($response, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE | JSON_PARTIAL_OUTPUT_ON_ERROR);
if ($json === false) {
  $fallback = [
    'match_id' => $matchID,
    'seed' => $seed,
    'winner' => $winner,
    'turns' => intval($GLOBALS['currentRound'] ?? 0),
    'stats' => [
      'events' => $executedActionCount,
      'illegal_actions' => $illegalActions,
      'game_over' => $gameOver,
      'policy' => $policy,
      'forced_passes' => $forcedPasses,
      'no_op_filtered_actions' => $noOpFilteredActions,
      'no_op_action_retries' => $noOpActionRetries,
      'max_actions_requested' => $maxActions,
      'action_cap' => $actionCap,
      'terminated_reason' => 'json_encode_failed',
      'mcts_iterations' => ($policy === 'mcts' ? $mctsIterations : 0),
      'mcts_max_depth' => ($policy === 'mcts' ? $mctsMaxDepth : 0),
      'json_error' => json_last_error_msg(),
    ],
    'events' => [],
    'round_pages' => [],
  ];
  $json = json_encode($fallback, JSON_UNESCAPED_SLASHES);
}
$GLOBALS['__runner_finished'] = true;
$GLOBALS['__runner_checkpoint'] = 'finished';
echo $json;
