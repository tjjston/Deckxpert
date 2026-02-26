<?php

interface AgentInterface
{
  public function chooseAction(Observation $obs, array $legalActions): Action;
}
