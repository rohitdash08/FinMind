# FinMind Helm Chart

Install with:

```bash
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind \
  --create-namespace
```

For local Tilt-driven development, use `deploy/helm/finmind/values.tilt.yaml`.
