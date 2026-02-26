<?php

class Observation
{
  public function __construct(private array $context = [])
  {
  }

  public function get(string $key, mixed $default = null): mixed
  {
    return $this->context[$key] ?? $default;
  }

  public function all(): array
  {
    return $this->context;
  }
}
