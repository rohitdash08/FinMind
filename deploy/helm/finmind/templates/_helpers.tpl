{{/*
Common labels
*/}}
{{- define "finmind.labels" -}}
app.kubernetes.io/name: finmind
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Selector labels for a component
*/}}
{{- define "finmind.selectorLabels" -}}
app.kubernetes.io/name: finmind
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}
