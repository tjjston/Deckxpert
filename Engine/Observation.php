<?php

class Observation
{
  public array $turn;
  public array $decisionQueue;

  public function __construct(array $turn, array $decisionQueue)
  {
    $this->turn = $turn;
    $this->decisionQueue = $decisionQueue;
  }

  public static function fromGlobals(): Observation
  {
    global $turn, $decisionQueue;
    return new Observation($turn ?? [], $decisionQueue ?? []);
  }
}
