{{- define "finmind.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "finmind.fullname" -}}
{{- printf "%s" (include "finmind.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
