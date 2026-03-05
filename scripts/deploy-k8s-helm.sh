#!/usr/bin/env sh
set -eu

NAMESPACE=${NAMESPACE:-finmind}
RELEASE=${RELEASE:-finmind}

helm upgrade --install "$RELEASE" deploy/helm/finmind \
  --namespace "$NAMESPACE" --create-namespace

echo "Helm deployment applied: release=$RELEASE namespace=$NAMESPACE"
