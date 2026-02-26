<?php

include_once __DIR__ . '/../AgentInterface.php';
include_once __DIR__ . '/../Action.php';
include_once __DIR__ . '/../Observation.php';

class AgentDecisionAdapter
{
  public function __construct(private AgentInterface $agent)
  {
  }

  public function act(Observation $obs, array $legalActions): Action
  {
    $action = $this->agent->chooseAction($obs, $legalActions);
    $payload = $action->getPayload();
    if(isset($payload['handler']) && is_callable($payload['handler']))
    {
      $payload['handler']();
    }
    return $action;
  }
}
