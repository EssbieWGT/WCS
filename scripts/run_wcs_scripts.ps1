#running version of the script lives in C:/Scripts 

$logPath = "C:\Scripts\pipenv_scripts_log.txt"
Start-Transcript -Path $logPath -Append

# Set the working directory to the project folder
$projectPath = "C:\Users\wesle\Desktop\Coding Projects\wcs"
Set-Location $projectPath

# Start SSH agent (if needed for Git operations)
if (-not (Get-Process ssh-agent -ErrorAction SilentlyContinue)) {
    Start-Process ssh-agent -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

# Add SSH key (only if necessary)
$sshKeyPath = "c:\Users\wesle\.ssh\id_ed25519.pub"
if (-not (ssh-add -l | Select-String $sshKeyPath)) {
    ssh-add $sshKeyPath
}

# List of Python scripts to run
$scripts = @("./scripts/tricare.py", "./scripts/saf.py", "./scripts/gitPush.py")  # Add more scripts as needed

# Run each script inside the Pipenv shell
foreach ($script in $scripts) {
    Write-Output "Running $script..."
    cmd /c "pipenv run python $script"
}

Stop-Transcript
