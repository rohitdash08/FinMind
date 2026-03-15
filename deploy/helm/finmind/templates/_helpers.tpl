{{/*
Expand the name of the chart.
*/}}
{{- define "finmind.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
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
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- end }}

{{/*
Backend labels
*/}}
{{- define "finmind.backend.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/name: {{ include "finmind.name" . }}-backend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "finmind.backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}-backend
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "finmind.frontend.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/name: {{ include "finmind.name" . }}-frontend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "finmind.frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}-frontend
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
PostgreSQL labels
*/}}
{{- define "finmind.postgresql.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/name: {{ include "finmind.name" . }}-postgresql
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: database
{{- end }}

{{/*
PostgreSQL selector labels
*/}}
{{- define "finmind.postgresql.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}-postgresql
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Redis labels
*/}}
{{- define "finmind.redis.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/name: {{ include "finmind.name" . }}-redis
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: cache
{{- end }}

{{/*
Redis selector labels
*/}}
{{- define "finmind.redis.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}-redis
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Namespace helper
*/}}
{{- define "finmind.namespace" -}}
{{- default .Release.Namespace .Values.global.namespace }}
{{- end }}

{{/*
Backend service name
*/}}
{{- define "finmind.backend.serviceName" -}}
{{- printf "%s-backend" (include "finmind.fullname" .) }}
{{- end }}

{{/*
Frontend service name
*/}}
{{- define "finmind.frontend.serviceName" -}}
{{- printf "%s-frontend" (include "finmind.fullname" .) }}
{{- end }}

{{/*
PostgreSQL service name
*/}}
{{- define "finmind.postgresql.serviceName" -}}
{{- printf "%s-postgresql" (include "finmind.fullname" .) }}
{{- end }}

{{/*
Redis service name
*/}}
{{- define "finmind.redis.serviceName" -}}
{{- printf "%s-redis" (include "finmind.fullname" .) }}
{{- end }}

{{/*
Secret name
*/}}
{{- define "finmind.secretName" -}}
{{- printf "%s-secret" (include "finmind.fullname" .) }}
{{- end }}

{{/*
ConfigMap name
*/}}
{{- define "finmind.configMapName" -}}
{{- printf "%s-config" (include "finmind.fullname" .) }}
{{- end }}

{{/*
Image pull secrets
*/}}
{{- define "finmind.imagePullSecrets" -}}
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
