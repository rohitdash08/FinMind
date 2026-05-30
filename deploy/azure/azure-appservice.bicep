param location string = resourceGroup().location
param appName string = 'finmind-backend'
param containerImage string = 'ghcr.io/rohitdash08/finmind-backend:latest'

resource appServicePlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: '${appName}-plan'
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
}

resource webApp 'Microsoft.Web/sites@2022-03-01' = {
  name: appName
  location: location
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'DOCKER|${containerImage}'
      appSettings: [
        { name: 'LOG_LEVEL', value: 'INFO' }
        { name: 'GEMINI_MODEL', value: 'gemini-1.5-flash' }
        { name: 'DATABASE_URL', value: '@Microsoft.KeyVault(SecretUri=https://finmind-kv.vault.azure.net/secrets/DATABASE_URL/)' }
        { name: 'JWT_SECRET', value: '@Microsoft.KeyVault(SecretUri=https://finmind-kv.vault.azure.net/secrets/JWT_SECRET/)' }
      ]
      alwaysOn: true
    }
  }
}

output appUrl string = 'https://${webApp.properties.defaultHostName}'
