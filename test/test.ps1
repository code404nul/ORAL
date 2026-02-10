# Test de l'API Fireworks.ai avec Molmo8b - Version DEBUG
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Test API Fireworks.ai avec Molmo8b" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$headers = @{
    "Accept" = "application/json"
    "Content-Type" = "application/json"
    "Authorization" = "Bearer fw_9jPTovViK51DBPKw7ukvDm"
}

$body = @{
    model = "accounts/code404nul/deployments/f5jaxvzq"
    max_tokens = 512
    top_p = 1
    top_k = 40
    presence_penalty = 0
    frequency_penalty = 0
    temperature = 0.6
    messages = @(
        @{
            role = "user"
            content = @(
                @{
                    type = "text"
                    text = "Can you describe this image?"
                },
                @{
                    type = "image_url"
                    image_url = @{
                        url = "https://images.unsplash.com/photo-1582538885592-e70a5d7ab3d3?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1770&q=80"
                    }
                }
            )
        }
    )
}

$jsonBody = $body | ConvertTo-Json -Depth 10

Write-Host "Requete envoyee:" -ForegroundColor Yellow
Write-Host $jsonBody -ForegroundColor Gray
Write-Host ""

try {
    Write-Host "Envoi de la requete..." -ForegroundColor Yellow
    
    $response = Invoke-RestMethod `
        -Uri "https://api.fireworks.ai/inference/v1/chat/completions" `
        -Method Post `
        -Headers $headers `
        -Body $jsonBody `
        -TimeoutSec 120

    Write-Host ""
    Write-Host "Reponse recue!" -ForegroundColor Green
    Write-Host ""
    
    # Debug: afficher la structure complète
    Write-Host "=== REPONSE COMPLETE ===" -ForegroundColor Cyan
    $response | ConvertTo-Json -Depth 10 | Write-Host
    Write-Host ""
    
    # Vérifier si la réponse contient les données attendues
    if ($response.choices -and $response.choices.Count -gt 0) {
        Write-Host "=== MESSAGE DU MODELE ===" -ForegroundColor Magenta
        Write-Host $response.choices[0].message.content -ForegroundColor White
    } elseif ($response.error) {
        Write-Host "=== ERREUR API ===" -ForegroundColor Red
        Write-Host $response.error | ConvertTo-Json -ForegroundColor Red
    } else {
        Write-Host "=== REPONSE INATTENDUE ===" -ForegroundColor Yellow
        Write-Host "La structure de la reponse est differente de celle attendue"
    }
    
} catch {
    Write-Host ""
    Write-Host "Erreur lors de la requete:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    
    if ($_.Exception.Response) {
        Write-Host "Code statut HTTP:" $_.Exception.Response.StatusCode.value__ -ForegroundColor Yellow
        
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $responseBody = $reader.ReadToEnd()
            Write-Host ""
            Write-Host "Details de l'erreur:" -ForegroundColor Yellow
            Write-Host $responseBody -ForegroundColor Yellow
        } catch {
            Write-Host "Impossible de lire le corps de la reponse d'erreur" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "Stack trace complete:" -ForegroundColor Gray
    Write-Host $_.Exception.ToString() -ForegroundColor Gray
}

Write-Host ""
Write-Host "Test termine" -ForegroundColor Green
Write-Host ""
Read-Host "Appuyez sur Entree pour fermer"