$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$modelDirectory = Join-Path $projectRoot 'models'
New-Item -ItemType Directory -Force -Path $modelDirectory | Out-Null
Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task' -OutFile (Join-Path $modelDirectory 'hand_landmarker.task')
Write-Output 'Hand Landmarker model downloaded. Restart or reconnect the app to refresh availability.'
