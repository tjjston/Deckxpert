<?php

declare(strict_types=1);

ob_start();
error_reporting(0);
ini_set('display_errors', '0');
ini_set('display_startup_errors', '0');
include_once __DIR__ . '/Engine/HeadlessEngine.php';
ob_end_clean();

function readEngineCliRequest(): array
{
  $raw = stream_get_contents(STDIN);
  $payload = json_decode($raw ?: '', true);
  if (!is_array($payload)) {
    throw new InvalidArgumentException('Input must be valid JSON object.');
  }
  if (!isset($payload['type'])) {
    throw new InvalidArgumentException('Missing required key: type');
  }
  return $payload;
}

function handleInitGame(array $request): array
{
  foreach (['deckA', 'deckB', 'seed'] as $required) {
    if (!array_key_exists($required, $request)) {
      throw new InvalidArgumentException("Missing required key: {$required}");
    }
  }

  $deckA = normalizeDecklistForHeadless($request['deckA']);
  $deckB = normalizeDecklistForHeadless($request['deckB']);
  $seed = intval($request['seed']);

  initHeadlessGame($deckA, $deckB, $seed);

  return [
    'ok' => true,
    'type' => 'init_game',
    'events' => [
      [
        'event' => 'game_initialized',
        'seed' => $seed,
        'deckSizes' => ['player1' => count($deckA['main']), 'player2' => count($deckB['main'])],
      ],
      [
        'event' => 'state_snapshot',
        'state' => headlessStateModel(),
      ],
      [
        'event' => 'observation',
        'playerId' => 1,
        'observation' => getObservation(1),
      ],
      [
        'event' => 'legal_actions',
        'playerId' => 1,
        'actions' => getLegalActions(1),
      ],
    ],
  ];
}


function maybeInitializeFromRequest(array $request): void
{
  if (array_key_exists('deckA', $request) && array_key_exists('deckB', $request) && array_key_exists('seed', $request)) {
    $deckA = normalizeDecklistForHeadless($request['deckA']);
    $deckB = normalizeDecklistForHeadless($request['deckB']);
    $seed = intval($request['seed']);
    initHeadlessGame($deckA, $deckB, $seed);
  }
}

function handleGetObservation(array $request): array
{
  maybeInitializeFromRequest($request);
  $playerId = intval($request['player_id'] ?? 1);
  return ['ok' => true, 'type' => 'get_observation', 'playerId' => $playerId, 'observation' => getObservation($playerId)];
}

function handleGetLegalActions(array $request): array
{
  maybeInitializeFromRequest($request);
  $playerId = intval($request['player_id'] ?? 1);
  return ['ok' => true, 'type' => 'get_legal_actions', 'playerId' => $playerId, 'actions' => getLegalActions($playerId)];
}

function handleApplyAction(array $request): array
{
  maybeInitializeFromRequest($request);
  $playerId = intval($request['player_id'] ?? 1);
  $action = $request['action'] ?? null;
  if (!is_array($action)) {
    throw new InvalidArgumentException('apply_action requires an action object.');
  }
  $result = applyAction($playerId, $action);
  return ['ok' => true, 'type' => 'apply_action', 'playerId' => $playerId, 'result' => $result];
}

try {
  $request = readEngineCliRequest();
  $type = strval($request['type']);

  if ($type === 'init_game') {
    $response = handleInitGame($request);
  } elseif ($type === 'get_observation') {
    $response = handleGetObservation($request);
  } elseif ($type === 'get_legal_actions') {
    $response = handleGetLegalActions($request);
  } elseif ($type === 'apply_action') {
    $response = handleApplyAction($request);
  } else {
    throw new InvalidArgumentException('Unsupported type: ' . $type);
  }

  echo json_encode($response, JSON_UNESCAPED_SLASHES);
} catch (Throwable $t) {
  echo json_encode([
    'ok' => false,
    'error' => $t->getMessage(),
    'type' => 'error',
  ], JSON_UNESCAPED_SLASHES);
}
