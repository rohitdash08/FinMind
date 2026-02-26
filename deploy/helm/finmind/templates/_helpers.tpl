{{/*
Common labels for all FinMind resources
*/}}
{{- define "finmind.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "finmind.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "finmind.backend.selectorLabels" -}}
app: backend
{{ include "finmind.selectorLabels" . }}
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "finmind.frontend.selectorLabels" -}}
app: frontend
{{ include "finmind.selectorLabels" . }}
{{- end }}

{{/*
Full database URL constructed from secrets
*/}}
{{- define "finmind.databaseUrl" -}}
postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@postgres:5432/$(POSTGRES_DB)
{{- end }}
