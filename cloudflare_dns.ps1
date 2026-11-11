param(
    [ValidateSet('List','Plan','Apply','Dhcp')][string]$Mode = 'List',
    [int]$InterfaceIndex = -1
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$Servers = @('1.1.1.1','1.0.0.1','2606:4700:4700::1111','2606:4700:4700::1001')
if ($Mode -eq 'Plan') {
    @{ mode='Plan'; writes_dns=$false; servers=$Servers; scope='selected Windows adapter'; dhcp_reset='not a backup of custom DNS'; encrypted_dns_configured=$false } | ConvertTo-Json -Compress
    exit 0
}
if ($Mode -eq 'List') {
    $Rows = @(Get-NetIPInterface -AddressFamily IPv4 | Where-Object { $_.ConnectionState -eq 'Connected' -and $_.InterfaceAlias -notmatch 'Loopback' } | ForEach-Object {
        $Addresses = @(Get-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex | ForEach-Object { $_.ServerAddresses })
        @{ index=[int]$_.InterfaceIndex; name=$_.InterfaceAlias; servers=$Addresses; cloudflare=($Addresses.Count -gt 0 -and @($Addresses | Where-Object { $_ -notin $Servers }).Count -eq 0) }
    })
    ConvertTo-Json -InputObject $Rows -Depth 4 -Compress
    exit 0
}
if ($InterfaceIndex -le 0) { throw 'Select a valid network adapter.' }
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator permission is required.' }
$Adapter = Get-NetIPInterface -InterfaceIndex $InterfaceIndex -AddressFamily IPv4
Write-Host ('Adapter: ' + $Adapter.InterfaceAlias)
Write-Host 'Previous DNS:'
Get-DnsClientServerAddress -InterfaceIndex $InterfaceIndex | Format-Table -AutoSize
if ($Mode -eq 'Apply') {
    Set-DnsClientServerAddress -InterfaceIndex $InterfaceIndex -ServerAddresses $Servers
} else {
    Set-DnsClientServerAddress -InterfaceIndex $InterfaceIndex -ResetServerAddresses
}
Clear-DnsClientCache
Write-Host 'Current DNS:'
Get-DnsClientServerAddress -InterfaceIndex $InterfaceIndex | Format-Table -AutoSize
Write-Host 'DNS-over-HTTPS is not configured by this helper. Proxy/VPN/managed policy may use a different resolver.'
Read-Host 'Press Enter to close'
