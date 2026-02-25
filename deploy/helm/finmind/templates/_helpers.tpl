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
{{ include "finmind.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "finmind.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "finmind.backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}-backend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "finmind.frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}-frontend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Nginx selector labels
*/}}
{{- define "finmind.nginx.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}-nginx
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: nginx
{{- end }}

{{/*
Postgres selector labels
*/}}
{{- define "finmind.postgres.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}-postgres
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: postgres
{{- end }}

{{/*
Redis selector labels
*/}}
{{- define "finmind.redis.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}-redis
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: redis
{{- end }}

{{/*
Secret name — use external secret or built-in
*/}}
{{- define "finmind.secretName" -}}
{{- if .Values.externalSecrets.enabled }}
{{- include "finmind.fullname" . }}-external
{{- else }}
{{- include "finmind.fullname" . }}-secrets
{{- end }}
{{- end }}

{{/*
Database URL constructed from secret values
*/}}
{{- define "finmind.databaseUrl" -}}
postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ include "finmind.fullname" . }}-postgres:5432/$(POSTGRES_DB)
{{- end }}

{{/*
Redis URL
*/}}
{{- define "finmind.redisUrl" -}}
redis://{{ include "finmind.fullname" . }}-redis:6379/0
{{- end }}
