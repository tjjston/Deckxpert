<?php

class Action
{
  public function __construct(private string $id, private array $payload = [])
  {
  }

  public function getId(): string
  {
    return $this->id;
  }

  public function getPayload(): array
  {
    return $this->payload;
  }
}
