<?php

class Result
{
  public bool $ok;
  public string $message;

  public function __construct(bool $ok, string $message = "")
  {
    $this->ok = $ok;
    $this->message = $message;
  }
}
