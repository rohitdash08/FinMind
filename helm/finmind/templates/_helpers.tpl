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
Backend image
*/}}
{{- define "finmind.backend.image" -}}
{{ .Values.global.imageRegistry }}/{{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}
{{- end }}

{{/*
Frontend image
*/}}
{{- define "finmind.frontend.image" -}}
{{ .Values.global.imageRegistry }}/{{ .Values.frontend.image.repository }}:{{ .Values.frontend.image.tag }}
{{- end }}

{{/*
Database URL
*/}}
{{- define "finmind.databaseUrl" -}}
postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ include "finmind.fullname" . }}-postgresql:5432/$(POSTGRES_DB)
{{- end }}

{{/*
Redis URL
*/}}
{{- define "finmind.redisUrl" -}}
redis://{{ include "finmind.fullname" . }}-redis:6379/0
{{- end }}
