{{/*
Common labels
*/}}
{{- define "finmind.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Selector labels for a component
*/}}
{{- define "finmind.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Full name helper
*/}}
{{- define "finmind.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Database URL construction
*/}}
{{- define "finmind.databaseUrl" -}}
postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ .Release.Name }}-postgres:5432/$(POSTGRES_DB)
{{- end }}

{{/*
Redis URL construction
*/}}
{{- define "finmind.redisUrl" -}}
redis://{{ .Release.Name }}-redis:6379/0
{{- end }}
