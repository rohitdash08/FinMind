allow_k8s_contexts(['docker-desktop', 'kind-kind', 'kind-finmind-review', 'minikube'])

backend_ref = 'finmind-backend:tilt'
frontend_ref = 'finmind-frontend:tilt'

k8s_yaml(helm('deploy/helm/finmind', name='finmind', namespace='finmind', values=['deploy/helm/finmind/values.tilt.yaml']))

docker_build(
  backend_ref,
  'packages/backend',
  live_update=[
    sync('packages/backend/app', '/app/app'),
    sync('packages/backend/wsgi.py', '/app/wsgi.py'),
    run('pip install -r requirements.txt', trigger=['packages/backend/requirements.txt']),
  ],
)

docker_build(
  frontend_ref,
  'app',
  live_update=[
    sync('app/src', '/app/src'),
    sync('app/public', '/app/public'),
    run('npm install', trigger=['app/package.json', 'app/package-lock.json']),
  ],
)

k8s_resource('finmind-backend', port_forwards='8000:8000')
k8s_resource('finmind-frontend', port_forwards='8081:80')
