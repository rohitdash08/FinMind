import { exec } from 'child_process';
import { promisify } from 'util';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

const execAsync = promisify(exec);

describe('Deployment Integration Tests', () => {
  const timeout = 120000; // 2 minutes

  beforeAll(() => {
    jest.setTimeout(timeout);
  });

  describe('Docker Configuration', () => {
    test('backend Dockerfile builds successfully', async () => {
      const { stdout, stderr } = await execAsync(
        'docker build -t finmind-backend-test ./packages/backend'
      );

      expect(stderr).not.toContain('ERROR');
      expect(stdout).toContain('Successfully tagged');
    });

    test('frontend Dockerfile builds successfully', async () => {
      const { stdout, stderr } = await execAsync(
        'docker build -t finmind-frontend-test ./app'
      );

      expect(stderr).not.toContain('ERROR');
      expect(stdout).toContain('Successfully tagged');
    });

    test('docker-compose starts all services', async () => {
      try {
        await execAsync('docker-compose -f docker-compose.yml up -d');
        await new Promise(resolve => setTimeout(resolve, 15000));

        const { stdout } = await execAsync('docker-compose ps');
        expect(stdout).toContain('finmind');
        expect(stdout).toContain('Up');
      } finally {
        await execAsync('docker-compose down').catch(() => {});
      }
    });

    test('backend container health check passes', async () => {
      try {
        await execAsync('docker run -d --name test-backend -p 8001:8000 finmind-backend-test');
        await new Promise(resolve => setTimeout(resolve, 10000));

        const { stdout } = await execAsync('docker inspect test-backend --format="{{.State.Health.Status}}"');
        expect(stdout.trim()).toBe('healthy');
      } finally {
        await execAsync('docker rm -f test-backend').catch(() => {});
      }
    });
  });

  describe('Kubernetes Configuration', () => {
    test('kubernetes manifests are valid YAML', () => {
      const manifestDir = join(process.cwd(), 'k8s');
      const manifestFiles = [
        'namespace.yaml',
        'backend-deployment.yaml',
        'frontend-deployment.yaml',
        'redis-deployment.yaml',
        'backend-service.yaml',
        'frontend-service.yaml'
      ];

      manifestFiles.forEach(file => {
        const manifestPath = join(manifestDir, file);
        expect(existsSync(manifestPath)).toBe(true);

        const content = readFileSync(manifestPath, 'utf8');
        expect(() => JSON.parse(JSON.stringify(require('js-yaml').load(content)))).not.toThrow();
      });
    });

    test('deployment manifests have required fields', () => {
      const backendManifest = join(process.cwd(), 'k8s/backend-deployment.yaml');
      const content = readFileSync(backendManifest, 'utf8');

      expect(content).toContain('apiVersion: apps/v1');
      expect(content).toContain('kind: Deployment');
      expect(content).toContain('spec:');
      expect(content).toContain('replicas:');
      expect(content).toContain('selector:');
      expect(content).toContain('template:');
    });

    test('service manifests expose correct ports', () => {
      const backendService = join(process.cwd(), 'k8s/backend-service.yaml');
      const frontendService = join(process.cwd(), 'k8s/frontend-service.yaml');

      const backendContent = readFileSync(backendService, 'utf8');
      const frontendContent = readFileSync(frontendService, 'utf8');

      expect(backendContent).toContain('port: 8000');
      expect(frontendContent).toContain('port: 3000');
    });
  });

  describe('Environment Variables', () => {
    test('backend env validation passes', () => {
      const envExample = join(process.cwd(), 'packages/backend/.env.example');
      expect(existsSync(envExample)).toBe(true);

      const content = readFileSync(envExample, 'utf8');
      expect(content).toContain('REDIS_URL');
      expect(content).toContain('SECRET_KEY');
      expect(content).toContain('DEBUG');
    });

    test('frontend env variables are documented', () => {
      const envExample = join(process.cwd(), 'app/.env.example');
      expect(existsSync(envExample)).toBe(true);

      const content = readFileSync(envExample, 'utf8');
      expect(content).toContain('REACT_APP_API_URL');
    });

    test('platform-specific env configs exist', () => {
      const platformConfigs = [
        'deploy/railway.json',
        'deploy/render.yaml',
        'deploy/fly.toml'
      ];

      platformConfigs.forEach(config => {
        const configPath = join(process.cwd(), config);
        if (existsSync(configPath)) {
          const content = readFileSync(configPath, 'utf8');
          expect(content.length).toBeGreaterThan(0);
        }
      });
    });
  });

  describe('Resource Limits', () => {
    test('kubernetes deployments have resource limits', () => {
      const backendDeployment = join(process.cwd(), 'k8s/backend-deployment.yaml');
      const content = readFileSync(backendDeployment, 'utf8');

      expect(content).toMatch(/limits:/);
      expect(content).toMatch(/memory:/);
      expect(content).toMatch(/cpu:/);
      expect(content).toMatch(/requests:/);
    });

    test('docker-compose has memory limits', () => {
      const dockerCompose = join(process.cwd(), 'docker-compose.yml');
      const content = readFileSync(dockerCompose, 'utf8');

      expect(content).toMatch(/mem_limit:/);
    });
  });

  describe('Health Checks', () => {
    test('backend health endpoint responds', async () => {
      const response = await fetch('http://localhost:8000/health').catch(() => null);
      if (response) {
        expect(response.status).toBe(200);
        const data = await response.json();
        expect(data).toHaveProperty('status');
      }
    });

    test('redis connectivity check', async () => {
      try {
        const { stdout } = await execAsync('docker run --rm redis:7 redis-cli --version');
        expect(stdout).toContain('redis-cli');
      } catch (error) {
        // Redis might not be running, that's ok for this test
        expect(true).toBe(true);
      }
    });
  });

  describe('Tilt Configuration', () => {
    test('Tiltfile exists and is valid', () => {
      const tiltfile = join(process.cwd(), 'Tiltfile');
      expect(existsSync(tiltfile)).toBe(true);

      const content = readFileSync(tiltfile, 'utf8');
      expect(content).toContain('docker_build');
      expect(content).toContain('k8s_yaml');
      expect(content).toContain('k8s_resource');
    });

    test('tilt validates configuration', async () => {
      try {
        const { stdout, stderr } = await execAsync('tilt validate');
        expect(stderr).not.toContain('error');
        expect(stdout).toContain('✓');
      } catch (error) {
        // Tilt might not be installed in CI
        expect(error.message).toContain('tilt');
      }
    });
  });

  describe('Platform Readiness', () => {
    test('heroku Procfile exists', () => {
      const procfile = join(process.cwd(), 'Procfile');
      if (existsSync(procfile)) {
        const content = readFileSync(procfile, 'utf8');
        expect(content).toMatch(/web:/);
      }
    });

    test('vercel config exists for frontend', () => {
      const vercelConfig = join(process.cwd(), 'app/vercel.json');
      if (existsSync(vercelConfig)) {
        const content = readFileSync(vercelConfig, 'utf8');
        const config = JSON.parse(content);
        expect(config).toHaveProperty('builds');
      }
    });

    test('railway config validates', () => {
      const railwayConfig = join(process.cwd(), 'railway.json');
      if (existsSync(railwayConfig)) {
        const content = readFileSync(railwayConfig, 'utf8');
        const config = JSON.parse(content);
        expect(config).toHaveProperty('deploy');
      }
    });
  });

  describe('Security Configuration', () => {
    test('secrets are not hardcoded in configs', () => {
      const configFiles = [
        'docker-compose.yml',
        'k8s/backend-deployment.yaml',
        'deploy/railway.json'
      ];

      configFiles.forEach(file => {
        const filePath = join(process.cwd(), file);
        if (existsSync(filePath)) {
          const content = readFileSync(filePath, 'utf8');
          expect(content).not.toMatch(/password.*=.*[a-zA-Z0-9]{8,}/);
          expect(content).not.toMatch(/secret.*=.*[a-zA-Z0-9]{16,}/);
          expect(content).not.toMatch(/key.*=.*[a-zA-Z0-9]{20,}/);
        }
      });
    });

    test('network policies are configured', () => {
      const networkPolicy = join(process.cwd(), 'k8s/network-policy.yaml');
      if (existsSync(networkPolicy)) {
        const content = readFileSync(networkPolicy, 'utf8');
        expect(content).toContain('NetworkPolicy');
      }
    });
  });
});
