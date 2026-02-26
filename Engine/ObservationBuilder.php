<?php

class Observation
{
  public array $public;
  public array $playerPrivate;

  public function __construct(array $public, array $playerPrivate)
  {
    $this->public = $public;
    $this->playerPrivate = $playerPrivate;
  }

  public function toArray(): array
  {
    return [
      "public" => $this->public,
      "playerPrivate" => $this->playerPrivate,
    ];
  }
}

function BuildInternalStateModel(): array
{
  global $playerHealths, $currentPlayer, $currentRound, $turn, $actionPoints, $combatChain, $combatChainState;
  global $p1Hand, $p1Deck, $p1CharEquip, $p1Resources, $p1Arsenal, $p1Items, $p1Auras, $p1Discard, $p1Pitch, $p1Banish, $p1Allies, $p1Permanents;
  global $p2Hand, $p2Deck, $p2CharEquip, $p2Resources, $p2Arsenal, $p2Items, $p2Auras, $p2Discard, $p2Pitch, $p2Banish, $p2Allies, $p2Permanents;

  return [
    "turn" => [
      "currentPlayer" => $currentPlayer,
      "currentRound" => $currentRound,
      "phase" => $turn,
      "actionPoints" => $actionPoints,
      "combatChain" => $combatChain,
      "combatChainState" => $combatChainState,
    ],
    "players" => [
      1 => [
        "health" => intval($playerHealths[0] ?? 0),
        "hand" => $p1Hand,
        "deck" => $p1Deck,
        "character" => $p1CharEquip,
        "resources" => $p1Resources,
        "arsenal" => $p1Arsenal,
        "items" => $p1Items,
        "auras" => $p1Auras,
        "discard" => $p1Discard,
        "pitch" => $p1Pitch,
        "banish" => $p1Banish,
        "allies" => $p1Allies,
        "permanents" => $p1Permanents,
      ],
      2 => [
        "health" => intval($playerHealths[1] ?? 0),
        "hand" => $p2Hand,
        "deck" => $p2Deck,
        "character" => $p2CharEquip,
        "resources" => $p2Resources,
        "arsenal" => $p2Arsenal,
        "items" => $p2Items,
        "auras" => $p2Auras,
        "discard" => $p2Discard,
        "pitch" => $p2Pitch,
        "banish" => $p2Banish,
        "allies" => $p2Allies,
        "permanents" => $p2Permanents,
      ],
    ],
  ];
}

function getObservation(int $playerId): array
{
  $internalState = BuildInternalStateModel();
  $otherPlayer = $playerId == 1 ? 2 : 1;

  $public = [
    "turn" => $internalState["turn"],
    "players" => [
      $playerId => [
        "health" => $internalState["players"][$playerId]["health"],
        "character" => $internalState["players"][$playerId]["character"],
        "resources" => $internalState["players"][$playerId]["resources"],
        "arsenal" => $internalState["players"][$playerId]["arsenal"],
        "items" => $internalState["players"][$playerId]["items"],
        "auras" => $internalState["players"][$playerId]["auras"],
        "discard" => $internalState["players"][$playerId]["discard"],
        "pitch" => $internalState["players"][$playerId]["pitch"],
        "banish" => $internalState["players"][$playerId]["banish"],
        "allies" => $internalState["players"][$playerId]["allies"],
        "permanents" => $internalState["players"][$playerId]["permanents"],
        "deckCount" => count($internalState["players"][$playerId]["deck"]),
        "handCount" => count($internalState["players"][$playerId]["hand"]),
      ],
      $otherPlayer => [
        "health" => $internalState["players"][$otherPlayer]["health"],
        "character" => $internalState["players"][$otherPlayer]["character"],
        "resources" => $internalState["players"][$otherPlayer]["resources"],
        "arsenal" => $internalState["players"][$otherPlayer]["arsenal"],
        "items" => $internalState["players"][$otherPlayer]["items"],
        "auras" => $internalState["players"][$otherPlayer]["auras"],
        "discard" => $internalState["players"][$otherPlayer]["discard"],
        "pitch" => $internalState["players"][$otherPlayer]["pitch"],
        "banish" => $internalState["players"][$otherPlayer]["banish"],
        "allies" => $internalState["players"][$otherPlayer]["allies"],
        "permanents" => $internalState["players"][$otherPlayer]["permanents"],
        "deckCount" => count($internalState["players"][$otherPlayer]["deck"]),
        "handCount" => count($internalState["players"][$otherPlayer]["hand"]),
      ],
    ],
  ];

  $playerPrivate = [
    "hand" => $internalState["players"][$playerId]["hand"],
    "deck" => $internalState["players"][$playerId]["deck"],
  ];

  return (new Observation($public, $playerPrivate))->toArray();
}

function AssertObservationPayloadHasNoHiddenZones(array $payload): void
{
  $serialized = json_encode($payload);
  if($serialized === false) return;
  $forbiddenTokens = [
    '"theirHand":',
    '"theirDeck":',
    '"opponentHandContents":',
    '"opponentDeckOrder":',
    '"hiddenDeckOrder":',
  ];
  foreach($forbiddenTokens as $token)
  {
    if(str_contains($serialized, $token))
    {
      throw new Exception("Hidden zone leaked into payload: " . $token);
    }
  }
}
