// FinMind �?Azure Bicep Deployment Template
// ──────────────────────────────────────────
// Deploy:
//   az deployment group create \
//     --resource-group finmind-rg \
//     --template-file deploy/azure/bicep/main.bicep \
//     --parameters backendImage='ghcr.io/rohitdash08/finmind-backend:latest' \
//                  frontendImage='ghcr.io/rohitdash08/finmind-frontend:latest' \
//                  jwtSecret='YOUR_SECRET' \
//                  databaseUrl='postgresql://...' \
//                  redisUrl='redis://...'

@description('Location for all resources')
param location string = resourceGroup().location

@description('Backend container image')
param backendImage string

@description('Frontend container image')
param frontendImage string

@secure()
@description('JWT signing secret')
param jwtSecret string

@secure()
@description('PostgreSQL connection string')
param databaseUrl string

@secure()
@description('Redis connection string')
param redisUrl string

@description('Gemini API key (optional)')
@secure()
param geminiApiKey string = ''

// ── Log Analytics Workspace ──────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'finmind-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ── Container Apps Environment ───────────────────
resource containerEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: 'finmind-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ── Backend Container App ────────────────────────
resource backend 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'finmind-backend'
  location: location
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      secrets: [
        { name: 'jwt-secret', value: jwtSecret }
        { name: 'database-url', value: databaseUrl }
        { name: 'redis-url', value: redisUrl }
        { name: 'gemini-api-key', value: geminiApiKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'GEMINI_API_KEY', secretRef: 'gemini-api-key' }
            { name: 'GEMINI_MODEL', value: 'gemini-1.5-flash' }
            { name: 'LOG_LEVEL', value: 'INFO' }
          ]
          command: [
            'sh'
            '-c'
            'python -m flask --app wsgi:app init-db && gunicorn --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app'
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 15
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 5
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

// ── Frontend Container App ───────────────────────
resource frontend 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'finmind-frontend'
  location: location
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 80
        transport: 'http'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
      }
    }
  }
}

// ── Outputs ──────────────────────────────────────
output backendUrl string = 'https://${backend.properties.configuration.ingress.fqdn}'
output frontendUrl string = 'https://${frontend.properties.configuration.ingress.fqdn}'
