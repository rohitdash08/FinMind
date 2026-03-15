// ============================================================================
// FinMind — Azure Bicep Template
// ============================================================================
// Deploys:
//   - Container App Environment with Log Analytics
//   - Backend Container App (Python/Flask, port 8000)
//   - Frontend Container App (React/nginx, port 80)
//   - Azure Database for PostgreSQL Flexible Server
//
// Usage:
//   az deployment group create \
//     --resource-group finmind-rg \
//     --template-file main.bicep \
//     --parameters backendImage=<acr>.azurecr.io/finmind-backend:latest \
//                  frontendImage=<acr>.azurecr.io/finmind-frontend:latest \
//                  postgresAdminPassword=<password> \
//                  jwtSecret=<secret> \
//                  geminiApiKey=<key>
// ============================================================================

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

@description('Name prefix for all resources')
param projectName string = 'finmind'

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('Backend container image (full ACR path with tag)')
param backendImage string

@description('Frontend container image (full ACR path with tag)')
param frontendImage string

@description('ACR login server (e.g., finmindacr.azurecr.io)')
param acrLoginServer string

@description('ACR username')
param acrUsername string

@secure()
@description('ACR password')
param acrPassword string

@secure()
@description('PostgreSQL admin password')
param postgresAdminPassword string

@description('PostgreSQL admin username')
param postgresAdminUser string = 'finmindadmin'

@secure()
@description('JWT signing secret')
param jwtSecret string

@secure()
@description('Google Gemini API key')
param geminiApiKey string

@description('Gemini model name')
param geminiModel string = 'gemini-pro'

@description('Log level for backend')
param logLevel string = 'info'

@description('Minimum backend replicas')
param backendMinReplicas int = 1

@description('Maximum backend replicas')
param backendMaxReplicas int = 10

@description('Minimum frontend replicas')
param frontendMinReplicas int = 0

@description('Maximum frontend replicas')
param frontendMaxReplicas int = 5

// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

var envName = '${projectName}-env'
var backendAppName = '${projectName}-backend'
var frontendAppName = '${projectName}-frontend'
var postgresServerName = '${projectName}-pgserver'
var logAnalyticsName = '${projectName}-logs'
var postgresDbName = 'finmind'

// ---------------------------------------------------------------------------
// Log Analytics Workspace
// ---------------------------------------------------------------------------

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
  tags: {
    app: projectName
    environment: 'production'
  }
}

// ---------------------------------------------------------------------------
// Container App Environment
// ---------------------------------------------------------------------------

resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: envName
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
  tags: {
    app: projectName
    environment: 'production'
  }
}

// ---------------------------------------------------------------------------
// Azure Database for PostgreSQL Flexible Server
// ---------------------------------------------------------------------------

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-03-01-preview' = {
  name: postgresServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '15'
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
  tags: {
    app: projectName
    environment: 'production'
  }
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-03-01-preview' = {
  parent: postgresServer
  name: postgresDbName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Allow Azure services to connect
resource postgresFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-03-01-preview' = {
  parent: postgresServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ---------------------------------------------------------------------------
// Backend Container App
// ---------------------------------------------------------------------------

resource backendApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: backendAppName
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
        {
          name: 'database-url'
          value: 'postgresql://${postgresAdminUser}:${postgresAdminPassword}@${postgresServer.properties.fullyQualifiedDomainName}:5432/${postgresDbName}?sslmode=require'
        }
        {
          name: 'jwt-secret'
          value: jwtSecret
        }
        {
          name: 'gemini-api-key'
          value: geminiApiKey
        }
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
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'REDIS_URL'
              value: 'redis://localhost:6379/0'  // Update with actual Redis URL
            }
            {
              name: 'JWT_SECRET'
              secretRef: 'jwt-secret'
            }
            {
              name: 'GEMINI_API_KEY'
              secretRef: 'gemini-api-key'
            }
            {
              name: 'LOG_LEVEL'
              value: logLevel
            }
            {
              name: 'GEMINI_MODEL'
              value: geminiModel
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 30
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 5
            }
            {
              type: 'Startup'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              failureThreshold: 10
              timeoutSeconds: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: backendMinReplicas
        maxReplicas: backendMaxReplicas
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
  tags: {
    app: projectName
    component: 'backend'
    environment: 'production'
  }
}

// ---------------------------------------------------------------------------
// Frontend Container App
// ---------------------------------------------------------------------------

resource frontendApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: frontendAppName
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 80
        transport: 'http'
        allowInsecure: false
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password-fe'
        }
      ]
      secrets: [
        {
          name: 'acr-password-fe'
          value: acrPassword
        }
      ]
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
          env: [
            {
              name: 'VITE_API_URL'
              value: 'https://${backendApp.properties.configuration.ingress.fqdn}'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/'
                port: 80
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/'
                port: 80
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: frontendMinReplicas
        maxReplicas: frontendMaxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
  tags: {
    app: projectName
    component: 'frontend'
    environment: 'production'
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output backendUrl string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output frontendUrl string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'
output postgresServer string = postgresServer.properties.fullyQualifiedDomainName
output containerAppEnvironment string = containerAppEnv.name
