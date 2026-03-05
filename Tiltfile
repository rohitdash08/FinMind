# FinMind local Kubernetes dev via Helm

helm_yaml = helm('deploy/helm/finmind', name='finmind', namespace='finmind')
k8s_yaml(helm_yaml)

k8s_resource('backend', port_forwards=['8000:8000'])
