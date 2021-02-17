# Delete and stop the service if it already exists.
 # Delete and stop the service if it already exists.
 if (Get-Service iis_filebeat -ErrorAction SilentlyContinue) {
  $service = Get-WmiObject -Class Win32_Service -Filter "name='iis_filebeat'"
  $service.StopService()
  Start-Sleep -s 1
  $service.delete()
}

$workdir = Split-Path $MyInvocation.MyCommand.Path

# Create the new service.
New-Service -name iis_filebeat `
  -displayName iis_filebeat `
  -binaryPathName "`"$workdir\filebeat.exe`" --environment=windows_service -c `"$workdir\filebeat.yml`" --path.home `"$workdir`" --path.data `"C:\ProgramData\filebeat`" --path.logs `"C:\ProgramData\filebeat\logs`" -E logging.files.redirect_stderr=true"

# Attempt to set the service to delayed start using sc config.
Try {
  Start-Process -FilePath sc.exe -ArgumentList 'config iis_filebeat start= delayed-auto'
}
Catch { Write-Host -f red "An error occured setting the service to delayed start." }
 
