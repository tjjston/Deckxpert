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

    if (($obs->decisionQueue[0] ?? "") !== "") {
      $actions = array_merge($actions, $this->decisionQueueActions($playerId, $obs));
    }

    $actions = array_merge($actions, $this->priorityActions($playerId, $turnType));

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
      false,
      $action->inputText
    );
    return new Result(true);
  }

  private function decisionQueueActions(int $playerId, Observation $obs): array
  {
    $actions = [];
    $turnType = $obs->turn[0] ?? "";
    $rawOptions = $obs->turn[2] ?? "";
    $options = $rawOptions === "" ? [] : explode(",", $rawOptions);

    switch ($turnType) {
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
        foreach ($options as $option) {
          $mode = ($turnType === "CHOOSETOPOPPONENT") ? 29 : (($turnType === "CHOOSECARD" || $turnType === "MAYCHOOSECARD") ? 23 : 17);
          $actions[] = new Action("decision", $mode, $option, 0, 0, "");
        }
        break;
      case "YESNO":
        $actions[] = new Action("yesno", 20, "YES", 0, 0, "");
        $actions[] = new Action("yesno", 20, "NO", 0, 0, "");
        break;
      case "CHOOSEDECK":
      case "MAYCHOOSEDECK":
        $deck = &GetDeck($playerId);
        for ($i = 0; $i < count($deck); ++$i) {
          $actions[] = new Action("choose_deck", 11, "", $i, 0, "");
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
      default:
        break;
    }

    return $actions;
  }

  private function priorityActions(int $playerId, string $turnType): array
  {
    $actions = [];

    $character = &GetPlayerCharacter($playerId);
    for ($index = 0; $index < count($character); $index += CharacterPieces()) {
      if (IsPlayable($character[$index], $turnType, "CHAR", $index)) {
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
        $actions[] = new Action("play_item", 10, "", $index, 0, "");
      }
    }

    $allies = &GetAllies($playerId);
    for ($index = 0; $index < count($allies); $index += AllyPieces()) {
      if (IsPlayable($allies[$index], $turnType, "PLAY", $index)) {
        $actions[] = new Action("play_ally", 24, "", $index, 0, "");
      }
    }

    return $actions;
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
