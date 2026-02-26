<?php

include_once __DIR__ . '/../AgentInterface.php';
include_once __DIR__ . '/../Action.php';
include_once __DIR__ . '/../Observation.php';

class SimpleHeuristicAgent implements AgentInterface
{
  public function chooseAction(Observation $obs, array $legalActions): Action
  {
    if(count($legalActions) === 0) {
      throw new RuntimeException('SimpleHeuristicAgent requires at least one legal action.');
    }

    $bestAction = $legalActions[0];
    $bestScore = $this->scoreAction($bestAction);

    for($i = 1; $i < count($legalActions); ++$i)
    {
      $candidateScore = $this->scoreAction($legalActions[$i]);
      if($candidateScore > $bestScore)
      {
        $bestAction = $legalActions[$i];
        $bestScore = $candidateScore;
      }
    }

    return $bestAction;
  }

  private function scoreAction(Action $action): float
  {
    $payload = $action->getPayload();
    if(isset($payload['score']) && is_numeric($payload['score'])) return floatval($payload['score']);
    if($action->getId() === 'PASS') return -1000;
    return 0;
  }
}
