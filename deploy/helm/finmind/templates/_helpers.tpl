{{/*
Generate chart name
*/}}
{{- define "finmind.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

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

{{- define "finmind.labels" -}}
helm.sh/chart: {{ include "finmind.name" . }}-{{ .Chart.Version }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: finmind
{{- end }}

{{- define "finmind.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finmind.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "finmind.databaseUrl" -}}
postgresql+psycopg2://{{ .Values.secrets.postgresUser }}:{{ .Values.secrets.postgresPassword }}@{{ include "finmind.fullname" . }}-postgres:5432/{{ .Values.secrets.postgresDb }}
{{- end }}
