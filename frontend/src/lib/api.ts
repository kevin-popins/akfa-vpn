export type DashboardStats = {
  nodes_total: number;
  nodes_online: number;
  users_total: number;
  users_active: number;
  traffic_total_bytes: number;
};

export type NodeRead = {
  id: number;
  name: string;
  ip_address: string;
  ssh_port: number;
  ssh_username: string;
  ssh_auth_type?: string;
  location?: string;
  public_host?: string;
  vless_port: number;
  sni: string;
  fingerprint: string;
  xray_config_path?: string;
  xray_service_name?: string;
  status: string;
  short_id?: string;
  reality_public_key?: string;
  xray_installed?: boolean;
  managed_mode?: string;
  inbound_tag?: string | null;
  import_status?: string | null;
  install_log: Array<Record<string, unknown>>;
  last_config_applied_at?: string | null;
  last_config_apply_status?: string;
  last_config_apply_error?: string | null;
  last_config_version?: string | null;
  apply_status?: ConfigApplySummary | null;
};

export type NodeActionJobAccepted = {
  job_id: string;
  status: string;
  current_step: string;
};

export type NodeActionJob = {
  job_id: string;
  node_id: number;
  action: string;
  status: "pending" | "running" | "success" | "failed" | string;
  current_step: string;
  logs: Array<Record<string, unknown>>;
  error?: string | null;
  result?: NodeRead | null;
  created_at: string;
  updated_at: string;
};

export type NodeBulkActionResult = {
  ok: boolean;
  message: string;
  users_changed: number;
  profiles_changed: number;
  affected_node_ids: number[];
  apply_status?: ConfigApplySummary | null;
  apply_error?: string | null;
  errors?: string[];
};

export type NodeApplyResult = {
  node_id: number;
  node_name: string;
  ok: boolean;
  status: string;
  error?: string | null;
  applied_at?: string | null;
  config_version?: string | null;
};

export type ConfigApplySummary = {
  ok: boolean;
  attempted: number;
  succeeded: number;
  failed: number;
  skipped: number;
  results: NodeApplyResult[];
};

export type NodeMetric = {
  node_id: number;
  name: string;
  ip_address: string;
  status: string;
  cpu_percent?: number | null;
  ram_used_bytes?: number | null;
  ram_total_bytes?: number | null;
  ram_percent?: number | null;
  disk_used_bytes?: number | null;
  disk_total_bytes?: number | null;
  disk_percent?: number | null;
  vpn_traffic_upload_bytes: number;
  vpn_traffic_download_bytes: number;
  vpn_traffic_total_bytes: number;
  vpn_traffic_source: "xray_stats";
  traffic_upload_bytes: number;
  traffic_download_bytes: number;
  traffic_total_bytes: number;
  traffic_type: "vpn_xray";
  traffic_source: "xray_inbound" | "node_traffic";
  system_traffic_upload_bytes?: number | null;
  system_traffic_download_bytes?: number | null;
  system_traffic_total_bytes?: number | null;
  system_traffic_source: "host_proc_net_dev" | "unavailable";
  system_traffic_interface?: string | null;
  system_traffic_available: boolean;
  system_traffic_error?: string | null;
  last_checked_at?: string | null;
  errors: string[];
};

export type VpnUser = {
  id: number;
  first_name: string;
  last_name: string;
  username: string;
  status: string;
  access_status: string;
  online_status: string;
  subscription_token: string;
  uuid: string;
  connect_url?: string | null;
  device_limit: number;
  active_devices_count: number;
  devices_label: string;
  department_id?: number | null;
  access_profile_id?: number | null;
  allowed_node_ids: number[];
  primary_node_id?: number | null;
  expires_at?: string | null;
  used_upload_bytes: number;
  used_download_bytes: number;
  used_total_bytes: number;
  last_seen_delta_bytes: number;
  last_traffic_collected_at?: string | null;
  last_online_at?: string | null;
  traffic_limit_bytes?: number | null;
  created_at: string;
  updated_at: string;
  apply_status?: ConfigApplySummary | null;
  apply_error?: string | null;
};

export type VpnUserDevice = {
  id: number;
  vpn_user_id: number;
  name?: string | null;
  display_name?: string | null;
  uuid: string;
  status: string;
  hwid_masked?: string | null;
  platform?: string | null;
  client_name?: string | null;
  device_model?: string | null;
  os_version?: string | null;
  app_version?: string | null;
  user_agent?: string | null;
  last_ip_address?: string | null;
  last_subscribed_at?: string | null;
  upload_bytes: number;
  download_bytes: number;
  total_bytes: number;
  online_status: string;
};

export type BulkImportResult = {
  created: number;
  updated: number;
  skipped: number;
  errors: string[];
  users: VpnUser[];
  apply_status?: ConfigApplySummary | null;
};

export type RestoreSummary = {
  restored: Record<string, number>;
  apply_status?: ConfigApplySummary | null;
};

export type SubscriptionVlessUri = {
  node_id: number;
  name: string;
  location?: string | null;
  ip_address: string;
  uri: string;
};

export type SubscriptionPreview = {
  subscription_url: string;
  vless_uri?: string;
  vless_uris?: SubscriptionVlessUri[];
  xray_json?: string;
  sing_box?: string;
};

export type Department = { id: number; name: string; description?: string; default_access_profile_id?: number };
export type AccessProfile = {
  id: number;
  name: string;
  description?: string;
  routing_mode: string;
  direct_domains: string[];
  blocked_domains: string[];
  traffic_limit_bytes?: number;
  expires_in_days?: number;
  allowed_nodes: number[];
  client_template: string;
  is_active: boolean;
};

export type SniCheckResult = {
  sni: string;
  dns_ok: boolean;
  tcp_443_ok: boolean;
  tls_ok: boolean;
  latency_ms?: number | null;
  certificate_summary?: string | null;
  errors: string[];
};

export type SshCheckResult = {
  ok: boolean;
  logs: Array<Record<string, string | number | boolean | null>>;
};

export type XrayProbeResult = {
  ssh_ok: boolean;
  xray_installed: boolean;
  xray_version?: string | null;
  service_active?: boolean | null;
  service_enabled?: boolean | null;
  config_found: boolean;
  config_valid: boolean;
  reality_inbound_found: boolean;
  partial_import_required: boolean;
  manual_public_key_required: boolean;
  public_key_missing: boolean;
  inbound_tag?: string | null;
  port?: number | null;
  server_names: string[];
  short_ids: string[];
  clients_count: number;
  public_key?: string | null;
  logs: Array<Record<string, unknown>>;
};

export type TrafficUser = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  status: string;
  access_status: string;
  online_status: string;
  upload_bytes: number;
  download_bytes: number;
  total_bytes: number;
  last_seen_delta_bytes: number;
  last_online_at?: string | null;
  last_traffic_collected_at?: string | null;
  traffic_limit_bytes?: number | null;
  devices_label: string;
  active_devices_count: number;
  device_limit: number;
  collected: boolean;
};

export type PublicConnect = {
  display_name: string;
  status: string;
  expires_at?: string | null;
  traffic_limit?: number | null;
  used_traffic: number;
  device_limit: number;
  active_devices_count: number;
  devices_label: string;
  devices: VpnUserDevice[];
  help_links: PublicHelpLinks;
};

export type PublicHelpLinks = {
  android_happ_url?: string | null;
  iphone_happ_url?: string | null;
  windows_fclashx_url?: string | null;
  macos_fclashx_url?: string | null;
};

export type TrafficCollectResult = {
  nodes_considered: Array<Record<string, unknown>>;
  selected_nodes: number[];
  commands: Array<Record<string, unknown>>;
  raw_xray_stats: Array<Record<string, unknown>>;
  parsed_user_stats: Record<string, { upload: number; download: number }>;
  akfa_users: Array<Record<string, unknown>>;
  unmatched_xray_emails: string[];
  akfa_users_without_xray_stats: string[];
  db_committed: boolean;
  errors: string[];
  collected_users: number;
  updated_users: number;
  matched_users: string[];
  message: string;
};

const API_TIMEOUT_MS = 12000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function normalizePublicConnect(value: unknown): PublicConnect {
  if (!isRecord(value)) {
    throw new Error("Страница подключения получила некорректный ответ сервера. Проверьте proxy /public/ в nginx.");
  }
  return {
    display_name: typeof value.display_name === "string" ? value.display_name : "AKFA VPN",
    status: typeof value.status === "string" ? value.status : "unknown",
    expires_at: typeof value.expires_at === "string" || value.expires_at === null ? value.expires_at : null,
    traffic_limit: typeof value.traffic_limit === "number" || value.traffic_limit === null ? value.traffic_limit : null,
    used_traffic: typeof value.used_traffic === "number" ? value.used_traffic : 0,
    device_limit: typeof value.device_limit === "number" ? value.device_limit : 0,
    active_devices_count: typeof value.active_devices_count === "number" ? value.active_devices_count : 0,
    devices_label: typeof value.devices_label === "string" ? value.devices_label : `${typeof value.active_devices_count === "number" ? value.active_devices_count : 0}/${typeof value.device_limit === "number" ? value.device_limit : 0}`,
    devices: Array.isArray(value.devices) ? (value.devices as VpnUserDevice[]) : [],
    help_links: isRecord(value.help_links) ? (value.help_links as PublicHelpLinks) : {}
  };
}

export class ApiMaintenanceError extends Error {
  constructor(message = "Панель временно перезапускается") {
    super(message);
    this.name = "ApiMaintenanceError";
  }
}

export function isApiMaintenanceError(error: unknown): error is ApiMaintenanceError {
  return error instanceof ApiMaintenanceError;
}

function notifyMaintenance() {
  window.dispatchEvent(new CustomEvent("akfa:maintenance"));
}

let csrfToken = localStorage.getItem("akfa_csrf") || "";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const { headers: optionHeaders, signal: optionSignal, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  if (optionSignal) {
    optionSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  let response: Response;
  try {
    response = await fetch(path, {
      ...fetchOptions,
      credentials: "include",
      signal: controller.signal,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        ...(optionHeaders || {})
      }
    });
  } catch (error) {
    notifyMaintenance();
    throw new ApiMaintenanceError("Панель временно перезапускается");
  } finally {
    window.clearTimeout(timeout);
  }
  if ([502, 503, 504].includes(response.status)) {
    notifyMaintenance();
    throw new ApiMaintenanceError("Панель временно перезапускается");
  }
  if (!response.ok) {
    const text = await response.text();
    let message = /^\s*<!doctype html/i.test(text) || /^\s*<html/i.test(text)
      ? "Сервер не ответил вовремя. Проверьте статус установки в журнале."
      : text || `HTTP ${response.status}`;
    try {
      const data = JSON.parse(text) as { detail?: unknown; message?: unknown; diagnostics?: unknown };
      const detail = data.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (detail && typeof detail === "object" && "message" in detail) {
        message = String((detail as { message?: unknown }).message || message);
      } else if (Array.isArray(detail)) {
        message = detail
          .map((item) => {
            if (typeof item === "string") return item;
            if (item && typeof item === "object" && "msg" in item) return String((item as { msg?: unknown }).msg || "");
            return "";
          })
          .filter(Boolean)
          .join("; ") || message;
      } else if (typeof data.message === "string") {
        message = data.message;
      } else if (typeof data.diagnostics === "string") {
        message = data.diagnostics;
      }
    } catch {
      // Keep the original response body if it is not JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text.trim()) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as T;
  }
}

export const api = {
  setCsrf(token: string) {
    csrfToken = token;
    localStorage.setItem("akfa_csrf", token);
  },
  login(email: string, password: string) {
    return request<{ requires_2fa: boolean; setup_required?: boolean; login_token?: string; csrf_token?: string; admin?: { email: string; role: string; totp_enabled: boolean } | null }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
  },
  verify2fa(code: string) {
    return request<{ csrf_token?: string }>("/auth/2fa", { method: "POST", body: JSON.stringify({ code }) });
  },
  verify2faToken(loginToken: string, code: string) {
    return request<{ csrf_token?: string }>("/auth/2fa/verify", { method: "POST", body: JSON.stringify({ login_token: loginToken, code }) });
  },
  me() {
    return request<{ email: string; role: string; totp_enabled: boolean }>("/auth/me");
  },
  startTotpSetup(loginToken?: string) {
    return request<{ secret: string; otpauth_url: string }>("/auth/2fa/setup/start", { method: "POST", body: JSON.stringify({ login_token: loginToken || null }) });
  },
  confirmTotpSetup(loginToken: string | null, code: string) {
    return request<{ csrf_token?: string; admin?: { email: string; role: string; totp_enabled: boolean } | null }>("/auth/2fa/setup/confirm", { method: "POST", body: JSON.stringify({ login_token: loginToken, code }) });
  },
  disableTotp(password: string) {
    return request<{ email: string; role: string; totp_enabled: boolean }>("/auth/2fa/disable", { method: "POST", body: JSON.stringify({ password }) });
  },
  dashboard() {
    return request<DashboardStats>("/admin/dashboard");
  },
  publicHelpLinks() {
    return request<PublicHelpLinks>("/admin/settings/public-help-links");
  },
  savePublicHelpLinks(payload: PublicHelpLinks) {
    return request<PublicHelpLinks>("/admin/settings/public-help-links", { method: "PUT", body: JSON.stringify(payload) });
  },
  nodes() {
    return request<NodeRead[]>("/admin/nodes");
  },
  nodeMetrics(period = "all") {
    return request<NodeMetric[]>(`/admin/nodes/metrics?period=${encodeURIComponent(period)}`);
  },
  createNode(payload: Record<string, unknown>) {
    return request<NodeRead>("/admin/nodes", { method: "POST", body: JSON.stringify(payload) });
  },
  updateNode(id: number, payload: Record<string, unknown>) {
    return request<NodeRead>(`/admin/nodes/${id}`, { method: "PUT", body: JSON.stringify(payload) });
  },
  nodeAction(id: number, action: "check" | "dry-run" | "install" | "verify") {
    return request<NodeRead>(`/admin/nodes/${id}/${action}`, { method: "POST" });
  },
  startNodeInstall(id: number) {
    return request<NodeActionJobAccepted>(`/admin/nodes/${id}/install`, { method: "POST" });
  },
  nodeActionJob(jobId: string) {
    return request<NodeActionJob>(`/admin/node-actions/${jobId}`);
  },
  applyConfig(id: number) {
    return request<NodeRead>(`/admin/nodes/${id}/apply-config`, { method: "POST" });
  },
  nodeConfig(id: number) {
    return request<Record<string, unknown>>(`/admin/nodes/${id}/config-preview`);
  },
  checkSsh(payload: Record<string, unknown>) {
    return request<SshCheckResult>("/admin/tools/check-ssh", { method: "POST", body: JSON.stringify(payload) });
  },
  probeNode(payload: Record<string, unknown>) {
    return request<XrayProbeResult>("/admin/nodes/probe", { method: "POST", body: JSON.stringify(payload) });
  },
  probeExistingNode(id: number) {
    return request<XrayProbeResult>(`/admin/nodes/${id}/probe`, { method: "POST" });
  },
  importXray(id: number, payload: Record<string, unknown>) {
    return request<NodeRead>(`/admin/nodes/${id}/import-xray`, { method: "POST", body: JSON.stringify(payload) });
  },
  checkSni(sni: string) {
    return request<SniCheckResult>("/admin/tools/check-sni", { method: "POST", body: JSON.stringify({ sni }) });
  },
  nodeLifecycle(id: number, action: "disable" | "enable" | "maintenance") {
    return request<NodeBulkActionResult>(`/admin/nodes/${id}/${action}`, { method: "POST" });
  },
  addNodeToProfile(id: number, profile_id: number) {
    return request<NodeBulkActionResult>(`/admin/nodes/${id}/profiles/add`, { method: "POST", body: JSON.stringify({ profile_id }) });
  },
  removeNodeFromProfile(id: number, profile_id: number) {
    return request<NodeBulkActionResult>(`/admin/nodes/${id}/profiles/remove`, { method: "POST", body: JSON.stringify({ profile_id }) });
  },
  addNodeToUsers(id: number, payload: Record<string, unknown>) {
    return request<NodeBulkActionResult>(`/admin/nodes/${id}/users/add`, { method: "POST", body: JSON.stringify(payload) });
  },
  removeNodeFromUsers(id: number, payload: Record<string, unknown>) {
    return request<NodeBulkActionResult>(`/admin/nodes/${id}/users/remove`, { method: "POST", body: JSON.stringify(payload) });
  },
  replaceNode(id: number, new_node_id: number) {
    return request<NodeBulkActionResult>(`/admin/nodes/${id}/replace`, { method: "POST", body: JSON.stringify({ new_node_id }) });
  },
  deleteNode(id: number, force = false) {
    return request<NodeBulkActionResult>(`/admin/nodes/${id}${force ? "?force=true" : ""}`, { method: "DELETE" });
  },
  departments() {
    return request<Department[]>("/admin/departments");
  },
  createDepartment(payload: Record<string, unknown>) {
    return request<Department>("/admin/departments", { method: "POST", body: JSON.stringify(payload) });
  },
  updateDepartment(id: number, payload: Record<string, unknown>) {
    return request<Department>(`/admin/departments/${id}`, { method: "PUT", body: JSON.stringify(payload) });
  },
  profiles() {
    return request<AccessProfile[]>("/admin/access-profiles");
  },
  createProfile(payload: Record<string, unknown>) {
    return request<AccessProfile>("/admin/access-profiles", { method: "POST", body: JSON.stringify(payload) });
  },
  updateProfile(id: number, payload: Record<string, unknown>) {
    return request<AccessProfile>(`/admin/access-profiles/${id}`, { method: "PUT", body: JSON.stringify(payload) });
  },
  deleteProfile(id: number) {
    return request<{ message: string }>(`/admin/access-profiles/${id}`, { method: "DELETE" });
  },
  seedDefaultProfile() {
    return request<AccessProfile[]>("/admin/seed/default-profile", { method: "POST" });
  },
  users() {
    return request<VpnUser[]>("/admin/users");
  },
  async publicConnect(token: string) {
    const response = await request<unknown>(`/public/connect/${token}`);
    return normalizePublicConnect(response);
  },
  createUser(payload: Record<string, unknown>, idempotencyKey?: string) {
    return request<VpnUser>("/admin/users", {
      method: "POST",
      headers: idempotencyKey ? { "X-Idempotency-Key": idempotencyKey } : undefined,
      body: JSON.stringify(payload)
    });
  },
  updateUser(id: number, payload: Record<string, unknown>) {
    return request<VpnUser>(`/admin/users/${id}`, { method: "PUT", body: JSON.stringify(payload) });
  },
  userDevices(id: number) {
    return request<VpnUserDevice[]>(`/admin/users/${id}/devices`);
  },
  revokeDevice(userId: number, deviceId: number) {
    return request<{ message: string }>(`/admin/users/${userId}/devices/${deviceId}/revoke`, { method: "POST" });
  },
  resetDevices(userId: number) {
    return request<VpnUserDevice[]>(`/admin/users/${userId}/devices/reset`, { method: "POST" });
  },
  publicRemoveDevice(token: string, deviceId: number) {
    return request<{ message: string }>(`/public/connect/${token}/devices/${deviceId}`, { method: "DELETE" });
  },
  deleteUser(id: number) {
    return request<{ message: string; diagnostics?: string; apply_status?: ConfigApplySummary | null }>(`/admin/users/${id}`, { method: "DELETE" });
  },
  userAction(id: number, action: "enable" | "disable" | "regenerate-uuid" | "regenerate-subscription" | "reset-traffic") {
    return request<VpnUser>(`/admin/users/${id}/${action}`, { method: "POST" });
  },
  importUsers(file: File) {
    const body = new FormData();
    body.append("file", file);
    return request<BulkImportResult>("/admin/users/import", { method: "POST", body });
  },
  async exportBackup() {
    let response: Response;
    try {
      response = await fetch("/admin/backup/export", {
        credentials: "include",
        headers: {
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {})
        }
      });
    } catch {
      notifyMaintenance();
      throw new ApiMaintenanceError("Панель временно перезапускается");
    }
    if ([502, 503, 504].includes(response.status)) {
      notifyMaintenance();
      throw new ApiMaintenanceError("Панель временно перезапускается");
    }
    if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`);
    const disposition = response.headers.get("Content-Disposition") || "";
    const filename = disposition.match(/filename="([^"]+)"/)?.[1] || "akfa-backup.tar.gz";
    return { blob: await response.blob(), filename };
  },
  importBackup(file: File) {
    const body = new FormData();
    body.append("file", file);
    return request<RestoreSummary>("/admin/backup/import", { method: "POST", body });
  },
  subscriptionPreview(id: number) {
    return request<SubscriptionPreview>(`/admin/users/${id}/subscription-preview`);
  },
  collectTraffic(nodeId: number) {
    return request<TrafficCollectResult>(`/admin/traffic/collect/${nodeId}`, { method: "POST" });
  },
  collectTrafficNow() {
    return request<TrafficCollectResult>("/admin/traffic/collect-now", { method: "POST" });
  },
  collectTrafficBackground() {
    return request<TrafficCollectResult>("/admin/traffic/collect-background", { method: "POST" });
  },
  debugCollectTraffic() {
    return request<TrafficCollectResult>("/admin/traffic/debug-collect", { method: "POST" });
  },
  trafficOverview() {
    return request<TrafficUser[]>("/admin/traffic/overview");
  },
  trafficSnapshots() {
    return request<Array<Record<string, unknown>>>("/admin/traffic/snapshots");
  },
  auditLog() {
    return request<Array<Record<string, unknown>>>("/admin/audit-log");
  }
};
