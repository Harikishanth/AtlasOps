"""AtlasOps — 20 real SRE tools for the agent runtime."""

from agents.tools.kubectl import (
    kubectl_get, kubectl_describe, kubectl_logs, kubectl_top_pods,
    kubectl_top_nodes, kubectl_rollout, kubectl_scale, kubectl_exec,
)
from agents.tools.prometheus import promql_query, promql_query_range
from agents.tools.jaeger import jaeger_search, jaeger_get_trace
from agents.tools.argocd import (
    argocd_list_apps, argocd_app_history, argocd_rollback, argocd_app_get,
)
from agents.tools.gcloud_logging import gcloud_logs_read
from agents.tools.cloud_monitoring import cloud_monitoring_query
from agents.tools.alertmanager import alertmanager_silence, alertmanager_list_alerts
from agents.tools.comms import slack_post_update, postmortem_draft


TOOL_REGISTRY = {
    "kubectl_get": kubectl_get,
    "kubectl_describe": kubectl_describe,
    "kubectl_logs": kubectl_logs,
    "kubectl_top_pods": kubectl_top_pods,
    "kubectl_top_nodes": kubectl_top_nodes,
    "kubectl_rollout": kubectl_rollout,
    "kubectl_scale": kubectl_scale,
    "kubectl_exec": kubectl_exec,
    "promql_query": promql_query,
    "promql_query_range": promql_query_range,
    "jaeger_search": jaeger_search,
    "jaeger_get_trace": jaeger_get_trace,
    "argocd_list_apps": argocd_list_apps,
    "argocd_app_history": argocd_app_history,
    "argocd_rollback": argocd_rollback,
    "argocd_app_get": argocd_app_get,
    "gcloud_logs_read": gcloud_logs_read,
    "cloud_monitoring_query": cloud_monitoring_query,
    "alertmanager_silence": alertmanager_silence,
    "alertmanager_list_alerts": alertmanager_list_alerts,
    "slack_post_update": slack_post_update,
    "postmortem_draft": postmortem_draft,
}
