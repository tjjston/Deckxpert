<?php

use PHPUnit\Framework\TestCase;

final class AIConditionAssignmentTest extends TestCase
{
  public function testNoAccidentalAssignmentInBooleanConditionsInAIModules(): void
  {
    $aiFiles = glob(__DIR__ . '/../AI/*.php');
    $violations = [];

    foreach($aiFiles as $file)
    {
      $lines = file($file);
      foreach($lines as $lineNumber => $line)
      {
        if(preg_match('/\b(if|elseif|else\s+if)\s*\([^)]*\$[A-Za-z_][A-Za-z0-9_]*\s*=\s*\$[A-Za-z_][A-Za-z0-9_]*/', $line) === 1)
        {
          if(str_contains($line, '==') || str_contains($line, '!=') || str_contains($line, '<=') || str_contains($line, '>=')) continue;
          $violations[] = basename($file) . ':' . ($lineNumber + 1) . ' => ' . trim($line);
        }
      }
    }

    $this->assertSame([], $violations, "Potential assignment in AI condition(s):\n" . implode("\n", $violations));
  }
}
