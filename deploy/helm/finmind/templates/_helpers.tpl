{{/*
Generate a full image reference from an image dict.
*/}}
{{- define "finmind.image" -}}
{{- $registry := .global.imageRegistry | default "" -}}
{{- if $registry -}}
{{ $registry }}/{{ .image.repository }}:{{ .image.tag | default "latest" }}
{{- else -}}
{{ .image.repository }}:{{ .image.tag | default "latest" }}
{{- end -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "finmind.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: finmind
{{- end -}}

{{/*
Selector labels for a component
*/}}
{{- define "finmind.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .instance }}
{{- end -}}

{{/*
Service account name
*/}}
{{- define "finmind.serviceAccountName" -}}
{{- if .Values.serviceAccount.name -}}
{{ .Values.serviceAccount.name }}
{{- else -}}
{{ .Release.Name }}-finmind
{{- end -}}
{{- end -}}

{{/*
Database URL composed from secret values
*/}}
{{- define "finmind.databaseUrl" -}}
postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ .Release.Name }}-postgres:5432/$(POSTGRES_DB)
{{- end -}}

{{/*
Redis URL
*/}}
{{- define "finmind.redisUrl" -}}
redis://{{ .Release.Name }}-redis:6379/0
{{- end -}}
