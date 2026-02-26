<?php

class Action
{
  public string $type;
  public int $mode;
  public string $buttonInput;
  public int|string $cardID;
  public mixed $chkCount;
  public mixed $chkInput;
  public string $inputText;

  public function __construct(
    string $type,
    int $mode,
    string $buttonInput = "",
    int|string $cardID = 0,
    mixed $chkCount = 0,
    mixed $chkInput = "",
    string $inputText = ""
  ) {
    $this->type = $type;
    $this->mode = $mode;
    $this->buttonInput = $buttonInput;
    $this->cardID = $cardID;
    $this->chkCount = $chkCount;
    $this->chkInput = $chkInput;
    $this->inputText = $inputText;
  }

  public function toArray(): array
  {
    return [
      "type" => $this->type,
      "mode" => $this->mode,
      "buttonInput" => $this->buttonInput,
      "cardID" => $this->cardID,
      "chkCount" => $this->chkCount,
      "chkInput" => $this->chkInput,
      "inputText" => $this->inputText,
    ];
  }

  public function stableKey(): string
  {
    return json_encode($this->toArray(), JSON_UNESCAPED_SLASHES);
  }
}
