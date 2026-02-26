<?php

declare(strict_types=1);

error_reporting(0);
ini_set('display_errors', '0');
ini_set('display_startup_errors', '0');

require_once __DIR__ . '/../Engine/HeadlessEngine.php';

$options = getopt('', ['seed:', 'deck-a:', 'deck-b:', 'match-id:', 'log-format::', 'max-actions:']);
$seed = intval($options['seed'] ?? 0);
$deckAInput = $options['deck-a'] ?? 'deck_a';
$deckBInput = $options['deck-b'] ?? 'deck_b';
$matchID = intval($options['match-id'] ?? 0);
$logFormat = $options['log-format'] ?? 'json';
$maxActions = max(1, intval($options['max-actions'] ?? 500));

$deckA = normalizeDecklistForHeadless($deckAInput);
$deckB = normalizeDecklistForHeadless($deckBInput);

$gameName = 'sim_' . $matchID;
$GLOBALS['gameName'] = $gameName;
if (!is_dir("./Games/$gameName")) mkdir("./Games/$gameName", 0700, true);
CreateLog($gameName);
SetMatchSeed(strval($seed), $gameName);
if ($logFormat === 'json') SetStructuredLogMode(true);

initHeadlessGame($deckA, $deckB, $seed);
$GLOBALS['gameName'] = $gameName;

function chooseAction(array $legalActions): ?array
{
  if (count($legalActions) === 0) return null;
  foreach ($legalActions as $action) {
    if (($action['type'] ?? '') !== 'pass') return $action;
  }
  return $legalActions[0];
}

function resolveCardReference(int $playerId, array $action): string
{
  $type = strval($action['type'] ?? '');
  $cardID = $action['cardID'] ?? 0;

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
  if ($type === 'play_item') {
    $items = &GetItems($playerId);
    return strval($items[intval($cardID)] ?? '');
  }
  if ($type === 'play_ally') {
    $allies = &GetAllies($playerId);
    return strval($allies[intval($cardID)] ?? '');
  }
  if ($type === 'arsenal') return strval($cardID);
  return '';
}

function allyArenaCardIds(int $playerId): array
{
  $allies = &GetAllies($playerId);
  $land = [];
  $space = [];
  for ($i = 0; $i < count($allies); $i += AllyPieces()) {
    $cardId = strval($allies[$i] ?? '');
    if ($cardId === '') continue;
    $override = strval($allies[$i + 15] ?? 'NA');
    $arena = $override !== 'NA' ? $override : strval(CardArenas($cardId));
    if (strtoupper($arena) === 'SPACE') $space[] = $cardId;
    else $land[] = $cardId;
  }
  return ['land' => $land, 'space' => $space];
}

function playerPhaseSnapshot(int $playerId): array
{
  $hand = &GetHand($playerId);
  $deck = &GetDeck($playerId);
  $discard = &GetDiscard($playerId);
  $resources = &GetResources($playerId);
  $arenas = allyArenaCardIds($playerId);

  return [
    'resources' => [
      'raw' => $resources,
      'available' => intval($resources[0] ?? 0),
      'spent' => intval($resources[1] ?? 0),
    ],
    'zones' => [
      'hand' => $hand,
      'deck' => $deck,
      'discard' => $discard,
      'land_arena' => $arenas['land'],
      'space_arena' => $arenas['space'],
    ],
  ];
}

function phaseSnapshot(): array
{
  return [
    'player_1' => playerPhaseSnapshot(1),
    'player_2' => playerPhaseSnapshot(2),
  ];
}

function numericDelta(int $before, int $after): int
{
  return $after - $before;
}

function deriveEffects(array $before, array $after): array
{
  $effects = [];
  foreach (['player_1', 'player_2'] as $playerKey) {
    $b = $before[$playerKey];
    $a = $after[$playerKey];
    $effects[$playerKey] = [
      'resources_available_delta' => numericDelta(intval($b['resources']['available']), intval($a['resources']['available'])),
      'hand_count_delta' => numericDelta(count($b['zones']['hand']), count($a['zones']['hand'])),
      'deck_count_delta' => numericDelta(count($b['zones']['deck']), count($a['zones']['deck'])),
      'discard_count_delta' => numericDelta(count($b['zones']['discard']), count($a['zones']['discard'])),
      'land_arena_count_delta' => numericDelta(count($b['zones']['land_arena']), count($a['zones']['land_arena'])),
      'space_arena_count_delta' => numericDelta(count($b['zones']['space_arena']), count($a['zones']['space_arena'])),
    ];
  }
  return $effects;
}

$events = [];
$illegalActions = 0;

for ($step = 1; $step <= $maxActions && !IsGameOver(); ++$step) {
  $playerId = intval($GLOBALS['currentPlayer'] ?? 1);
  $turnSnapshot = $GLOBALS['turn'] ?? ['-', '0'];
  $phase = strval($turnSnapshot[0] ?? '-');
  $round = intval($GLOBALS['currentRound'] ?? 1);

  $phaseBegin = phaseSnapshot();
  $legalActions = getLegalActions($playerId);
  $chosen = chooseAction($legalActions);
  if ($chosen === null) break;

  $cardRef = resolveCardReference($playerId, $chosen);
  $cardCost = $cardRef !== '' ? intval(CardCost($cardRef)) : null;
  $cardType = $cardRef !== '' ? strval(DefinedCardType($cardRef)) : '';

  $GLOBALS['gameName'] = $gameName;
  $result = applyAction($playerId, $chosen);
  $ok = boolval($result['ok'] ?? false);
  if (!$ok) $illegalActions++;

  $phaseEnd = phaseSnapshot();

  $event = [
    'step' => $step,
    'round' => $round,
    'phase' => $phase,
    'player' => $playerId,
    'action' => $chosen,
    'card' => [
      'id' => $cardRef,
      'cost' => $cardCost,
      'type' => $cardType,
    ],
    'legal_action_count' => count($legalActions),
    'apply_ok' => $ok,
    'message' => strval($result['message'] ?? ''),
    'next_player' => intval($GLOBALS['currentPlayer'] ?? $playerId),
    'next_phase' => strval(($GLOBALS['turn'][0] ?? '-')),
    'phase_state_begin' => $phaseBegin,
    'phase_state_end' => $phaseEnd,
    'effects' => deriveEffects($phaseBegin, $phaseEnd),
  ];
  $events[] = $event;

  $GLOBALS['gameName'] = $gameName;
  WriteLog('Sim step ' . $step, $playerId, false, './', !$ok, [
    'action' => 'engine_apply_action',
    'result' => $ok ? 'ok' : 'illegal',
    'action_type' => strval($chosen['type'] ?? ''),
    'mode' => intval($chosen['mode'] ?? 0),
    'card' => $cardRef,
    'round' => $round,
    'phase' => $phase,
    'extra' => [
      'card_cost' => $cardCost,
      'card_type' => $cardType,
      'resources_available' => $phaseBegin['player_' . $playerId]['resources']['available'] ?? null,
    ],
  ]);
}

$winner = intval($GLOBALS['winner'] ?? 0);
$turns = intval($GLOBALS['currentRound'] ?? 0);

$response = [
  'match_id' => $matchID,
  'seed' => $seed,
  'winner' => $winner,
  'turns' => $turns,
  'deck_a' => $deckAInput,
  'deck_b' => $deckBInput,
  'log_path' => LogPath($gameName),
  'stats' => [
    'events' => count($events),
    'illegal_actions' => $illegalActions,
    'game_over' => IsGameOver(),
  ],
  'events' => $events,
];

echo json_encode($response, JSON_UNESCAPED_SLASHES);
