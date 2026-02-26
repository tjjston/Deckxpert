<?php

use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../Engine/Agent/Action.php';
require_once __DIR__ . '/../Engine/Agent/Observation.php';
require_once __DIR__ . '/../Engine/Agent/AgentInterface.php';
require_once __DIR__ . '/../Engine/Agent/Agents/RandomLegalAgent.php';
require_once __DIR__ . '/../Engine/Agent/Agents/SimpleHeuristicAgent.php';

final class AgentInterfaceTest extends TestCase
{
  public function testRandomLegalAgentReturnsLegalAction(): void
  {
    $agent = new RandomLegalAgent();
    $actions = [new Action('A'), new Action('B'), new Action('C')];

    $picked = $agent->chooseAction(new Observation(), $actions);

    $ids = array_map(fn(Action $action) => $action->getId(), $actions);
    $this->assertContains($picked->getId(), $ids);
  }

  public function testSimpleHeuristicAgentPrefersHighestScore(): void
  {
    $agent = new SimpleHeuristicAgent();
    $actions = [
      new Action('PASS', ['score' => -100]),
      new Action('MID', ['score' => 3]),
      new Action('BEST', ['score' => 5]),
    ];

    $picked = $agent->chooseAction(new Observation(), $actions);

    $this->assertSame('BEST', $picked->getId());
  }
}
