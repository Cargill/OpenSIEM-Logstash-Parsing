import-module activedirectory
#create list of domains
$objForest = [System.DirectoryServices.ActiveDirectory.Forest]::GetCurrentForest()
$DomainList = @($objForest.Domains | Select-Object Name)
$Domains = $DomainList | foreach {$_.Name}
$sdate = Get-Date
"Start " + $sdate
foreach($domain in ($Domains)) {
    $user = @()
    $ddate = Get-Date
    "Started " + $domain + " " + $ddate
    
    $path_tmp = 'D:\maintenance_script\Create Lists\AD_USers\' + $domain + '_out.tmp'
    $path_log = 'D:\maintenance_script\Create Lists\AD_USers\' + $domain + '_out.log'
    $user = Get-ADUser -filter * -server $domain -Properties Name, DistinguishedName, SamAccountName, SID, CanonicalName, EmailAddress, directReports, Description, Office, telephoneNumber, City, State, Country, Title, Department, Company, Manager, MemberOf | select @{n='user.full_name';e={$_.Name}}, @{n='file.path';e={$_.DistinguishedName}}, @{n='user.name';e={$_.SamAccountName}}, @{n='user.id';e={$_.SID.Value}}, @{n='_id';e={$_.SID.Value}}, @{n='user.effective.domain';e={$_.CanonicalName}}, @{n='user.domain';e={$domain}}, @{n='user.email';e={$_.EmailAddress}}, @{n='user.description';e={$_.Description}}, @{n='user.office';e={$_.Office}}, @{n='user.telephone';e={$_.telephoneNumber}}, @{n='user.city';e={$_.City}}, @{n='user.stat';e={$_.State}}, @{n='user.country';e={$_.Country}}, @{n='user.title';e={$_.Title}}, @{n='user.business.unit';e={$_.Department}}, @{n='user.company';e={$_.Company}}, @{n='event.ingested';e={((get-date ).AddHours(-7)).tostring("yyyy-MM-dd'T'HH:mm:ss.000'Z'")}}, @{n='tmp_user.roles';e={(($_.MemberOf).split(",") | where-object {$_.contains("CN=")}).replace("CN=","")}}, @{n='tmp_user.directreports';e={(($_.directReports).split(",") | where-object {$_.contains("CN=")}).replace("CN=","")}}, @{n='user.manager';e={(($_.Manager).split(",") | where-object {$_.contains("CN=")}).replace("CN=","")}}
    ($user | ConvertTo-Json -Depth 5).ToLower() | Out-File -FilePath $path_tmp -Append -Encoding utf8
    Rename-Item -NewName $path_log -Path $path_tmp -Force
}
$edate = Get-Date
"Start " + $edate