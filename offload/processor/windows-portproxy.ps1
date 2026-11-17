# Refresh a Windows port proxy to the current WSL IP.
# Use this only when mirrored networking is not available (Windows 10).
# Run in an elevated PowerShell after every WSL restart, or schedule it at logon.
# Mirrored mode (Windows 11) does not need this script.

$ErrorActionPreference = "Stop"
$ListenPort = 2222
$WslPort = 2222

$wslIp = (wsl.exe -d Ubuntu -e hostname -I).Trim().Split(" ")[0]
if (-not $wslIp) {
  throw "WSL did not report an address. Start Ubuntu first."
}

netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$ListenPort | Out-Null
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$ListenPort connectaddress=$wslIp connectport=$WslPort

$rule = Get-NetFirewallRule -DisplayName "Allsky WSL SSH" -ErrorAction SilentlyContinue
if (-not $rule) {
  New-NetFirewallRule -DisplayName "Allsky WSL SSH" -Direction Inbound -Protocol TCP -LocalPort $ListenPort -Action Allow | Out-Null
}

Write-Output "Forwarding 0.0.0.0:$ListenPort -> ${wslIp}:$WslPort"
