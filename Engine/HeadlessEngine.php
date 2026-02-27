<?php

declare(strict_types=1);

include_once __DIR__ . '/../GameLogic.php';
include_once __DIR__ . '/../GameTerms.php';
include_once __DIR__ . '/../Libraries/SHMOPLibraries.php';
include_once __DIR__ . '/../Libraries/StatFunctions.php';
include_once __DIR__ . '/../Libraries/PlayerSettings.php';
include_once __DIR__ . '/../Libraries/UILibraries2.php';
include_once __DIR__ . '/../AI/PlayerMacros.php';
include_once __DIR__ . '/../Libraries/CoreLibraries.php';
include_once __DIR__ . '/../WriteLog.php';
include_once __DIR__ . '/Action.php';
include_once __DIR__ . '/LegalActions.php';

$GLOBALS['headlessInitialDeckSizes'] = [1 => 0, 2 => 0];
$GLOBALS['headlessSeed'] = 0;


if (!function_exists('GamestateSanitize')) {
  function GamestateSanitize($input)
  {
    $output = str_replace(",", "<44>", strval($input));
    $output = str_replace(" ", "<45>", $output);
    $output = str_replace("-", "<46>", $output);
    $output = str_replace("_", "<47>", $output);
    return $output;
  }
}

if (!function_exists('GamestateUnsanitize')) {
  function GamestateUnsanitize($input)
  {
    $output = str_replace("<44>", ",", strval($input));
    $output = str_replace("<45>", " ", $output);
    $output = str_replace("<46>", "-", $output);
    $output = str_replace("<47>", "_", $output);
    return $output;
  }
}


if (!function_exists('MakeGamestateBackup')) {
  function MakeGamestateBackup($filename = "gamestateBackup.txt")
  {
    // No-op in headless mode.
  }
}

if (!function_exists('MakeStartTurnBackup')) {
  function MakeStartTurnBackup()
  {
    // No-op in headless mode.
  }
}

if (!function_exists('UpdateGameState')) {
  function UpdateGameState($playerID): void
  {
    BuildMyGamestate($playerID);
  }
}

if (!function_exists('DoGamestateUpdate')) {
  function DoGamestateUpdate(): void
  {
    // Headless mode does not persist serialized game files.
  }
}

if (!function_exists('BuildMainPlayerGamestate')) {
  function BuildMainPlayerGamestate(): void
  {
    // Compatibility alias for mixed-case calls.
  }
}

if (!function_exists('BuildMyGamestate')) {
  function BuildMyGamestate($playerID): void
  {
    global $p1Deck, $p1Hand, $p1Resources, $p1CharEquip, $p1Arsenal, $playerHealths, $p1Auras, $p1Pitch, $p1Banish, $p1ClassState, $p1Items;
    global $p1CharacterEffects, $p1Discard, $p1CardStats, $p1TurnStats, $p1Material;
    global $p2Deck, $p2Hand, $p2Resources, $p2CharEquip, $p2Arsenal, $p2Auras, $p2Pitch, $p2Banish, $p2ClassState, $p2Items;
    global $p2CharacterEffects, $p2Discard, $p2CardStats, $p2TurnStats, $p2Material;
    global $myDeck, $myHand, $myResources, $myCharacter, $myArsenal, $myHealth, $myAuras, $myPitch, $myBanish, $myClassState, $myItems;
    global $myCharacterEffects, $myDiscard, $myCardStats, $myTurnStats, $myMaterial;
    global $theirDeck, $theirHand, $theirResources, $theirCharacter, $theirArsenal, $theirHealth, $theirAuras, $theirPitch, $theirBanish, $theirClassState, $theirItems;
    global $theirCharacterEffects, $theirDiscard, $theirCardStats, $theirTurnStats, $theirMaterial;

    $myHand = $playerID == 1 ? $p1Hand : $p2Hand;
    $myDeck = $playerID == 1 ? $p1Deck : $p2Deck;
    $myResources = $playerID == 1 ? $p1Resources : $p2Resources;
    $myCharacter = $playerID == 1 ? $p1CharEquip : $p2CharEquip;
    $myArsenal = $playerID == 1 ? $p1Arsenal : $p2Arsenal;
    $myHealth = $playerID == 1 ? ($playerHealths[0] ?? 0) : ($playerHealths[1] ?? 0);
    $myItems = $playerID == 1 ? $p1Items : $p2Items;
    $myAuras = $playerID == 1 ? $p1Auras : $p2Auras;
    $myDiscard = $playerID == 1 ? $p1Discard : $p2Discard;
    $myPitch = $playerID == 1 ? $p1Pitch : $p2Pitch;
    $myBanish = $playerID == 1 ? $p1Banish : $p2Banish;
    $myClassState = $playerID == 1 ? $p1ClassState : $p2ClassState;
    $myCharacterEffects = $playerID == 1 ? $p1CharacterEffects : $p2CharacterEffects;
    $myMaterial = $playerID == 1 ? $p1Material : $p2Material;
    $myCardStats = $playerID == 1 ? $p1CardStats : $p2CardStats;
    $myTurnStats = $playerID == 1 ? $p1TurnStats : $p2TurnStats;

    $theirHand = $playerID == 1 ? $p2Hand : $p1Hand;
    $theirDeck = $playerID == 1 ? $p2Deck : $p1Deck;
    $theirResources = $playerID == 1 ? $p2Resources : $p1Resources;
    $theirCharacter = $playerID == 1 ? $p2CharEquip : $p1CharEquip;
    $theirArsenal = $playerID == 1 ? $p2Arsenal : $p1Arsenal;
    $theirHealth = $playerID == 1 ? ($playerHealths[1] ?? 0) : ($playerHealths[0] ?? 0);
    $theirItems = $playerID == 1 ? $p2Items : $p1Items;
    $theirAuras = $playerID == 1 ? $p2Auras : $p1Auras;
    $theirDiscard = $playerID == 1 ? $p2Discard : $p1Discard;
    $theirPitch = $playerID == 1 ? $p2Pitch : $p1Pitch;
    $theirBanish = $playerID == 1 ? $p2Banish : $p1Banish;
    $theirClassState = $playerID == 1 ? $p2ClassState : $p1ClassState;
    $theirCharacterEffects = $playerID == 1 ? $p2CharacterEffects : $p1CharacterEffects;
    $theirMaterial = $playerID == 1 ? $p2Material : $p1Material;
    $theirCardStats = $playerID == 1 ? $p2CardStats : $p1CardStats;
    $theirTurnStats = $playerID == 1 ? $p2TurnStats : $p1TurnStats;
  }
}

function headlessTokensFromLine(string $line): array
{
  $line = trim($line);
  if ($line === '') return [];
  return preg_split('/\s+/', $line) ?: [];
}

function normalizeDecklistForHeadless(mixed $deck): array
{
  if (is_string($deck)) {
    $lines = preg_split('/\R+/', trim($deck)) ?: [];
    if (count($lines) < 2) {
      throw new InvalidArgumentException('Deck string format must contain material line + main deck line.');
    }
    return ['material' => headlessTokensFromLine($lines[0]), 'main' => headlessTokensFromLine($lines[1])];
  }

  if (is_array($deck)) {
    if (isset($deck['material'], $deck['main']) && is_array($deck['material']) && is_array($deck['main'])) {
      return [
        'material' => array_values(array_map('strval', $deck['material'])),
        'main' => array_values(array_map('strval', $deck['main'])),
      ];
    }

    if (array_is_list($deck) && count($deck) >= 2 && is_array($deck[0]) && is_array($deck[1])) {
      return [
        'material' => array_values(array_map('strval', $deck[0])),
        'main' => array_values(array_map('strval', $deck[1])),
      ];
    }
  }

  throw new InvalidArgumentException('Deck must be string or object with material/main arrays.');
}

function initHeadlessGame(array $deckA, array $deckB, int $seed): void
{
  global $gameName, $playerID, $otherPlayer, $skipWriteGamestate, $mainPlayerGamestateStillBuilt, $makeCheckpoint, $makeBlockBackup, $MakeStartTurnBackup, $conceded;
  global $playerHealths, $winner, $firstPlayer, $currentPlayer, $currentRound, $turn, $actionPoints, $combatChain, $combatChainState;
  global $currentTurnEffects, $currentTurnEffectsFromCombat, $nextTurnEffects, $decisionQueue, $dqVars, $dqState, $layers, $layerPriority;
  global $mainPlayer, $lastPlayed, $chainLinks, $chainLinkSummary, $p1Key, $p2Key, $permanentUniqueIDCounter, $inGameStatus, $currentPlayerActivity;
  global $p1TotalTime, $p2TotalTime, $lastUpdateTime, $roguelikeGameID, $events, $EffectContext, $initiativePlayer, $initiativeTaken, $randomSeeded;
  global $p1Hand, $p1Deck, $p1CharEquip, $p1Resources, $p1Arsenal, $p1Items, $p1Auras, $p1Discard, $p1Pitch, $p1Banish, $p1ClassState, $p1CharacterEffects, $p1Material, $p1CardStats, $p1TurnStats, $p1Allies, $p1Permanents, $p1Settings;
  global $p2Hand, $p2Deck, $p2CharEquip, $p2Resources, $p2Arsenal, $p2Items, $p2Auras, $p2Discard, $p2Pitch, $p2Banish, $p2ClassState, $p2CharacterEffects, $p2Material, $p2CardStats, $p2TurnStats, $p2Allies, $p2Permanents, $p2Settings;
  global $landmarks, $defPlayer, $afterResolveEffects, $animations;

  $gameName = 'headless-engine';
  $playerID = 1;
  $otherPlayer = 2;
  $skipWriteGamestate = true;
  $mainPlayerGamestateStillBuilt = 0;
  $makeCheckpoint = 0;
  $makeBlockBackup = 0;
  $MakeStartTurnBackup = false;
  $conceded = false;

  $playerHealths = ['30', '30'];

  $p1Hand = [];
  $p1Deck = $deckA['main'];
  $p1CharEquip = $deckA['material'];
  $p1Resources = ['0', '0'];
  $p1Arsenal = [];
  $p1Items = [];
  $p1Auras = [];
  $p1Discard = [];
  $p1Pitch = [];
  $p1Banish = [];
  $p1ClassState = headlessTokensFromLine('0 0 0 0 0 0 0 0 DOWN 0 -1 0 0 0 0 0 0 -1 0 0 0 0 NA 0 0 0 - -1 0 0 0 0 0 0 - 0 0 0 0 0 0 0 0 - - 0 -1 0 0 0 0 0 - 0 0 0 0 0 -1 0 - 0 0 - 0 0 0 - -1 0 0 -');
  $p1CharacterEffects = [];
  $p1Material = $deckA['material'];
  $p1CardStats = [];
  $p1TurnStats = [];
  $p1Allies = [];
  $p1Permanents = [];
  $p1Settings = array_fill(0, 20, '0');

  $p2Hand = [];
  $p2Deck = $deckB['main'];
  $p2CharEquip = $deckB['material'];
  $p2Resources = ['0', '0'];
  $p2Arsenal = [];
  $p2Items = [];
  $p2Auras = [];
  $p2Discard = [];
  $p2Pitch = [];
  $p2Banish = [];
  $p2ClassState = headlessTokensFromLine('0 0 0 0 0 0 0 0 DOWN 0 -1 0 0 0 0 0 0 -1 0 0 0 0 NA 0 0 0 - -1 0 0 0 0 0 0 - 0 0 0 0 0 0 0 0 - - 0 -1 0 0 0 0 0 - 0 0 0 0 0 -1 0 - 0 0 - 0 0 0 - -1 0 0 -');
  $p2CharacterEffects = [];
  $p2Material = $deckB['material'];
  $p2CardStats = [];
  $p2TurnStats = [];
  $p2Allies = [];
  $p2Permanents = [];
  $p2Settings = array_fill(0, 20, '0');

  $landmarks = [];
  $winner = '0';
  $firstPlayer = '1';
  $currentPlayer = '1';
  $currentRound = '1';
  $turn = ['M', '1'];
  $actionPoints = '1';
  $combatChain = [];
  $combatChainState = [];
  $currentTurnEffects = [];
  $currentTurnEffectsFromCombat = [];
  $nextTurnEffects = [];
  $decisionQueue = [];
  $dqVars = ['0'];
  $dqState = ['0', '-', '-', '-'];
  $layers = [];
  $layerPriority = [];
  $mainPlayer = '1';
  $defPlayer = '2';
  $lastPlayed = [];
  $chainLinks = [];
  $chainLinkSummary = [];
  $p1Key = 'headless-p1';
  $p2Key = 'headless-p2';
  $permanentUniqueIDCounter = '0';
  $inGameStatus = '1';
  $animations = [];
  $afterResolveEffects = [];
  $currentPlayerActivity = '0';
  $p1TotalTime = '0';
  $p2TotalTime = '0';
  $lastUpdateTime = (string) time();
  $roguelikeGameID = '';
  $events = [];
  $EffectContext = '-';
  $initiativePlayer = '1';
  $initiativeTaken = '0';

  $GLOBALS['headlessInitialDeckSizes'] = [1 => count($deckA['main']), 2 => count($deckB['main'])];
  $GLOBALS['headlessSeed'] = $seed;
  mt_srand($seed);
  $randomSeeded = true;

  BuildMyGamestate(1);
}

function headlessStateModel(): array
{
  global $playerHealths, $currentPlayer, $currentRound, $turn, $actionPoints, $winner, $decisionQueue;
  global $p1Hand, $p1Deck, $p1CharEquip, $p1Resources, $p1Arsenal, $p1Items, $p1Auras, $p1Discard, $p1Pitch, $p1Banish, $p1Allies, $p1Permanents;
  global $p2Hand, $p2Deck, $p2CharEquip, $p2Resources, $p2Arsenal, $p2Items, $p2Auras, $p2Discard, $p2Pitch, $p2Banish, $p2Allies, $p2Permanents;

  $initialSizes = $GLOBALS['headlessInitialDeckSizes'] ?? [1 => 0, 2 => 0];

  return [
    'turn' => [
      'currentPlayer' => intval($currentPlayer ?? 1),
      'currentRound' => intval($currentRound ?? 1),
      'phase' => $turn,
      'actionPoints' => intval($actionPoints ?? 0),
      'decisionQueueHead' => $decisionQueue[0] ?? '',
      'winner' => intval($winner ?? 0),
    ],
    'players' => [
      1 => [
        'health' => intval($playerHealths[0] ?? 0),
        'handCount' => count($p1Hand),
        'deckCount' => count($p1Deck),
        'drawCount' => max(0, intval($initialSizes[1] ?? 0) - count($p1Deck)),
        'board' => [
          'character' => $p1CharEquip,
          'resources' => $p1Resources,
          'arsenal' => $p1Arsenal,
          'items' => $p1Items,
          'allies' => $p1Allies,
          'permanents' => $p1Permanents,
          'auras' => $p1Auras,
        ],
        'zones' => [
          'discard' => $p1Discard,
          'pitch' => $p1Pitch,
          'banish' => $p1Banish,
        ],
      ],
      2 => [
        'health' => intval($playerHealths[1] ?? 0),
        'handCount' => count($p2Hand),
        'deckCount' => count($p2Deck),
        'drawCount' => max(0, intval($initialSizes[2] ?? 0) - count($p2Deck)),
        'board' => [
          'character' => $p2CharEquip,
          'resources' => $p2Resources,
          'arsenal' => $p2Arsenal,
          'items' => $p2Items,
          'allies' => $p2Allies,
          'permanents' => $p2Permanents,
          'auras' => $p2Auras,
        ],
        'zones' => [
          'discard' => $p2Discard,
          'pitch' => $p2Pitch,
          'banish' => $p2Banish,
        ],
      ],
    ],
    'rng' => [
      'seed' => intval($GLOBALS['headlessSeed'] ?? 0),
      'engineRandomSeeded' => boolval($GLOBALS['randomSeeded'] ?? false),
    ],
  ];
}

function getObservation(int $player_id): array
{
  $state = headlessStateModel();
  $opponent = $player_id === 1 ? 2 : 1;
  global $p1Hand, $p1Deck, $p2Hand, $p2Deck;

  return [
    'public' => [
      'turn' => $state['turn'],
      'players' => [
        $player_id => $state['players'][$player_id],
        $opponent => $state['players'][$opponent],
      ],
    ],
    'playerPrivate' => [
      'hand' => $player_id === 1 ? $p1Hand : $p2Hand,
      'deck' => $player_id === 1 ? $p1Deck : $p2Deck,
    ],
  ];
}

function getLegalActions(int $player_id): array
{
  $engine = new LegalActions();
  $obs = Observation::fromGlobals();
  return array_map(static fn(Action $action) => $action->toArray(), $engine->getLegalActions($player_id, $obs));
}

function applyAction(int $player_id, array $action): array
{
  $engine = new LegalActions();
  $engineAction = new Action(
    strval($action['type'] ?? 'unknown'),
    intval($action['mode'] ?? 0),
    strval($action['buttonInput'] ?? ''),
    $action['cardID'] ?? 0,
    $action['chkCount'] ?? 0,
    $action['chkInput'] ?? '',
    strval($action['inputText'] ?? '')
  );
  $result = $engine->applyAction($player_id, $engineAction);

  return [
    'ok' => $result->ok,
    'message' => $result->message,
    'state' => headlessStateModel(),
    'observation' => getObservation($player_id),
    'legalActions' => getLegalActions($player_id),
  ];
}
