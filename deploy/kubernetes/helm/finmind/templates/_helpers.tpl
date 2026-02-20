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
Backend labels
*/}}
{{- define "finmind.backend.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "finmind.frontend.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
PostgreSQL labels
*/}}
{{- define "finmind.postgresql.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/component: database
{{- end }}

{{/*
Redis labels
*/}}
{{- define "finmind.redis.labels" -}}
{{ include "finmind.labels" . }}
app.kubernetes.io/component: cache
{{- end }}
