<?php

include_once __DIR__ . "/Action.php";
include_once __DIR__ . "/Observation.php";
include_once __DIR__ . "/Result.php";
include_once __DIR__ . "/../Libraries/NetworkingLibraries.php";

class LegalActions
{
  public function getLegalActions(int $playerId, Observation $obs): array
  {
    $actions = [];
    $turnType = $obs->turn[0] ?? "";
    $turnPlayer = intval($obs->turn[1] ?? 0);
    $priorityPlayer = intval($GLOBALS['currentPlayer'] ?? 0);
    $hasDecisionQueue = ($obs->decisionQueue[0] ?? "") !== "";

    if ($priorityPlayer !== 0 && $priorityPlayer !== $playerId) {
      return [];
    }
    if ($priorityPlayer === 0 && $turnPlayer !== 0 && $turnPlayer !== $playerId) {
      return [];
    }

    if ($hasDecisionQueue) {
      $actions = $this->decisionQueueActions($playerId, $obs);
    } else {
      $actions = $this->priorityActions($playerId, $turnType);
    }

    if (CanPassPhase($turnType)) {
      $actions[] = new Action("pass", 99, "-", 0, 0, "");
    }

    return $this->dedupeAndNormalize($actions);
  }

  public function applyAction(int $playerId, Action $action): Result
  {
    $obs = Observation::fromGlobals();
    $legal = $this->getLegalActions($playerId, $obs);
    $legalKeys = [];
    foreach ($legal as $legalAction) {
      $legalKeys[$legalAction->stableKey()] = true;
    }

    if (!isset($legalKeys[$action->stableKey()])) {
      return new Result(false, "Illegal action for current state");
    }

    ProcessInput(
      $playerId,
      $action->mode,
      $action->buttonInput,
      $action->cardID,
      $action->chkCount,
      $action->chkInput,
      true,
      $action->inputText
    );
    ProcessMacros();
    CacheCombatResult();
    return new Result(true);
  }

  private function decisionQueueActions(int $playerId, Observation $obs): array
  {
    $actions = [];
    $turnType = $obs->turn[0] ?? "";
    $rawOptions = $obs->turn[2] ?? "";
    $options = $rawOptions === "" ? [] : array_values(array_filter(explode(",", $rawOptions), static fn(string $option): bool => $option !== ""));

    switch ($turnType) {
      case "CHOOSEMULTIZONE":
      case "MAYCHOOSEMULTIZONE":
      case "CHOOSEARSENAL":
      case "MAYCHOOSEARSENAL":
      case "CHOOSEARSENALCANCEL":
      case "CHOOSEPERMANENT":
      case "MAYCHOOSEPERMANENT":
      case "CHOOSEHAND":
      case "MAYCHOOSEHAND":
      case "CHOOSEHANDCANCEL":
      case "CHOOSEDISCARD":
      case "MAYCHOOSEDISCARD":
      case "CHOOSEDISCARDCANCEL":
      case "MAYCHOOSETHEIRDISCARD":
      case "CHOOSEBANISH":
      case "CHOOSECOMBATCHAIN":
      case "MAYCHOOSECOMBATCHAIN":
      case "CHOOSECHARACTER":
      case "CHOOSETHEIRCHARACTER":
      case "CHOOSEMYAURA":
      case "CHOOSEMYSOUL":
      case "MAYCHOOSEMYSOUL":
        $zoneOptions = ($turnType === "CHOOSEMULTIZONE" || $turnType === "MAYCHOOSEMULTIZONE")
          ? $this->filterChooseZoneOptionsForState($options)
          : $options;
        foreach ($zoneOptions as $option) {
          $actions[] = new Action("choose_zone", 16, "", $option, 0, "");
        }
        break;
      case "OPT":
      case "CHOOSETOP":
      case "MAYCHOOSETOP":
      case "MAYCHOOSETOPREVEALED":
      case "MAYCHOOSEBOTTOM":
        foreach ($options as $option) {
          $actions[] = new Action("opt_top", 8, $option, 0, 0, "");
          $actions[] = new Action("opt_bottom", 9, $option, 0, 0, "");
        }
        break;
      case "CHOOSECARD":
      case "MAYCHOOSECARD":
      case "CHOOSETOPOPPONENT":
      case "BUTTONINPUT":
      case "CHOOSEARCANE":
      case "BUTTONINPUTNOPASS":
      case "CHOOSEFIRSTPLAYER":
        $decisionOptions = $options;
        if ($turnType === "BUTTONINPUT" || $turnType === "BUTTONINPUTNOPASS") {
          $leaderContext = $this->currentLeaderCardFromPlayIndex($playerId);
          if ($leaderContext !== null) {
            $decisionOptions = $this->filterLeaderAbilityOptionsForState($playerId, $leaderContext['card_id'], $decisionOptions);
          }
        }
        foreach ($decisionOptions as $option) {
          $mode = ($turnType === "CHOOSETOPOPPONENT") ? 29 : (($turnType === "CHOOSECARD" || $turnType === "MAYCHOOSECARD") ? 23 : 17);
          $actions[] = new Action("decision", $mode, $option, 0, 0, "");
        }
        break;
      case "CHOOSEOPTION":
      case "MAYCHOOSEOPTION":
        $decisionOptions = $options;
        $leaderContext = $this->currentLeaderCardFromPlayIndex($playerId);
        if ($leaderContext !== null) {
          $decisionOptions = $this->filterLeaderAbilityOptionsForState($playerId, $leaderContext['card_id'], $decisionOptions);
        }
        foreach ($decisionOptions as $option) {
          $actions[] = new Action("decision", 36, $option, 0, 0, "");
        }
        break;
      case "YESNO":
        $actions[] = new Action("yesno", 20, "YES", 0, 0, "");
        $actions[] = new Action("yesno", 20, "NO", 0, 0, "");
        break;
      case "CHOOSEDECK":
      case "MAYCHOOSEDECK":
        foreach ($options as $option) {
          if (!is_numeric($option)) continue;
          $actions[] = new Action("choose_deck", 11, "", intval($option), 0, "");
        }
        break;
      case "HANDTOPBOTTOM":
        $hand = &GetHand($playerId);
        for ($i = 0; $i < count($hand); ++$i) {
          $actions[] = new Action("hand_top", 12, (string)$i, 0, 0, "");
          $actions[] = new Action("hand_bottom", 13, (string)$i, 0, 0, "");
        }
        break;
      case "DYNPITCH":
        foreach ($options as $option) {
          $actions[] = new Action("dynamic_input", 7, $option, 0, 0, "");
        }
        break;
      case "MULTICHOOSEMULTIZONE":
        $multiChoose = $this->defaultMultiChooseAction($turnType, $rawOptions);
        if ($multiChoose !== null) {
          $actions[] = $multiChoose;
        }
        break;
      default:
        if (str_starts_with($turnType, "MULTICHOOSE") || str_starts_with($turnType, "MAYMULTICHOOSE")) {
          $multiChoose = $this->defaultMultiChooseAction($turnType, $rawOptions);
          if ($multiChoose !== null) {
            $actions[] = $multiChoose;
          }
        }
        // Fallback for unmodeled prompt phases that still pass options through turn[2].
        // This avoids deadlocks where the headless sim sees no legal actions and stops early.
        if (count($actions) === 0 && count($options) > 0) {
          foreach ($options as $option) {
            $actions[] = new Action("decision", 17, $option, 0, 0, "");
          }
        }
        break;
    }

    return $actions;
  }

  private function defaultMultiChooseAction(string $turnType, string $rawOptions): ?Action
  {
    if ($rawOptions === "") return null;

    if ($turnType === "MULTICHOOSEMULTIZONE") {
      $parts = explode("-", $rawOptions);
      if (count($parts) < 2 || !is_numeric($parts[0])) return null;
      $maxSelect = max(1, intval($parts[0]));
      $options = explode(",", implode("-", array_slice($parts, 1)));
      $options = array_values(array_filter($options, static fn(string $option): bool => $option !== ""));
      if (count($options) === 0) return null;
      $pickCount = min($maxSelect, count($options));
      $indices = range(0, max(0, $pickCount - 1));
      return new Action("multi_choose", 19, "", 0, count($indices), $indices, "");
    }

    if (str_contains($rawOptions, "&")) return null;
    $parts = explode("-", $rawOptions);
    if (count($parts) < 2 || !is_numeric($parts[0])) return null;

    $maxSelect = max(1, intval($parts[0]));
    $options = array_values(array_filter(explode(",", $parts[1]), static fn(string $option): bool => $option !== ""));
    if (count($options) === 0) return null;

    $minSelect = 1;
    if (isset($parts[2]) && is_numeric($parts[2])) {
      $minSelect = max(1, intval($parts[2]));
    }

    $pickCount = min($maxSelect, max($minSelect, 1), count($options));
    $indices = range(0, max(0, $pickCount - 1));
    return new Action("multi_choose", 19, "", 0, count($indices), $indices, "");
  }

  private function filterChooseZoneOptionsForState(array $options): array
  {
    if (count($options) === 0) return $options;
    if (!$this->isAttachToUnitPrompt()) return $options;

    // Safety guard: attach prompts should only select a unit target.
    // Keep both friendly and enemy units available when the engine offered them.
    $unitOptions = array_values(array_filter(
      $options,
      static fn(string $option): bool => preg_match('/^(MYALLY|THEIRALLY)-\d+$/', $option) === 1
    ));

    // Avoid deadlocks if context detection is wrong for a niche prompt.
    if (count($unitOptions) === 0) return $options;
    return $unitOptions;
  }

  private function isAttachToUnitPrompt(): bool
  {
    global $dqState;
    $context = strval($dqState[4] ?? "");
    if ($context === "" || $context === "-") return false;
    $context = strtolower(str_replace("_", " ", $context));
    return str_contains($context, "attach") && str_contains($context, "unit");
  }

  private function priorityActions(int $playerId, string $turnType): array
  {
    $actions = [];
    $currentPlayer = intval($GLOBALS['currentPlayer'] ?? 0);
    $initiativeTaken = intval($GLOBALS['initiativeTaken'] ?? 0);
    $initiativePlayer = intval($GLOBALS['initiativePlayer'] ?? 0);

    // Rule parity: after claiming initiative, that player cannot take further main-phase actions this round.
    // getLegalActions() appends pass when CanPassPhase(M) is true.
    if ($turnType === "M" && $initiativeTaken === 1 && $initiativePlayer === $playerId) {
      return $actions;
    }

    // Match arena UI behavior: active player in M phase may claim initiative once per round.
    if ($turnType === "M" && $initiativeTaken !== 1 && $currentPlayer === $playerId) {
      $actions[] = new Action("claim_initiative", 34, "-", 0, 0, "");
    }

    // Include leader character actions so sims can deploy leaders / use epic action paths.
    // Keep non-leader character abilities excluded to avoid noisy hidden-precondition reverts.
    $characters = &GetPlayerCharacter($playerId);
    for ($index = 0; $index < count($characters); $index += CharacterPieces()) {
      $cardId = strval($characters[$index] ?? "");
      if ($cardId === "") {
        continue;
      }
      if (!DefinedTypesContains($cardId, "Leader", $playerId)) {
        continue;
      }
      if ($this->shouldOfferLeaderCharacterAction($playerId, $cardId, $index, $turnType)) {
        $actions[] = new Action("play_character", 3, "", $index, 0, "");
      }
    }

    $hand = &GetHand($playerId);
    for ($index = 0; $index < count($hand); ++$index) {
      if (IsPlayable($hand[$index], $turnType, "HAND", $index)) {
        $actions[] = new Action("play_hand", 27, "", $index, 0, "");
      }
      if ($turnType == "ARS") {
        $actions[] = new Action("arsenal", 4, "", $hand[$index], 0, "");
      }
    }

    $arsenal = &GetArsenal($playerId);
    for ($index = 0; $index < count($arsenal); $index += ArsenalPieces()) {
      if (IsPlayable($arsenal[$index], $turnType, "RESOURCES", $index)) {
        $actions[] = new Action("play_arsenal", 5, "", $index, 0, "");
      }
    }

    $items = &GetItems($playerId);
    for ($index = 0; $index < count($items); $index += ItemPieces()) {
      if (IsPlayable($items[$index], $turnType, "PLAY", $index)) {
        $actions[] = new Action("activate_item", 10, "", $index, 0, "");
      }
    }

    $allies = &GetAllies($playerId);
    for ($index = 0; $index < count($allies); $index += AllyPieces()) {
      $ally = new Ally("MYALLY-" . $index, $playerId);
      $playable = IsPlayable($allies[$index], $turnType, "PLAY", $index)
        && (!$ally->IsExhausted() || AllyPlayableExhausted($ally));
      if ($playable) {
        $actions[] = new Action("activate_ally", 24, "", $index, 0, "");
      }
    }

    global $combatChain;
    if (!is_array($combatChain ?? null)) {
      $combatChain = [];
    }
    for ($index = 0; $index < count($combatChain); $index += CombatChainPieces()) {
      if (!AbilityPlayableFromCombatChain($combatChain[$index])) {
        continue;
      }
      if (IsPlayable($combatChain[$index], $turnType, "PLAY", $index)) {
        $actions[] = new Action("play_combat_chain", 21, "", $index, 0, "");
      }
    }

    $auras = &GetAuras($playerId);
    for ($index = 0; $index < count($auras); $index += AuraPieces()) {
      if (IsPlayable($auras[$index], $turnType, "PLAY", $index)) {
        $actions[] = new Action("activate_aura", 22, "", $index, 0, "");
      }
    }

    $discard = &GetDiscard($playerId);
    for ($index = 0; $index < count($discard); $index += DiscardPieces()) {
      if (IsPlayable($discard[$index], $turnType, "GY", $index)) {
        $actions[] = new Action("play_discard", 35, "", $index, 0, "");
      }
    }

    $otherPlayer = $playerId === 1 ? 2 : 1;
    $theirDiscard = &GetDiscard($otherPlayer);
    for ($index = 0; $index < count($theirDiscard); $index += DiscardPieces()) {
      if (IsPlayable($theirDiscard[$index], $turnType, "TGY", $index, player: $otherPlayer)) {
        $actions[] = new Action("play_their_discard", 37, "", $index, 0, "");
      }
    }

    $resourceCards = &GetResourceCards($playerId);
    for ($index = 0; $index < count($resourceCards); $index += ResourcePieces()) {
      if (IsPlayable($resourceCards[$index], $turnType, "RESOURCES", $index)) {
        $actions[] = new Action("play_resource", 5, "", $index, 0, "");
      }
    }

    return $actions;
  }

  private function shouldOfferLeaderCharacterAction(int $playerId, string $cardId, int $index, string $turnType): bool
  {
    if (!IsPlayable($cardId, $turnType, "CHAR", $index)) return false;

    $characters = &GetPlayerCharacter($playerId);
    $status = intval($characters[$index + 1] ?? 0); // 2=ready, 1=unavailable/exhausted, 0=destroyed
    $numUses = intval($characters[$index + 5] ?? 0);
    if ($status !== 2 || $numUses <= 0) return false;

    $abilityNames = strval(GetAbilityNames($cardId, $index, validate: true));
    if ($abilityNames === "") return false;
    $options = array_values(array_filter(explode(",", $abilityNames), static fn(string $name): bool => $name !== ""));
    $options = $this->filterLeaderAbilityOptionsForState($playerId, $cardId, $options, false);
    return count($options) > 0;
  }

  private function currentLeaderCardFromPlayIndex(int $playerId): ?array
  {
    global $CS_PlayIndex;
    $playIndex = intval(GetClassState($playerId, $CS_PlayIndex));
    if ($playIndex < 0) return null;

    $characters = &GetPlayerCharacter($playerId);
    $cardId = strval($characters[$playIndex] ?? "");
    if ($cardId === "" || !DefinedTypesContains($cardId, "Leader", $playerId)) return null;
    return ['index' => $playIndex, 'card_id' => $cardId];
  }

  private function filterLeaderAbilityOptionsForState(int $playerId, string $leaderCardId, array $options, bool $allowFallback = true): array
  {
    if (count($options) === 0) return $options;

    $filtered = [];
    foreach ($options as $option) {
      $normalized = strtolower(trim($option));
      if ($this->leaderAbilityRequiresForce($leaderCardId, $option) && !HasTheForce($playerId)) {
        continue;
      }
      if ($normalized === "deploy" && !$this->canDeployLeaderNow($playerId, $leaderCardId)) {
        continue;
      }
      if ($normalized === "pilot" && !$this->leaderPilotTargetAvailable($playerId, $leaderCardId)) {
        continue;
      }
      $filtered[] = $option;
    }

    // In prompt filtering paths we keep a fallback to avoid deadlocks from incomplete modeling.
    // In strict legality checks (e.g. shouldOfferLeaderCharacterAction), empty is intentional.
    if (count($filtered) === 0 && $allowFallback) return $options;
    return $filtered;
  }

  private function leaderAbilityRequiresForce(string $leaderCardId, string $option): bool
  {
    $optionKey = strtolower(trim($option));
    if ($optionKey === "") return false;

    // Keep this aligned with CoreLogic LOF leader handlers that gate on HasTheForce().
    $forceGatedOptions = [
      "0024560758" => ["deal damage"], // Darth Maul
      "2580909557" => ["bounce/play"], // Qui-Gon Jinn
      "2693401411" => ["experience"], // Obi-Wan Kenobi
      "2520636620" => ["debuff"], // Mother Talzin
      "5917432593" => ["attack"], // Grand Inquisitor
      "7077983867" => ["sentinel"], // Ahsoka Tano
      "6677799440" => ["exhaust"], // Cal Kestis
      "1184397926" => ["play"], // Barriss Offee
      "8536024453" => ["play"], // Anakin Skywalker
    ];
    $leaderOptions = $forceGatedOptions[$leaderCardId] ?? null;
    if ($leaderOptions === null) return false;
    return in_array($optionKey, $leaderOptions, true);
  }

  private function canDeployLeaderNow(int $playerId, string $leaderCardId): bool
  {
    global $CS_NumTimesUsedTheForce;
    if ($leaderCardId === "8520821318") { // Poe Dameron JTL
      return NumResources($playerId) >= 5;
    }
    if ($leaderCardId === "0092239541") { // Avar Kriss LOF
      $forceUsesThisPhase = intval(GetClassState($playerId, $CS_NumTimesUsedTheForce));
      return (NumResources($playerId) + $forceUsesThisPhase) >= 9;
    }
    return NumResources($playerId) >= CardCost($leaderCardId);
  }

  private function leaderPilotTargetAvailable(int $playerId, string $leaderCardId): bool
  {
    if (!LeaderCanPilot($leaderCardId)) return false;
    return SearchCount(SearchAllies($playerId, trait: "Vehicle", canAddPilot: ($leaderCardId != "5375722883"))) > 0;
  }

  private function dedupeAndNormalize(array $actions): array
  {
    usort($actions, function (Action $a, Action $b) {
      return strcmp($a->stableKey(), $b->stableKey());
    });

    $deduped = [];
    $seen = [];
    foreach ($actions as $action) {
      $key = $action->stableKey();
      if (isset($seen[$key])) {
        continue;
      }
      $seen[$key] = true;
      $deduped[] = $action;
    }
    return $deduped;
  }
}
