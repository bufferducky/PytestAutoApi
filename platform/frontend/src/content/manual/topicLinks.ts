import type { HelpTopic } from '../helpTopics';

// 每个就地帮助都有具体小节，不回退到概览。
export const manualTopicLinks: Record<HelpTopic, { articleId: string; sectionId: string }> = {
  "selector": {
    "articleId": "field-paths",
    "sectionId": "selector"
  },
  "environment": {
    "articleId": "environment",
    "sectionId": "environment"
  },
  "baseUrl": {
    "articleId": "environment",
    "sectionId": "base-url"
  },
  "environmentStatus": {
    "articleId": "environment",
    "sectionId": "environment-status"
  },
  "target": {
    "articleId": "target",
    "sectionId": "target"
  },
  "profileKind": {
    "articleId": "target",
    "sectionId": "profile-kind"
  },
  "requiresContext": {
    "articleId": "target",
    "sectionId": "requires-context"
  },
  "authMode": {
    "articleId": "login",
    "sectionId": "auth-mode"
  },
  "loginPath": {
    "articleId": "login",
    "sectionId": "login-path"
  },
  "requestMode": {
    "articleId": "login",
    "sectionId": "request-mode"
  },
  "passwordTransform": {
    "articleId": "login",
    "sectionId": "password-transform"
  },
  "tokenPath": {
    "articleId": "login",
    "sectionId": "token-path"
  },
  "userAgent": {
    "articleId": "login",
    "sectionId": "user-agent"
  },
  "headerTemplate": {
    "articleId": "login",
    "sectionId": "header-template"
  },
  "profileAdvanced": {
    "articleId": "login",
    "sectionId": "profile-advanced"
  },
  "identity": {
    "articleId": "identity",
    "sectionId": "identity"
  },
  "targetIds": {
    "articleId": "identity",
    "sectionId": "target-ids"
  },
  "secretRef": {
    "articleId": "identity",
    "sectionId": "secret-ref"
  },
  "binding": {
    "articleId": "binding",
    "sectionId": "binding"
  },
  "tenantId": {
    "articleId": "binding",
    "sectionId": "tenant-id"
  },
  "projectId": {
    "articleId": "binding",
    "sectionId": "project-id"
  },
  "scopePath": {
    "articleId": "binding",
    "sectionId": "scope-path"
  },
  "tenantPath": {
    "articleId": "binding",
    "sectionId": "tenant-path"
  },
  "projectPath": {
    "articleId": "binding",
    "sectionId": "project-path"
  },
  "executeLogin": {
    "articleId": "preflight",
    "sectionId": "execute-login"
  },
  "contextPreflight": {
    "articleId": "preflight",
    "sectionId": "context-preflight"
  },
  "priority": {
    "articleId": "scenario",
    "sectionId": "priority"
  },
  "tags": {
    "articleId": "scenario",
    "sectionId": "tags"
  },
  "stepId": {
    "articleId": "scenario",
    "sectionId": "step-id"
  },
  "stepType": {
    "articleId": "scenario",
    "sectionId": "step-type"
  },
  "phase": {
    "articleId": "scenario",
    "sectionId": "phase"
  },
  "assetStatus": {
    "articleId": "scenario",
    "sectionId": "asset-status"
  },
  "configurationRevision": {
    "articleId": "scenario",
    "sectionId": "configuration-revision"
  },
  "method": {
    "articleId": "request",
    "sectionId": "method"
  },
  "url": {
    "articleId": "request",
    "sectionId": "url"
  },
  "operation": {
    "articleId": "request",
    "sectionId": "operation"
  },
  "contract": {
    "articleId": "request",
    "sectionId": "contract"
  },
  "headers": {
    "articleId": "request",
    "sectionId": "headers"
  },
  "query": {
    "articleId": "request",
    "sectionId": "query"
  },
  "bodyType": {
    "articleId": "request",
    "sectionId": "body-type"
  },
  "body": {
    "articleId": "request",
    "sectionId": "body"
  },
  "replay": {
    "articleId": "request",
    "sectionId": "replay"
  },
  "schema": {
    "articleId": "parameters",
    "sectionId": "schema"
  },
  "parameters": {
    "articleId": "parameters",
    "sectionId": "parameters"
  },
  "dependencies": {
    "articleId": "dependencies",
    "sectionId": "dependencies"
  },
  "extractors": {
    "articleId": "extractors",
    "sectionId": "extractors"
  },
  "assertSource": {
    "articleId": "assertions",
    "sectionId": "assert-source"
  },
  "operator": {
    "articleId": "assertions",
    "sectionId": "operator"
  },
  "expected": {
    "articleId": "assertions",
    "sectionId": "expected"
  },
  "assertJson": {
    "articleId": "assertions",
    "sectionId": "assert-json"
  },
  "expectedRef": {
    "articleId": "advanced-assertions",
    "sectionId": "expected-ref"
  },
  "valueType": {
    "articleId": "advanced-assertions",
    "sectionId": "value-type"
  },
  "tolerance": {
    "articleId": "advanced-assertions",
    "sectionId": "tolerance"
  },
  "invariant": {
    "articleId": "advanced-assertions",
    "sectionId": "invariant"
  },
  "baseline": {
    "articleId": "advanced-assertions",
    "sectionId": "baseline"
  },
  "stateSelector": {
    "articleId": "async-wait",
    "sectionId": "state-selector"
  },
  "stateMap": {
    "articleId": "async-wait",
    "sectionId": "state-map"
  },
  "pollInterval": {
    "articleId": "async-wait",
    "sectionId": "poll-interval"
  },
  "pollDeadline": {
    "articleId": "async-wait",
    "sectionId": "poll-deadline"
  },
  "pollAttempts": {
    "articleId": "async-wait",
    "sectionId": "poll-attempts"
  },
  "networkRetries": {
    "articleId": "async-wait",
    "sectionId": "network-retries"
  },
  "waitPolicy": {
    "articleId": "async-wait",
    "sectionId": "wait-policy"
  },
  "debugParameters": {
    "articleId": "debugging",
    "sectionId": "debug-parameters"
  },
  "debugInputs": {
    "articleId": "debugging",
    "sectionId": "debug-inputs"
  },
  "debugScenario": {
    "articleId": "debugging",
    "sectionId": "debug-scenario"
  },
  "debugStep": {
    "articleId": "debugging",
    "sectionId": "debug-step"
  },
  "import": {
    "articleId": "import-export",
    "sectionId": "import"
  },
  "export": {
    "articleId": "import-export",
    "sectionId": "export"
  },
  "migration": {
    "articleId": "import-export",
    "sectionId": "migration"
  },
  "preflight": {
    "articleId": "publishing",
    "sectionId": "preflight"
  },
  "publish": {
    "articleId": "publishing",
    "sectionId": "publish"
  },
  "version": {
    "articleId": "publishing",
    "sectionId": "version"
  },
  "archive": {
    "articleId": "publishing",
    "sectionId": "archive"
  },
  "scenarioRef": {
    "articleId": "suites",
    "sectionId": "scenario-ref"
  },
  "budget": {
    "articleId": "suites",
    "sectionId": "budget"
  },
  "runEnvironment": {
    "articleId": "running",
    "sectionId": "run-environment"
  },
  "build": {
    "articleId": "running",
    "sectionId": "build"
  },
  "plan": {
    "articleId": "running",
    "sectionId": "plan"
  },
  "run": {
    "articleId": "running",
    "sectionId": "run"
  },
  "liveConfirmation": {
    "articleId": "running",
    "sectionId": "live-confirmation"
  },
  "transport": {
    "articleId": "running",
    "sectionId": "transport"
  },
  "cron": {
    "articleId": "scheduling",
    "sectionId": "cron"
  },
  "timezone": {
    "articleId": "scheduling",
    "sectionId": "timezone"
  },
  "missed": {
    "articleId": "scheduling",
    "sectionId": "missed"
  },
  "busyPolicy": {
    "articleId": "scheduling",
    "sectionId": "busy-policy"
  },
  "queueBudget": {
    "articleId": "scheduling",
    "sectionId": "queue-budget"
  },
  "suiteId": {
    "articleId": "scheduling",
    "sectionId": "suite-id"
  },
  "scheduleSave": {
    "articleId": "scheduling",
    "sectionId": "schedule-save"
  },
  "scheduleToggle": {
    "articleId": "scheduling",
    "sectionId": "schedule-toggle"
  },
  "pauseAll": {
    "articleId": "scheduling",
    "sectionId": "pause-all"
  },
  "scheduleDelete": {
    "articleId": "scheduling",
    "sectionId": "schedule-delete"
  },
  "schedulePreview": {
    "articleId": "scheduling",
    "sectionId": "schedule-preview"
  },
  "triggers": {
    "articleId": "scheduling",
    "sectionId": "triggers"
  },
  "scheduler": {
    "articleId": "scheduling",
    "sectionId": "scheduler"
  },
  "scheduleState": {
    "articleId": "scheduling",
    "sectionId": "schedule-state"
  },
  "reportRuns": {
    "articleId": "release-report",
    "sectionId": "report-runs"
  },
  "reportMode": {
    "articleId": "release-report",
    "sectionId": "report-mode"
  },
  "report": {
    "articleId": "release-report",
    "sectionId": "report"
  },
  "metricsTotal": {
    "articleId": "dashboard",
    "sectionId": "metrics-total"
  },
  "metricsFailed": {
    "articleId": "dashboard",
    "sectionId": "metrics-failed"
  },
  "metricsPage": {
    "articleId": "dashboard",
    "sectionId": "metrics-page"
  },
  "metricsSuccess": {
    "articleId": "dashboard",
    "sectionId": "metrics-success"
  },
  "metricsInflight": {
    "articleId": "dashboard",
    "sectionId": "metrics-inflight"
  },
  "elapsed": {
    "articleId": "dashboard",
    "sectionId": "elapsed"
  },
  "runStatus": {
    "articleId": "diagnostics",
    "sectionId": "run-status"
  },
  "errorCategory": {
    "articleId": "diagnostics",
    "sectionId": "error-category"
  },
  "rerun": {
    "articleId": "diagnostics",
    "sectionId": "rerun"
  },
  "failedRerun": {
    "articleId": "diagnostics",
    "sectionId": "failed-rerun"
  },
  "cancel": {
    "articleId": "diagnostics",
    "sectionId": "cancel"
  },
  "snapshot": {
    "articleId": "diagnostics",
    "sectionId": "snapshot"
  },
  "evidence": {
    "articleId": "diagnostics",
    "sectionId": "evidence"
  },
  "compare": {
    "articleId": "diagnostics",
    "sectionId": "compare"
  },
  "rawEvidence": {
    "articleId": "diagnostics",
    "sectionId": "raw-evidence"
  },
  "isoTime": {
    "articleId": "run-filters",
    "sectionId": "iso-time"
  },
  "trend": {
    "articleId": "run-filters",
    "sectionId": "trend"
  },
  "filterEnvironment": {
    "articleId": "run-filters",
    "sectionId": "filter-environment"
  },
  "filterTarget": {
    "articleId": "run-filters",
    "sectionId": "filter-target"
  },
  "filterScenario": {
    "articleId": "run-filters",
    "sectionId": "filter-scenario"
  },
  "filterVersion": {
    "articleId": "run-filters",
    "sectionId": "filter-version"
  },
  "filterBuild": {
    "articleId": "run-filters",
    "sectionId": "filter-build"
  },
  "attachment": {
    "articleId": "evidence",
    "sectionId": "attachment"
  },
  "attachmentStep": {
    "articleId": "evidence",
    "sectionId": "attachment-step"
  },
  "pin": {
    "articleId": "evidence",
    "sectionId": "pin"
  },
  "retentionDays": {
    "articleId": "evidence",
    "sectionId": "retention-days"
  },
  "retention": {
    "articleId": "evidence",
    "sectionId": "retention"
  },
  "reclaim": {
    "articleId": "evidence",
    "sectionId": "reclaim"
  },
  "cleanupPreflight": {
    "articleId": "cleanup",
    "sectionId": "cleanup-preflight"
  },
  "cleanup": {
    "articleId": "cleanup",
    "sectionId": "cleanup"
  },
  "businessDatasource": {
    "articleId": "business-datasource",
    "sectionId": "business-datasource"
  },
  "businessDatasourceProbe": {
    "articleId": "business-datasource",
    "sectionId": "business-datasource-probe"
  },
  "receptionPack": {
    "articleId": "reception",
    "sectionId": "reception-pack"
  },
  "expectedUser": {
    "articleId": "reception",
    "sectionId": "expected-user"
  },
  "yanjiPack": {
    "articleId": "reception",
    "sectionId": "yanji-pack"
  },
  "fixture": {
    "articleId": "fixtures",
    "sectionId": "fixture"
  },
  "strategy": {
    "articleId": "fixtures",
    "sectionId": "strategy"
  },
  "acquire": {
    "articleId": "fixtures",
    "sectionId": "acquire"
  },
  "resourceSnapshot": {
    "articleId": "fixtures",
    "sectionId": "resource-snapshot"
  },
  "release": {
    "articleId": "fixtures",
    "sectionId": "release"
  },
  "restore": {
    "articleId": "fixtures",
    "sectionId": "restore"
  },
  "pool": {
    "articleId": "resource-pools",
    "sectionId": "pool"
  },
  "objectId": {
    "articleId": "resource-pools",
    "sectionId": "object-id"
  },
  "dedicated": {
    "articleId": "resource-pools",
    "sectionId": "dedicated"
  },
  "leaseState": {
    "articleId": "resource-pools",
    "sectionId": "lease-state"
  },
  "media": {
    "articleId": "media",
    "sectionId": "media"
  },
  "coverage": {
    "articleId": "coverage",
    "sectionId": "coverage"
  },
  "riskId": {
    "articleId": "coverage",
    "sectionId": "risk-id"
  },
  "required": {
    "articleId": "coverage",
    "sectionId": "required"
  },
  "contractStatus": {
    "articleId": "coverage",
    "sectionId": "contract-status"
  },
  "references": {
    "articleId": "coverage",
    "sectionId": "references"
  },
  "runner": {
    "articleId": "journeys",
    "sectionId": "runner"
  },
  "browserVersion": {
    "articleId": "journeys",
    "sectionId": "browser-version"
  },
  "device": {
    "articleId": "journeys",
    "sectionId": "device"
  },
  "synthetic": {
    "articleId": "journeys",
    "sectionId": "synthetic"
  },
  "recording": {
    "articleId": "journeys",
    "sectionId": "recording"
  },
  "journeyActions": {
    "articleId": "journeys",
    "sectionId": "journey-actions"
  },
  "journeyPreflight": {
    "articleId": "journeys",
    "sectionId": "journey-preflight"
  },
  "journeyRun": {
    "articleId": "journeys",
    "sectionId": "journey-run"
  },
  "quarantine": {
    "articleId": "quarantine",
    "sectionId": "quarantine"
  },
  "resolveQuarantine": {
    "articleId": "quarantine",
    "sectionId": "resolve-quarantine"
  },
  "evaluation": {
    "articleId": "evaluation",
    "sectionId": "evaluation"
  },
  "evaluationCompare": {
    "articleId": "evaluation",
    "sectionId": "evaluation-compare"
  }
};
