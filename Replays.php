<?php
include "HostFiles/Redirector.php";
include_once 'MenuBar.php';
include_once 'APIKeys/APIKeys.php';

$userId = "";
if(isset($_SESSION["userid"])) $userId = $_SESSION["userid"];
if($userId == "")
{
  echo("You must be logged in to use this feature.");
  exit;
}

$path = "./Replays/" . $userId . "/";
if(!file_exists($path)) mkdir($path, 0777, true);

$simReplayError = $_SESSION["simReplayError"] ?? "";
if(isset($_SESSION["simReplayError"])) unset($_SESSION["simReplayError"]);

$simDeckOptions = [];
$simDecksPath = __DIR__ . "/sim_harness/data/decks.json";
if(file_exists($simDecksPath))
{
  $decoded = json_decode(file_get_contents($simDecksPath), true);
  if(is_array($decoded))
  {
    foreach($decoded as $deck)
    {
      if(!is_array($deck)) continue;
      $deckId = trim(strval($deck["deck_id"] ?? ""));
      if($deckId == "") continue;
      $deckName = trim(strval($deck["swudb"]["metadata"]["name"] ?? $deckId));
      $simDeckOptions[] = ["id" => $deckId, "name" => $deckName];
    }
  }
}
usort($simDeckOptions, function($a, $b) {
  return strcmp($a["name"], $b["name"]);
});

$replayFolders = [];
if ($handle = opendir($path)) {
  while (false !== ($folder = readdir($handle))) {
    if ($folder === "." || $folder === ".." || $folder === "counter.txt") continue;
    if (!is_dir($path . $folder . "/")) continue;
    $replayFolders[] = $folder;
  }
  closedir($handle);
}
usort($replayFolders, function($a, $b) {
  return intval($b) <=> intval($a);
});

?>
<style>
  body {
    background-image: url('Images/Metrix.jpg');
    background-position: top center;
    background-repeat: no-repeat;
    background-size: cover;
    overflow: hidden;
  }
</style>


<section class="draft-form">
  <h2>Replays</h2>
  <?php
  if($simReplayError !== "")
  {
    echo("<div class='draft-form-form' style='border:1px solid rgba(255, 80, 80, 0.8); color:#fff; background:rgba(120, 0, 0, 0.45);'>" . htmlspecialchars($simReplayError, ENT_QUOTES) . "</div>");
  }

  if(count($simDeckOptions) > 1)
  {
      $defaultDeckA = $simDeckOptions[0]["id"];
      $defaultDeckB = $simDeckOptions[1]["id"];
      echo('<div class="draft-form-form">');
      echo("<h3 style='margin-top:0;'>Generate Bot Replay (SWU Visuals)</h3>");
      echo('<form action="CreateSimReplay.php" method="post">');
      echo("<label for='deckA'>Deck A</label><br/>");
      echo("<select id='deckA' name='deckA' required style='margin-bottom:8px; width:100%;'>");
      foreach($simDeckOptions as $deck) {
        $selected = $deck["id"] === $defaultDeckA ? " selected" : "";
        echo("<option value='" . htmlspecialchars($deck["id"], ENT_QUOTES) . "'$selected>" . htmlspecialchars($deck["name"], ENT_QUOTES) . " (" . htmlspecialchars($deck["id"], ENT_QUOTES) . ")</option>");
      }
      echo("</select><br/>");
      echo("<label for='deckB'>Deck B</label><br/>");
      echo("<select id='deckB' name='deckB' required style='margin-bottom:8px; width:100%;'>");
      foreach($simDeckOptions as $deck) {
        $selected = $deck["id"] === $defaultDeckB ? " selected" : "";
        echo("<option value='" . htmlspecialchars($deck["id"], ENT_QUOTES) . "'$selected>" . htmlspecialchars($deck["name"], ENT_QUOTES) . " (" . htmlspecialchars($deck["id"], ENT_QUOTES) . ")</option>");
      }
      echo("</select><br/>");
      echo("<label for='policy'>Bot Policy</label><br/>");
      echo("<select id='policy' name='policy' style='margin-bottom:8px; width:100%;'>");
      echo("<option value='heuristic'>Heuristic</option>");
      echo("<option value='mcts'>MCTS</option>");
      echo("<option value='random_legal'>Random Legal</option>");
      echo("<option value='random_non_pass'>Random Non-Pass</option>");
      echo("<option value='first_non_pass'>First Non-Pass</option>");
      echo("</select><br/>");
      echo("<label for='seed'>Seed (optional)</label><br/>");
      echo("<input id='seed' name='seed' type='number' min='1' placeholder='Auto-random if blank' style='margin-bottom:12px; width:100%;'/>");
      echo("<input type='submit' style='font-size:20px;' value='Generate Bot Replay'>");
      echo('</form>');
      echo('</div>');
  }
  else
  {
    echo("<div class='draft-form-form'>Simulation deck data is unavailable. Add decks to sim_harness/data/decks.json to enable bot replay generation.</div>");
  }

  if (count($replayFolders) === 0) {
    echo("<div class='draft-form-form'>You have no saved replays yet.</div>");
  } else {
    foreach ($replayFolders as $gameToken) {
      echo('<div class="draft-form-form">');
      echo('<form action="CreateReplayGame.php" method="get">');
      echo("<input type='hidden' id='replayNumber' name='replayNumber' value='$gameToken'>");
      echo("<input type='submit' style='font-size:20px;' value='Replay #$gameToken'>");
      echo('</form>');
      echo('</div>');
    }
  }
   ?>
</section>

<?php
include_once 'Disclaimer.php'
?>
