{{/*
=============================================================================
FinMind Helm Chart — Template Helpers
=============================================================================
*/}}

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
Chart label for all resources.
*/}}
{{- define "finmind.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "finmind.labels" -}}
helm.sh/chart: {{ include "finmind.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: finmind
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{/*
Selector labels for a specific component.
Usage: {{ include "finmind.selectorLabels" (dict "component" "backend" "context" .) }}
*/}}
{{- define "finmind.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" .context }}
app.kubernetes.io/instance: {{ .context.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Construct the DATABASE_URL from secret references.
*/}}
{{- define "finmind.databaseUrl" -}}
postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ include "finmind.fullname" . }}-postgresql:5432/$(POSTGRES_DB)
{{- end }}

{{/*
Redis URL pointing to the in-cluster Redis service.
*/}}
{{- define "finmind.redisUrl" -}}
redis://{{ include "finmind.fullname" . }}-redis:6379/0
{{- end }}

{{/*
Service account name.
*/}}
{{- define "finmind.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "finmind.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
