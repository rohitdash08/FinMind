param location string = resourceGroup().location
param environmentName string = 'finmind-env'
param containerAppName string = 'finmind'
param appImage string
@secure()
param jwtSecret string
@secure()
param databaseUrl string
@secure()
param redisUrl string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {}
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
      }
      secrets: [
        { name: 'jwt-secret'; value: jwtSecret }
        { name: 'database-url'; value: databaseUrl }
        { name: 'redis-url'; value: redisUrl }
      ]
    }
    template: {
      containers: [
        {
          name: 'finmind'
          image: appImage
          env: [
            { name: 'DATABASE_URL'; secretRef: 'database-url' }
            { name: 'REDIS_URL'; secretRef: 'redis-url' }
            { name: 'JWT_SECRET'; secretRef: 'jwt-secret' }
            { name: 'LOG_LEVEL'; value: 'INFO' }
            { name: 'GEMINI_MODEL'; value: 'gemini-1.5-flash' }
            { name: 'FINMIND_SERVE_SPA'; value: '1' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 5
      }
    }
  }
}
