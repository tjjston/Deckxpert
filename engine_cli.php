<?php

declare(strict_types=1);

ob_start();
error_reporting(0);
ini_set('display_errors', '0');
ini_set('display_startup_errors', '0');

include "GameLogic.php";
include "GameTerms.php";
include "Libraries/SHMOPLibraries.php";
include "Libraries/StatFunctions.php";
include "Libraries/PlayerSettings.php";
include "AI/PlayerMacros.php";
require_once "Libraries/CoreLibraries.php";
include_once "WriteLog.php";
ob_end_clean();


if (!function_exists('UpdateGameState')) {
    function UpdateGameState($playerID): void
    {
        BuildMyGamestate($playerID);
    }
}

if (!function_exists('DoGamestateUpdate')) {
    function DoGamestateUpdate(): void
    {
        // In-memory CLI runner does not maintain serialized gamestate snapshots.
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

interface EngineStateAdapter
{
    public function initializeFromDecks(array $deckA, array $deckB): void;
}

final class InMemoryStateAdapter implements EngineStateAdapter
{
    public function initializeFromDecks(array $deckA, array $deckB): void
    {
        initializeEngineGlobals($deckA, $deckB);
    }
}

function readJsonPayload(): array
{
    $raw = stream_get_contents(STDIN);
    $payload = json_decode($raw ?: '', true);
    if (!is_array($payload)) {
        throw new InvalidArgumentException('Input must be valid JSON.');
    }
    foreach (['deckA', 'deckB', 'seed'] as $required) {
        if (!array_key_exists($required, $payload)) {
            throw new InvalidArgumentException("Missing required key: {$required}");
        }
    }
    return $payload;
}

function normalizeDecklist(mixed $deck): array
{
    if (is_string($deck)) {
        $lines = preg_split('/\R+/', trim($deck)) ?: [];
        if (count($lines) < 2) {
            throw new InvalidArgumentException('Deck string format must contain material line + main deck line.');
        }
        return [
            'material' => tokensFromLine($lines[0]),
            'main' => tokensFromLine($lines[1]),
        ];
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

function tokensFromLine(string $line): array
{
    $line = trim($line);
    if ($line === '') {
        return [];
    }
    return preg_split('/\s+/', $line) ?: [];
}

function initializeEngineGlobals(array $deckA, array $deckB): void
{
    global $gameName, $playerID, $otherPlayer, $skipWriteGamestate, $mainPlayerGamestateStillBuilt, $makeCheckpoint, $makeBlockBackup, $MakeStartTurnBackup, $conceded;
    global $playerHealths, $winner, $firstPlayer, $currentPlayer, $currentRound, $turn, $actionPoints, $combatChain, $combatChainState;
    global $currentTurnEffects, $currentTurnEffectsFromCombat, $nextTurnEffects, $decisionQueue, $dqVars, $dqState, $layers, $layerPriority;
    global $mainPlayer, $lastPlayed, $chainLinks, $chainLinkSummary, $p1Key, $p2Key, $permanentUniqueIDCounter, $inGameStatus, $currentPlayerActivity;
    global $p1TotalTime, $p2TotalTime, $lastUpdateTime, $roguelikeGameID, $events, $EffectContext, $initiativePlayer, $initiativeTaken, $randomSeeded;
    global $p1Hand, $p1Deck, $p1CharEquip, $p1Resources, $p1Arsenal, $p1Items, $p1Auras, $p1Discard, $p1Pitch, $p1Banish, $p1ClassState, $p1CharacterEffects, $p1Material, $p1CardStats, $p1TurnStats, $p1Allies, $p1Permanents, $p1Settings;
    global $p2Hand, $p2Deck, $p2CharEquip, $p2Resources, $p2Arsenal, $p2Items, $p2Auras, $p2Discard, $p2Pitch, $p2Banish, $p2ClassState, $p2CharacterEffects, $p2Material, $p2CardStats, $p2TurnStats, $p2Allies, $p2Permanents, $p2Settings;
    global $landmarks, $mainPlayer, $defPlayer, $afterResolveEffects, $animations;

    $gameName = 'engine-cli';
    $playerID = 1;
    $otherPlayer = 2;
    $skipWriteGamestate = true;
    $mainPlayerGamestateStillBuilt = 0;
    $makeCheckpoint = 0;
    $makeBlockBackup = 0;
    $MakeStartTurnBackup = false;
    $conceded = false;

    // Engine stores base damage taken, not remaining HP.
    $playerHealths = ['0', '0'];

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
    $p1ClassState = tokensFromLine('0 0 0 0 0 0 0 0 DOWN 0 -1 0 0 0 0 0 0 -1 0 0 0 0 NA 0 0 0 - -1 0 0 0 0 0 0 - 0 0 0 0 0 0 0 0 - - 0 -1 0 0 0 0 0 - 0 0 0 0 0 -1 0 - 0 0 - 0 0 0 - -1 0 0 -');
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
    $p2ClassState = tokensFromLine('0 0 0 0 0 0 0 0 DOWN 0 -1 0 0 0 0 0 0 -1 0 0 0 0 NA 0 0 0 - -1 0 0 0 0 0 0 - 0 0 0 0 0 0 0 0 - - 0 -1 0 0 0 0 0 - 0 0 0 0 0 -1 0 - 0 0 - 0 0 0 - -1 0 0 -');
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
    $p1Key = 'cli-p1';
    $p2Key = 'cli-p2';
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
    $randomSeeded = false;

    BuildMyGamestate(1);
}

function runSimulation(array $payload): array
{
    global $winner, $turn, $currentRound, $currentPlayer, $conceded, $randomSeeded;

    $deckA = normalizeDecklist($payload['deckA']);
    $deckB = normalizeDecklist($payload['deckB']);
    $seed = (int) $payload['seed'];
    $maxActions = isset($payload['max_actions']) ? max(1, (int) $payload['max_actions']) : 2000;
    $verboseTurns = !empty($payload['verbose_turns']);
    $verboseActions = !empty($payload['verbose_actions']);

    $adapter = new InMemoryStateAdapter();
    $adapter->initializeFromDecks($deckA, $deckB);

    mt_srand($seed);
    $randomSeeded = true;

    $turnSummary = [];
    $actionLog = [];
    $errorFlags = [];
    $lastTurnKey = null;

    for ($i = 0; $i < $maxActions && !IsGameOver(); ++$i) {
        $before = [
            'round' => (int) $currentRound,
            'player' => (int) $currentPlayer,
            'phase' => $turn[0] ?? '-',
        ];

        ob_start();
        try {
            PassInput();
            ProcessMacros();
            CacheCombatResult();
        } catch (Throwable $t) {
            $errorFlags[] = 'runtime_exception';
            $actionLog[] = ['step' => $i + 1, 'error' => $t->getMessage()];
            ob_end_clean();
            break;
        }
        ob_end_clean();

        $after = [
            'round' => (int) $currentRound,
            'player' => (int) $currentPlayer,
            'phase' => $turn[0] ?? '-',
        ];

        $turnKey = implode(':', [$after['round'], $after['player'], $after['phase']]);
        if ($verboseTurns && $turnKey !== $lastTurnKey) {
            $turnSummary[] = [
                'step' => $i + 1,
                'from' => $before,
                'to' => $after,
            ];
            $lastTurnKey = $turnKey;
        }

        if ($verboseActions) {
            $actionLog[] = [
                'step' => $i + 1,
                'before' => $before,
                'after' => $after,
            ];
        }
    }

    if (!IsGameOver() && (int) $winner === 0) {
        $errorFlags[] = 'max_actions_reached';
    }

    return [
        'winner' => (int) $winner,
        'turn_summary' => $turnSummary,
        'action_log' => $verboseActions ? $actionLog : [],
        'stats' => [
            'turn_count' => (int) $currentRound,
            'concessions' => $conceded ? 1 : 0,
            'error_flags' => array_values(array_unique($errorFlags)),
            'seed' => $seed,
            'game_over' => IsGameOver(),
        ],
    ];
}

try {
    $result = runSimulation(readJsonPayload());
    echo json_encode($result, JSON_UNESCAPED_SLASHES);
} catch (Throwable $t) {
    $result = [
        'winner' => 0,
        'turn_summary' => [],
        'action_log' => [],
        'stats' => [
            'turn_count' => 0,
            'concessions' => 0,
            'error_flags' => ['invalid_input', $t->getMessage()],
            'game_over' => false,
        ],
    ];
    echo json_encode($result, JSON_UNESCAPED_SLASHES);
}
