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
Common labels
*/}}
{{- define "finmind.labels" -}}
helm.sh/chart: {{ include "finmind.chart" . }}
{{ include "finmind.selectorLabels" . }}
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
Chart label
*/}}
{{- define "finmind.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Database URL - auto-generate if using built-in PostgreSQL
*/}}
{{- define "finmind.databaseUrl" -}}
{{- if .Values.secrets.databaseUrl }}
{{- .Values.secrets.databaseUrl }}
{{- else if .Values.postgresql.enabled }}
{{- printf "postgresql+psycopg2://%s:%s@%s-postgresql:5432/%s" .Values.postgresql.auth.username .Values.postgresql.auth.password (include "finmind.fullname" .) .Values.postgresql.auth.database }}
{{- else }}
{{- fail "Either secrets.databaseUrl or postgresql.enabled must be set" }}
{{- end }}
{{- end }}

{{/*
Redis URL - auto-generate if using built-in Redis
*/}}
{{- define "finmind.redisUrl" -}}
{{- if .Values.secrets.redisUrl }}
{{- .Values.secrets.redisUrl }}
{{- else if .Values.redis.enabled }}
{{- printf "redis://%s-redis-master:6379/0" (include "finmind.fullname" .) }}
{{- else }}
{{- fail "Either secrets.redisUrl or redis.enabled must be set" }}
{{- end }}
{{- end }}
