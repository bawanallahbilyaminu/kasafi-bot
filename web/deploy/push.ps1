<#
Kasafi web app: deploy from this laptop to the VPS (Windows PowerShell; uses the built-in ssh/scp).

  .\web\deploy\push.ps1 -Server root@your-vps-ip -Check          see what's on the VPS (changes nothing)
  .\web\deploy\push.ps1 -Server root@your-vps-ip                 build + start + publish at ai.kasafi.halalnumeriq.com.ng
  .\web\deploy\push.ps1 -Server root@your-vps-ip -EngineUrl https://xxxx.trycloudflare.com   new engine URL (after a Colab restart)
  .\web\deploy\push.ps1 -Server root@your-vps-ip -Logs

Only COMMITTED files are sent (git archive), so .env files never leave the laptop. Commit first.
Set $env:KASAFI_VPS = "root@your-vps-ip" once to skip -Server.
#>
param(
  [string]$Server = $env:KASAFI_VPS,
  [switch]$Check,
  [string]$EngineUrl,
  [switch]$Logs
)
$ErrorActionPreference = "Stop"
if (-not $Server) { throw "Pass -Server user@host (or set `$env:KASAFI_VPS)" }

$repo = (git rev-parse --show-toplevel).Trim()
Set-Location $repo
$remote = "/opt/kasafi-web/app/web/deploy/vps-deploy.sh"

if ($EngineUrl) { ssh -t $Server "sudo bash $remote set-engine '$EngineUrl'"; exit $LASTEXITCODE }
if ($Logs)      { ssh -t $Server "sudo bash $remote logs"; exit $LASTEXITCODE }

$dirty = git status --porcelain -- web
if ($dirty) { Write-Warning "Uncommitted changes in web/ will NOT be deployed:`n$dirty" }
$commit = (git rev-parse --short HEAD).Trim()
$tar = Join-Path $env:TEMP "kasafi-web-$commit.tar.gz"
Write-Host "Packing web/ at commit $commit ..."
git archive --format=tar.gz -o $tar HEAD web
Write-Host "Uploading to $Server ..."
scp $tar "${Server}:/tmp/kasafi-web.tar.gz"
if ($LASTEXITCODE) { throw "upload failed" }

$unpack = "set -e; sudo mkdir -p /opt/kasafi-web; cd /opt/kasafi-web; sudo rm -rf app.new; sudo mkdir app.new; " +
          "sudo tar -xzf /tmp/kasafi-web.tar.gz -C app.new; sudo rm -rf app.old; [ -d app ] && sudo mv app app.old; " +
          "sudo mv app.new app; echo $commit | sudo tee app/REVISION >/dev/null; rm -f /tmp/kasafi-web.tar.gz"
$action = if ($Check) { "check" } else { "deploy" }
ssh -t $Server "$unpack; sudo bash $remote $action"
exit $LASTEXITCODE
