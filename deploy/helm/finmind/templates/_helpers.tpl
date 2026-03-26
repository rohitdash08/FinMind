{{/*
Expand the name of the chart.
*/}}
{{- define "finmind.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "finmind.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "finmind.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "finmind.labels" -}}
helm.sh/chart: {{ include "finmind.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: finmind
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{/*
Selector labels for a specific component
*/}}
{{- define "finmind.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend labels
*/}}
{{- define "finmind.backend.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/component: backend
app: backend
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "finmind.frontend.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/component: frontend
app: frontend
{{- end }}

{{/*
Postgres labels
*/}}
{{- define "finmind.postgres.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/component: database
app: postgres
{{- end }}

{{/*
Redis labels
*/}}
{{- define "finmind.redis.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/component: cache
app: redis
{{- end }}

{{/*
Nginx labels
*/}}
{{- define "finmind.nginx.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/component: proxy
app: nginx
{{- end }}

{{/*
Namespace
*/}}
{{- define "finmind.namespace" -}}
{{- default "finmind" .Values.global.namespace }}
{{- end }}

{{/*
Database URL construction
*/}}
{{- define "finmind.databaseUrl" -}}
postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@postgres:5432/$(POSTGRES_DB)
{{- end }}

{{/*
ConfigMap checksum annotation — forces pod restart when config changes
*/}}
{{- define "finmind.configChecksum" -}}
checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
checksum/secret: {{ include (print $.Template.BasePath "/secrets.yaml") . | sha256sum }}
{{- end }}

{{/*
Service Account name
*/}}
{{- define "finmind.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "finmind.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
