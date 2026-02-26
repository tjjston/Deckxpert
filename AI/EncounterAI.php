<?php

include "EncounterPriorityValues.php";
include "EncounterPriorityLogic.php";
include "EncounterPlayLogic.php";
include_once __DIR__ . "/../Engine/Agent/Action.php";
include_once __DIR__ . "/../Engine/Agent/Observation.php";
include_once __DIR__ . "/../Engine/Agent/Agents/EncounterAgent.php";
include_once __DIR__ . "/../Engine/Agent/Adapters/AgentDecisionAdapter.php";

function EncounterAI()
{
  global $currentPlayer, $p2CharEquip, $decisionQueue;
  $AIDebug = false;
  $currentPlayerIsAI = $currentPlayer == 2 && IsEncounterAI($p2CharEquip[0]);
  $isBowActive = false;
  $adapter = new AgentDecisionAdapter(new EncounterAgent());

  if(!IsGameOver() && $currentPlayerIsAI)
  {
    for($logicCount=0; $logicCount<=30 && $currentPlayerIsAI; ++$logicCount)
    {
      global $turn, $mainPlayer, $actionPoints, $EffectContext;
      FixHand($currentPlayer);
      $hand = &GetHand($currentPlayer);
      $character = &GetPlayerCharacter($currentPlayer);
      $arsenal = &GetArsenal($currentPlayer);
      $resources = &GetResources($currentPlayer);
      $items = &GetItems($currentPlayer);
      $allies = &GetAllies($currentPlayer);
      CacheCombatResult();

      $obs = new Observation([
        'turnType' => $turn[0],
        'decisionQueueCount' => count($decisionQueue),
        'decisionQueueHead' => $decisionQueue[0] ?? null,
        'effectContext' => $EffectContext ?? '',
        'isBowActive' => $isBowActive,
        'mainPlayer' => $mainPlayer,
        'currentPlayer' => $currentPlayer,
        'actionPoints' => $actionPoints,
      ]);

      $legalActions = BuildEncounterLegalActions($currentPlayer, $hand, $character, $arsenal, $resources, $items, $allies, $isBowActive, $AIDebug);
      $chosenAction = $adapter->act($obs, $legalActions);

      ProcessMacros();
      $currentPlayerIsAI = $currentPlayer == 2;
      if($logicCount == 30 && $currentPlayerIsAI)
      {
        for($i=0; $i<=30 && $currentPlayerIsAI; ++$i)
        {
          PassInput();
          $currentPlayerIsAI = $currentPlayer == 2;
        }
      }
    }
  }
}

function BuildEncounterLegalActions($currentPlayer, &$hand, &$character, &$arsenal, &$resources, &$items, &$allies, &$isBowActive, $AIDebug)
{
  global $turn;

  return [
    new Action('DQ_BLOODROT', ['handler' => function() use ($AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Bloodrot');
      ContinueDecisionQueue('NO');
    }]),
    new Action('DQ_SHIVER', ['handler' => function() use (&$turn, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Shiver');
      $options = explode(',', $turn[2]);
      ContinueDecisionQueue($options[1]);
    }]),
    new Action('DQ_BOW', ['handler' => function() use (&$turn, &$hand, &$character, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Bow Active');
      $optionIndex = 0;
      $index = 0;
      $largestIndex = 0;
      for($i = 0; $i < count($hand); ++$i)
      {
        if(CardSubtype($hand[0]) == 'Arrow')
        {
          if(GetPriority($hand[$largestIndex], $character[0], 2) <= GetPriority($hand[$i], $character[0], 2))
          {
            $largestIndex = $i;
            $optionIndex = $index;
          }
          ++$index;
        }
      }
      $options = explode(',', $turn[2]);
      ContinueDecisionQueue($options[$optionIndex]);
    }]),
    new Action('DQ_INPUTCARDNAME', ['handler' => function() use ($currentPlayer, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Input Arcane');
      ProcessInput($currentPlayer, 30, '-', 0, 0, '-', false, 'Crouching Tiger');
    }]),
    new Action('DQ_FIRST_OPTION', ['handler' => function() use (&$turn, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - DQ First Option');
      $options = explode(',', $turn[2]);
      ContinueDecisionQueue($options[0]);
    }]),
    new Action('BLOCK', ['handler' => function() use (&$hand, &$character, &$arsenal, &$items, &$allies, $currentPlayer, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Block');
      $priortyArray = GeneratePriorityValues($hand, $character, $arsenal, $items, $allies, 'Block');
      $found = false;
      while (count($priortyArray) > 0 && !$found) {
        $storedPriorityNode = $priortyArray[count($priortyArray)-1];
        array_pop($priortyArray);
        if(CardIsBlockable($storedPriorityNode)) $found = true;
      }
      $health = &GetBaseDamage($currentPlayer);
      if($found == true && $storedPriorityNode[3] != 0 && ((CachedTotalAttack() - CachedTotalBlock() >= $health && $storedPriorityNode[3] != 0) || (CachedTotalAttack() - CachedTotalBlock() >= BlockValue($storedPriorityNode[0]) && 2.1 <= $storedPriorityNode[3] && $storedPriorityNode[3] <= 2.9)))
      {
        BlockCardAttempt($storedPriorityNode);
      }
      else
      {
        PassInput();
      }
    }]),
    new Action('MAIN', ['handler' => function() use (&$hand, &$character, &$arsenal, &$items, &$allies, &$resources, &$isBowActive, $AIDebug) {
      if($AIDebug) WriteLog("AI Branch - AI's Turn");
      $priortyArray = GeneratePriorityValues($hand, $character, $arsenal, $items, $allies, 'Action');
      $found = false;
      while (count($priortyArray) > 0 && !$found) {
        $storedPriorityNode = $priortyArray[count($priortyArray)-1];
        array_pop($priortyArray);
        if(CardIsPlayable($storedPriorityNode, $hand, $resources))
        {
          if($storedPriorityNode[0] != 'Hand' || count($hand) > 1 || ResourcesNeededToSave($character[0]) >= ($resources[0] - CardCost($storedPriorityNode[0])))
          {
            $found = true;
          }
        }
      }
      if($found == true && $storedPriorityNode[3] != 0)
      {
        if(CardSubtype($storedPriorityNode[0]) == 'Bow') $isBowActive = true;
        else $isBowActive = false;
        PlayCardAttempt($storedPriorityNode);
        CacheCombatResult();
      }
      else
      {
        PassInput();
      }
    }]),
    new Action('ATTACK_REACTION', ['handler' => function() use (&$hand, &$character, &$arsenal, &$items, &$allies, &$resources, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Attack Reactions');
      $priortyArray = GeneratePriorityValues($hand, $character, $arsenal, $items, $allies, 'Reaction');
      $found = false;
      while (count($priortyArray) > 0 && !$found) {
        $storedPriorityNode = $priortyArray[count($priortyArray)-1];
        array_pop($priortyArray);
        if(ReactionCardIsPlayable($storedPriorityNode, $hand, $resources)) $found = true;
      }
      if($found == true && $storedPriorityNode[3] != 0)
      {
        PlayCardAttempt($storedPriorityNode);
        CacheCombatResult();
      }
      else
      {
        PassInput();
      }
    }]),
    new Action('PITCH', ['handler' => function() use (&$hand, &$character, &$arsenal, &$items, &$allies, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Pitch');
      $priortyArray = GeneratePriorityValues($hand, $character, $arsenal, $items, $allies, 'Pitch');
      $found = false;
      while (count($priortyArray) > 0 && !$found) {
        $storedPriorityNode = $priortyArray[count($priortyArray)-1];
        array_pop($priortyArray);
        if(CardIsPitchable($storedPriorityNode)) $found = true;
      }
      if($found == true && $storedPriorityNode[3] != 0)
      {
        PitchCardAttempt($storedPriorityNode);
      }
      else
      {
        PassInput();
      }
    }]),
    new Action('ARS', ['handler' => function() use (&$hand, &$character, &$arsenal, &$items, &$allies, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Choose Arsenal');
      $priortyArray = GeneratePriorityValues($hand, $character, $arsenal, $items, $allies, 'ToArsenal');
      $found = false;
      while (count($priortyArray) > 0 && !$found) {
        $storedPriorityNode = $priortyArray[count($priortyArray)-1];
        array_pop($priortyArray);
        if(CardIsArsenalable($storedPriorityNode)) $found = true;
      }
      if($found == true && $storedPriorityNode[3] != 0)
      {
        ArsenalCardAttempt($storedPriorityNode);
      }
      else
      {
        PassInput();
      }
    }]),
    new Action('OPT', ['handler' => function() use (&$turn, $currentPlayer, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Opt');
      $options = explode(',', $turn[2]);
      ProcessInput($currentPlayer, 9, $options[0], 0, 0, '');
      CacheCombatResult();
    }]),
    new Action('LOOKHAND', ['handler' => function() use (&$turn, $currentPlayer, $AIDebug) {
      if($AIDebug) WriteLog("AI Branch - Opponent's Hand");
      $options = explode(',', $turn[2]);
      ProcessInput($currentPlayer, 99, $options[0], 0, 0, '');
      CacheCombatResult();
    }]),
    new Action('HANDTOPBOTTOM', ['handler' => function() use (&$turn, $currentPlayer, $AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Hand Top/Bottom');
      $options = explode(',', $turn[2]);
      ProcessInput($currentPlayer, 12, $options[0], 0, 0, '');
      CacheCombatResult();
    }]),
    new Action('PASS', ['score' => -1000, 'handler' => function() use ($AIDebug) {
      if($AIDebug) WriteLog('AI Branch - Pass');
      PassInput();
    }]),
  ];
}

function IsEncounterAI($enemyHero)
{
  return str_contains($enemyHero, "ROGUE");
}

function LogPriorityArray($priorityArray)
{
  WriteLog("Priority Array:");
  for($i = 0; $i < count($priorityArray); ++$i)
  {
    WriteLog("[" . $priorityArray[$i][0] . "," . $priorityArray[$i][1] . "," . $priorityArray[$i][2] . "," . $priorityArray[$i][3] . "]");
  }
}

function LogHandArray($hand)
{
  $rv = "Hand=[";
  for($i = 0; $i < count($hand); ++$i)
  {
    if($i != 0) $rv.=",";
    $rv.=$hand[$i];
  }
  WriteLog($rv . "]");
}
