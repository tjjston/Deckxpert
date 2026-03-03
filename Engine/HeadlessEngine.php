<?php

declare(strict_types=1);

include_once __DIR__ . '/../GameLogic.php';
include_once __DIR__ . '/../GameTerms.php';
include_once __DIR__ . '/../Libraries/SHMOPLibraries.php';
include_once __DIR__ . '/../Libraries/StatFunctions.php';
include_once __DIR__ . '/../Libraries/PlayerSettings.php';
include_once __DIR__ . '/../Libraries/UILibraries2.php';
include_once __DIR__ . '/../AI/PlayerMacros.php';
include_once __DIR__ . '/../AI/CombatDummy.php';
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


if (!function_exists('headlessBackupExcludedGlobals')) {
  function headlessBackupExcludedGlobals(): array
  {
    return [
      'GLOBALS',
      '_SERVER',
      '_GET',
      '_POST',
      '_FILES',
      '_COOKIE',
      '_SESSION',
      '_REQUEST',
      '_ENV',
      'argc',
      'argv',
      '__headlessGamestateBackups',
    ];
  }
}

if (!function_exists('headlessCaptureGamestateSnapshot')) {
  function headlessCaptureGamestateSnapshot(): array
  {
    $excluded = array_flip(headlessBackupExcludedGlobals());
    $snapshot = [];
    foreach ($GLOBALS as $key => $value) {
      if (isset($excluded[$key])) continue;
      if (is_object($value) || is_resource($value)) continue;
      $snapshot[$key] = $value;
    }
    return $snapshot;
  }
}

if (!function_exists('headlessRestoreGamestateSnapshot')) {
  function headlessRestoreGamestateSnapshot(array $snapshot): void
  {
    $excluded = array_flip(headlessBackupExcludedGlobals());
    foreach (array_keys($GLOBALS) as $key) {
      if (isset($excluded[$key])) continue;
      if (!array_key_exists($key, $snapshot)) unset($GLOBALS[$key]);
    }
    foreach ($snapshot as $key => $value) {
      $GLOBALS[$key] = $value;
    }
  }
}

if (!function_exists('MakeGamestateBackup')) {
  function MakeGamestateBackup($filename = "gamestateBackup.txt")
  {
    if (!isset($GLOBALS['__headlessGamestateBackups']) || !is_array($GLOBALS['__headlessGamestateBackups'])) {
      $GLOBALS['__headlessGamestateBackups'] = [];
    }
    $GLOBALS['__headlessGamestateBackups'][strval($filename)] = headlessCaptureGamestateSnapshot();
  }
}

if (!function_exists('RevertGamestate')) {
  function RevertGamestate($filename = "gamestateBackup.txt")
  {
    $name = strval($filename);
    $backups = $GLOBALS['__headlessGamestateBackups'] ?? [];
    if (!is_array($backups)) $backups = [];

    if (!array_key_exists($name, $backups)) {
      if (array_key_exists('gamestateBackup.txt', $backups)) {
        $name = 'gamestateBackup.txt';
      } else {
        // Mirror browser-engine behavior where revert suppresses write/advance.
        $GLOBALS['skipWriteGamestate'] = true;
        return;
      }
    }

    headlessRestoreGamestateSnapshot($backups[$name]);
    $GLOBALS['skipWriteGamestate'] = true;
  }
}

if (!function_exists('MakeStartTurnBackup')) {
  function MakeStartTurnBackup()
  {
    if (!isset($GLOBALS['__headlessGamestateBackups']) || !is_array($GLOBALS['__headlessGamestateBackups'])) {
      $GLOBALS['__headlessGamestateBackups'] = [];
    }
    $backups = &$GLOBALS['__headlessGamestateBackups'];
    if (array_key_exists('beginTurnGamestate.txt', $backups)) {
      $backups['lastTurnGamestate.txt'] = $backups['beginTurnGamestate.txt'];
    }
    $backups['beginTurnGamestate.txt'] = headlessCaptureGamestateSnapshot();
  }
}

if (!function_exists('UpdateGameState')) {
  function UpdateGameState($playerID): void
  {
    DoGamestateUpdate();
    BuildMyGamestate($playerID);
  }
}

if (!function_exists('DoGamestateUpdate')) {
  function DoGamestateUpdate(): void
  {
    global $mainPlayerGamestateStillBuilt, $myStateBuiltFor;
    if (($mainPlayerGamestateStillBuilt ?? 0) == 1) UpdateMainPlayerGameStateInner();
    else if (($myStateBuiltFor ?? -1) != -1) UpdateGameStateInner();
  }
}

if (!function_exists('UpdateGameStateInner')) {
  function UpdateGameStateInner(): void
  {
    global $myStateBuiltFor;
    global $p1Deck, $p1Hand, $p1Resources, $p1CharEquip, $p1Arsenal, $playerHealths, $p1Auras, $p1Pitch, $p1Banish, $p1ClassState, $p1Items;
    global $p1CharacterEffects, $p1Discard, $p1CardStats, $p1TurnStats;
    global $p2Deck, $p2Hand, $p2Resources, $p2CharEquip, $p2Arsenal, $p2Auras, $p2Pitch, $p2Banish, $p2ClassState, $p2Items;
    global $p2CharacterEffects, $p2Discard, $p2CardStats, $p2TurnStats;
    global $myDeck, $myHand, $myResources, $myCharacter, $myArsenal, $myHealth, $myAuras, $myPitch, $myBanish, $myClassState, $myItems;
    global $myCharacterEffects, $myDiscard, $myCardStats, $myTurnStats;
    global $theirDeck, $theirHand, $theirResources, $theirCharacter, $theirArsenal, $theirHealth, $theirAuras, $theirPitch, $theirBanish, $theirClassState, $theirItems;
    global $theirCharacterEffects, $theirDiscard, $theirCardStats, $theirTurnStats;
    global $p1Material, $p2Material, $myMaterial, $theirMaterial;

    $activePlayer = intval($myStateBuiltFor ?? -1);
    if ($activePlayer === 1) {
      $p1Deck = $myDeck;
      $p1Hand = $myHand;
      $p1Resources = $myResources;
      $p1CharEquip = $myCharacter;
      $p1Arsenal = $myArsenal;
      $playerHealths[0] = $myHealth;
      $p1Items = $myItems;
      $p1Auras = $myAuras;
      $p1Pitch = $myPitch;
      $p1Banish = $myBanish;
      $p1ClassState = $myClassState;
      $p1CharacterEffects = $myCharacterEffects;
      $p1Discard = $myDiscard;
      $p1Material = $myMaterial;
      $p1CardStats = $myCardStats;
      $p1TurnStats = $myTurnStats;

      $p2Deck = $theirDeck;
      $p2Hand = $theirHand;
      $p2Resources = $theirResources;
      $p2CharEquip = $theirCharacter;
      $p2Arsenal = $theirArsenal;
      $playerHealths[1] = $theirHealth;
      $p2Items = $theirItems;
      $p2Auras = $theirAuras;
      $p2Pitch = $theirPitch;
      $p2Banish = $theirBanish;
      $p2ClassState = $theirClassState;
      $p2CharacterEffects = $theirCharacterEffects;
      $p2Discard = $theirDiscard;
      $p2Material = $theirMaterial;
      $p2CardStats = $theirCardStats;
      $p2TurnStats = $theirTurnStats;
      return;
    }

    if ($activePlayer === 2) {
      $p2Deck = $myDeck;
      $p2Hand = $myHand;
      $p2Resources = $myResources;
      $p2CharEquip = $myCharacter;
      $p2Arsenal = $myArsenal;
      $playerHealths[1] = $myHealth;
      $p2Items = $myItems;
      $p2Auras = $myAuras;
      $p2Pitch = $myPitch;
      $p2Banish = $myBanish;
      $p2ClassState = $myClassState;
      $p2CharacterEffects = $myCharacterEffects;
      $p2Discard = $myDiscard;
      $p2Material = $myMaterial;
      $p2CardStats = $myCardStats;
      $p2TurnStats = $myTurnStats;

      $p1Deck = $theirDeck;
      $p1Hand = $theirHand;
      $p1Resources = $theirResources;
      $p1CharEquip = $theirCharacter;
      $p1Arsenal = $theirArsenal;
      $playerHealths[0] = $theirHealth;
      $p1Items = $theirItems;
      $p1Auras = $theirAuras;
      $p1Pitch = $theirPitch;
      $p1Banish = $theirBanish;
      $p1ClassState = $theirClassState;
      $p1CharacterEffects = $theirCharacterEffects;
      $p1Discard = $theirDiscard;
      $p1Material = $theirMaterial;
      $p1CardStats = $theirCardStats;
      $p1TurnStats = $theirTurnStats;
    }
  }
}

if (!function_exists('UpdateMainPlayerGameStateInner')) {
  function UpdateMainPlayerGameStateInner(): void
  {
    global $mainPlayerGamestateStillBuilt, $mpgBuiltFor;
    global $mainHand, $mainDeck, $mainResources, $mainCharacter, $mainArsenal, $mainHealth, $mainAuras, $mainPitch, $mainBanish, $mainClassState, $mainItems;
    global $mainCharacterEffects, $mainDiscard;
    global $defHand, $defDeck, $defResources, $defCharacter, $defArsenal, $defHealth, $defAuras, $defPitch, $defBanish, $defClassState, $defItems;
    global $defCharacterEffects, $defDiscard;
    global $p1Deck, $p1Hand, $p1Resources, $p1CharEquip, $p1Arsenal, $playerHealths, $p1Auras, $p1Pitch, $p1Banish, $p1ClassState, $p1Items;
    global $p1CharacterEffects, $p1Discard;
    global $p2Deck, $p2Hand, $p2Resources, $p2CharEquip, $p2Arsenal, $p2Auras, $p2Pitch, $p2Banish, $p2ClassState, $p2Items;
    global $p2CharacterEffects, $p2Discard;
    global $p1Material, $p2Material, $mainMaterial, $defMaterial;
    global $p1CardStats, $p2CardStats, $mainCardStats, $defCardStats;
    global $p1TurnStats, $p2TurnStats, $mainTurnStats, $defTurnStats;

    $p1Deck = $mpgBuiltFor == 1 ? $mainDeck : $defDeck;
    $p1Hand = $mpgBuiltFor == 1 ? $mainHand : $defHand;
    $p1Resources = $mpgBuiltFor == 1 ? $mainResources : $defResources;
    $p1CharEquip = $mpgBuiltFor == 1 ? $mainCharacter : $defCharacter;
    $p1Arsenal = $mpgBuiltFor == 1 ? $mainArsenal : $defArsenal;
    $playerHealths[0] = $mpgBuiltFor == 1 ? $mainHealth : $defHealth;
    $p1Items = $mpgBuiltFor == 1 ? $mainItems : $defItems;
    $p1Auras = $mpgBuiltFor == 1 ? $mainAuras : $defAuras;
    $p1Pitch = $mpgBuiltFor == 1 ? $mainPitch : $defPitch;
    $p1Banish = $mpgBuiltFor == 1 ? $mainBanish : $defBanish;
    $p1ClassState = $mpgBuiltFor == 1 ? $mainClassState : $defClassState;
    $p1CharacterEffects = $mpgBuiltFor == 1 ? $mainCharacterEffects : $defCharacterEffects;
    $p1Discard = $mpgBuiltFor == 1 ? $mainDiscard : $defDiscard;
    $p1Material = $mpgBuiltFor == 1 ? $mainMaterial : $defMaterial;
    $p1CardStats = $mpgBuiltFor == 1 ? $mainCardStats : $defCardStats;
    $p1TurnStats = $mpgBuiltFor == 1 ? $mainTurnStats : $defTurnStats;

    $p2Deck = $mpgBuiltFor == 2 ? $mainDeck : $defDeck;
    $p2Hand = $mpgBuiltFor == 2 ? $mainHand : $defHand;
    $p2Resources = $mpgBuiltFor == 2 ? $mainResources : $defResources;
    $p2CharEquip = $mpgBuiltFor == 2 ? $mainCharacter : $defCharacter;
    $p2Arsenal = $mpgBuiltFor == 2 ? $mainArsenal : $defArsenal;
    $playerHealths[1] = $mpgBuiltFor == 2 ? $mainHealth : $defHealth;
    $p2Items = $mpgBuiltFor == 2 ? $mainItems : $defItems;
    $p2Auras = $mpgBuiltFor == 2 ? $mainAuras : $defAuras;
    $p2Pitch = $mpgBuiltFor == 2 ? $mainPitch : $defPitch;
    $p2Banish = $mpgBuiltFor == 2 ? $mainBanish : $defBanish;
    $p2ClassState = $mpgBuiltFor == 2 ? $mainClassState : $defClassState;
    $p2CharacterEffects = $mpgBuiltFor == 2 ? $mainCharacterEffects : $defCharacterEffects;
    $p2Discard = $mpgBuiltFor == 2 ? $mainDiscard : $defDiscard;
    $p2Material = $mpgBuiltFor == 2 ? $mainMaterial : $defMaterial;
    $p2CardStats = $mpgBuiltFor == 2 ? $mainCardStats : $defCardStats;
    $p2TurnStats = $mpgBuiltFor == 2 ? $mainTurnStats : $defTurnStats;
    $mainPlayerGamestateStillBuilt = 1;
  }
}

if (!function_exists('UpdateMainPlayerGameState')) {
  function UpdateMainPlayerGameState(): void
  {
    DoGamestateUpdate();
  }
}

if (!function_exists('BuildMainPlayerGamestate')) {
  function BuildMainPlayerGamestate(): void
  {
    global $mainPlayer, $mainPlayerGamestateStillBuilt, $playerHealths;
    global $mpgBuiltFor;
    global $mainHand, $mainDeck, $mainResources, $mainCharacter, $mainArsenal, $mainHealth, $mainAuras, $mainPitch, $mainBanish, $mainClassState, $mainItems;
    global $mainCharacterEffects, $mainDiscard, $mainMaterial, $mainCardStats, $mainTurnStats;
    global $defHand, $defDeck, $defResources, $defCharacter, $defArsenal, $defHealth, $defAuras, $defPitch, $defBanish, $defClassState, $defItems;
    global $defCharacterEffects, $defDiscard, $defMaterial, $defCardStats, $defTurnStats;
    global $p1Deck, $p1Hand, $p1Resources, $p1CharEquip, $p1Arsenal, $p1Auras, $p1Pitch, $p1Banish, $p1ClassState, $p1Items, $p1CharacterEffects, $p1Discard, $p1Material, $p1CardStats, $p1TurnStats;
    global $p2Deck, $p2Hand, $p2Resources, $p2CharEquip, $p2Arsenal, $p2Auras, $p2Pitch, $p2Banish, $p2ClassState, $p2Items, $p2CharacterEffects, $p2Discard, $p2Material, $p2CardStats, $p2TurnStats;

    DoGamestateUpdate();
    $mpgBuiltFor = $mainPlayer;

    $mainHand = $mainPlayer == 1 ? $p1Hand : $p2Hand;
    $mainDeck = $mainPlayer == 1 ? $p1Deck : $p2Deck;
    $mainResources = $mainPlayer == 1 ? $p1Resources : $p2Resources;
    $mainCharacter = $mainPlayer == 1 ? $p1CharEquip : $p2CharEquip;
    $mainArsenal = $mainPlayer == 1 ? $p1Arsenal : $p2Arsenal;
    $mainHealth = $mainPlayer == 1 ? $playerHealths[0] : $playerHealths[1];
    $mainItems = $mainPlayer == 1 ? $p1Items : $p2Items;
    $mainAuras = $mainPlayer == 1 ? $p1Auras : $p2Auras;
    $mainPitch = $mainPlayer == 1 ? $p1Pitch : $p2Pitch;
    $mainBanish = $mainPlayer == 1 ? $p1Banish : $p2Banish;
    $mainClassState = $mainPlayer == 1 ? $p1ClassState : $p2ClassState;
    $mainCharacterEffects = $mainPlayer == 1 ? $p1CharacterEffects : $p2CharacterEffects;
    $mainDiscard = $mainPlayer == 1 ? $p1Discard : $p2Discard;
    $mainMaterial = $mainPlayer == 1 ? $p1Material : $p2Material;
    $mainCardStats = $mainPlayer == 1 ? $p1CardStats : $p2CardStats;
    $mainTurnStats = $mainPlayer == 1 ? $p1TurnStats : $p2TurnStats;

    $defHand = $mainPlayer == 1 ? $p2Hand : $p1Hand;
    $defDeck = $mainPlayer == 1 ? $p2Deck : $p1Deck;
    $defResources = $mainPlayer == 1 ? $p2Resources : $p1Resources;
    $defCharacter = $mainPlayer == 1 ? $p2CharEquip : $p1CharEquip;
    $defArsenal = $mainPlayer == 1 ? $p2Arsenal : $p1Arsenal;
    $defHealth = $mainPlayer == 1 ? $playerHealths[1] : $playerHealths[0];
    $defItems = $mainPlayer == 1 ? $p2Items : $p1Items;
    $defAuras = $mainPlayer == 1 ? $p2Auras : $p1Auras;
    $defPitch = $mainPlayer == 1 ? $p2Pitch : $p1Pitch;
    $defBanish = $mainPlayer == 1 ? $p2Banish : $p1Banish;
    $defClassState = $mainPlayer == 1 ? $p2ClassState : $p1ClassState;
    $defCharacterEffects = $mainPlayer == 1 ? $p2CharacterEffects : $p1CharacterEffects;
    $defDiscard = $mainPlayer == 1 ? $p2Discard : $p1Discard;
    $defMaterial = $mainPlayer == 1 ? $p2Material : $p1Material;
    $defCardStats = $mainPlayer == 1 ? $p2CardStats : $p1CardStats;
    $defTurnStats = $mainPlayer == 1 ? $p2TurnStats : $p1TurnStats;

    $mainPlayerGamestateStillBuilt = 1;
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
    global $myStateBuiltFor;
    global $mainPlayerGamestateStillBuilt;

    $mainPlayerGamestateStillBuilt = 0;
    $myStateBuiltFor = intval($playerID);
    if (intval($playerID) === 1) {
      $myHand = $p1Hand;
      $myDeck = $p1Deck;
      $myResources = $p1Resources;
      $myCharacter = $p1CharEquip;
      $myArsenal = $p1Arsenal;
      $myItems = $p1Items;
      $myAuras = $p1Auras;
      $myDiscard = $p1Discard;
      $myPitch = $p1Pitch;
      $myBanish = $p1Banish;
      $myClassState = $p1ClassState;
      $myCharacterEffects = $p1CharacterEffects;
      $myMaterial = $p1Material;
      $myCardStats = $p1CardStats;
      $myTurnStats = $p1TurnStats;

      $theirHand = $p2Hand;
      $theirDeck = $p2Deck;
      $theirResources = $p2Resources;
      $theirCharacter = $p2CharEquip;
      $theirArsenal = $p2Arsenal;
      $theirItems = $p2Items;
      $theirAuras = $p2Auras;
      $theirDiscard = $p2Discard;
      $theirPitch = $p2Pitch;
      $theirBanish = $p2Banish;
      $theirClassState = $p2ClassState;
      $theirCharacterEffects = $p2CharacterEffects;
      $theirMaterial = $p2Material;
      $theirCardStats = $p2CardStats;
      $theirTurnStats = $p2TurnStats;
      $myHealth = $playerHealths[0] ?? 0;
      $theirHealth = $playerHealths[1] ?? 0;
    } else {
      $myHand = $p2Hand;
      $myDeck = $p2Deck;
      $myResources = $p2Resources;
      $myCharacter = $p2CharEquip;
      $myArsenal = $p2Arsenal;
      $myItems = $p2Items;
      $myAuras = $p2Auras;
      $myDiscard = $p2Discard;
      $myPitch = $p2Pitch;
      $myBanish = $p2Banish;
      $myClassState = $p2ClassState;
      $myCharacterEffects = $p2CharacterEffects;
      $myMaterial = $p2Material;
      $myCardStats = $p2CardStats;
      $myTurnStats = $p2TurnStats;

      $theirHand = $p1Hand;
      $theirDeck = $p1Deck;
      $theirResources = $p1Resources;
      $theirCharacter = $p1CharEquip;
      $theirArsenal = $p1Arsenal;
      $theirItems = $p1Items;
      $theirAuras = $p1Auras;
      $theirDiscard = $p1Discard;
      $theirPitch = $p1Pitch;
      $theirBanish = $p1Banish;
      $theirClassState = $p1ClassState;
      $theirCharacterEffects = $p1CharacterEffects;
      $theirMaterial = $p1Material;
      $theirCardStats = $p1CardStats;
      $theirTurnStats = $p1TurnStats;
      $myHealth = $playerHealths[1] ?? 0;
      $theirHealth = $playerHealths[0] ?? 0;
    }
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

function bootstrapHeadlessStartOfGame(): void
{
  global $firstPlayer, $mainPlayer, $currentPlayer, $otherPlayer, $layerPriority, $initiativePlayer, $initiativeTaken;
  global $MakeStartTurnBackup, $MakeStartGameBackup;
  global $p1Material, $p2Material;

  array_push($layerPriority, ShouldHoldPriority(1), ShouldHoldPriority(2));

  $mainPlayer = $firstPlayer;
  $currentPlayer = $firstPlayer;
  $otherPlayer = ($currentPlayer == 1 ? 2 : 1);
  StatsStartTurn();

  $MakeStartTurnBackup = false;
  $MakeStartGameBackup = false;

  $orderedP1 = headlessMaterialBaseFirst($p1Material);
  if (isset($orderedP1[0])) AddCharacter($orderedP1[0], 1);
  if (isset($orderedP1[MaterialPieces()])) AddCharacter($orderedP1[MaterialPieces()], 1);

  if (count($p2Material) == 1 && ($p2Material[0] ?? '') === "DUMMY") {
    AddCharacter("DUMMY", 2);
  } else {
    $orderedP2 = headlessMaterialBaseFirst($p2Material);
    if (isset($orderedP2[0])) AddCharacter($orderedP2[0], 2);
    if (isset($orderedP2[MaterialPieces()])) AddCharacter($orderedP2[MaterialPieces()], 2);
  }

  $initiativePlayer = $firstPlayer;
  $initiativeTaken = 0;

  for ($i = 0; $i < 10; $i++) {
    AddDecisionQueue("SHUFFLEDECK", 1, "SKIPSEED");
    AddDecisionQueue("SHUFFLEDECK", 2, "SKIPSEED");
  }
  AddDecisionQueue("STARTGAME", $initiativePlayer, "-");
  ProcessDecisionQueue();
  DoGamestateUpdate();
  BuildMyGamestate(intval($initiativePlayer));
}

function headlessMaterialBaseFirst(array $material): array
{
  $cards = array_values(array_map('strval', $material));
  if (count($cards) < 2) return $cards;

  // Base should be slot 0 for engine semantics. Pick highest HP card as base.
  $hp0 = intval(CardHP($cards[0]));
  $hp1 = intval(CardHP($cards[1]));
  if ($hp1 > $hp0) {
    return [$cards[1], $cards[0]];
  }
  return $cards;
}

function normalizeHeadlessOpeningHands(int $targetHandSize = 6): void
{
  if ($targetHandSize < 0) $targetHandSize = 0;

  foreach ([1, 2] as $player) {
    BuildMyGamestate($player);
    $hand = &GetHand($player);
    $deck = &GetDeck($player);

    while (count($hand) < $targetHandSize && count($deck) > 0) {
      $hand[] = array_shift($deck);
    }
    while (count($hand) > $targetHandSize) {
      $cardId = array_pop($hand);
      if ($cardId === null) break;
      $deck[] = $cardId;
    }
  }

  DoGamestateUpdate();
  BuildMyGamestate(1);
}

function initHeadlessGame(array $deckA, array $deckB, int $seed): void
{
  global $gameName, $playerID, $otherPlayer, $skipWriteGamestate, $mainPlayerGamestateStillBuilt, $makeCheckpoint, $makeBlockBackup, $MakeStartTurnBackup, $MakeStartGameBackup, $conceded;
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
  $MakeStartGameBackup = false;
  $conceded = false;

  // Engine stores base damage taken, not remaining HP.
  // Canonical start state is 0 damage on each base.
  $playerHealths = ['0', '0'];

  $p1Hand = [];
  $p1Deck = $deckA['main'];
  $p1CharEquip = [];
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
  $p2CharEquip = [];
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
  bootstrapHeadlessStartOfGame();
  // Sim harness rule: always begin simulated matches with 6 cards in hand.
  normalizeHeadlessOpeningHands(6);
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
  DoGamestateUpdate();
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
  DoGamestateUpdate();
  BuildMyGamestate($player_id);
  $engine = new LegalActions();
  $obs = Observation::fromGlobals();
  return array_map(static fn(Action $action) => $action->toArray(), $engine->getLegalActions($player_id, $obs));
}

function applyAction(int $player_id, array $action): array
{
  global $skipWriteGamestate, $makeCheckpoint, $makeBlockBackup, $MakeStartTurnBackup;
  $skipWriteGamestate = false;
  $makeCheckpoint = 0;
  $makeBlockBackup = 0;
  $MakeStartTurnBackup = false;
  // Match ProcessInput2.php behavior so FinalizeAction() can evaluate pass-mode correctly.
  $GLOBALS['inputMode'] = intval($action['mode'] ?? 0);
  DoGamestateUpdate();
  BuildMyGamestate($player_id);

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
  DoGamestateUpdate();
  BuildMyGamestate($player_id);

  return [
    'ok' => $result->ok,
    'message' => $result->message,
    'state' => headlessStateModel(),
    'observation' => getObservation($player_id),
    'legalActions' => getLegalActions($player_id),
  ];
}
