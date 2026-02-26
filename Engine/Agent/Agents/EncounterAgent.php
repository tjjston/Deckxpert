<?php

include_once __DIR__ . '/SimpleHeuristicAgent.php';

class EncounterAgent implements AgentInterface
{
  public function __construct(private SimpleHeuristicAgent $fallbackAgent = new SimpleHeuristicAgent())
  {
  }

  public function chooseAction(Observation $obs, array $legalActions): Action
  {
    $turnType = $obs->get('turnType');
    $decisionQueueCount = intval($obs->get('decisionQueueCount', 0));
    $isBowActive = boolval($obs->get('isBowActive', false));
    $effectContext = $obs->get('effectContext', '');
    $mainPlayer = $obs->get('mainPlayer');
    $currentPlayer = $obs->get('currentPlayer');
    $actionPoints = intval($obs->get('actionPoints', 0));

    if($decisionQueueCount > 0)
    {
      if($effectContext === 'OUT234') return $this->findAction($legalActions, 'DQ_BLOODROT');
      if($turnType === 'INPUTCARDNAME') return $this->findAction($legalActions, 'DQ_INPUTCARDNAME');
      if($isBowActive) return $this->findAction($legalActions, 'DQ_BOW');
      if($obs->get('decisionQueueHead') === 'SHIVER') return $this->findAction($legalActions, 'DQ_SHIVER');
      return $this->findAction($legalActions, 'DQ_FIRST_OPTION');
    }

    if($turnType === 'B') return $this->findAction($legalActions, 'BLOCK');
    if($turnType === 'M' && $mainPlayer == $currentPlayer && $actionPoints > 0) return $this->findAction($legalActions, 'MAIN');
    if($turnType === 'A' && $mainPlayer == $currentPlayer) return $this->findAction($legalActions, 'ATTACK_REACTION');
    if($turnType === 'P' && $mainPlayer == $currentPlayer) return $this->findAction($legalActions, 'PITCH');
    if($turnType === 'ARS' && $mainPlayer == $currentPlayer) return $this->findAction($legalActions, 'ARS');
    if($turnType === 'OPT' && $mainPlayer == $currentPlayer) return $this->findAction($legalActions, 'OPT');
    if($turnType === 'LOOKHAND' && $mainPlayer == $currentPlayer) return $this->findAction($legalActions, 'LOOKHAND');
    if($turnType === 'HANDTOPBOTTOM' && $mainPlayer == $currentPlayer) return $this->findAction($legalActions, 'HANDTOPBOTTOM');

    return $this->findAction($legalActions, 'PASS');
  }

  private function findAction(array $legalActions, string $id): Action
  {
    for($i = 0; $i < count($legalActions); ++$i)
    {
      if($legalActions[$i]->getId() === $id) return $legalActions[$i];
    }

    return $this->fallbackAgent->chooseAction(new Observation(), $legalActions);
  }
}
