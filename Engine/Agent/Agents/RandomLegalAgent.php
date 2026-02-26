<?php

include_once __DIR__ . '/../AgentInterface.php';
include_once __DIR__ . '/../Action.php';
include_once __DIR__ . '/../Observation.php';

class RandomLegalAgent implements AgentInterface
{
  public function chooseAction(Observation $obs, array $legalActions): Action
  {
    if(count($legalActions) === 0) {
      throw new RuntimeException('RandomLegalAgent requires at least one legal action.');
    }

    $index = random_int(0, count($legalActions) - 1);
    return $legalActions[$index];
  }
}
