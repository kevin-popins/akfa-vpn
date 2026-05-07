import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Download,
  Eye,
  EyeOff,
  FileJson,
  Link2,
  Play,
  Plus,
  RefreshCcw,
  RotateCcw,
  Save,
  ShieldCheck,
  Trash2,
  Upload,
  UserPlus,
  XCircle
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { QRCodeCanvas } from "qrcode.react";

import { ConfirmDialog } from "./components/ConfirmDialog";
import { Layout, type PageKey } from "./components/Layout";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardHeader } from "./components/ui/card";
import { Field, Input, Select, Textarea } from "./components/ui/input";
import { StatusBadge, Table } from "./components/ui/table";
import { api, isApiMaintenanceError, type AccessProfile, type ConfigApplySummary, type DashboardStats, type Department, type NodeMetric, type NodeRead, type PublicConnect, type PublicHelpLinks, type SniCheckResult, type SshCheckResult, type SubscriptionVlessUri, type TrafficUser, type VpnUser, type VpnUserDevice, type XrayProbeResult } from "./lib/api";
import { formatBytes } from "./lib/utils";

type SessionState = "checking" | "login" | "totp" | "setup" | "ready";
type NodeAction = "check" | "dry-run" | "install" | "verify" | "apply-config";
type PreviewBlock = { label: string; value: string; mono?: boolean };
type PreviewState = { title: string; empty: string; blocks: PreviewBlock[] };
type ConfirmState = { title: string; text: string; onConfirm: () => void; confirmLabel?: string } | null;
type OperationState = { title: string; message: string; tone: "pending" | "success" | "warning" | "error" } | null;
type TrafficSortKey = "user" | "online" | "upload" | "download" | "total" | "lastOnline";
type SortDirection = "asc" | "desc";

const DEFAULT_REALITY_SNI = "www.googletagmanager.com";
const SNI_PRESETS = [
  DEFAULT_REALITY_SNI,
  "yandex.ru",
  "ya.ru",
  "yandex.net",
  "vk.com",
  "vk.ru",
  "mail.ru",
  "ok.ru",
  "habr.com",
  "web.max.ru",
  "www.microsoft.com",
  "www.cloudflare.com"
];
const SNI_HELP =
  "SNI / Reality target используется для маскировки TLS-соединения в REALITY. Работоспособность зависит от VPS, провайдера, домена и клиента. Перед установкой рекомендуется проверить SNI.";

const emptyNode = {
  name: "",
  ip_address: "",
  ssh_port: 22,
  ssh_username: "root",
  ssh_auth_type: "password",
  ssh_password: "",
  private_key: "",
  location: "",
  public_host: "",
  vless_port: 443,
  sni: DEFAULT_REALITY_SNI,
  fingerprint: "chrome"
};

const defaultProfileForm = {
  name: "Российские сервисы напрямую",
  description: "Российские домены и популярные российские сервисы идут напрямую, остальной трафик идет через VPN.",
  routing_mode: "ru_direct",
  traffic_limit_gb: "",
  expires_in_days: "",
  direct_domains: "gosuslugi.ru\nmos.ru\nvk.com\nyandex.ru",
  blocked_domains: "",
  client_template: "vless_uri",
  is_active: true
};

const defaultUserForm = {
  first_name: "",
  last_name: "",
  username: "",
  department_id: "",
  access_profile_id: "",
  device_limit: "5",
  traffic_limit_gb: "",
  expires_at: "",
  status: "active",
  allowed_node_ids: [] as number[],
  primary_node_id: ""
};

const defaultPublicHelpLinks: PublicHelpLinks = {
  android_happ_url: "",
  iphone_happ_url: "",
  windows_fclashx_url: "",
  macos_fclashx_url: ""
};

function App() {
  const [session, setSession] = useState<SessionState>("checking");
  const [maintenance, setMaintenance] = useState(false);
  const [page, setPage] = useState<PageKey>("dashboard");
  const [notice, setNotice] = useState("");
  const publicToken = publicConnectToken();

  useEffect(() => {
    if (publicToken) return;
    const onMaintenance = () => setMaintenance(true);
    window.addEventListener("akfa:maintenance", onMaintenance);
    api
      .me()
      .then(() => {
        setMaintenance(false);
        setSession("ready");
      })
      .catch((error) => {
        if (isApiMaintenanceError(error)) {
          setMaintenance(true);
          return;
        }
        setSession("login");
      });
    return () => window.removeEventListener("akfa:maintenance", onMaintenance);
  }, [publicToken]);

  if (publicToken) return <PublicConnectPage userToken={publicToken} />;
  if (maintenance) return <MaintenanceScreen />;
  if (session === "checking") return <Splash />;
  if (session === "login" || session === "totp" || session === "setup") {
    return (
      <LoginPage
        mode={session}
        onTotp={() => setSession("totp")}
        onSetup={() => setSession("setup")}
        onReady={() => setSession("ready")}
        onNotice={setNotice}
        notice={notice}
      />
    );
  }

  return (
    <Layout page={page} onPage={setPage}>
      <AdminPages page={page} setPage={setPage} />
    </Layout>
  );
}

function MaintenanceScreen() {
  return (
    <div className="grid min-h-screen place-items-center bg-akfa-soft px-4">
      <Card className="w-full max-w-lg text-center">
        <CardHeader>
          <img className="mx-auto h-10 w-auto object-contain" src="/assets/akfa-logo.svg" alt="AKFA VPN" />
        </CardHeader>
        <CardContent className="grid gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Панель временно перезапускается</h1>
            <p className="mt-2 text-sm leading-6 text-akfa-muted">
              Выполняется автоматическое восстановление сервиса. Обновите страницу через 1–2 минуты.
            </p>
          </div>
          <Button onClick={() => window.location.reload()}>
            <RefreshCcw size={16} />
            Обновить страницу
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Splash() {
  return (
    <div className="grid min-h-screen place-items-center">
      <img className="h-10 w-auto object-contain" src="/assets/akfa-logo.svg" alt="AKFA VPN" />
    </div>
  );
}

function PublicConnectPage({ userToken }: { userToken: string }) {
  const [data, setData] = useState<PublicConnect | null>(null);
  const [selected, setSelected] = useState("android-happ");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [pollMs, setPollMs] = useState(7000);
  const [removingIds, setRemovingIds] = useState<Set<number>>(new Set());
  const refreshingRef = useRef(false);
  const mutatingRef = useRef(false);
  const refreshSeqRef = useRef(0);

  const refresh = useCallback(async (silent = false, force = false) => {
    if (refreshingRef.current && !force) return;
    if (silent && mutatingRef.current) return;
    refreshingRef.current = true;
    const seq = ++refreshSeqRef.current;
    try {
      const next = await api.publicConnect(userToken);
      if (seq === refreshSeqRef.current) setData(next);
      setPollMs(7000);
      if (!silent) setNotice("");
    } catch (error) {
      if (seq === refreshSeqRef.current) setData(null);
      setPollMs(15000);
      if (!silent) setNotice(error instanceof Error ? error.message : "Подключение недоступно");
    } finally {
      refreshingRef.current = false;
      setLoading(false);
    }
  }, [userToken]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      void refresh(true);
    }, pollMs);
    return () => window.clearInterval(timer);
  }, [pollMs, refresh]);

  const options = connectOptions(userToken);
  const current = options.find((item) => item.id === selected) || options[0];
  const limitReached = data ? data.active_devices_count >= data.device_limit : false;
  const currentHelpUrl = data?.help_links?.[current.helpKey] || "";

  async function copyLink(value: string) {
    await navigator.clipboard.writeText(value);
    setNotice("Ссылка скопирована");
    void refresh(true);
  }

  async function removeDevice(device: VpnUserDevice) {
    const name = device.display_name || `DEV-${device.id}`;
    if (!window.confirm(`Отключить устройство "${name}"?`)) return;
    mutatingRef.current = true;
    refreshSeqRef.current += 1;
    setRemovingIds((current) => new Set(current).add(device.id));
    setData((current) => current ? {
      ...current,
      devices: current.devices.filter((item) => item.id !== device.id),
      active_devices_count: Math.max(0, current.active_devices_count - 1),
      devices_label: `${Math.max(0, current.active_devices_count - 1)}/${current.device_limit}`,
    } : current);
    try {
      await api.publicRemoveDevice(userToken, device.id);
      setNotice("Устройство отключено");
      await refresh(false, true);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Устройство не отключено");
      await refresh(true, true);
    } finally {
      setRemovingIds((current) => {
        const next = new Set(current);
        next.delete(device.id);
        return next;
      });
      mutatingRef.current = false;
    }
  }

  return (
    <div className="min-h-screen bg-white px-4 py-8 text-akfa-text">
      <main className="mx-auto grid max-w-5xl gap-6">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-akfa-line pb-4">
          <div>
            <img className="mb-2 h-8 w-auto object-contain" src="/assets/akfa-logo.svg" alt="AKFA VPN" />
            <h1 className="text-2xl font-semibold">Выберите устройство</h1>
            {data ? <p className="mt-1 text-sm text-akfa-muted">{data.display_name}</p> : null}
          </div>
          {data ? <div className="rounded-md border border-akfa-line px-3 py-2 text-sm">Устройства: <b>{data.devices_label}</b></div> : null}
        </header>
        {notice ? <Message tone={notice.includes("скопирована") ? "success" : "error"} text={notice} /> : null}
        {loading ? <Message tone="success" text="Загрузка подключения..." /> : null}
        {limitReached ? <Message tone="warning" text="Лимит устройств исчерпан. Новое устройство не сможет получить конфиг." /> : null}
        {currentHelpUrl ? (
          <section className="rounded-md border border-akfa-red/30 bg-red-50 px-4 py-3">
            <div className="font-semibold">Не знаете как подключить?</div>
            <a
              className="mt-1 inline-flex font-semibold text-akfa-red underline-offset-4 hover:underline"
              href={currentHelpUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              Инструкция для {current.title} →
            </a>
          </section>
        ) : null}
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {options.map((option) => (
            <button
              key={option.id}
              className={`rounded-md border p-4 text-left transition ${selected === option.id ? "border-akfa-red bg-red-50" : "border-akfa-line hover:border-akfa-red/50"}`}
              onClick={() => {
                setSelected(option.id);
                void refresh(true);
              }}
            >
              <div className="font-semibold">{option.title}</div>
              <div className="mt-1 text-sm text-akfa-muted">{option.client}</div>
            </button>
          ))}
        </section>
        <Card>
          <CardHeader>
            <h2 className="font-semibold">{current.title}: {current.client}</h2>
            <p className="mt-1 text-sm text-akfa-muted">Откройте приложение и добавьте подписку по ссылке или QR-коду. Если подключение не добавляется, обратитесь к администратору.</p>
          </CardHeader>
          <CardContent className="grid gap-4 lg:grid-cols-[1fr_220px]">
            <div className="grid gap-3">
              <Field label="Ссылка подписки">
                <div className="flex gap-2">
                  <Input readOnly value={absoluteUrl(current.path)} />
                  <Button variant="secondary" onClick={() => copyLink(absoluteUrl(current.path))}><Copy size={16} />Копировать</Button>
                </div>
              </Field>
              <ol className="list-decimal space-y-2 pl-5 text-sm text-akfa-muted">
                {current.steps.map((step) => <li key={step}>{step}</li>)}
              </ol>
            </div>
            <div className="grid place-items-center rounded-md border border-akfa-line p-4">
              <QRCodeCanvas value={absoluteUrl(current.path)} size={180} />
            </div>
          </CardContent>
        </Card>
        {data?.devices?.length ? (
          <section className="grid gap-2">
            <h2 className="font-semibold">Устройства</h2>
            <div className="divide-y divide-akfa-line rounded-md border border-akfa-line">
              {data.devices.map((device) => (
                <div key={device.id} className="flex items-center justify-between gap-3 px-3 py-3 text-sm">
                  <span className="min-w-0 truncate font-medium" title={device.display_name || `DEV-${device.id}`}>
                    {device.display_name || `DEV-${device.id}`}
                  </span>
                  <Button
                    variant="secondary"
                    className="h-8 w-8 shrink-0 p-0"
                    onClick={() => removeDevice(device)}
                    disabled={removingIds.has(device.id)}
                    title="Отключить устройство"
                  >
                    <XCircle size={16} />
                  </Button>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </main>
    </div>
  );
}

function LoginPage({
  mode,
  onTotp,
  onSetup,
  onReady,
  onNotice,
  notice
}: {
  mode: SessionState;
  onTotp: () => void;
  onSetup: () => void;
  onReady: () => void;
  onNotice: (value: string) => void;
  notice: string;
}) {
  const [email, setEmail] = useState("ADMIN_EMAIL");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [loginToken, setLoginToken] = useState("");
  const [setup, setSetup] = useState<{ secret: string; otpauth_url: string } | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    try {
      if (mode === "setup") {
        const response = await api.confirmTotpSetup(loginToken, code);
        if (response.csrf_token) api.setCsrf(response.csrf_token);
        onReady();
        return;
      }
      if (mode === "totp") {
        const response = loginToken ? await api.verify2faToken(loginToken, code) : await api.verify2fa(code);
        if (response.csrf_token) api.setCsrf(response.csrf_token);
        onReady();
        return;
      }
      const response = await api.login(email, password);
      if (response.login_token) setLoginToken(response.login_token);
      if (response.requires_2fa) onTotp();
      if (response.setup_required && response.login_token) {
        const setupResponse = await api.startTotpSetup(response.login_token);
        setSetup(setupResponse);
        onSetup();
      }
      if (response.csrf_token) {
        api.setCsrf(response.csrf_token);
        onReady();
      }
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Не удалось войти");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="flex items-center gap-3">
            <img className="h-8 w-auto shrink-0 object-contain" src="/assets/akfa-logo.svg" alt="AKFA VPN" />
            <div>
              <div className="text-sm text-akfa-muted">Вход администратора</div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4">
          {notice ? <Message tone="error" text={notice} /> : null}
          {mode === "setup" ? (
            <>
              <p className="text-sm text-akfa-muted">Отсканируйте QR-код в Google Authenticator или другом приложении для одноразовых кодов.</p>
              <p className="text-sm text-akfa-muted">2FA включится только после подтверждения кода.</p>
              {setup ? <div className="grid place-items-center"><QRCodeCanvas value={setup.otpauth_url} size={180} /></div> : null}
              {setup ? <Field label="Secret"><Input readOnly value={setup.secret} /></Field> : null}
              <Field label="Введите 6-значный код">
                <Input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" autoFocus />
              </Field>
            </>
          ) : mode === "totp" ? (
            <Field label="Код 2FA" hint="Введите одноразовый код из приложения аутентификации.">
              <Input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" autoFocus />
            </Field>
          ) : (
            <>
              <Field label="Email администратора">
                <Input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
              </Field>
              <Field label="Пароль">
                <Input value={password} onChange={(event) => setPassword(event.target.value)} type="password" />
              </Field>
            </>
          )}
          <Button onClick={submit} disabled={loading}>
            <CheckCircle2 size={16} />
            {loading ? "Проверка..." : mode === "setup" ? "Подтвердить" : "Войти"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function AdminPages({
  page,
  setPage
}: {
  page: PageKey;
  setPage: (page: PageKey) => void;
}) {
  const [notice, setNotice] = useState("");
  const [dashboard, setDashboard] = useState<DashboardStats | null>(null);
  const [nodes, setNodes] = useState<NodeRead[]>([]);
  const [nodeMetrics, setNodeMetrics] = useState<NodeMetric[]>([]);
  const [dashboardTrafficPeriod, setDashboardTrafficPeriod] = useState("all");
  const [users, setUsers] = useState<VpnUser[]>([]);
  const [trafficRows, setTrafficRows] = useState<TrafficUser[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [profiles, setProfiles] = useState<AccessProfile[]>([]);
  const [auditRows, setAuditRows] = useState<Array<Record<string, unknown>>>([]);
  const [selectedUser, setSelectedUser] = useState<VpnUser | null>(null);
  const [selectedNode, setSelectedNode] = useState<NodeRead | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<AccessProfile | null>(null);
  const [operation, setOperation] = useState<OperationState>(null);
  const [nodeActionPending, setNodeActionPending] = useState<{ nodeId: number; action: NodeAction } | null>(null);
  const [deletingUserIds, setDeletingUserIds] = useState<Set<number>>(new Set());
  const deletingUserIdsRef = useRef<Set<number>>(new Set());
  const nodeActionInFlightRef = useRef(false);
  const [preview, setPreview] = useState<PreviewState>({
    title: "Предпросмотр подписки",
    empty: "Подписка появится после создания активного пользователя и сервера.",
    blocks: []
  });
  const [confirm, setConfirm] = useState<ConfirmState>(null);
  const pollingRef = useRef(false);

  const onNotice = useCallback((value: string) => {
    setNotice(value);
    window.setTimeout(() => setNotice(""), 4500);
  }, []);

  const noticeWithApplyStatus = useCallback((base: string, applyStatus?: ConfigApplySummary | null) => {
    onNotice(formatApplyStatusMessage(base, applyStatus));
  }, [onNotice]);

  useEffect(() => {
    setNotice("");
  }, [page]);

  const refresh = useCallback(async () => {
    try {
      const [stats, nodeList, metricList, userList, departmentList, profileList, auditList, trafficList] = await Promise.all([
        api.dashboard(),
        api.nodes(),
        api.nodeMetrics(dashboardTrafficPeriod),
        api.users(),
        api.departments(),
        api.profiles(),
        api.auditLog(),
        api.trafficOverview()
      ]);
      setDashboard(stats);
      setNodes(nodeList);
      setNodeMetrics(metricList);
      setUsers(visibleUsers(userList));
      setTrafficRows(trafficList);
      setDepartments(departmentList);
      setProfiles(profileList);
      setAuditRows(auditList);
      setSelectedNode((current) => nodeList.find((node) => node.id === current?.id) || nodeList[0] || null);
      setSelectedUser((current) => visibleUsers(userList).find((user) => user.id === current?.id) || visibleUsers(userList)[0] || null);
      setSelectedProfile((current) => profileList.find((profile) => profile.id === current?.id) || profileList[0] || null);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "API недоступен");
    }
  }, [onNotice, dashboardTrafficPeriod]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const refreshVisibleData = useCallback(async (targetPage: PageKey) => {
    if (targetPage === "dashboard") {
      const [stats, metricList, userList] = await Promise.all([api.dashboard(), api.nodeMetrics(dashboardTrafficPeriod), api.users()]);
      const visible = visibleUsers(userList);
      setDashboard(stats);
      setNodeMetrics(metricList);
      setUsers(visible);
      setSelectedUser((current) => visible.find((user) => user.id === current?.id) || current);
      return;
    }
    if (targetPage === "users" || targetPage === "user-detail") {
      const visible = visibleUsers(await api.users());
      setUsers(visible);
      setSelectedUser((current) => visible.find((user) => user.id === current?.id) || current);
      return;
    }
    if (targetPage === "traffic") {
      setTrafficRows(await api.trafficOverview());
      return;
    }
    if (targetPage === "servers" || targetPage === "server-detail" || targetPage === "install-xray") {
      const [nodeList, metricList] = await Promise.all([api.nodes(), api.nodeMetrics(dashboardTrafficPeriod)]);
      setNodes(nodeList);
      setNodeMetrics(metricList);
      setSelectedNode((current) => nodeList.find((node) => node.id === current?.id) || current);
    }
  }, [dashboardTrafficPeriod]);

  useEffect(() => {
    let stopped = false;
    const run = async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;
      try {
        await api.collectTrafficBackground();
        if (!stopped) await refreshVisibleData(page);
      } catch {
        // Background polling stays quiet; manual refresh buttons still surface errors.
      } finally {
        pollingRef.current = false;
      }
    };
    const timer = window.setInterval(() => {
      void run();
    }, 30000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [page, refreshVisibleData]);

  function upsertNode(updated: NodeRead) {
    setSelectedNode(updated);
    setNodes((items) => items.map((item) => (item.id === updated.id ? updated : item)));
  }

  function upsertUser(updated: VpnUser) {
    if (updated.status === "deleted") {
      setSelectedUser((current) => (current?.id === updated.id ? null : current));
      setUsers((items) => items.filter((item) => item.id !== updated.id));
      return;
    }
    setSelectedUser(updated);
    setUsers((items) => items.map((item) => (item.id === updated.id ? updated : item)));
  }

  async function runNodeAction(action: NodeAction, nodeOverride?: NodeRead) {
    const node = nodeOverride || selectedNode;
    if (!node) return;
    if (action === "install" || action === "apply-config") {
      setConfirm({
        title: action === "install" ? "Запустить установку Xray?" : "Применить конфиг Xray?",
        text:
          action === "install"
            ? `AKFA установит Xray на выбранный VPS и настроит VLESS Reality с SNI \`${node.sni}\`. Старый конфиг Xray будет сохранен в резервную копию.`
            : `AKFA применит новый Xray config на сервере ${node.name}, создаст резервную копию и перезапустит сервис.`,
        onConfirm: () => {
          setConfirm(null);
          void runNodeActionUnsafe(action, node);
        }
      });
      return;
    }
    await runNodeActionUnsafe(action, node);
  }

  async function runNodeActionUnsafe(action: NodeAction, node: NodeRead) {
    if (nodeActionInFlightRef.current) {
      setOperation({ title: "Действие с Xray", message: "Операция уже выполняется.", tone: "warning" });
      return;
    }
    nodeActionInFlightRef.current = true;
    setNodeActionPending({ nodeId: node.id, action });
    const timers: number[] = [];
    const title = nodeActionTitle(action);
    try {
      setOperation({ title, message: nodeActionInitialMessage(action), tone: "pending" });
      nodeActionStages(action).forEach(([delay, message]) => {
        timers.push(window.setTimeout(() => setOperation({ title, message, tone: "pending" }), delay));
      });
      const updated =
        action === "install"
          ? await runInstallJob(node.id, title, setOperation)
          : action === "apply-config"
            ? await api.applyConfig(node.id)
            : await api.nodeAction(node.id, action);
      upsertNode(updated);
      const failedInstall = action === "install" && (!updated.xray_installed || updated.status !== "online");
      if (failedInstall) {
        const reason = nodeLogFailureReason(updated.install_log) || "установка не завершилась";
        setOperation({ title, message: `Установка Xray не завершена: ${reason}`, tone: "error" });
      } else {
        setOperation({ title, message: nodeActionSuccessMessage(action, updated.apply_status), tone: applyStatusHasProblems(updated.apply_status) ? "warning" : "success" });
      }
      await refresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Действие не выполнено";
      setOperation({ title, message: nodeActionErrorMessage(action, message), tone: "error" });
      await refreshVisibleData("install-xray").catch(() => undefined);
    } finally {
      timers.forEach((timer) => window.clearTimeout(timer));
      setNodeActionPending(null);
      nodeActionInFlightRef.current = false;
    }
  }

  async function loadConfigPreview(nodeId?: number) {
    const id = nodeId || selectedNode?.id;
    if (!id) {
      setPreview({
        title: "Предпросмотр конфигурации",
        empty: "Конфигурация появится после добавления сервера.",
        blocks: []
      });
      setPage("config-preview");
      return;
    }
    try {
      const config = await api.nodeConfig(id);
      setPreview({
        title: "Предпросмотр конфигурации сервера",
        empty: "Конфигурация пока недоступна.",
        blocks: [{ label: "JSON сервера Xray", value: JSON.stringify(config, null, 2), mono: true }]
      });
      setPage("config-preview");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Предпросмотр недоступен");
    }
  }

  async function seedDefaultProfile() {
    try {
      const seededProfiles = await api.seedDefaultProfile();
      setProfiles((items) => {
        const byId = new Map(items.map((item) => [item.id, item]));
        seededProfiles.forEach((profile) => byId.set(profile.id, profile));
        return Array.from(byId.values());
      });
      setSelectedProfile(seededProfiles[0] || null);
      onNotice("Базовые профили доступа обновлены");
      await refresh();
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Профили не созданы");
    }
  }

  async function deleteProfile(profile: AccessProfile) {
    setConfirm({
      title: "Удалить профиль доступа?",
      text: `${profile.name}. Если профиль используется, AKFA не позволит удалить его.`,
      onConfirm: async () => {
        setConfirm(null);
        try {
          await api.deleteProfile(profile.id);
          onNotice("Профиль удален");
          await refresh();
        } catch (error) {
          onNotice(error instanceof Error ? error.message : "Профиль не удален");
        }
      }
    });
  }

  async function deleteUser(user: VpnUser) {
    if (deletingUserIdsRef.current.has(user.id)) return;
    setConfirm({
      title: "Удалить пользователя VPN?",
      text: `Удалить пользователя ${user.last_name} ${user.first_name}? Пользователь будет отключён, его устройства будут убраны из конфигурации.`,
      confirmLabel: "Удалить",
      onConfirm: async () => {
        if (deletingUserIdsRef.current.has(user.id)) return;
        setConfirm(null);
        deletingUserIdsRef.current.add(user.id);
        setDeletingUserIds((current) => new Set(current).add(user.id));
        setOperation({ title: "Удаление пользователя", message: "Удаляем пользователя...", tone: "pending" });
        const applyTimer = window.setTimeout(() => setOperation({ title: "Удаление пользователя", message: "Применяем конфигурацию...", tone: "pending" }), 250);
        try {
          const result = await api.deleteUser(user.id);
          window.clearTimeout(applyTimer);
          setUsers((items) => items.filter((item) => item.id !== user.id));
          setSelectedUser((current) => (current?.id === user.id ? null : current));
          const message = result.diagnostics || formatApplyStatusMessage("Пользователь удалён", result.apply_status, "Пользователь удалён, но конфигурация не применена");
          const tone = applyStatusHasProblems(result.apply_status) ? "warning" : "success";
          try {
            await refresh();
            setPage("users");
            setOperation({ title: "Удаление пользователя", message, tone });
          } catch (refreshError) {
            const refreshMessage = refreshError instanceof Error ? refreshError.message : "список не обновился";
            setPage("users");
            setOperation({ title: "Пользователь удалён", message: `${message}. Операция выполнена, но список не обновился: ${refreshMessage}`, tone: "warning" });
          }
        } catch (error) {
          window.clearTimeout(applyTimer);
          setOperation({ title: "Ошибка удаления", message: `Ошибка: ${error instanceof Error ? error.message : "Пользователь не удален"}`, tone: "error" });
        } finally {
          deletingUserIdsRef.current.delete(user.id);
          setDeletingUserIds((current) => {
            const next = new Set(current);
            next.delete(user.id);
            return next;
          });
        }
      }
    });
  }

  async function deleteServer(node: NodeRead) {
    setConfirm({
      title: "Удалить сервер из AKFA?",
      text: `${node.name}. Обычное удаление доступно только если сервер не используется пользователями и профилями.`,
      onConfirm: async () => {
        setConfirm(null);
        try {
          setOperation({ title: "Удаление сервера", message: "Проверяем связи сервера...", tone: "pending" });
          const result = await api.deleteNode(node.id);
          setNodes(nodes.filter((item) => item.id !== node.id));
          setSelectedNode((current) => (current?.id === node.id ? null : current));
          setOperation({ title: "Удаление сервера", message: result.message || "Сервер удален из AKFA", tone: applyStatusHasProblems(result.apply_status) ? "warning" : "success" });
          await refresh().catch((error) => {
            const message = error instanceof Error ? error.message : "список не обновился";
            setOperation({ title: "Сервер удалён", message: `${result.message}. Обновите список вручную: ${message}`, tone: "warning" });
          });
          setPage("servers");
        } catch (error) {
          setOperation({ title: "Сервер не удалён", message: error instanceof Error ? error.message : "Сервер не удален", tone: "error" });
        }
      }
    });
  }

  async function runNodeManagement(title: string, startMessage: string, action: () => Promise<{ message: string; apply_status?: ConfigApplySummary | null; apply_error?: string | null }>) {
    try {
      setOperation({ title, message: startMessage, tone: "pending" });
      const applyTimer = window.setTimeout(() => setOperation({ title, message: "Применяем конфигурации...", tone: "pending" }), 250);
      const result = await action();
      window.clearTimeout(applyTimer);
      const message = result.apply_error ? `${result.message}: ${result.apply_error}` : result.message;
      setOperation({ title, message, tone: result.apply_error || applyStatusHasProblems(result.apply_status) ? "warning" : "success" });
      await refresh().catch((error) => {
        const refreshMessage = error instanceof Error ? error.message : "список не обновился";
        setOperation({ title, message: `${message}. Обновите список вручную: ${refreshMessage}`, tone: "warning" });
      });
    } catch (error) {
      setOperation({ title, message: error instanceof Error ? error.message : "Действие не выполнено", tone: "error" });
    }
  }

  const pages = {
    dashboard: <DashboardPage stats={dashboard} nodeMetrics={nodeMetrics} users={users} setPage={setPage} onRefresh={() => refreshVisibleData("dashboard")} trafficPeriod={dashboardTrafficPeriod} onTrafficPeriodChange={setDashboardTrafficPeriod} />,
    servers: (
      <ServersPage
        nodes={nodes}
        onSelect={(node) => {
          setSelectedNode(node);
          setPage("server-detail");
        }}
        onAdd={() => setPage("add-server")}
        onPreview={loadConfigPreview}
        onDelete={deleteServer}
      />
    ),
    "add-server": (
      <AddServerPage
        onCreated={(node) => {
          setNodes([node, ...nodes]);
          setSelectedNode(node);
        }}
        onCheck={(payload) => api.checkSsh(payload)}
        onGoInstall={() => setPage("install-xray")}
        onNotice={onNotice}
      />
    ),
    "server-detail": (
      <ServerDetailPage
        node={selectedNode}
        onAction={runNodeAction}
        pendingAction={nodeActionPending}
        onPreview={loadConfigPreview}
        onBack={() => setPage("servers")}
        onUpdated={async (node) => {
          upsertNode(node);
          await refresh();
        }}
        onNotice={noticeWithApplyStatus}
        onDelete={selectedNode ? () => deleteServer(selectedNode) : undefined}
        nodes={nodes}
        profiles={profiles}
        departments={departments}
        onLifecycle={(action) => selectedNode ? runNodeManagement(
          action === "enable" ? "Включение сервера" : action === "maintenance" ? "Обслуживание сервера" : "Отключение сервера",
          "Обновляем статус сервера...",
          () => api.nodeLifecycle(selectedNode.id, action)
        ) : undefined}
        onProfileAction={(mode, profileId) => selectedNode ? runNodeManagement(
          mode === "add" ? "Добавление сервера в профиль" : "Удаление сервера из профиля",
          "Обновляем профиль доступа...",
          () => mode === "add" ? api.addNodeToProfile(selectedNode.id, profileId) : api.removeNodeFromProfile(selectedNode.id, profileId)
        ) : undefined}
        onBulkUsers={(mode, payload) => selectedNode ? runNodeManagement(
          mode === "add" ? "Массовое добавление сервера" : "Массовое удаление сервера",
          "Ищем пользователей...",
          () => mode === "add" ? api.addNodeToUsers(selectedNode.id, payload) : api.removeNodeFromUsers(selectedNode.id, payload)
        ) : undefined}
        onReplace={(newNodeId) => selectedNode ? runNodeManagement(
          "Замена сервера",
          "Обновляем пользователей и профили...",
          () => api.replaceNode(selectedNode.id, newNodeId)
        ) : undefined}
        onForceDelete={() => selectedNode ? runNodeManagement(
          "Принудительное удаление сервера",
          "Отключаем сервер у пользователей и профилей...",
          () => api.deleteNode(selectedNode.id, true)
        ).then(() => setPage("servers")) : undefined}
      />
    ),
    "install-xray": (
      <InstallWizardPage
        nodes={nodes}
        node={selectedNode}
        onSelect={setSelectedNode}
        onAction={runNodeAction}
        pendingAction={nodeActionPending}
        onAdd={() => setPage("add-server")}
      />
    ),
    departments: (
      <DepartmentsPage
        items={departments}
        profiles={profiles}
        users={users}
        onCreated={async (item) => {
          setDepartments([...departments, item]);
          await refresh();
        }}
        onNotice={onNotice}
      />
    ),
    "department-detail": <DepartmentDetailPage item={departments[0]} users={users} profiles={profiles} />,
    profiles: (
      <ProfilesPage
        items={profiles}
        onNew={() => {
          setSelectedProfile(null);
          setPage("profile-editor");
        }}
        onEdit={(profile) => {
          setSelectedProfile(profile);
          setPage("profile-editor");
        }}
        onDelete={deleteProfile}
        onSeed={seedDefaultProfile}
      />
    ),
    "profile-editor": (
      <ProfileEditorPage
        profile={selectedProfile}
        onSaved={async (item) => {
          setSelectedProfile(item);
          await refresh();
          setPage("profiles");
        }}
        onBack={() => setPage("profiles")}
        onNotice={onNotice}
      />
    ),
    users: (
      <UsersPage
        users={users}
        nodes={nodes}
        departments={departments}
        profiles={profiles}
        onCreated={async (user) => {
          setSelectedUser(user);
          await refresh();
        }}
        onSelect={(user) => {
          setSelectedUser(user);
          setPage("user-detail");
        }}
        onDelete={deleteUser}
        deletingUserIds={deletingUserIds}
        onNotice={onNotice}
      />
    ),
    "user-detail": (
      <UserDetailPage
        user={selectedUser}
        nodes={nodes}
        departments={departments}
        profiles={profiles}
        onDelete={selectedUser ? () => deleteUser(selectedUser) : undefined}
        onUpdated={async (user) => {
          upsertUser(user);
          await refresh();
        }}
        onBack={() => setPage("users")}
        onNotice={onNotice}
      />
    ),
    "bulk-import": <BulkImportPage onImported={refresh} onNotice={onNotice} />,
    "subscription-preview": <PreviewPage preview={preview} onCopy={onNotice} onBack={() => setPage(selectedUser ? "user-detail" : "users")} backLabel={selectedUser ? "← К карточке пользователя" : "← К пользователям"} />,
    "config-preview": <PreviewPage preview={preview} onCopy={onNotice} onBack={() => setPage("servers")} backLabel="← К серверам" />,
    traffic: <TrafficPage nodes={nodes} rows={trafficRows} onRows={setTrafficRows} />,
    backup: <BackupPage onRestored={refresh} onNotice={noticeWithApplyStatus} />,
    audit: <AuditPage rows={auditRows} onRefresh={refresh} />,
    settings: <SettingsPage />
  } satisfies Record<PageKey, JSX.Element>;

  return (
    <>
      {notice ? <Toast text={notice} onClose={() => setNotice("")} /> : null}
      {pages[page]}
      <ConfirmDialog
        open={Boolean(confirm)}
        title={confirm?.title || ""}
        text={confirm?.text || ""}
        confirmLabel={confirm?.confirmLabel}
        onCancel={() => setConfirm(null)}
        onConfirm={() => confirm?.onConfirm()}
      />
      <OperationPopup state={operation} onClose={() => setOperation(null)} />
    </>
  );
}

function DashboardPage({
  stats,
  nodeMetrics,
  users,
  setPage,
  onRefresh,
  trafficPeriod,
  onTrafficPeriodChange
}: {
  stats: DashboardStats | null;
  nodeMetrics: NodeMetric[];
  users: VpnUser[];
  setPage: (page: PageKey) => void;
  onRefresh: () => Promise<void>;
  trafficPeriod: string;
  onTrafficPeriodChange: (value: string) => void;
}) {
  const visibleUserRows = visibleUsers(users).filter((user) => user.status === "active");
  const tiles = [
    ["Серверы", stats?.nodes_total ?? 0],
    ["Онлайн", stats?.nodes_online ?? 0],
    ["Пользователи", stats?.users_total ?? 0]
  ];
  const systemTraffic = systemTrafficSummary(nodeMetrics);
  return (
    <div className="grid gap-5">
      <PageHeader
        title="Дашборд"
        description="Состояние серверов, пользователей и текущей нагрузки."
        action={<Button onClick={() => setPage("add-server")}><Plus size={16} />Добавить VPS</Button>}
      />
      <div className="grid gap-4 md:grid-cols-3">
        {tiles.map(([label, value]) => (
          <Card key={label}>
            <CardContent>
              <div className="text-sm text-akfa-muted">{label}</div>
              <div className="mt-2 text-2xl font-semibold">{value}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <h2 className="font-semibold">Данные по серверам</h2>
          <div className="flex flex-wrap gap-2">
            <Select className="w-40" value={trafficPeriod} onChange={(event) => onTrafficPeriodChange(event.target.value)}>
              <option value="today">Сегодня</option>
              <option value="7d">7 дней</option>
              <option value="month">Этот месяц</option>
              <option value="all">Всё время</option>
            </Select>
            <Button variant="secondary" onClick={onRefresh}><RefreshCcw size={16} />Обновить</Button>
            <Button variant="secondary" onClick={() => setPage("servers")}>Серверы</Button>
          </div>
        </CardHeader>
        <CardContent className="max-h-[620px] overflow-auto">
          {!nodeMetrics.length ? (
            <EmptyPanel title="Серверы пока не добавлены" text="Добавьте VPS, чтобы увидеть метрики CPU, RAM, диска и traffic." />
          ) : (
            <div className="grid gap-3">
              <div className="rounded-md border border-akfa-line bg-zinc-50 px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold">Общий трафик VPS</div>
                    <div className="mt-1 text-xs text-akfa-muted">Весь сетевой трафик серверов: VPN, Nginx, база знаний, downloads, SSH, apt/docker, certbot и другие процессы.</div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-semibold">{systemTraffic.available ? formatBytes(systemTraffic.total) : "нет данных"}</div>
                    <div className="text-xs text-akfa-muted">{systemTraffic.sourceLabel}</div>
                  </div>
                </div>
                {systemTraffic.available ? (
                  <div className="mt-3 grid gap-2 text-sm md:grid-cols-3">
                    <div><span className="text-akfa-muted">Upload</span><div className="font-medium">{formatBytes(systemTraffic.upload)}</div></div>
                    <div><span className="text-akfa-muted">Download</span><div className="font-medium">{formatBytes(systemTraffic.download)}</div></div>
                    <div><span className="text-akfa-muted">Интерфейсы</span><div className="font-medium">{systemTraffic.interfaces}</div></div>
                  </div>
                ) : (
                  <Message tone="warning" text="Не удалось получить общий трафик VPS. Проверьте SSH-доступ к ноде." />
                )}
              </div>
              {nodeMetrics.map((metric) => <ServerMetricRow key={metric.node_id} metric={metric} />)}
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <h2 className="font-semibold">Пользователи VPN</h2>
          <Button variant="secondary" onClick={() => setPage("users")}>Все пользователи</Button>
        </CardHeader>
        <CardContent>
          {!visibleUserRows.length ? (
            <EmptyPanel title="Пользователей пока нет" text="Сначала создайте отдел, профиль доступа и сервер." />
          ) : (
            <div className="grid gap-2">
              {visibleUserRows.slice(0, 5).map((user) => (
                <div key={user.id} className="flex items-center justify-between gap-3 rounded-md border border-akfa-line px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{user.last_name} {user.first_name}</div>
                    <div className="truncate font-mono text-xs text-akfa-muted">{user.username}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <StatusBadge value={user.online_status || "offline"} />
                    <span className="whitespace-nowrap text-sm font-medium">{formatBytes(user.used_total_bytes)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function systemTrafficSummary(metrics: NodeMetric[]) {
  const available = metrics.filter((metric) => metric.system_traffic_available);
  const upload = available.reduce((sum, metric) => sum + (metric.system_traffic_upload_bytes ?? 0), 0);
  const download = available.reduce((sum, metric) => sum + (metric.system_traffic_download_bytes ?? 0), 0);
  const interfaces = Array.from(new Set(available.map((metric) => metric.system_traffic_interface).filter(Boolean))).join(", ");
  return {
    available: available.length > 0,
    upload,
    download,
    total: upload + download,
    interfaces: interfaces || "/proc/net/dev",
    sourceLabel: available.length > 0 ? "Источник: системный сетевой интерфейс (/proc/net/dev)" : "Источник: недоступен"
  };
}

function ServerMetricRow({ metric }: { metric: NodeMetric }) {
  return (
    <div className="rounded-md border border-akfa-line bg-white px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-semibold">{metric.name}</div>
          <div className="font-mono text-xs text-akfa-muted">{metric.ip_address}</div>
        </div>
        <StatusBadge value={metric.status} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <MetricBar label="CPU" value={metric.cpu_percent} />
        <MetricBar
          label="RAM"
          value={metric.ram_percent}
          detail={metric.ram_used_bytes && metric.ram_total_bytes ? `${formatBytes(metric.ram_used_bytes)} / ${formatBytes(metric.ram_total_bytes)}` : undefined}
        />
        <MetricBar
          label="Disk"
          value={metric.disk_percent}
          detail={metric.disk_used_bytes && metric.disk_total_bytes ? `${formatBytes(metric.disk_used_bytes)} / ${formatBytes(metric.disk_total_bytes)}` : undefined}
        />
      </div>
      <div className="mt-3 grid gap-3 text-sm xl:grid-cols-2">
        <div className="rounded-md bg-zinc-50 px-3 py-2">
          <div className="font-semibold">Сетевой трафик сервера</div>
          <div className="mt-1 text-xs text-akfa-muted">Весь сетевой трафик интерфейса сервера с момента загрузки счётчиков.</div>
          <div className="mt-3 grid gap-2 md:grid-cols-4">
            <div><span className="text-akfa-muted">Upload</span><div className="font-medium">{formatMetricBytes(metric.system_traffic_upload_bytes)}</div></div>
            <div><span className="text-akfa-muted">Download</span><div className="font-medium">{formatMetricBytes(metric.system_traffic_download_bytes)}</div></div>
            <div><span className="text-akfa-muted">Total</span><div className="font-medium">{formatMetricBytes(metric.system_traffic_total_bytes)}</div></div>
            <div><span className="text-akfa-muted">Источник</span><div className="font-medium">{systemTrafficSourceLabel(metric)}</div></div>
          </div>
          {!metric.system_traffic_available ? <div className="mt-2 text-xs text-akfa-red">{metric.system_traffic_error || "Не удалось получить общий трафик VPS. Проверьте SSH-доступ к ноде."}</div> : null}
        </div>
        <div className="rounded-md bg-zinc-50 px-3 py-2">
          <div className="font-semibold">VPN-трафик через Xray</div>
          <div className="mt-1 text-xs text-akfa-muted">Только VPN/proxy-трафик, который прошёл через Xray inbound на этой ноде.</div>
          <div className="mt-3 grid gap-2 md:grid-cols-4">
            <div><span className="text-akfa-muted">Upload</span><div className="font-medium">{formatBytes(metric.vpn_traffic_upload_bytes)}</div></div>
            <div><span className="text-akfa-muted">Download</span><div className="font-medium">{formatBytes(metric.vpn_traffic_download_bytes)}</div></div>
            <div><span className="text-akfa-muted">Total</span><div className="font-medium">{formatBytes(metric.vpn_traffic_total_bytes)}</div></div>
            <div><span className="text-akfa-muted">Источник</span><div className="font-medium">{vpnTrafficSourceLabel(metric.traffic_source)}</div></div>
          </div>
        </div>
      </div>
      {metric.errors.length ? <div className="mt-2 text-xs text-akfa-red">{metric.errors.join("; ")}</div> : null}
    </div>
  );
}

function vpnTrafficSourceLabel(source: NodeMetric["traffic_source"]) {
  return source === "xray_inbound" ? "Xray inbound counters" : "Сохранённые Xray deltas";
}

function formatMetricBytes(value?: number | null) {
  return typeof value === "number" ? formatBytes(value) : "нет данных";
}

function systemTrafficSourceLabel(metric: NodeMetric) {
  if (metric.system_traffic_source !== "host_proc_net_dev") return "нет данных";
  return metric.system_traffic_interface ? `/proc/net/dev: ${metric.system_traffic_interface}` : "/proc/net/dev";
}

function MetricBar({ label, value, detail }: { label: string; value?: number | null; detail?: string }) {
  const percent = typeof value === "number" ? Math.max(0, Math.min(100, value)) : null;
  const tone = percent === null || percent <= 50 ? "green" : percent <= 80 ? "yellow" : "red";
  const colors = {
    green: "bg-green-500",
    yellow: "bg-amber-500",
    red: "bg-red-500"
  };
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
        <span className="font-medium text-akfa-muted">{label}</span>
        <span className="font-semibold">{percent === null ? "нет данных" : `${percent}%`}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-zinc-100">
        <div className={`h-full ${colors[tone]}`} style={{ width: `${percent ?? 0}%` }} />
      </div>
      {detail ? <div className="mt-1 text-xs text-akfa-muted">{detail}</div> : null}
    </div>
  );
}

function ServersPage({
  nodes,
  onSelect,
  onAdd,
  onPreview,
  onDelete
}: {
  nodes: NodeRead[];
  onSelect: (node: NodeRead) => void;
  onAdd: () => void;
  onPreview: (id: number) => void;
  onDelete: (node: NodeRead) => void;
}) {
  return (
    <div className="grid gap-5">
      <PageHeader
        title="Серверы"
        description="VPS-ноды с Xray Reality, SSH-доступом и журналом установки."
        action={<Button onClick={onAdd}><Plus size={16} />Добавить VPS</Button>}
      />
      <Card>
        <CardContent>
          {!nodes.length ? (
            <EmptyPanel
              title="Серверы пока не добавлены"
              text="Добавьте VPS, чтобы установить Xray и создать первую ноду."
              action={<Button onClick={onAdd}><Plus size={16} />Добавить VPS</Button>}
            />
          ) : (
            <div className="max-w-full overflow-x-auto overscroll-x-contain">
              <Table className="min-w-[920px] whitespace-nowrap">
                <thead>
                  <tr className="border-b border-akfa-line text-akfa-muted">
                    <th className="py-2 pr-4">Название</th>
                    <th className="pr-4">IP-адрес</th>
                    <th className="pr-4">Локация</th>
                    <th className="pr-4">Порт VLESS</th>
                    <th className="pr-4">Статус</th>
                    <th className="pr-4">Синхронизация</th>
                    <th className="text-right">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map((node) => (
                    <tr key={node.id} className="border-b border-akfa-line last:border-0">
                      <td className="max-w-[220px] truncate py-3 pr-4 font-medium" title={node.name}>{node.name}</td>
                      <td className="pr-4 font-mono text-xs">{node.ip_address}</td>
                      <td className="max-w-[180px] truncate pr-4" title={node.location || "-"}>{node.location || "-"}</td>
                      <td className="pr-4">{node.vless_port}</td>
                      <td className="pr-4"><StatusBadge value={node.status} /></td>
                      <td className="pr-4">{syncLabel(node)}</td>
                      <td className="py-2">
                        <div className="flex justify-end gap-2">
                          <Button variant="secondary" onClick={() => onPreview(node.id)}><FileJson size={15} />Конфиг</Button>
                          <Button variant="ghost" onClick={() => onSelect(node)}>Открыть</Button>
                          <Button variant="danger" onClick={() => onDelete(node)}><Trash2 size={15} />Удалить</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AddServerPage({
  onCreated,
  onCheck,
  onGoInstall,
  onNotice
}: {
  onCreated: (node: NodeRead) => void;
  onCheck: (payload: Record<string, unknown>) => Promise<SshCheckResult>;
  onGoInstall: () => void;
  onNotice: (value: string) => void;
}) {
  const [form, setForm] = useState<Record<string, string | number>>(emptyNode);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState<"save" | "check" | "sni" | "probe" | "import" | null>(null);
  const [success, setSuccess] = useState("");
  const [sniMode, setSniMode] = useState("preset");
  const [sniResult, setSniResult] = useState<SniCheckResult | null>(null);
  const [sshResult, setSshResult] = useState<SshCheckResult | null>(null);
  const [probeResult, setProbeResult] = useState<XrayProbeResult | null>(null);
  const [manualPublicKey, setManualPublicKey] = useState("");
  const [savedNode, setSavedNode] = useState<NodeRead | null>(null);

  function update(key: string, value: string | number) {
    setForm({ ...form, [key]: value });
    setErrors({ ...errors, [key]: "" });
    setSuccess("");
    setSshResult(null);
    setProbeResult(null);
    setSavedNode(null);
    if (key === "sni") setSniResult(null);
  }

  function selectSni(value: string) {
    if (value === "manual") {
      setSniMode("manual");
      setSniResult(null);
      return;
    }
    setSniMode("preset");
    update("sni", value);
  }

  function validate() {
    const next: Record<string, string> = {};
    if (!String(form.name).trim()) next.name = "Укажите название сервера.";
    if (!String(form.ip_address).trim()) next.ip_address = "Укажите IP-адрес сервера.";
    if (!String(form.ssh_username).trim()) next.ssh_username = "Укажите SSH-пользователя.";
    const sniError = validateSniValue(String(form.sni));
    if (sniError) next.sni = sniError;
    if (Number(form.ssh_port) < 1 || Number(form.ssh_port) > 65535) next.ssh_port = "Порт должен быть от 1 до 65535.";
    if (Number(form.vless_port) < 1 || Number(form.vless_port) > 65535) next.vless_port = "Порт должен быть от 1 до 65535.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function save() {
    if (!validate()) return;
    setLoading("save");
    try {
      const node = await api.createNode(form);
      setSavedNode(node);
      setSuccess("Сервер сохранён");
      onCreated(node);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Сервер не создан");
    } finally {
      setLoading(null);
    }
  }

  async function check() {
    if (!validate()) return;
    setLoading("check");
    setSshResult(null);
    try {
      const result = await onCheck(form);
      setSshResult(result);
      setSuccess(result.ok ? "SSH подключение успешно" : "SSH подключение не прошло проверку");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Проверка не выполнена");
    } finally {
      setLoading(null);
    }
  }

  async function probe() {
    if (!validate()) return;
    setLoading("probe");
    setProbeResult(null);
    try {
      const result = await api.probeNode(form);
      setProbeResult(result);
      setSuccess(result.reality_inbound_found ? "Reality inbound найден" : "Проверка завершена");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Проверка сервера не выполнена");
    } finally {
      setLoading(null);
    }
  }

  async function importExisting() {
    if (!probeResult) return;
    if ((probeResult.manual_public_key_required || probeResult.public_key_missing || probeResult.partial_import_required) && !manualPublicKey.trim()) {
      onNotice("Введите Reality publicKey для импорта");
      return;
    }
    setLoading("import");
    try {
      const node = savedNode || await api.createNode(form);
      const imported = await api.importXray(node.id, { probe: probeResult, public_key: manualPublicKey.trim() || null });
      setSavedNode(imported);
      onCreated(imported);
      setSuccess("Существующий Xray импортирован");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Импорт Xray не выполнен");
    } finally {
      setLoading(null);
    }
  }

  async function checkSni() {
    const sniError = validateSniValue(String(form.sni));
    setErrors({ ...errors, sni: sniError });
    if (sniError) return;
    setLoading("sni");
    setSniResult(null);
    try {
      const result = await api.checkSni(String(form.sni));
      setSniResult(result);
      onNotice(formatSniStatus(result));
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "SNI не проверен");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="grid gap-5">
      <PageHeader title="Добавить VPS" description="Сохраните данные SSH-доступа и параметры VLESS Reality для новой ноды." />
      <Card>
        <CardContent className="grid gap-5">
          {success ? <Message tone="success" text={success} /> : null}
          {savedNode ? (
            <div className="flex flex-wrap gap-3 rounded-md border border-akfa-line bg-akfa-soft p-3">
              <Button onClick={onGoInstall}><Play size={16} />Перейти к установке Xray</Button>
              <Button variant="secondary" onClick={() => setSuccess("Можно остаться здесь и добавить ещё один сервер.")}>Остаться здесь</Button>
            </div>
          ) : null}
          {sshResult ? <SshCheckPanel result={sshResult} /> : null}
          {probeResult ? (
            <ProbePanel
              result={probeResult}
              manualPublicKey={manualPublicKey}
              onManualPublicKey={setManualPublicKey}
              onImport={importExisting}
              importing={loading === "import"}
            />
          ) : null}
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Название сервера" error={errors.name}>
              <Input value={String(form.name)} onChange={(event) => update("name", event.target.value)} placeholder="Москва-1" />
            </Field>
            <Field label="IP-адрес сервера" hint="Публичный IPv4 или IPv6 адрес VPS." error={errors.ip_address}>
              <Input value={String(form.ip_address)} onChange={(event) => update("ip_address", event.target.value)} placeholder="203.0.113.10" />
            </Field>
            <Field label="SSH-порт" error={errors.ssh_port}>
              <Input value={form.ssh_port} onChange={(event) => update("ssh_port", Number(event.target.value))} type="number" min={1} max={65535} />
            </Field>
            <Field label="SSH-пользователь" error={errors.ssh_username}>
              <Input value={String(form.ssh_username)} onChange={(event) => update("ssh_username", event.target.value)} placeholder="root" />
            </Field>
            <Field label="SSH-пароль" hint="Пароль отправляется только в backend и не выводится в логах." error={errors.ssh_password}>
              <div className="relative">
                <Input
                  value={String(form.ssh_password)}
                  onChange={(event) => update("ssh_password", event.target.value)}
                  type={showPassword ? "text" : "password"}
                  className="pr-11"
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-2 grid w-8 place-items-center text-akfa-muted"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </Field>
            <Field label="Публичный адрес подключения" hint="Домен или IP, который получат клиенты. Если пусто, будет использован IP сервера.">
              <Input value={String(form.public_host)} onChange={(event) => update("public_host", event.target.value)} placeholder="vpn.example.com" />
            </Field>
            <Field label="SNI / Reality target" hint={SNI_HELP} error={errors.sni}>
              <div className="grid gap-2">
                <Select value={sniMode === "manual" ? "manual" : String(form.sni)} onChange={(event) => selectSni(event.target.value)}>
                  <optgroup label="Рекомендуемые кандидаты">
                    {SNI_PRESETS.map((preset) => <option key={preset} value={preset}>{preset}</option>)}
                  </optgroup>
                  <option value="manual">Ручной ввод</option>
                </Select>
                {sniMode === "manual" ? (
                  <Input value={String(form.sni)} onChange={(event) => update("sni", event.target.value)} placeholder={DEFAULT_REALITY_SNI} />
                ) : null}
                <Button type="button" variant="secondary" onClick={checkSni} disabled={Boolean(loading)}>
                  <ShieldCheck size={16} />
                  {loading === "sni" ? "Проверяю SNI..." : "Проверить SNI"}
                </Button>
                {sniResult ? <SniCheckPanel result={sniResult} /> : null}
              </div>
            </Field>
            <Field label="Локация">
              <Input value={String(form.location)} onChange={(event) => update("location", event.target.value)} placeholder="Москва" />
            </Field>
            <Field label="Порт VLESS" error={errors.vless_port}>
              <Input value={form.vless_port} onChange={(event) => update("vless_port", Number(event.target.value))} type="number" min={1} max={65535} />
            </Field>
            <Field label="Fingerprint">
              <Select value={String(form.fingerprint)} onChange={(event) => update("fingerprint", event.target.value)}>
                <option value="chrome">chrome</option>
                <option value="firefox">firefox</option>
                <option value="safari">safari</option>
                <option value="randomized">randomized</option>
              </Select>
            </Field>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" onClick={check} disabled={Boolean(loading)}>
              <ShieldCheck size={16} />
              {loading === "check" ? "Проверяю..." : "Проверить подключение"}
            </Button>
            <Button variant="secondary" onClick={probe} disabled={Boolean(loading)}>
              <ShieldCheck size={16} />
              {loading === "probe" ? "Проверяю сервер..." : "Проверить сервер"}
            </Button>
            <Button onClick={save} disabled={Boolean(loading)}>
              <Save size={16} />
              {loading === "save" ? "Сохраняю..." : "Сохранить сервер"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ServerDetailPage({
  node,
  nodes,
  profiles,
  departments,
  onAction,
  pendingAction,
  onPreview,
  onBack,
  onUpdated,
  onNotice,
  onDelete,
  onLifecycle,
  onProfileAction,
  onBulkUsers,
  onReplace,
  onForceDelete
}: {
  node: NodeRead | null;
  nodes: NodeRead[];
  profiles: AccessProfile[];
  departments: Department[];
  onAction: (action: NodeAction) => void;
  pendingAction?: { nodeId: number; action: NodeAction } | null;
  onPreview: () => void;
  onBack: () => void;
  onUpdated: (node: NodeRead) => Promise<void>;
  onNotice: (value: string, applyStatus?: ConfigApplySummary | null) => void;
  onDelete?: () => void;
  onLifecycle?: (action: "disable" | "enable" | "maintenance") => void;
  onProfileAction?: (mode: "add" | "remove", profileId: number) => void;
  onBulkUsers?: (mode: "add" | "remove", payload: Record<string, unknown>) => void;
  onReplace?: (newNodeId: number) => void;
  onForceDelete?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Record<string, string | number>>({});
  const [saving, setSaving] = useState(false);
  const [profileActionId, setProfileActionId] = useState<number>(profiles[0]?.id || 0);
  const [bulkScope, setBulkScope] = useState("all_active");
  const [bulkDepartmentId, setBulkDepartmentId] = useState<number>(departments[0]?.id || 0);
  const [bulkProfileId, setBulkProfileId] = useState<number>(profiles[0]?.id || 0);
  const [replaceNodeId, setReplaceNodeId] = useState<number>(nodes.find((item) => item.id !== node?.id)?.id || 0);

  useEffect(() => {
    if (!node) return;
    setForm({
      name: node.name,
      ip_address: node.ip_address,
      location: node.location || "",
      public_host: node.public_host || "",
      vless_port: node.vless_port,
      sni: node.sni,
      fingerprint: node.fingerprint,
      xray_config_path: node.xray_config_path || "/usr/local/etc/xray/config.json",
      xray_service_name: node.xray_service_name || "xray"
    });
  }, [node]);

  useEffect(() => {
    if (!profileActionId && profiles[0]) setProfileActionId(profiles[0].id);
    if (!bulkProfileId && profiles[0]) setBulkProfileId(profiles[0].id);
  }, [profiles, profileActionId, bulkProfileId]);

  useEffect(() => {
    if (!bulkDepartmentId && departments[0]) setBulkDepartmentId(departments[0].id);
  }, [departments, bulkDepartmentId]);

  useEffect(() => {
    const fallback = nodes.find((item) => item.id !== node?.id && item.status !== "deleted");
    if (!replaceNodeId && fallback) setReplaceNodeId(fallback.id);
  }, [nodes, node?.id, replaceNodeId]);

  if (!node) {
    return <EmptyPanel title="Сервер не выбран" text="Откройте список серверов и выберите VPS для просмотра деталей." />;
  }
  const nodeBusy = pendingAction?.nodeId === node.id;
  const otherNodes = nodes.filter((item) => item.id !== node.id && item.status !== "deleted");
  const bulkPayload = {
    scope: bulkScope,
    department_id: bulkScope === "department" ? bulkDepartmentId : null,
    access_profile_id: bulkScope === "profile" ? bulkProfileId : null,
    user_ids: []
  };

  function update(key: string, value: string | number) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function saveNode() {
    if (!node) return;
    const sniError = validateSniValue(String(form.sni || ""));
    if (sniError) {
      onNotice(sniError);
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateNode(node.id, {
        ...form,
        public_host: String(form.public_host || "").trim() || null,
        location: String(form.location || "").trim() || null,
        vless_port: Number(form.vless_port)
      });
      await onUpdated(updated);
      setEditing(false);
      onNotice("Параметры сервера сохранены. Пользователям может потребоваться обновить подписку в клиенте.", updated.apply_status);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Сервер не обновлен");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
      <PageHeader title={node.name} description="Параметры подключения и статус установки Xray." action={<Button variant="secondary" onClick={onBack}>Назад к серверам</Button>} />
      <Card>
        <CardHeader><h2 className="font-semibold">Сводка сервера</h2></CardHeader>
        <CardContent className="grid gap-3 text-sm">
          <Line k="IP-адрес" v={node.ip_address} />
          <Line k="SSH-порт" v={node.ssh_port} />
          <Line k="SSH-пользователь" v={node.ssh_username} />
          <Line k="Публичный адрес" v={node.public_host || node.ip_address} />
          <Line k="SNI / Reality target" v={node.sni} />
          <Line k="Fingerprint" v={node.fingerprint} />
          <Line k="Порт VLESS" v={node.vless_port} />
          <Line k="Flow" v="xtls-rprx-vision" />
          <Line k="Security" v="reality" />
          <Line k="Network" v="tcp" />
          <Line k="Публичный ключ Reality" v={node.reality_public_key || "-"} />
          <Line k="Short ID" v={node.short_id || "-"} />
          <Line k="Статус" v={translateStatus(node.status)} />
          <Line k="Синхронизация" v={syncLabel(node)} />
          <Line k="Последнее применение" v={node.last_config_applied_at ? formatDate(node.last_config_applied_at) : "Не применялось"} />
          {node.last_config_apply_error ? <div className="md:col-span-2"><Message tone="error" text={node.last_config_apply_error} /></div> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><h2 className="font-semibold">Действия</h2></CardHeader>
        <CardContent className="grid gap-2">
          <Button variant="secondary" disabled={nodeBusy} onClick={() => onAction("check")}>Проверить подключение</Button>
          <Button variant="secondary" disabled={nodeBusy} onClick={() => onAction("verify")}><ShieldCheck size={16} />Проверить состояние Xray</Button>
          <Button variant="secondary" disabled={nodeBusy} onClick={() => onAction("dry-run")}>Сухой запуск установки</Button>
          <Button disabled={nodeBusy} onClick={() => onAction(node.status === "online" ? "apply-config" : "install")}><Play size={16} />{nodeBusy ? "Выполняется..." : node.status === "online" ? "Применить конфиг" : "Установить Xray"}</Button>
          <Button variant="secondary" disabled={nodeBusy} onClick={() => setEditing((value) => !value)}><Save size={16} />Редактировать</Button>
          <Button variant="ghost" disabled={nodeBusy} onClick={onPreview}><FileJson size={16} />Предпросмотр конфига</Button>
          {node.status === "disabled" || node.status === "maintenance" || node.status === "offline" || node.status === "failed" ? (
            <Button variant="secondary" disabled={nodeBusy} onClick={() => onLifecycle?.("enable")}><CheckCircle2 size={16} />Включить сервер</Button>
          ) : (
            <Button variant="secondary" disabled={nodeBusy} onClick={() => onLifecycle?.("disable")}><XCircle size={16} />Отключить сервер</Button>
          )}
          <Button variant="secondary" disabled={nodeBusy} onClick={() => onLifecycle?.("maintenance")}><AlertTriangle size={16} />На обслуживание</Button>
          {onDelete ? <Button variant="danger" disabled={nodeBusy} onClick={onDelete}><Trash2 size={16} />Удалить сервер</Button> : null}
        </CardContent>
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader><h2 className="font-semibold">Массовое управление доступом</h2></CardHeader>
        <CardContent className="grid gap-4 lg:grid-cols-3">
          <div className="grid gap-2 rounded-md border border-akfa-line p-3">
            <h3 className="text-sm font-semibold">Профили доступа</h3>
            <Select value={profileActionId || ""} onChange={(event) => setProfileActionId(Number(event.target.value))}>
              {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
            </Select>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" disabled={!profileActionId} onClick={() => onProfileAction?.("add", profileActionId)}>Добавить в профиль</Button>
              <Button variant="secondary" disabled={!profileActionId} onClick={() => onProfileAction?.("remove", profileActionId)}>Убрать из профиля</Button>
            </div>
          </div>
          <div className="grid gap-2 rounded-md border border-akfa-line p-3">
            <h3 className="text-sm font-semibold">Пользователи</h3>
            <Select value={bulkScope} onChange={(event) => setBulkScope(event.target.value)}>
              <option value="all_active">Все активные</option>
              <option value="department">По отделу</option>
              <option value="profile">По профилю</option>
            </Select>
            {bulkScope === "department" ? (
              <Select value={bulkDepartmentId || ""} onChange={(event) => setBulkDepartmentId(Number(event.target.value))}>
                {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
              </Select>
            ) : null}
            {bulkScope === "profile" ? (
              <Select value={bulkProfileId || ""} onChange={(event) => setBulkProfileId(Number(event.target.value))}>
                {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
              </Select>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => onBulkUsers?.("add", bulkPayload)}>Добавить пользователям</Button>
              <Button variant="secondary" onClick={() => onBulkUsers?.("remove", bulkPayload)}>Убрать у пользователей</Button>
            </div>
          </div>
          <div className="grid gap-2 rounded-md border border-akfa-line p-3">
            <h3 className="text-sm font-semibold">Замена и удаление</h3>
            <Select value={replaceNodeId || ""} onChange={(event) => setReplaceNodeId(Number(event.target.value))}>
              {otherNodes.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.ip_address}</option>)}
            </Select>
            <Button variant="secondary" disabled={!replaceNodeId} onClick={() => onReplace?.(replaceNodeId)}>Заменить этим сервером</Button>
            <Button
              variant="danger"
              onClick={() => {
                if (window.confirm("Принудительно удалить сервер и убрать его у всех пользователей/профилей?")) {
                  onForceDelete?.();
                }
              }}
            >
              Принудительно удалить
            </Button>
          </div>
        </CardContent>
      </Card>
      {editing ? (
        <Card className="lg:col-span-2">
          <CardHeader><h2 className="font-semibold">Редактирование Reality-параметров</h2></CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="md:col-span-2">
              <Message tone="warning" text="После изменения SNI, fingerprint, публичного адреса или порта пользователям может потребоваться обновить подписку в клиенте. Сама ссылка подписки не меняется." />
            </div>
            <Field label="Название">
              <Input value={String(form.name || "")} onChange={(event) => update("name", event.target.value)} />
            </Field>
            <Field label="IP-адрес">
              <Input value={String(form.ip_address || "")} onChange={(event) => update("ip_address", event.target.value)} />
            </Field>
            <Field label="Публичный адрес подключения">
              <Input value={String(form.public_host || "")} onChange={(event) => update("public_host", event.target.value)} placeholder="vpn.example.com" />
            </Field>
            <Field label="Локация">
              <Input value={String(form.location || "")} onChange={(event) => update("location", event.target.value)} />
            </Field>
            <Field label="SNI / Reality target">
              <Input value={String(form.sni || "")} onChange={(event) => update("sni", event.target.value)} />
            </Field>
            <Field label="Fingerprint">
              <Select value={String(form.fingerprint || "chrome")} onChange={(event) => update("fingerprint", event.target.value)}>
                <option value="chrome">chrome</option>
                <option value="firefox">firefox</option>
                <option value="safari">safari</option>
                <option value="randomized">randomized</option>
              </Select>
            </Field>
            <Field label="Порт VLESS">
              <Input value={form.vless_port || 443} onChange={(event) => update("vless_port", Number(event.target.value))} type="number" min={1} max={65535} />
            </Field>
            <div className="flex items-end gap-2">
              <Button onClick={saveNode} disabled={saving}><Save size={16} />{saving ? "Сохраняю..." : "Сохранить и применить"}</Button>
              <Button variant="secondary" onClick={() => setEditing(false)}>Отмена</Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      <Card className="lg:col-span-2">
        <CardHeader><h2 className="font-semibold">Журнал установки</h2></CardHeader>
        <CardContent className="grid gap-4">
          <XrayStatusPanel logs={node.install_log} port={node.vless_port} />
          <LogList logs={node.install_log} />
        </CardContent>
      </Card>
    </div>
  );
}

function InstallWizardPage({
  nodes,
  node,
  onSelect,
  onAction,
  pendingAction,
  onAdd
}: {
  nodes: NodeRead[];
  node: NodeRead | null;
  onSelect: (node: NodeRead) => void;
  onAction: (action: NodeAction) => void;
  pendingAction?: { nodeId: number; action: NodeAction } | null;
  onAdd: () => void;
}) {
  if (!nodes.length) {
    return (
      <EmptyPanel
        title="Серверы пока не добавлены"
        text="Добавьте VPS, чтобы установить Xray и создать первую ноду."
        action={<Button onClick={onAdd}><Plus size={16} />Добавить VPS</Button>}
      />
    );
  }
  const nodeBusy = Boolean(node && pendingAction?.nodeId === node.id);
  return (
    <div className="grid min-w-0 gap-5">
      <PageHeader
        title="Установка Xray"
        description="Проверьте SSH, выполните сухой запуск и только затем запустите реальную установку."
      />
      <Card>
        <CardContent className="grid gap-4">
          <div className="max-w-full lg:max-w-md">
            <Field label="Выберите VPS-ноду">
              <Select
                value={node?.id || ""}
                onChange={(event) => {
                  const found = nodes.find((item) => item.id === Number(event.target.value));
                  if (found) onSelect(found);
                }}
              >
                {nodes.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.ip_address}</option>)}
              </Select>
            </Field>
          </div>
          {node ? (
            <div className="grid min-w-0 gap-2 rounded-md border border-akfa-line bg-akfa-soft p-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
              <InfoTile label="VPS IP" value={node.ip_address} />
              <InfoTile label="VLESS port" value={node.vless_port} />
              <InfoTile label="SNI / Reality target" value={node.sni} />
              <InfoTile label="Fingerprint" value={node.fingerprint} />
              <InfoTile label="Flow" value="xtls-rprx-vision" />
              <InfoTile label="Security" value="reality" />
              <InfoTile label="Network" value="tcp" />
              <InfoTile label="Статус" value={translateStatus(node.status)} />
            </div>
          ) : null}
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-3">
        <StepCard
          step="1"
          title="Проверить подключение"
          text="Проверяет SSH-доступ без вывода пароля и без установки пакетов."
          action={<Button variant="secondary" disabled={!node || nodeBusy} onClick={() => onAction("check")}><ShieldCheck size={16} />Проверить</Button>}
        />
        <StepCard
          step="2"
          title="Сухой запуск"
          text="Генерирует команды и конфиг, чтобы увидеть будущие действия без изменения сервера."
          action={<Button variant="secondary" disabled={!node || nodeBusy} onClick={() => onAction("dry-run")}><FileJson size={16} />Сухой запуск</Button>}
        />
        <StepCard
          step="3"
          title={node?.status === "online" ? "Применить конфиг" : "Установить Xray"}
          text={node?.status === "online" ? "Обновляет Xray config без переустановки бинарника и перезапускает сервис." : "Выполняет установку на VPS. Перед запуском появится подтверждение."}
          action={<Button disabled={!node || nodeBusy} onClick={() => onAction(node?.status === "online" ? "apply-config" : "install")}><Play size={16} />{nodeBusy ? "Выполняется..." : node?.status === "online" ? "Применить конфиг" : "Установить Xray"}</Button>}
          warning
        />
      </div>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <h2 className="font-semibold">Журнал команд</h2>
          <Button variant="secondary" disabled={!node || nodeBusy} onClick={() => onAction("verify")}><ShieldCheck size={16} />Проверить состояние Xray</Button>
        </CardHeader>
        <CardContent className="grid gap-4">
          {node ? <XrayStatusPanel logs={node.install_log} port={node.vless_port} /> : null}
          <LogList logs={node?.install_log || []} />
        </CardContent>
      </Card>
    </div>
  );
}

function DepartmentsPage({
  items,
  profiles,
  users,
  onCreated,
  onNotice
}: {
  items: Department[];
  profiles: AccessProfile[];
  users: VpnUser[];
  onCreated: (item: Department) => void;
  onNotice: (value: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [profile, setProfile] = useState("");

  async function create() {
    if (!name.trim()) {
      onNotice("Укажите название отдела");
      return;
    }
    try {
      const created = await api.createDepartment({
        name,
        description: description || null,
        default_access_profile_id: profile ? Number(profile) : null
      });
      setName("");
      setDescription("");
      setProfile("");
      onCreated(created);
      onNotice("Отдел создан");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Отдел не создан");
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
      <PageHeader title="Отделы" description="Группируйте пользователей и назначайте профиль доступа по умолчанию." />
      <Card>
        <CardHeader><h2 className="font-semibold">Список отделов</h2></CardHeader>
        <CardContent>
          {!items.length ? (
            <EmptyPanel title="Отделы пока не созданы" text="Создайте отдел, чтобы назначать пользователям профиль доступа и видеть сводку по трафику." />
          ) : (
            <div className="grid gap-3">
              {items.map((item) => {
                const departmentUsers = visibleUsers(users).filter((user) => user.department_id === item.id);
                const traffic = departmentUsers.reduce((sum, user) => sum + (user.used_total_bytes || 0), 0);
                return (
                  <div key={item.id} className="rounded-md border border-akfa-line p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-medium">{item.name}</div>
                        <div className="text-sm text-akfa-muted">{item.description || "Описание не указано"}</div>
                      </div>
                      <StatusBadge value={profileName(item.default_access_profile_id, profiles) || "Профиль не выбран"} />
                    </div>
                    <div className="mt-3 grid gap-2 text-sm md:grid-cols-2">
                      <Line k="Всего пользователей" v={departmentUsers.length} />
                      <Line k="Трафик" v={formatBytes(traffic)} />
                    </div>
                    <MiniList
                      items={departmentUsers.map((user) => `${user.last_name} ${user.first_name} · ${user.username}`)}
                      empty="В этом отделе пока нет пользователей."
                    />
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><h2 className="font-semibold">Новый отдел</h2></CardHeader>
        <CardContent className="grid gap-4">
          <Field label="Название отдела">
            <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Продажи" />
          </Field>
          <Field label="Описание">
            <Textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Кратко о назначении отдела" />
          </Field>
          <Field label="Профиль доступа по умолчанию">
            <Select value={profile} onChange={(event) => setProfile(event.target.value)}>
              <option value="">Не выбран</option>
              {profiles.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </Select>
          </Field>
          <Button onClick={create}><Plus size={16} />Создать отдел</Button>
        </CardContent>
      </Card>
    </div>
  );
}

function DepartmentDetailPage({ item, users, profiles }: { item?: Department; users: VpnUser[]; profiles: AccessProfile[] }) {
  if (!item) return <EmptyPanel title="Отдел не выбран" text="Выберите отдел в списке, чтобы увидеть пользователей и настройки." />;
  const departmentUsers = visibleUsers(users).filter((user) => user.department_id === item.id);
  return (
    <Card>
      <CardHeader><h2 className="font-semibold">{item.name}</h2></CardHeader>
      <CardContent className="grid gap-3">
        <Line k="Профиль доступа" v={profileName(item.default_access_profile_id, profiles) || "Не выбран"} />
        <MiniList items={departmentUsers.map((user) => user.username)} empty="В отделе пока нет пользователей." />
      </CardContent>
    </Card>
  );
}

function ProfilesPage({
  items,
  onNew,
  onEdit,
  onDelete,
  onSeed
}: {
  items: AccessProfile[];
  onNew: () => void;
  onEdit: (profile: AccessProfile) => void;
  onDelete: (profile: AccessProfile) => void;
  onSeed: () => void;
}) {
  return (
    <div className="grid min-w-0 gap-5">
      <PageHeader
        title="Профили доступа"
        description="Маршрутизация, лимиты, срок действия и шаблон клиентской конфигурации."
        action={<div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={onSeed}>Базовые профили</Button><Button onClick={onNew}><Plus size={16} />Новый профиль</Button></div>}
      />
      <Card className="max-w-full overflow-hidden">
        <CardContent className="min-w-0">
          {!items.length ? (
            <EmptyPanel
              title="Профили доступа пока не созданы"
              text="Создайте профиль или добавьте базовые политики доступа, чтобы назначать их отделам и пользователям."
              action={<Button onClick={onSeed}>Создать базовые профили</Button>}
            />
          ) : (
            <div className="w-full max-w-full overflow-x-auto rounded-md border border-akfa-line">
              <Table className="min-w-[780px]">
                <thead>
                  <tr className="border-b border-akfa-line text-akfa-muted">
                    <th className="py-2 pl-3 pr-4">Название</th>
                    <th className="px-3">Режим маршрутизации</th>
                    <th className="px-3">Лимит</th>
                    <th className="px-3">Срок</th>
                    <th className="px-3">Шаблон</th>
                    <th className="px-3 text-right">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id} className="border-b border-akfa-line last:border-0">
                      <td className="py-3 pl-3 pr-4">
                        <div className="font-medium">{item.name}</div>
                        <div className="text-xs text-akfa-muted">{item.description || "Описание не указано"}</div>
                      </td>
                      <td className="px-3"><StatusBadge value={item.routing_mode} /></td>
                      <td className="whitespace-nowrap px-3">{item.traffic_limit_bytes ? formatBytes(item.traffic_limit_bytes) : "Без лимита"}</td>
                      <td className="whitespace-nowrap px-3">{item.expires_in_days ? `${item.expires_in_days} дн.` : "Без срока"}</td>
                      <td className="px-3"><StatusBadge value={item.client_template} /></td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex justify-end gap-2 whitespace-nowrap">
                          <Button variant="secondary" onClick={() => onEdit(item)}>Редактировать</Button>
                          <Button variant="danger" onClick={() => onDelete(item)}><Trash2 size={15} />Удалить</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ProfileEditorPage({
  profile,
  onSaved,
  onBack,
  onNotice
}: {
  profile: AccessProfile | null;
  onSaved: (item: AccessProfile) => void;
  onBack: () => void;
  onNotice: (value: string) => void;
}) {
  const [form, setForm] = useState(defaultProfileForm);

  useEffect(() => {
    if (!profile) {
      setForm(defaultProfileForm);
      return;
    }
    setForm({
      name: profile.name,
      description: profile.description || "",
      routing_mode: profile.routing_mode,
      traffic_limit_gb: profile.traffic_limit_bytes ? String(profile.traffic_limit_bytes / 1024 / 1024 / 1024) : "",
      expires_in_days: profile.expires_in_days ? String(profile.expires_in_days) : "",
      direct_domains: (profile.direct_domains || []).join("\n"),
      blocked_domains: (profile.blocked_domains || []).join("\n"),
      client_template: profile.client_template,
      is_active: profile.is_active
    });
  }, [profile]);

  async function save() {
    if (!form.name.trim()) {
      onNotice("Укажите название профиля");
      return;
    }
    const payload = {
      name: form.name,
      description: form.description || null,
      routing_mode: form.routing_mode,
      direct_domains: form.direct_domains.split(/\s+/).map((domain) => domain.trim()).filter(Boolean),
      blocked_domains: form.blocked_domains.split(/\s+/).map((domain) => domain.trim()).filter(Boolean),
      traffic_limit_bytes: form.traffic_limit_gb ? Math.round(Number(form.traffic_limit_gb) * 1024 * 1024 * 1024) : null,
      expires_in_days: form.expires_in_days ? Number(form.expires_in_days) : null,
      allowed_nodes: [],
      client_template: form.client_template,
      is_active: form.is_active
    };
    try {
      const saved = profile ? await api.updateProfile(profile.id, payload) : await api.createProfile(payload);
      onNotice(profile ? "Профиль обновлен" : "Профиль создан");
      onSaved(saved);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Профиль не сохранен");
    }
  }

  function addYoutubeExample() {
    const exampleDomains = ["youtube.com", "youtu.be", "googlevideo.com", "ytimg.com", "youtubei.googleapis.com"];
    const current = form.blocked_domains.split(/\s+/).map((domain) => domain.trim()).filter(Boolean);
    const merged = Array.from(new Set([...current, ...exampleDomains]));
    setForm({ ...form, blocked_domains: merged.join("\n") });
  }

  return (
    <div className="grid gap-5">
      <PageHeader title={profile ? "Редактировать профиль доступа" : "Новый профиль доступа"} description="Настройте маршрутизацию, direct-домены и формат выдачи клиенту." action={<Button variant="secondary" onClick={onBack}>К профилям</Button>} />
      <Card>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="Название профиля">
            <Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          </Field>
          <Field label="Шаблон клиента">
            <Select value={form.client_template} onChange={(event) => setForm({ ...form, client_template: event.target.value })}>
              <option value="vless_uri">VLESS URI</option>
              <option value="xray_json">Xray JSON</option>
              <option value="sing_box">sing-box JSON</option>
            </Select>
          </Field>
          <Field label="Описание">
            <Textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
          </Field>
          <Field label="Режим маршрутизации">
            <Select value={form.routing_mode} onChange={(event) => setForm({ ...form, routing_mode: event.target.value })}>
              <option value="full_tunnel">Весь трафик через VPN</option>
              <option value="ru_direct">Российские сервисы напрямую</option>
              <option value="custom_direct_domains">Пользовательский список direct-доменов</option>
            </Select>
          </Field>
          <Field label="Лимит трафика" hint="ГБ. Оставьте пустым, если лимита нет.">
            <Input value={form.traffic_limit_gb} onChange={(event) => setForm({ ...form, traffic_limit_gb: event.target.value })} type="number" min={0} step="0.5" />
          </Field>
          <Field label="Срок действия" hint="Дней от момента создания пользователя.">
            <Input value={form.expires_in_days} onChange={(event) => setForm({ ...form, expires_in_days: event.target.value })} type="number" min={1} />
          </Field>
          <Field label="Список direct-доменов">
            <Textarea value={form.direct_domains} onChange={(event) => setForm({ ...form, direct_domains: event.target.value })} />
          </Field>
          <Field
            label="Заблокированные домены"
            hint="Блокировка работает на уровне правил маршрутизации клиента/Xray. Приложения могут использовать другие домены, CDN или IP-адреса, поэтому для полного запрета сервиса может потребоваться добавить связанные домены."
          >
            <div className="grid gap-2">
              <Textarea value={form.blocked_domains} onChange={(event) => setForm({ ...form, blocked_domains: event.target.value })} />
              <Button type="button" variant="secondary" className="w-fit" onClick={addYoutubeExample}>
                Добавить пример YouTube
              </Button>
            </div>
          </Field>
          <label className="flex items-center gap-2 text-sm font-medium">
            <input checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} type="checkbox" />
            Профиль активен
          </label>
          <div className="md:col-span-2">
            <Button onClick={save}><Save size={16} />Сохранить профиль</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function UsersPage({
  users,
  nodes,
  departments,
  profiles,
  onCreated,
  onSelect,
  onDelete,
  deletingUserIds,
  onNotice
}: {
  users: VpnUser[];
  nodes: NodeRead[];
  departments: Department[];
  profiles: AccessProfile[];
  onCreated: (user: VpnUser) => void | Promise<void>;
  onSelect: (user: VpnUser) => void;
  onDelete: (user: VpnUser) => void;
  deletingUserIds?: Set<number>;
  onNotice: (value: string) => void;
}) {
  const [form, setForm] = useState(defaultUserForm);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [grouped, setGrouped] = useState(false);
  const [creating, setCreating] = useState(false);
  const [operation, setOperation] = useState<OperationState>(null);
  const createInFlightRef = useRef(false);
  const activeNodeIds = useMemo(() => nodes.filter((node) => node.status === "online").map((node) => node.id), [nodes]);

  useEffect(() => {
    if (form.allowed_node_ids.length || !activeNodeIds.length) return;
    setForm((current) => ({
      ...current,
      allowed_node_ids: activeNodeIds,
      primary_node_id: current.primary_node_id || String(activeNodeIds[0])
    }));
  }, [activeNodeIds, form.allowed_node_ids.length]);

  async function create() {
    if (createInFlightRef.current) return;
    if (!form.first_name.trim() || !form.last_name.trim() || !form.username.trim()) {
      onNotice("Укажите имя, фамилию и логин пользователя");
      return;
    }
    if (form.status === "active" && activeNodeIds.length > 0 && !form.allowed_node_ids.length) {
      onNotice("Выберите хотя бы один доступный сервер");
      return;
    }
    if (creating) return;
    const payload = userPayload(form);
    const username = form.username.trim();
    const existedBefore = users.some((user) => user.username === username);
    const requestId = newRequestId();
    createInFlightRef.current = true;
    setCreating(true);
    let applyTimer: number | null = null;
    try {
      setOperation({ title: "Создание пользователя", message: "Создаём пользователя...", tone: "pending" });
      applyTimer = window.setTimeout(() => setOperation({ title: "Создание пользователя", message: "Применяем конфигурацию...", tone: "pending" }), 250);
      const created = await api.createUser(payload, requestId);
      if (applyTimer) window.clearTimeout(applyTimer);
      setForm({ ...defaultUserForm, allowed_node_ids: activeNodeIds, primary_node_id: activeNodeIds[0] ? String(activeNodeIds[0]) : "" });
      const message = formatApplyStatusMessage("Пользователь успешно добавлен", created.apply_status, "Пользователь создан, но конфигурация не применена");
      const tone = applyStatusHasProblems(created.apply_status) ? "warning" : "success";
      try {
        await onCreated(created);
        setOperation({ title: "Создание пользователя", message, tone });
      } catch (refreshError) {
        const refreshMessage = refreshError instanceof Error ? refreshError.message : "список не обновился";
        setOperation({ title: "Пользователь создан", message: `${message}. Обновите список вручную: ${refreshMessage}`, tone: "warning" });
      }
    } catch (error) {
      if (applyTimer) window.clearTimeout(applyTimer);
      const message = error instanceof Error ? error.message : "Пользователь не создан";
      if (message.includes("таким логином") && !existedBefore) {
        try {
          const fresh = visibleUsers(await api.users());
          const created = fresh.find((user) => user.username === username);
          if (created) {
            await onCreated(created);
            setForm({ ...defaultUserForm, allowed_node_ids: activeNodeIds, primary_node_id: activeNodeIds[0] ? String(activeNodeIds[0]) : "" });
            setOperation({
              title: "Пользователь создан",
              message: "Пользователь успешно добавлен. Повторный запрос был проигнорирован.",
              tone: "success"
            });
            return;
          }
        } catch {
          setOperation({
            title: "Пользователь создан",
            message: "Пользователь мог быть создан, но список не обновился. Нажмите Обновить.",
            tone: "warning"
          });
          return;
        }
      }
      setOperation({ title: "Ошибка создания", message: `Ошибка: ${message}`, tone: "error" });
    } finally {
      createInFlightRef.current = false;
      setCreating(false);
    }
  }
  const visibleUserRows = visibleUsers(users);
  const filteredUsers = visibleUserRows.filter((user) => {
    const haystack = `${user.first_name} ${user.last_name} ${user.username} ${departmentName(user.department_id, departments)}`.toLowerCase();
    return (
      haystack.includes(query.toLowerCase()) &&
      (!statusFilter || user.status === statusFilter) &&
      (!departmentFilter || String(user.department_id || "") === departmentFilter)
    );
  });

  return (
    <div className="grid min-w-0 items-start gap-5 2xl:grid-cols-[minmax(0,1fr)_minmax(320px,360px)]">
      <PageHeader title="Пользователи VPN" description="Создание доступов, подписки, статусы и лимиты трафика." />
      <Card className="min-w-0 max-w-full overflow-hidden">
        <CardHeader className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <h2 className="font-semibold">Список пользователей</h2>
            <div className="mt-0.5 text-xs text-akfa-muted">Показано {filteredUsers.length} из {visibleUserRows.length}</div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 px-4 py-3">
          <div className="grid min-w-0 items-center gap-2 lg:grid-cols-[minmax(220px,1fr)_150px_180px_auto]">
            <Input className="h-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по имени, логину или отделу" />
            <Select className="h-9" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="">Все статусы</option>
              <option value="active">Активные</option>
              <option value="disabled">Отключенные</option>
              <option value="expired">Истекшие</option>
              <option value="traffic_limited">Лимит исчерпан</option>
            </Select>
            <Select className="h-9" value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)}>
              <option value="">Все отделы</option>
              {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </Select>
            <label className="flex h-9 select-none items-center gap-2 whitespace-nowrap rounded-md border border-akfa-line bg-white px-3 text-sm text-akfa-muted">
              <input className="h-4 w-4 accent-akfa-red" type="checkbox" checked={grouped} onChange={(event) => setGrouped(event.target.checked)} />
              Группировать по отделам
            </label>
          </div>
          {!visibleUserRows.length ? (
            <EmptyPanel title="Пользователей пока нет" text="Сначала создайте отдел, профиль доступа и сервер." />
          ) : grouped ? (
            !filteredUsers.length ? (
              <EmptyPanel title="Ничего не найдено" text="Измените поиск или фильтры." />
            ) : (
              <div className="grid gap-3">
                {groupUsersByDepartment(filteredUsers, departments).map((group) => (
                <details key={group.name} open className="overflow-hidden rounded-md border border-akfa-line bg-white">
                  <summary className="cursor-pointer bg-zinc-50 px-4 py-2.5 text-sm font-semibold transition hover:bg-zinc-100">
                    <span>{group.name}</span>
                    <span className="ml-2 font-normal text-akfa-muted">
                      {group.users.length} пользователей · активных {group.users.filter((user) => user.status === "active").length} · {formatBytes(group.users.reduce((sum, user) => sum + user.used_total_bytes, 0))}
                    </span>
                  </summary>
                  <div className="min-w-0 p-2">
              <UsersTable users={group.users} departments={departments} profiles={profiles} onSelect={onSelect} onDelete={onDelete} deletingUserIds={deletingUserIds} />
                  </div>
                </details>
                ))}
              </div>
            )
          ) : (
            <div className="min-w-0 max-w-full">
              <UsersTable users={filteredUsers} departments={departments} profiles={profiles} onSelect={onSelect} onDelete={onDelete} deletingUserIds={deletingUserIds} />
            </div>
          )}
        </CardContent>
      </Card>
      <Card className="w-full max-w-full 2xl:sticky 2xl:top-20">
        <CardHeader className="px-4 py-3">
          <h2 className="font-semibold">Новый пользователь</h2>
          <p className="mt-1 text-xs text-akfa-muted">Быстрое создание VPN-доступа</p>
        </CardHeader>
        <CardContent className="grid gap-3 px-4 py-3">
          <Field label="Имя">
            <Input className="h-9" value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} />
          </Field>
          <Field label="Фамилия">
            <Input className="h-9" value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} />
          </Field>
          <Field label="Логин">
            <Input className="h-9" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} />
          </Field>
          <Field label="Отдел">
            <Select className="h-9" value={form.department_id} onChange={(event) => setForm({ ...form, department_id: event.target.value })}>
              <option value="">Не выбран</option>
              {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </Select>
          </Field>
          <Field label="Профиль доступа">
            <Select className="h-9" value={form.access_profile_id} onChange={(event) => setForm({ ...form, access_profile_id: event.target.value })}>
              <option value="">Не выбран</option>
              {profiles.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </Select>
          </Field>
          <Field label="Количество устройств" hint="Лимит активных HWID-устройств.">
            <Input className="h-9" value={form.device_limit} onChange={(event) => setForm({ ...form, device_limit: event.target.value })} type="number" min={1} max={100} />
          </Field>
          <Field label="Лимит трафика" hint="ГБ. Если пусто, будет использован лимит профиля.">
            <Input className="h-9" value={form.traffic_limit_gb} onChange={(event) => setForm({ ...form, traffic_limit_gb: event.target.value })} type="number" min={0} step="0.5" />
          </Field>
          <Field label="Срок действия">
            <Input className="h-9" value={form.expires_at} onChange={(event) => setForm({ ...form, expires_at: event.target.value })} type="datetime-local" />
          </Field>
          <Field label="Статус">
            <Select className="h-9" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
              <option value="active">Активен</option>
              <option value="disabled">Отключен</option>
            </Select>
          </Field>
          <NodeAccessSelector
            nodes={nodes}
            selectedIds={form.allowed_node_ids}
            primaryNodeId={form.primary_node_id ? Number(form.primary_node_id) : null}
            onChange={(selectedIds, primaryNodeId) => setForm({ ...form, allowed_node_ids: selectedIds, primary_node_id: primaryNodeId ? String(primaryNodeId) : "" })}
          />
          <Button className="mt-1 h-9" onClick={create} disabled={creating}>
            <UserPlus size={16} />
            {creating ? "Создаём..." : "Создать пользователя"}
          </Button>
        </CardContent>
      </Card>
      <OperationPopup state={operation} onClose={() => setOperation(null)} />
    </div>
  );
}

function UsersTable({
  users,
  departments,
  profiles,
  onSelect,
  onDelete,
  deletingUserIds
}: {
  users: VpnUser[];
  departments: Department[];
  profiles: AccessProfile[];
  onSelect: (user: VpnUser) => void;
  onDelete: (user: VpnUser) => void;
  deletingUserIds?: Set<number>;
}) {
  if (!users.length) return <EmptyPanel title="Ничего не найдено" text="Измените поиск или фильтры." />;
  return (
    <div className="w-full max-w-full overflow-x-auto rounded-md border border-akfa-line">
      <Table className="min-w-[960px] table-fixed">
        <thead className="bg-zinc-50">
          <tr className="border-b border-akfa-line text-xs font-semibold text-akfa-muted">
            <th className="w-[24%] py-2.5 pl-3 pr-4">ФИО</th>
            <th className="w-[15%] px-3">Логин</th>
            <th className="w-[14%] px-3">Отдел</th>
            <th className="w-[18%] px-3">Профиль</th>
            <th className="w-[9%] px-3">Устройства</th>
            <th className="w-[10%] px-3">Онлайн</th>
            <th className="w-[9%] px-3 text-right">Трафик</th>
            <th className="w-[8%] px-3 text-right">Действия</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user, index) => (
            <tr key={user.id} className={`${index % 2 ? "bg-zinc-50/55" : "bg-white"} border-b border-akfa-line transition-colors hover:bg-red-50/35 last:border-0`}>
              <td className="py-2.5 pl-3 pr-4 font-medium">
                <div className="truncate" title={`${user.last_name} ${user.first_name}`}>{user.last_name} {user.first_name}</div>
              </td>
              <td className="px-3 py-2.5">
                <div className="truncate font-mono text-xs" title={user.username}>{user.username}</div>
              </td>
              <td className="px-3 py-2.5"><div className="truncate" title={departmentName(user.department_id, departments) || "-"}>{departmentName(user.department_id, departments) || "-"}</div></td>
              <td className="px-3 py-2.5"><div className="truncate" title={profileName(user.access_profile_id, profiles) || "-"}>{profileName(user.access_profile_id, profiles) || "-"}</div></td>
              <td className="whitespace-nowrap px-3 py-2.5 font-medium">{user.devices_label || `${user.active_devices_count || 0}/${user.device_limit || 5}`}</td>
              <td className="px-3 py-2.5"><StatusBadge value={user.online_status || "offline"} /></td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">{formatBytes(user.used_total_bytes)}</td>
              <td className="px-3 py-2">
                <div className="flex flex-nowrap justify-end gap-1">
                  <Button className="h-8 w-8 px-0" variant="secondary" title="Доступ и подписка" aria-label="Доступ и подписка" onClick={() => onSelect(user)}><Link2 size={15} /></Button>
                  <Button className="h-8 w-8 px-0" variant="danger" title="Удалить" aria-label="Удалить" disabled={deletingUserIds?.has(user.id)} onClick={() => onDelete(user)}><Trash2 size={15} /></Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

function NodeAccessSelector({
  nodes,
  selectedIds,
  primaryNodeId,
  onChange
}: {
  nodes: NodeRead[];
  selectedIds: number[];
  primaryNodeId?: number | null;
  onChange: (selectedIds: number[], primaryNodeId: number | null) => void;
}) {
  const selectableNodes = nodes.filter((node) => node.status === "online");

  function update(nextIds: number[], nextPrimaryId = primaryNodeId || null) {
    const uniqueIds = Array.from(new Set(nextIds));
    const resolvedPrimary = nextPrimaryId && uniqueIds.includes(nextPrimaryId) ? nextPrimaryId : uniqueIds[0] || null;
    onChange(uniqueIds, resolvedPrimary);
  }

  return (
    <div className="grid gap-2 rounded-md border border-akfa-line bg-zinc-50/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">Доступные серверы</div>
          <div className="text-xs text-akfa-muted">Эти ноды попадут в подписку пользователя.</div>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="secondary" className="h-8 px-2 text-xs" onClick={() => update(selectableNodes.map((node) => node.id))}>Выбрать все</Button>
          <Button type="button" variant="ghost" className="h-8 px-2 text-xs" onClick={() => update([], null)}>Снять все</Button>
        </div>
      </div>
      {!nodes.length ? (
        <div className="rounded-md border border-dashed border-akfa-line bg-white p-3 text-xs text-akfa-muted">Серверы ещё не добавлены.</div>
      ) : (
        <div className="grid gap-1.5">
          {nodes.map((node) => {
            const checked = selectedIds.includes(node.id);
            const disabled = node.status !== "online";
            return (
              <label key={node.id} className={`flex items-center gap-2 rounded-md border border-akfa-line bg-white px-2.5 py-2 text-sm ${disabled ? "opacity-55" : ""}`}>
                <input
                  className="h-4 w-4 accent-akfa-red"
                  type="checkbox"
                  checked={checked}
                  disabled={disabled}
                  onChange={(event) => update(event.target.checked ? [...selectedIds, node.id] : selectedIds.filter((id) => id !== node.id))}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium" title={node.name}>{node.name}</span>
                  <span className="block truncate text-xs text-akfa-muted" title={`${node.location || "Без локации"} · ${node.ip_address}`}>{node.location || "Без локации"} · {node.ip_address}</span>
                </span>
                <StatusBadge value={node.status} />
              </label>
            );
          })}
        </div>
      )}
      <Field label="Основной сервер">
        <Select className="h-9" value={primaryNodeId || ""} onChange={(event) => update(selectedIds, event.target.value ? Number(event.target.value) : null)}>
          <option value="">Автоматически</option>
          {selectedIds.map((nodeId) => {
            const node = nodes.find((item) => item.id === nodeId);
            if (!node) return null;
            return <option key={node.id} value={node.id}>{node.location || node.name} · {node.ip_address}</option>;
          })}
        </Select>
      </Field>
    </div>
  );
}

function UserDetailPage({
  user,
  nodes,
  departments,
  profiles,
  onDelete,
  onUpdated,
  onBack,
  onNotice
}: {
  user: VpnUser | null;
  nodes: NodeRead[];
  departments: Department[];
  profiles: AccessProfile[];
  onDelete?: () => void;
  onUpdated: (user: VpnUser) => void | Promise<void>;
  onBack: () => void;
  onNotice: (value: string) => void;
}) {
  const [accessBlocks, setAccessBlocks] = useState<PreviewBlock[]>([]);
  const [vlessEntries, setVlessEntries] = useState<SubscriptionVlessUri[]>([]);
  const [devices, setDevices] = useState<VpnUserDevice[]>([]);
  const [nodeSelection, setNodeSelection] = useState<{ ids: number[]; primaryId: number | null }>({ ids: [], primaryId: null });
  const [editForm, setEditForm] = useState(defaultUserForm);
  const [savingUser, setSavingUser] = useState(false);
  const [operation, setOperation] = useState<OperationState>(null);
  const [activeTab, setActiveTab] = useState("Ссылка подписки");
  const [confirm, setConfirm] = useState<ConfirmState>(null);

  useEffect(() => {
    if (!user) {
      setAccessBlocks([]);
      setVlessEntries([]);
      setDevices([]);
      setEditForm(defaultUserForm);
      return;
    }
    setEditForm(userFormFromUser(user));
    setNodeSelection({ ids: user.allowed_node_ids || [], primaryId: user.primary_node_id || null });
    const connectUrl = absoluteUrl(`/connect/${user.subscription_token}`);
    setAccessBlocks([{ label: "Connect-ссылка", value: connectUrl }]);
    setVlessEntries([]);
    setActiveTab("Connect-ссылка");
    api.userDevices(user.id).then(setDevices).catch(() => setDevices([]));
    api
      .subscriptionPreview(user.id)
      .then((data) => {
        setVlessEntries(data.vless_uris || []);
        setAccessBlocks(
          [
            { label: "Connect-ссылка", value: connectUrl },
            { label: "VLESS URI", value: data.vless_uri || "", mono: true },
            { label: "Xray JSON", value: prettyJson(data.xray_json), mono: true },
            { label: "sing-box JSON", value: prettyJson(data.sing_box), mono: true },
          ].filter((item) => item.value)
        );
      })
      .catch((error) => onNotice(error instanceof Error ? error.message : "Подписка недоступна"));
  }, [onNotice, user]);

  if (!user) return <EmptyPanel title="Пользователь не выбран" text="Откройте список пользователей и выберите доступ для просмотра." />;

  const subscriptionUrl = absoluteUrl(`/connect/${user.subscription_token}`);
  const tokenMasked = maskToken(user.subscription_token);
  const userId = user.id;
  const currentTab = activeTab === "QR-код" ? null : accessBlocks.find((block) => block.label === activeTab) || accessBlocks[0];
  const qrValue = subscriptionUrl;

  async function action(actionName: "enable" | "disable" | "regenerate-uuid" | "regenerate-subscription" | "reset-traffic", message: string) {
    try {
      const updated = await api.userAction(userId, actionName);
      await onUpdated(updated);
      onNotice(formatApplyStatusMessage(message, updated.apply_status));
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Действие не выполнено");
    }
  }

  function confirmAction(title: string, text: string, actionName: "enable" | "disable" | "regenerate-uuid" | "regenerate-subscription" | "reset-traffic", message: string) {
    setConfirm({
      title,
      text,
      onConfirm: () => {
        setConfirm(null);
        void action(actionName, message);
      }
    });
  }

  async function copyLink() {
    await navigator.clipboard.writeText(subscriptionUrl);
    onNotice("Ссылка подписки скопирована");
  }

  async function revokeDevice(deviceId: number) {
    try {
      await api.revokeDevice(userId, deviceId);
      setDevices(await api.userDevices(userId));
      onNotice("Устройство отключено");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Устройство не отключено");
    }
  }

  async function resetDevices() {
    try {
      await api.resetDevices(userId);
      setDevices(await api.userDevices(userId));
      onNotice("Устройства сброшены");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Устройства не сброшены");
    }
  }

  async function copyBlock(value: string) {
    await navigator.clipboard.writeText(value);
    onNotice("Скопировано");
  }

  async function saveNodeAccess() {
    if (!user) return;
    if (user.status === "active" && nodes.some((node) => node.status === "online") && !nodeSelection.ids.length) {
      onNotice("Выберите хотя бы один доступный сервер");
      return;
    }
    try {
      const updated = await api.updateUser(user.id, {
        first_name: user.first_name,
        last_name: user.last_name,
        username: user.username,
        department_id: user.department_id || null,
        access_profile_id: user.access_profile_id || null,
        traffic_limit_bytes: user.traffic_limit_bytes || null,
        device_limit: user.device_limit || 5,
        expires_at: user.expires_at || null,
        status: user.status,
        allowed_node_ids: nodeSelection.ids,
        primary_node_id: nodeSelection.primaryId
      });
      await onUpdated(updated);
      onNotice(formatApplyStatusMessage("Доступные серверы сохранены", updated.apply_status));
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Серверы пользователя не сохранены");
    }
  }

  async function saveUserSettings() {
    if (!user || savingUser) return;
    if (editForm.status === "active" && nodes.some((node) => node.status === "online") && !nodeSelection.ids.length) {
      onNotice("Выберите хотя бы один доступный сервер");
      return;
    }
    setSavingUser(true);
    let applyTimer: number | null = null;
    try {
      setOperation({ title: "Обновление пользователя", message: "Сохраняем изменения...", tone: "pending" });
      applyTimer = window.setTimeout(() => setOperation({ title: "Обновление пользователя", message: "Применяем конфигурацию...", tone: "pending" }), 250);
      const updated = await api.updateUser(user.id, userPayload({ ...editForm, allowed_node_ids: nodeSelection.ids, primary_node_id: nodeSelection.primaryId ? String(nodeSelection.primaryId) : "" }));
      if (applyTimer) window.clearTimeout(applyTimer);
      setEditForm(userFormFromUser(updated));
      setNodeSelection({ ids: updated.allowed_node_ids || [], primaryId: updated.primary_node_id || null });
      const message = formatApplyStatusMessage("Пользователь обновлён", updated.apply_status, "Пользователь обновлён, но конфигурация не применена");
      const tone = applyStatusHasProblems(updated.apply_status) ? "warning" : "success";
      try {
        await onUpdated(updated);
        setOperation({ title: "Обновление пользователя", message, tone });
      } catch (refreshError) {
        const refreshMessage = refreshError instanceof Error ? refreshError.message : "данные не обновились";
        setOperation({ title: "Пользователь обновлён", message: `${message}. Обновите список вручную: ${refreshMessage}`, tone: "warning" });
      }
    } catch (error) {
      if (applyTimer) window.clearTimeout(applyTimer);
      setOperation({ title: "Ошибка обновления", message: `Ошибка: ${error instanceof Error ? error.message : "Изменения не сохранены"}`, tone: "error" });
    } finally {
      setSavingUser(false);
    }
  }

  return (
    <>
    <div className="grid gap-5">
      <PageHeader title="Доступ пользователя" description={user.username} action={<Button variant="secondary" onClick={onBack}>← К пользователям</Button>} />
      <Card>
        <CardHeader>
          <div className="flex flex-wrap gap-2">
            {accessBlocks.map((block) => (
              <Button key={block.label} variant={activeTab === block.label ? "primary" : "secondary"} onClick={() => setActiveTab(block.label)}>
                {block.label}
              </Button>
            ))}
            <Button variant={activeTab === "QR-код" ? "primary" : "secondary"} onClick={() => setActiveTab("QR-код")}>QR-код</Button>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4">
          {!accessBlocks.length ? (
            <EmptyPanel title="Нет данных доступа" text="Добавьте сервер, чтобы сформировать подписку и клиентские конфигурации." />
          ) : activeTab === "QR-код" ? (
            <div className="grid gap-4">
              <QrPanel value={qrValue} filename={`${user.username}-subscription.png`} onNotice={onNotice} />
              {vlessEntries.length ? (
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {vlessEntries.map((entry) => (
                    <div key={entry.node_id} className="grid gap-2 rounded-md border border-akfa-line p-3">
                      <div className="truncate text-sm font-semibold" title={entry.name}>{entry.location || entry.name}</div>
                      <QRCodeCanvas value={entry.uri} size={128} />
                      <Button variant="secondary" className="h-8 text-xs" onClick={() => copyBlock(entry.uri)}><Copy size={14} />Копировать VLESS</Button>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : currentTab ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-semibold">{currentTab.label}</h2>
                <div className="flex flex-wrap gap-2">
                  {currentTab.label.includes("JSON") ? <Button variant="secondary" onClick={() => downloadText(`${currentTab.label}.json`, currentTab.value)}><Download size={16} />Скачать JSON</Button> : null}
                  <Button variant="secondary" onClick={() => copyBlock(currentTab.value)}><Copy size={16} />Копировать</Button>
                </div>
              </div>
              <pre className={currentTab.mono ? "max-h-[460px] max-w-full overflow-auto whitespace-pre-wrap break-all rounded-md bg-zinc-950 p-4 text-xs leading-relaxed text-white" : "max-w-full overflow-auto whitespace-pre-wrap break-all rounded-md border border-akfa-line p-4 text-sm"}>
                {currentTab.value}
              </pre>
              {currentTab.label === "VLESS URI" && vlessEntries.length ? (
                <div className="grid gap-2">
                  {vlessEntries.map((entry) => (
                    <div key={entry.node_id} className="flex flex-wrap items-center gap-2 rounded-md border border-akfa-line p-3">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold" title={entry.name}>{entry.location || entry.name}</div>
                        <div className="truncate font-mono text-xs text-akfa-muted" title={entry.uri}>{entry.uri}</div>
                      </div>
                      <Button variant="secondary" className="h-8" onClick={() => copyBlock(entry.uri)}><Copy size={14} />Копировать</Button>
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <h2 className="font-semibold">Настройки пользователя</h2>
          <p className="mt-1 text-xs text-akfa-muted">Основные параметры доступа, лимиты и доступные серверы.</p>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <Field label="Имя">
              <Input className="h-9" value={editForm.first_name} onChange={(event) => setEditForm({ ...editForm, first_name: event.target.value })} />
            </Field>
            <Field label="Фамилия">
              <Input className="h-9" value={editForm.last_name} onChange={(event) => setEditForm({ ...editForm, last_name: event.target.value })} />
            </Field>
            <Field label="Логин">
              <Input className="h-9" value={editForm.username} onChange={(event) => setEditForm({ ...editForm, username: event.target.value })} />
            </Field>
            <Field label="Отдел">
              <Select className="h-9" value={editForm.department_id} onChange={(event) => setEditForm({ ...editForm, department_id: event.target.value })}>
                <option value="">Не выбран</option>
                {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </Select>
            </Field>
            <Field label="Профиль доступа">
              <Select className="h-9" value={editForm.access_profile_id} onChange={(event) => setEditForm({ ...editForm, access_profile_id: event.target.value })}>
                <option value="">Не выбран</option>
                {profiles.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </Select>
            </Field>
            <Field label="Статус">
              <Select className="h-9" value={editForm.status} onChange={(event) => setEditForm({ ...editForm, status: event.target.value })}>
                <option value="active">Активен</option>
                <option value="disabled">Отключен</option>
              </Select>
            </Field>
            <Field label="Количество устройств" hint={`Сейчас активно: ${user.active_devices_count || 0}`}>
              <Input className="h-9" value={editForm.device_limit} onChange={(event) => setEditForm({ ...editForm, device_limit: event.target.value })} type="number" min={1} max={100} />
            </Field>
            <Field label="Лимит трафика" hint="ГБ. Пусто = без индивидуального лимита.">
              <Input className="h-9" value={editForm.traffic_limit_gb} onChange={(event) => setEditForm({ ...editForm, traffic_limit_gb: event.target.value })} type="number" min={0} step="0.5" />
            </Field>
            <Field label="Срок действия">
              <Input className="h-9" value={editForm.expires_at} onChange={(event) => setEditForm({ ...editForm, expires_at: event.target.value })} type="datetime-local" />
            </Field>
          </div>
          <NodeAccessSelector
            nodes={nodes}
            selectedIds={nodeSelection.ids}
            primaryNodeId={nodeSelection.primaryId}
            onChange={(ids, primaryId) => setNodeSelection({ ids, primaryId })}
          />
          <div className="flex flex-wrap gap-2">
            <Button onClick={saveUserSettings} disabled={savingUser}>
              <Save size={16} />
              {savingUser ? "Сохраняем..." : "Сохранить изменения"}
            </Button>
            <Button
              variant="secondary"
              disabled={savingUser}
              onClick={() => {
                setEditForm(userFormFromUser(user));
                setNodeSelection({ ids: user.allowed_node_ids || [], primaryId: user.primary_node_id || null });
              }}
            >
              <RotateCcw size={16} />
              Отменить изменения
            </Button>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader><h2 className="font-semibold">Карточка пользователя</h2></CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            <Line k="ФИО" v={`${user.last_name} ${user.first_name}`} />
            <Line k="Логин" v={user.username} />
            <Line k="Отдел" v={departmentName(user.department_id, departments) || "Не выбран"} />
            <Line k="Профиль доступа" v={profileName(user.access_profile_id, profiles) || "Не выбран"} />
            <Line k="Доступ" v={translateStatus(user.access_status || user.status)} />
            <Line k="Онлайн" v={user.online_status === "online" ? "Онлайн" : "Не в сети"} />
            <Line k="Отправлено" v={formatBytes(user.used_upload_bytes)} />
            <Line k="Получено" v={formatBytes(user.used_download_bytes)} />
            <Line k="Всего" v={formatBytes(user.used_total_bytes)} />
            <Line k="Устройства" v={user.devices_label || `${user.active_devices_count || 0}/${user.device_limit || 5}`} />
            <Line k="Последний онлайн" v={user.last_online_at ? formatDate(user.last_online_at) : "Не было"} />
            <Line k="Последний сбор" v={user.last_traffic_collected_at ? formatDate(user.last_traffic_collected_at) : "Не выполнялся"} />
            <Line k="Истекает" v={user.expires_at ? formatDate(user.expires_at) : "Без срока"} />
            <Line k="UUID" v={user.uuid} />
            <Line k="Токен подписки" v={tokenMasked} />
            <Line k="Лимит трафика" v={user.traffic_limit_bytes ? formatBytes(user.traffic_limit_bytes) : "Без лимита"} />
            <Line k="Последний прирост" v={formatBytes(user.last_seen_delta_bytes || 0)} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><h2 className="font-semibold">Действия</h2></CardHeader>
          <CardContent className="grid gap-2">
          <Button variant="secondary" onClick={copyLink}><Copy size={16} />Скопировать ссылку</Button>
          <Button variant="secondary" onClick={resetDevices}><RefreshCcw size={16} />Сбросить устройства</Button>
          {user.status === "active" ? (
            <Button variant="secondary" onClick={() => confirmAction("Отключить пользователя?", user.username, "disable", "Пользователь отключен")}><XCircle size={16} />Отключить</Button>
          ) : (
            <Button variant="secondary" onClick={() => confirmAction("Включить пользователя?", user.username, "enable", "Пользователь включен")}><CheckCircle2 size={16} />Включить</Button>
          )}
          <Button variant="secondary" onClick={() => confirmAction("Пересоздать UUID?", "Клиенту потребуется новая конфигурация.", "regenerate-uuid", "UUID пересоздан")}><RotateCcw size={16} />Пересоздать UUID</Button>
          <Button variant="secondary" onClick={() => confirmAction("Пересоздать ссылку подписки?", "Старая ссылка перестанет быть актуальной.", "regenerate-subscription", "Ссылка подписки пересоздана")}><RefreshCcw size={16} />Пересоздать ссылку подписки</Button>
          <Button variant="secondary" onClick={() => confirmAction("Сбросить трафик?", "Счетчики пользователя будут обнулены.", "reset-traffic", "Трафик сброшен")}><RefreshCcw size={16} />Сбросить трафик</Button>
          {onDelete ? <Button variant="danger" onClick={onDelete}><Trash2 size={16} />Удалить</Button> : null}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><h2 className="font-semibold">Устройства</h2></CardHeader>
        <CardContent className="grid gap-3">
          {!devices.length ? (
            <EmptyPanel title="Устройств пока нет" text="Первое устройство появится после первого запроса подписки клиентом." />
          ) : (
            <div className="overflow-x-auto">
              <Table className="min-w-[980px]">
                <thead>
                  <tr className="border-b border-akfa-line text-akfa-muted">
                    <th className="py-2">Название</th>
                    <th>Модель</th>
                    <th>Платформа</th>
                    <th>Клиент</th>
                    <th>HWID</th>
                    <th>IP</th>
                    <th>Трафик</th>
                    <th>Статус</th>
                    <th className="text-right">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {devices.map((device) => (
                    <tr key={device.id} className="border-b border-akfa-line last:border-0">
                      <td className="py-3 font-medium">{device.display_name || `DEV-${device.id}`}</td>
                      <td>{device.device_model || "-"}</td>
                      <td>{[device.platform, device.os_version].filter(Boolean).join(" ") || "-"}</td>
                      <td>{[device.client_name, device.app_version].filter(Boolean).join(" ") || "-"}</td>
                      <td className="font-mono text-xs">{device.hwid_masked || "-"}</td>
                      <td>{device.last_ip_address || "-"}</td>
                      <td>{formatBytes(device.total_bytes || 0)}</td>
                      <td><StatusBadge value={device.status} /></td>
                      <td className="text-right">
                        {device.status === "active" ? <Button variant="danger" className="h-8" onClick={() => revokeDevice(device.id)}>Отключить</Button> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
    <ConfirmDialog open={Boolean(confirm)} title={confirm?.title || ""} text={confirm?.text || ""} confirmLabel={confirm?.confirmLabel} onCancel={() => setConfirm(null)} onConfirm={() => confirm?.onConfirm()} />
    <OperationPopup state={operation} onClose={() => setOperation(null)} />
    </>
  );
}

function BulkImportPage({ onImported, onNotice }: { onImported: () => Promise<void>; onNotice: (value: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  async function upload() {
    if (!file) {
      onNotice("Выберите CSV-файл для импорта");
      return;
    }
    setLoading(true);
    try {
      const result = await api.importUsers(file);
      onNotice(formatApplyStatusMessage(`Импортировано пользователей: ${result.created}. Пропущено: ${result.skipped}`, result.apply_status));
      await onImported();
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Импорт не выполнен");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-5">
      <PageHeader title="Массовый импорт" description="CSV с колонками Имя, Фамилия, Логин или first_name, last_name, username." />
      <Card>
        <CardContent className="grid gap-4">
          <input className="rounded-md border border-akfa-line p-2 text-sm" type="file" accept=".csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          <Button onClick={upload} disabled={loading}><Upload size={16} />{loading ? "Импорт..." : "Импортировать CSV"}</Button>
        </CardContent>
      </Card>
    </div>
  );
}

function BackupPage({
  onRestored,
  onNotice
}: {
  onRestored: () => Promise<void>;
  onNotice: (value: string, applyStatus?: ConfigApplySummary | null) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState<"download" | "upload" | null>(null);
  const [confirm, setConfirm] = useState<ConfirmState>(null);
  const [summary, setSummary] = useState("");

  async function downloadBackup() {
    setLoading("download");
    try {
      const { blob, filename } = await api.exportBackup();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      link.click();
      URL.revokeObjectURL(link.href);
      onNotice("Бэкап скачан");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Бэкап не скачан");
    } finally {
      setLoading(null);
    }
  }

  async function restoreBackup() {
    if (!file) {
      onNotice("Выберите архив .tar.gz");
      return;
    }
    setLoading("upload");
    try {
      const result = await api.importBackup(file);
      const restored = result.restored || {};
      setSummary(
        `Восстановлено: пользователей ${restored.users || 0}, серверов ${restored.nodes || 0}, профилей ${restored.profiles || 0}, отделов ${restored.departments || 0}`
      );
      onNotice("Бэкап восстановлен", result.apply_status);
      await onRestored();
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Бэкап не восстановлен");
    } finally {
      setLoading(null);
    }
  }

  return (
    <>
      <div className="grid gap-5">
        <PageHeader
          title="Бэкап"
          description="Скачайте полный архив настроек AKFA или восстановите систему из ранее созданного архива."
        />
        <Message tone="warning" text="Архив содержит чувствительные данные: подписки, ключи Reality и параметры серверов. Храните его безопасно." />
        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader><h2 className="font-semibold">Скачать бэкап</h2></CardHeader>
            <CardContent className="grid gap-4">
              <p className="text-sm text-akfa-muted">Архив включает основные данные панели, manifest и текущие сгенерированные Xray config по нодам.</p>
              <Button onClick={downloadBackup} disabled={Boolean(loading)}>
                <Download size={16} />
                {loading === "download" ? "Готовлю архив..." : "Скачать бэкап"}
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><h2 className="font-semibold">Загрузить бэкап</h2></CardHeader>
            <CardContent className="grid gap-4">
              <Message tone="warning" text="Восстановление заменит текущие данные панели. Перед продолжением скачайте свежий бэкап." />
              <input className="rounded-md border border-akfa-line p-2 text-sm" type="file" accept=".tar.gz,application/gzip" onChange={(event) => setFile(event.target.files?.[0] || null)} />
              <Button
                variant="secondary"
                onClick={() =>
                  setConfirm({
                    title: "Восстановить бэкап?",
                    text: "Восстановление заменит текущие данные панели. Продолжить?",
                    confirmLabel: "Восстановить",
                    onConfirm: () => {
                      setConfirm(null);
                      void restoreBackup();
                    }
                  })
                }
                disabled={!file || Boolean(loading)}
              >
                <Upload size={16} />
                {loading === "upload" ? "Восстанавливаю..." : "Загрузить бэкап"}
              </Button>
              {summary ? <Message tone="success" text={summary} /> : null}
            </CardContent>
          </Card>
        </div>
      </div>
      <ConfirmDialog open={Boolean(confirm)} title={confirm?.title || ""} text={confirm?.text || ""} confirmLabel={confirm?.confirmLabel} onCancel={() => setConfirm(null)} onConfirm={() => confirm?.onConfirm()} />
    </>
  );
}

function PreviewPage({ preview, onCopy, onBack, backLabel = "← К пользователям" }: { preview: PreviewState; onCopy: (value: string) => void; onBack?: () => void; backLabel?: string }) {
  const [active, setActive] = useState("");
  useEffect(() => {
    setActive("");
  }, [preview]);
  async function copy(value: string) {
    await navigator.clipboard.writeText(value);
    onCopy("Скопировано");
  }
  const blocks = preview.blocks;
  const activeKey = active || blocks[0]?.label || "";
  const current = activeKey === "QR-код" ? null : blocks.find((block) => block.label === activeKey) || blocks[0];
  const isQr = activeKey === "QR-код";
  return (
    <div className="grid max-w-5xl gap-5">
      <PageHeader title={preview.title} description="Проверьте данные перед отправкой пользователю." action={onBack ? <Button variant="secondary" onClick={onBack}>{backLabel}</Button> : undefined} />
      {!blocks.length ? (
        <EmptyPanel title="Нет данных для предпросмотра" text={preview.empty} />
      ) : (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap gap-2">
              {blocks.map((block) => (
                <Button key={block.label} variant={(activeKey === block.label ? "primary" : "secondary")} onClick={() => setActive(block.label)}>
                  {block.label}
                </Button>
              ))}
              <Button variant={activeKey === "QR-код" ? "primary" : "secondary"} onClick={() => setActive("QR-код")}>QR-код</Button>
            </div>
          </CardHeader>
          {current && !isQr ? (
            <>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <h2 className="font-semibold">{current.label}</h2>
              <div className="flex gap-2">
                {current.label.includes("JSON") ? <Button variant="secondary" onClick={() => downloadText(`${current.label}.json`, current.value)}><Download size={16} />Скачать JSON</Button> : null}
                <Button variant="secondary" onClick={() => copy(current.value)}><Copy size={16} />Копировать</Button>
              </div>
            </CardHeader>
            <CardContent>
              <pre className={current.mono ? "max-h-[520px] max-w-full overflow-auto whitespace-pre-wrap break-all rounded-md bg-zinc-950 p-4 text-xs leading-relaxed text-white" : "max-w-full overflow-auto whitespace-pre-wrap break-all rounded-md border border-akfa-line p-4 text-sm"}>
                {current.value}
              </pre>
            </CardContent>
            </>
          ) : (
            <CardContent>
              <QrPanel value={blocks.find((block) => block.label === "VLESS URI")?.value || blocks[0].value} filename="akfa-subscription.png" onNotice={onCopy} />
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
}

function TrafficPage({ nodes, rows, onRows }: { nodes: NodeRead[]; rows: TrafficUser[]; onRows: (rows: TrafficUser[]) => void }) {
  const [nodeId, setNodeId] = useState("");
  const [message, setMessage] = useState("");
  const [sortKey, setSortKey] = useState<TrafficSortKey>("online");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const refreshRows = useCallback(async () => {
    onRows(await api.trafficOverview());
  }, [onRows]);
  const collectAndRefresh = useCallback(async (showResult: boolean) => {
    const result = nodeId ? await api.collectTraffic(Number(nodeId)) : await api.collectTrafficNow();
    if (showResult && (result.updated_users === 0 || result.errors.length)) {
      setMessage(result.message);
    } else if (showResult || result.updated_users > 0) {
      setMessage("");
    }
    await refreshRows();
  }, [nodeId, refreshRows]);

  useEffect(() => {
    void refreshRows().catch((error) => setMessage(error instanceof Error ? error.message : "Статистика недоступна"));
  }, [refreshRows]);
  const zeroTraffic = rows.length > 0 && rows.every((row) => row.total_bytes === 0);
  const sortedRows = useMemo(
    () => sortTrafficRows(rows, sortKey, sortDirection),
    [rows, sortDirection, sortKey]
  );

  async function collect() {
    try {
      await collectAndRefresh(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось собрать статистику");
    }
  }

  function changeSort(key: TrafficSortKey) {
    if (key === sortKey) {
      setSortDirection((current) => (current === "desc" ? "asc" : "desc"));
      return;
    }
    setSortKey(key);
    setSortDirection(defaultTrafficSortDirection(key));
  }

  function resetSort() {
    setSortKey("online");
    setSortDirection("desc");
  }

  return (
    <div className="grid gap-5">
      <PageHeader
        title="Аналитика трафика"
        description="VPN-трафик пользователей: per-user, per-device и per-node статистика из Xray stats."
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={resetSort}>Сбросить сортировку</Button>
            <Button variant="secondary" onClick={collect}>Собрать статистику сейчас</Button>
          </div>
        }
      />
      <Card>
        <CardContent className="grid gap-4">
          <Message tone="info" text="Источник: Xray stats. Этот раздел не показывает общий сетевой трафик VPS." />
          {message ? <Message tone={message.includes("Не удалось") || message.includes("не обновились") ? "error" : "warning"} text={message} /> : null}
          {!message && zeroTraffic ? <Message tone="warning" text="Пользователи найдены, статистика пока 0 Б" /> : null}
          <div className="max-w-sm">
            <Field label="Сервер для сбора">
              <Select value={nodeId} onChange={(event) => setNodeId(event.target.value)}>
                <option value="">Все активные серверы</option>
                {nodes.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}
              </Select>
            </Field>
          </div>
          {!rows.length ? (
            <EmptyPanel title="Пользователей пока нет" text="Создайте VPN-пользователя, чтобы увидеть аналитику трафика." />
          ) : (
            <div className="overflow-x-auto">
              <Table className="min-w-[900px]">
                <thead className="bg-zinc-50">
                  <tr className="border-b border-akfa-line text-akfa-muted">
                    <SortableTh label="Пользователь" active={sortKey === "user"} direction={sortDirection} onClick={() => changeSort("user")} className="py-3 pl-4 pr-3" />
                    <SortableTh label="Онлайн" active={sortKey === "online"} direction={sortDirection} onClick={() => changeSort("online")} className="px-3" />
                    <SortableTh label="Отправлено" active={sortKey === "upload"} direction={sortDirection} onClick={() => changeSort("upload")} className="px-3" />
                    <SortableTh label="Получено" active={sortKey === "download"} direction={sortDirection} onClick={() => changeSort("download")} className="px-3" />
                    <SortableTh label="Всего" active={sortKey === "total"} direction={sortDirection} onClick={() => changeSort("total")} className="px-3" />
                    <SortableTh label="Последний онлайн" active={sortKey === "lastOnline"} direction={sortDirection} onClick={() => changeSort("lastOnline")} className="px-3" />
                    <th className="px-3 py-3 font-medium">Устройства</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row, index) => (
                    <tr key={row.id} className={`${index % 2 ? "bg-zinc-50/60" : "bg-white"} border-b border-akfa-line transition-colors hover:bg-red-50/40 last:border-0`}>
                      <td className="py-4 pl-4 pr-3 font-medium">
                        {row.last_name} {row.first_name}
                        <div className="mt-1 font-mono text-xs text-akfa-muted">{row.username}</div>
                      </td>
                      <td className="px-3 py-4"><StatusBadge value={row.online_status || "offline"} /></td>
                      <td className="whitespace-nowrap px-3 py-4">{formatBytes(row.upload_bytes)}</td>
                      <td className="whitespace-nowrap px-3 py-4">{formatBytes(row.download_bytes)}</td>
                      <td className="whitespace-nowrap px-3 py-4 font-medium">{formatBytes(row.total_bytes)}</td>
                      <td className="whitespace-nowrap px-3 py-4">{row.last_online_at ? formatDate(row.last_online_at) : "Не было"}</td>
                      <td className="whitespace-nowrap px-3 py-4 text-akfa-muted">{row.devices_label || `${row.active_devices_count || 0}/${row.device_limit || 5}`}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SortableTh({
  label,
  active,
  direction,
  onClick,
  className = ""
}: {
  label: string;
  active: boolean;
  direction: SortDirection;
  onClick: () => void;
  className?: string;
}) {
  return (
    <th className={className}>
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-1 rounded-sm text-left font-medium transition hover:text-akfa-ink ${active ? "text-akfa-ink" : "text-akfa-muted"}`}
      >
        {label}
        <span className={`text-xs ${active ? "opacity-100" : "opacity-0"}`}>{direction === "asc" ? "↑" : "↓"}</span>
      </button>
    </th>
  );
}

function defaultTrafficSortDirection(key: TrafficSortKey): SortDirection {
  return key === "user" ? "asc" : "desc";
}

function sortTrafficRows(rows: TrafficUser[], key: TrafficSortKey, direction: SortDirection) {
  const multiplier = direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (key === "user") {
      return multiplier * trafficUserName(a).localeCompare(trafficUserName(b), "ru");
    }
    if (key === "online") {
      return multiplier * (onlineRank(a) - onlineRank(b)) || trafficUserName(a).localeCompare(trafficUserName(b), "ru");
    }
    if (key === "upload") return multiplier * ((a.upload_bytes || 0) - (b.upload_bytes || 0));
    if (key === "download") return multiplier * ((a.download_bytes || 0) - (b.download_bytes || 0));
    if (key === "total") return multiplier * ((a.total_bytes || 0) - (b.total_bytes || 0));
    return multiplier * (lastOnlineTime(a, direction) - lastOnlineTime(b, direction));
  });
}

function trafficUserName(row: TrafficUser) {
  return `${row.last_name} ${row.first_name} ${row.username}`.trim();
}

function onlineRank(row: TrafficUser) {
  return row.online_status === "online" ? 1 : 0;
}

function lastOnlineTime(row: TrafficUser, direction: SortDirection) {
  if (row.last_online_at) return new Date(row.last_online_at).getTime();
  return direction === "desc" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY;
}

function AuditPage({ rows, onRefresh }: { rows: Array<Record<string, unknown>>; onRefresh: () => Promise<void> }) {
  return (
    <div className="grid gap-5">
      <PageHeader
        title="Журнал аудита"
        description="Действия администраторов: создание, установка, импорт и изменения доступов."
        action={<Button variant="secondary" onClick={onRefresh}><RefreshCcw size={16} />Обновить</Button>}
      />
      <Card>
        <CardContent>
          <MiniList
            items={rows.map(formatAuditRow)}
            empty="Журнал пока пуст. Здесь будут отображаться действия администраторов."
          />
        </CardContent>
      </Card>
    </div>
  );
}

function SettingsPage() {
  const [admin, setAdmin] = useState<{ email: string; role: string; totp_enabled: boolean } | null>(null);
  const [setup, setSetup] = useState<{ secret: string; otpauth_url: string } | null>(null);
  const [helpLinks, setHelpLinks] = useState<PublicHelpLinks>(defaultPublicHelpLinks);
  const [savingHelpLinks, setSavingHelpLinks] = useState(false);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    Promise.all([api.me(), api.publicHelpLinks()])
      .then(([adminResponse, linksResponse]) => {
        setAdmin(adminResponse);
        setHelpLinks({
          android_happ_url: linksResponse.android_happ_url || "",
          iphone_happ_url: linksResponse.iphone_happ_url || "",
          windows_fclashx_url: linksResponse.windows_fclashx_url || "",
          macos_fclashx_url: linksResponse.macos_fclashx_url || ""
        });
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Настройки недоступны"));
  }, []);

  async function startSetup() {
    try {
      setSetup(await api.startTotpSetup());
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "2FA не запущена");
    }
  }

  async function confirmSetup() {
    try {
      const response = await api.confirmTotpSetup(null, code);
      if (response.csrf_token) api.setCsrf(response.csrf_token);
      if (response.admin) setAdmin(response.admin);
      else setAdmin(await api.me());
      setSetup(null);
      setCode("");
      setMessage("Двухфакторная защита включена");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Код не подтвержден");
    }
  }

  async function disable() {
    try {
      const next = await api.disableTotp(password);
      setAdmin(next);
      setSetup(null);
      setCode("");
      setPassword("");
      setMessage("Двухфакторная защита отключена");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "2FA не отключена");
    }
  }

  function updateHelpLink(key: keyof PublicHelpLinks, value: string) {
    setHelpLinks((current) => ({ ...current, [key]: value }));
  }

  async function saveHelpLinks() {
    setSavingHelpLinks(true);
    try {
      const saved = await api.savePublicHelpLinks(helpLinks);
      setHelpLinks({
        android_happ_url: saved.android_happ_url || "",
        iphone_happ_url: saved.iphone_happ_url || "",
        windows_fclashx_url: saved.windows_fclashx_url || "",
        macos_fclashx_url: saved.macos_fclashx_url || ""
      });
      setMessage("Ссылки на инструкции сохранены");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Ссылки не сохранены");
    } finally {
      setSavingHelpLinks(false);
    }
  }

  return (
    <div className="grid gap-5">
      <PageHeader title="Настройки администратора" description="Текущие механизмы безопасности панели." />
      {message ? <Message tone={message.includes("не") || message.includes("Невер") ? "error" : "success"} text={message} /> : null}
      <Card>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <StatusBadge value="secure_cookies" />
          <StatusBadge value={admin?.totp_enabled ? "2FA включена" : "2FA выключена"} />
          <StatusBadge value="csrf" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><h2 className="font-semibold">Двухфакторная защита</h2></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-[1fr_220px]">
          <div className="grid gap-3">
            {admin?.totp_enabled && !setup ? <Message tone="success" text="2FA включена" /> : null}
            {!admin?.totp_enabled || setup ? (
              <>
                <p className="text-sm text-akfa-muted">Отсканируйте QR-код в Google Authenticator или другом приложении для одноразовых кодов.</p>
                <p className="text-sm text-akfa-muted">2FA включится только после подтверждения кода. Если закрыть страницу сейчас, вход останется только по паролю.</p>
              </>
            ) : null}
            {setup ? (
              <>
                <Field label="Secret для ручного ввода"><Input readOnly value={setup.secret} /></Field>
                <Field label="Введите 6-значный код"><Input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" /></Field>
                <Button onClick={confirmSetup}><CheckCircle2 size={16} />Подтвердить</Button>
              </>
            ) : admin && !admin.totp_enabled ? (
              <Button onClick={startSetup}><ShieldCheck size={16} />Включить 2FA</Button>
            ) : null}
            {admin?.totp_enabled ? (
              <div className="grid gap-2 border-t border-akfa-line pt-3">
                <Field label="Пароль для отключения"><Input value={password} onChange={(event) => setPassword(event.target.value)} type="password" /></Field>
                <Button variant="secondary" onClick={disable}>Сбросить 2FA</Button>
              </div>
            ) : (
              null
            )}
          </div>
          {setup ? <div className="grid place-items-center rounded-md border border-akfa-line p-4"><QRCodeCanvas value={setup.otpauth_url} size={180} /></div> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <h2 className="font-semibold">Инструкции для пользователей</h2>
          <p className="mt-1 text-sm text-akfa-muted">Эти ссылки показываются на публичной странице подключения после выбора платформы.</p>
        </CardHeader>
        <CardContent className="grid gap-3">
          <Field label="Android / Happ">
            <Input
              value={helpLinks.android_happ_url || ""}
              onChange={(event) => updateHelpLink("android_happ_url", event.target.value)}
              placeholder="https://example.com/android-happ"
              type="url"
            />
          </Field>
          <Field label="iPhone / iPad / Happ">
            <Input
              value={helpLinks.iphone_happ_url || ""}
              onChange={(event) => updateHelpLink("iphone_happ_url", event.target.value)}
              placeholder="https://example.com/iphone-happ"
              type="url"
            />
          </Field>
          <Field label="Windows / FClashX">
            <Input
              value={helpLinks.windows_fclashx_url || ""}
              onChange={(event) => updateHelpLink("windows_fclashx_url", event.target.value)}
              placeholder="https://example.com/windows-fclashx"
              type="url"
            />
          </Field>
          <Field label="macOS / FClashX">
            <Input
              value={helpLinks.macos_fclashx_url || ""}
              onChange={(event) => updateHelpLink("macos_fclashx_url", event.target.value)}
              placeholder="https://example.com/macos-fclashx"
              type="url"
            />
          </Field>
          <div>
            <Button onClick={saveHelpLinks} disabled={savingHelpLinks}>
              <Save size={16} />
              {savingHelpLinks ? "Сохраняем..." : "Сохранить"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function StepCard({ step, title, text, action, warning }: { step: string; title: string; text: string; action: JSX.Element; warning?: boolean }) {
  return (
    <Card>
      <CardContent className="grid gap-3">
        <div className="flex items-center gap-3">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-red-50 text-sm font-semibold text-akfa-red">{step}</span>
          <h2 className="font-semibold">{title}</h2>
        </div>
        <p className="text-sm text-akfa-muted">{text}</p>
        {warning ? <Message tone="warning" text="Реальная установка изменит VPS. Запускайте только после проверки сухого запуска." /> : null}
        {action}
      </CardContent>
    </Card>
  );
}

function PageHeader({ title, description, action }: { title: string; description: string; action?: JSX.Element }) {
  return (
    <div className="flex min-w-0 flex-wrap items-end justify-between gap-4 lg:col-span-full">
      <div className="min-w-0">
        <h2 className="text-2xl font-semibold tracking-normal">{title}</h2>
        <p className="mt-1 max-w-3xl text-sm text-akfa-muted">{description}</p>
      </div>
      {action}
    </div>
  );
}

function MiniList({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <div className="rounded-md border border-dashed border-akfa-line p-4 text-sm text-akfa-muted">{empty}</div>;
  return <div className="mt-3 grid gap-2">{items.slice(0, 10).map((item) => <div key={item} className="rounded-md border border-akfa-line px-3 py-2 text-sm">{item}</div>)}</div>;
}

function LogList({ logs }: { logs: Array<Record<string, unknown>> }) {
  return (
    <MiniList
      items={(logs || []).map((log) => {
        const parts = [
          translateLogLevel(String(log.level || "")),
          log.mutating ? "изменяет VPS" : "read-only",
          log.message ? String(log.message) : "",
          log.command ? String(log.command) : "",
          typeof log.exit_code === "number" ? `код ${log.exit_code}` : "",
          log.stdout ? `stdout: ${String(log.stdout)}` : "",
          log.stderr ? `stderr: ${String(log.stderr)}` : ""
        ].filter(Boolean);
        return parts.join(" · ");
      })}
      empty="Журнал пока пуст. После проверки, сухого запуска или установки здесь появятся команды и результаты."
    />
  );
}

function Line({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-akfa-line bg-white px-3 py-2">
      <span className="text-akfa-muted">{k}</span>
      <span className="break-all text-right font-medium">{v}</span>
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0 rounded-md border border-akfa-line bg-white px-3 py-2">
      <div className="text-xs text-akfa-muted">{label}</div>
      <div className="mt-1 min-w-0 break-words text-sm font-medium leading-snug" title={String(value)}>
        {value}
      </div>
    </div>
  );
}

function EmptyPanel({ title, text, action }: { title: string; text: string; action?: JSX.Element }) {
  return (
    <div className="rounded-md border border-dashed border-akfa-line bg-akfa-soft p-6">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-akfa-muted">{text}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

function Message({ tone, text }: { tone: "success" | "error" | "warning" | "info"; text: string }) {
  const classes = {
    success: "border-green-200 bg-green-50 text-akfa-green",
    error: "border-red-200 bg-red-50 text-akfa-red",
    warning: "border-amber-200 bg-amber-50 text-amber-800",
    info: "border-blue-200 bg-blue-50 text-blue-800"
  };
  const Icon = tone === "success" ? CheckCircle2 : tone === "error" || tone === "warning" ? AlertTriangle : ShieldCheck;
  return (
    <div className={`flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${classes[tone]}`}>
      <Icon className="mt-0.5 shrink-0" size={16} />
      <span>{text}</span>
    </div>
  );
}

function OperationPopup({ state, onClose }: { state: OperationState; onClose: () => void }) {
  useEffect(() => {
    if (!state || state.tone === "pending" || state.tone === "error") return;
    const timer = window.setTimeout(onClose, 3000);
    return () => window.clearTimeout(timer);
  }, [state, onClose]);

  if (!state) return null;
  const Icon = state.tone === "success" ? CheckCircle2 : state.tone === "warning" || state.tone === "error" ? AlertTriangle : null;
  const toneClass = state.tone === "success" ? "text-akfa-green" : state.tone === "warning" ? "text-amber-700" : state.tone === "error" ? "text-akfa-red" : "text-akfa-red";
  return (
    <div className="fixed inset-x-0 top-8 z-[60] flex justify-center px-4">
      <div className="w-full max-w-md rounded-md border border-akfa-line bg-white p-4 shadow-panel">
        <div className="flex items-start gap-3">
          {state.tone === "pending" ? (
            <span className="mt-0.5 h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-akfa-line border-t-akfa-red" />
          ) : Icon ? (
            <Icon className={`mt-0.5 shrink-0 ${toneClass}`} size={18} />
          ) : null}
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{state.title}</div>
            <div className="mt-1 text-sm text-akfa-muted">{state.message}</div>
          </div>
          {state.tone !== "pending" ? <button className="text-akfa-muted" onClick={onClose}>×</button> : null}
        </div>
      </div>
    </div>
  );
}

function Toast({ text, onClose }: { text: string; onClose: () => void }) {
  return (
    <div className="fixed right-4 top-4 z-50 max-w-md rounded-md border border-akfa-line bg-white px-4 py-3 text-sm shadow-panel">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-0.5 shrink-0 text-akfa-green" size={16} />
        <span>{text}</span>
        <button className="text-akfa-muted" onClick={onClose}>×</button>
      </div>
    </div>
  );
}

function QrPanel({ value, filename, onNotice }: { value: string; filename: string; onNotice: (value: string) => void }) {
  async function copy() {
    await navigator.clipboard.writeText(value);
    onNotice("Скопировано");
  }

  function downloadQr() {
    const canvas = document.getElementById("akfa-qr") as HTMLCanvasElement | null;
    if (!canvas) return;
    const link = document.createElement("a");
    link.download = filename;
    link.href = canvas.toDataURL("image/png");
    link.click();
  }

  return (
    <div className="grid gap-4 rounded-md border border-akfa-line bg-white p-4">
      <div className="w-fit rounded-md border border-akfa-line bg-white p-3">
        <QRCodeCanvas id="akfa-qr" value={value} size={220} includeMargin />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={copy}><Copy size={16} />Скопировать ссылку</Button>
        <Button variant="secondary" onClick={downloadQr}><Download size={16} />Скачать QR PNG</Button>
      </div>
    </div>
  );
}

function SniCheckPanel({ result }: { result: SniCheckResult }) {
  const ok = result.dns_ok && result.tcp_443_ok && result.tls_ok;
  const partial = !ok && (result.dns_ok || result.tcp_443_ok || result.tls_ok);
  return (
    <div className="rounded-md border border-akfa-line bg-white p-3 text-sm">
      <div className={ok ? "font-semibold text-akfa-green" : partial ? "font-semibold text-amber-800" : "font-semibold text-akfa-red"}>
        {formatSniStatus(result)}
      </div>
      <div className="mt-2 grid gap-1 text-akfa-muted">
        <div>DNS: {result.dns_ok ? "доступен" : "ошибка"}</div>
        <div>TCP 443: {result.tcp_443_ok ? "доступен" : "ошибка"}</div>
        <div>TLS: {result.tls_ok ? "handshake выполнен" : "ошибка"}</div>
        {typeof result.latency_ms === "number" ? <div>Задержка: {result.latency_ms} мс</div> : null}
        {result.certificate_summary ? <div>Сертификат: {result.certificate_summary}</div> : null}
        {result.errors.length ? <div className="text-akfa-red">{result.errors.join("; ")}</div> : null}
      </div>
    </div>
  );
}

function SshCheckPanel({ result }: { result: SshCheckResult }) {
  const os = findLogOutput(result.logs, "cat /etc/os-release");
  const user = findLogOutput(result.logs, "whoami");
  const systemd = Boolean(findLogOutput(result.logs, "command -v systemctl"));
  const curl = Boolean(findLogOutput(result.logs, "command -v curl"));
  const jq = Boolean(findLogOutput(result.logs, "command -v jq"));
  return (
    <div className="rounded-md border border-akfa-line bg-white p-3 text-sm">
      <div className={result.ok ? "font-semibold text-akfa-green" : "font-semibold text-akfa-red"}>
        {result.ok ? "SSH подключение успешно" : "SSH подключение не прошло проверку"}
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-2">
        <Line k="ОС" v={parseOsName(os) || "-"} />
        <Line k="Пользователь" v={user.trim() || "-"} />
        <Line k="systemd" v={systemd ? "найден" : "не найден"} />
        <Line k="curl" v={curl ? "найден" : "не найден"} />
        <Line k="jq" v={jq ? "найден" : "не найден"} />
      </div>
    </div>
  );
}

function ProbePanel({
  result,
  manualPublicKey,
  onManualPublicKey,
  onImport,
  importing
}: {
  result: XrayProbeResult;
  manualPublicKey: string;
  onManualPublicKey: (value: string) => void;
  onImport: () => void;
  importing: boolean;
}) {
  const needsPublicKey = result.partial_import_required || result.manual_public_key_required || result.public_key_missing;
  return (
    <div className="grid gap-3 rounded-md border border-akfa-line bg-white p-3 text-sm">
      <div className={result.ssh_ok ? "font-semibold text-akfa-green" : "font-semibold text-akfa-red"}>
        {result.ssh_ok ? "Сервер проверен" : "Проверка не выполнена"}
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        <Line k="SSH" v={result.ssh_ok ? "OK" : "ошибка"} />
        <Line k="Xray" v={result.xray_installed ? "установлен" : "не установлен"} />
        <Line k="Service" v={result.service_active ? "active" : "inactive"} />
        <Line k="Config" v={result.config_found ? result.config_valid ? "валидный" : "невалидный" : "не найден"} />
        <Line k="Reality inbound" v={result.reality_inbound_found ? "найден" : "не найден"} />
        <Line k="Port" v={result.port ? String(result.port) : "-"} />
        <Line k="SNI/serverName" v={result.server_names?.[0] || "-"} />
        <Line k="ShortId" v={result.short_ids?.[0] || "-"} />
        <Line k="Clients" v={String(result.clients_count || 0)} />
      </div>
      {needsPublicKey ? (
        <Field label="Reality publicKey" hint="Введите publicKey из команды xray x25519 -i privateKey">
          <Input value={manualPublicKey} onChange={(event) => onManualPublicKey(event.target.value)} placeholder="Введите publicKey из команды xray x25519 -i privateKey" />
        </Field>
      ) : null}
      {result.xray_installed && result.reality_inbound_found ? (
        <Button onClick={onImport} disabled={importing || (needsPublicKey && !manualPublicKey.trim())}>
          <Download size={16} />
          {importing ? "Импортирую..." : "Импортировать существующий Xray"}
        </Button>
      ) : null}
      {!result.xray_installed ? <Message tone="warning" text="Xray не установлен. Можно сохранить сервер и перейти к установке Xray." /> : null}
    </div>
  );
}

function XrayStatusPanel({ logs, port }: { logs: Array<Record<string, unknown>>; port: number }) {
  const version = findLogOutput(logs, "xray version") || findLogOutput(logs, "/usr/local/bin/xray version");
  const statusLog = findLog(logs, "systemctl status");
  const lsLog = findLog(logs, "ls -la");
  const jqLog = findLog(logs, "jq empty");
  const portOutput = findLogOutput(logs, `:${port}`);
  if (!version && !statusLog && !lsLog && !jqLog && !portOutput) return null;
  return (
    <div className="grid gap-2 rounded-md border border-akfa-line bg-akfa-soft p-3 text-sm md:grid-cols-3">
      <Line k="Xray" v={version && !version.includes("не найден") ? "установлен" : "не найден"} />
      <Line k="Конфиг" v={lsLog && Number(lsLog.exit_code) === 0 ? "существует" : "не найден"} />
      <Line k="JSON" v={jqLog && Number(jqLog.exit_code) === 0 ? "валиден" : "невалиден"} />
      <Line k="Сервис" v={statusLog && Number(statusLog.exit_code) === 0 ? "активен" : "ошибка"} />
      <Line k="Порт" v={portOutput.trim() ? "слушает" : "не слушает"} />
    </div>
  );
}

function userPayload(form: typeof defaultUserForm) {
  return {
    first_name: form.first_name,
    last_name: form.last_name,
    username: form.username,
    department_id: form.department_id ? Number(form.department_id) : null,
    access_profile_id: form.access_profile_id ? Number(form.access_profile_id) : null,
    allowed_node_ids: form.allowed_node_ids,
    primary_node_id: form.primary_node_id ? Number(form.primary_node_id) : null,
    device_limit: Math.max(1, Number(form.device_limit || 5)),
    traffic_limit_bytes: form.traffic_limit_gb ? Math.round(Number(form.traffic_limit_gb) * 1024 * 1024 * 1024) : null,
    expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
    status: form.status
  };
}

function newRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function userFormFromUser(user: VpnUser): typeof defaultUserForm {
  return {
    first_name: user.first_name || "",
    last_name: user.last_name || "",
    username: user.username || "",
    department_id: user.department_id ? String(user.department_id) : "",
    access_profile_id: user.access_profile_id ? String(user.access_profile_id) : "",
    device_limit: String(user.device_limit || 5),
    traffic_limit_gb: user.traffic_limit_bytes ? trimNumber((user.traffic_limit_bytes / 1024 / 1024 / 1024).toFixed(2)) : "",
    expires_at: user.expires_at ? toDatetimeLocal(user.expires_at) : "",
    status: user.status || "active",
    allowed_node_ids: user.allowed_node_ids || [],
    primary_node_id: user.primary_node_id ? String(user.primary_node_id) : ""
  };
}

function trimNumber(value: string) {
  return value.replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
}

function toDatetimeLocal(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function groupUsersByDepartment(users: VpnUser[], departments: Department[]) {
  const map = new Map<string, VpnUser[]>();
  for (const user of users) {
    const name = departmentName(user.department_id, departments) || "Без отдела";
    map.set(name, [...(map.get(name) || []), user]);
  }
  return [...map.entries()].map(([name, groupUsers]) => ({ name, users: groupUsers }));
}

function visibleUsers(users: VpnUser[]) {
  return users.filter((user) => user.status !== "deleted");
}

function syncLabel(node: NodeRead) {
  if (node.last_config_apply_status === "failed") return "Ошибка применения";
  if (node.last_config_apply_status === "success") return "Синхронизировано";
  if (node.status === "online") return "Готов к синхронизации";
  if (node.status === "failed") return "Ошибка";
  return "Ожидает применения";
}

function formatApplyStatusMessage(base: string, applyStatus?: ConfigApplySummary | null, partialBase?: string) {
  if (!applyStatus) return base;
  const problematic = applyStatus.results.filter((item) => !item.ok || item.status === "skipped");
  if (!problematic.length) return base;
  const details = problematic
    .map((item) => [item.node_name, item.error].filter(Boolean).join(": "))
    .filter(Boolean)
    .join("; ");
  return `${partialBase || `${base}, но конфиг не применился`}${details ? `: ${details}` : ""}`;
}

function applyStatusHasProblems(applyStatus?: ConfigApplySummary | null) {
  return Boolean(applyStatus?.results.some((item) => !item.ok || item.status === "skipped"));
}

function nodeActionTitle(action: NodeAction) {
  if (action === "install") return "Установка Xray";
  if (action === "apply-config") return "Применение конфига Xray";
  if (action === "dry-run") return "Сухой запуск установки";
  if (action === "verify") return "Проверка Xray";
  return "Проверка SSH";
}

function nodeActionInitialMessage(action: NodeAction) {
  if (action === "install") return "Подключаемся к VPS...";
  if (action === "apply-config") return "Готовим и применяем конфигурацию...";
  if (action === "dry-run") return "Формируем план установки...";
  if (action === "verify") return "Проверяем статус ноды...";
  return "Проверяем SSH-подключение...";
}

function nodeActionStages(action: NodeAction): Array<[number, string]> {
  if (action === "install") {
    return [
      [1200, "Проверяем apt/dpkg..."],
      [3500, "Обновляем пакеты..."],
      [12000, "Устанавливаем зависимости..."],
      [25000, "Скачиваем и устанавливаем Xray..."],
      [45000, "Генерируем Reality config..."],
      [55000, "Проверяем конфигурацию Xray..."],
      [65000, "Запускаем Xray service..."],
      [75000, "Проверяем статус ноды..."]
    ];
  }
  if (action === "apply-config") {
    return [
      [1200, "Генерируем Reality config..."],
      [3000, "Проверяем конфигурацию Xray..."],
      [6000, "Перезапускаем Xray service..."]
    ];
  }
  return [];
}

function nodeActionSuccessMessage(action: NodeAction, applyStatus?: ConfigApplySummary | null) {
  const base =
    action === "install"
      ? "Установка Xray завершена"
      : action === "apply-config"
        ? "Конфиг Xray применен"
        : action === "dry-run"
          ? "Сухой запуск завершен"
          : action === "verify"
            ? "Проверка Xray завершена"
            : "Проверка SSH завершена";
  return formatApplyStatusMessage(base, applyStatus);
}

function nodeActionErrorMessage(action: NodeAction, message: string) {
  if (action === "install") return message.startsWith("Установка Xray не завершена") ? message : `Установка Xray не завершена: ${message}`;
  if (action === "apply-config") return `Конфиг Xray не применен: ${message}`;
  if (action === "dry-run") return `Сухой запуск не выполнен: ${message}`;
  if (action === "verify") return `Проверка Xray не выполнена: ${message}`;
  return `Проверка SSH не выполнена: ${message}`;
}

async function runInstallJob(
  nodeId: number,
  title: string,
  setOperation: (state: OperationState) => void
): Promise<NodeRead> {
  const accepted = await api.startNodeInstall(nodeId);
  let lastJob = await api.nodeActionJob(accepted.job_id);
  const startedAt = Date.now();
  while (lastJob.status === "pending" || lastJob.status === "running") {
    setOperation({ title, message: lastJob.current_step || "Установка выполняется...", tone: "pending" });
    if (Date.now() - startedAt > 20 * 60 * 1000) {
      throw new Error("Сервер не ответил вовремя. Проверьте статус установки в журнале.");
    }
    await sleep(1500);
    lastJob = await api.nodeActionJob(accepted.job_id);
  }
  if (lastJob.status === "success" && lastJob.result) {
    return lastJob.result;
  }
  if (lastJob.status === "success") {
    const nodes = await api.nodes();
    const node = nodes.find((item) => item.id === nodeId);
    if (node) return node;
    throw new Error("Установка завершена, но нода не найдена в списке.");
  }
  throw new Error(lastJob.error || nodeLogFailureReason(lastJob.logs) || "Установка Xray не завершена");
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function nodeLogFailureReason(logs: Array<Record<string, unknown>>) {
  const entry = [...(logs || [])].reverse().find((log) => log.level === "error");
  if (!entry) return "";
  return [entry.message, entry.command, entry.stderr].map((value) => String(value || "").trim()).filter(Boolean).join(" · ");
}

function downloadText(filename: string, value: string) {
  const blob = new Blob([value], { type: "application/json;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename.replace(/\s+/g, "-");
  link.click();
  URL.revokeObjectURL(link.href);
}

function findLog(logs: Array<Record<string, unknown>>, commandPart: string) {
  return [...logs].reverse().find((log) => String(log.command || "").includes(commandPart));
}

function findLogOutput(logs: Array<Record<string, unknown>>, commandPart: string) {
  const log = findLog(logs, commandPart);
  return String(log?.stdout || log?.output || "");
}

function parseOsName(value: string) {
  const pretty = value.match(/^PRETTY_NAME="?([^"\n]+)"?/m);
  if (pretty) return pretty[1];
  const name = value.match(/^NAME="?([^"\n]+)"?/m);
  return name?.[1] || value.split("\n")[0] || "";
}


function validateSniValue(value: string) {
  const sni = value.trim().toLowerCase();
  if (!sni) return "Укажите SNI / Reality target.";
  if (sni.startsWith("https://") || sni.startsWith("http://")) return "Укажите домен без http:// или https://.";
  if (sni.includes("/")) return "SNI не должен содержать путь или символ /.";
  if (/\s/.test(sni)) return "SNI не должен содержать пробелы.";
  if (sni.includes(":")) return "Порт указывается отдельно, не добавляйте его в SNI.";
  if (sni.length > 253) return "SNI слишком длинный.";
  const labels = sni.split(".");
  if (labels.length < 2 || labels.some((label) => !label)) return "Укажите корректный домен SNI.";
  if (labels.some((label) => label.length > 63 || !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(label))) {
    return "SNI содержит недопустимые символы.";
  }
  return "";
}

function formatSniStatus(result: SniCheckResult) {
  if (result.dns_ok && result.tcp_443_ok && result.tls_ok) return "SNI выглядит рабочим";
  if (result.dns_ok || result.tcp_443_ok || result.tls_ok) return "SNI частично доступен";
  return "SNI не прошел проверку";
}

function departmentName(id: number | null | undefined, departments: Department[]) {
  return departments.find((department) => department.id === id)?.name || "";
}

function profileName(id: number | null | undefined, profiles: AccessProfile[]) {
  return profiles.find((profile) => profile.id === id)?.name || "";
}

function translateStatus(value: string) {
  const map: Record<string, string> = {
    active: "активен",
    disabled: "отключен",
    expired: "истек",
    traffic_limited: "лимит исчерпан",
    deleted: "удален",
    draft: "черновик",
    checking: "проверка",
    online: "онлайн",
    offline: "офлайн",
    installing: "установка",
    failed: "ошибка",
    maintenance: "обслуживание"
  };
  return map[value] || value;
}

function translateLogLevel(value?: string) {
  if (value === "error") return "Ошибка";
  if (value === "warning") return "Предупреждение";
  return "Инфо";
}

function formatAuditRow(row: Record<string, unknown>) {
  const action = String(row.action || "");
  const entity = String(row.entity_type || "");
  const id = row.entity_id ? ` #${row.entity_id}` : "";
  return `${translateAuditAction(action)} · ${translateEntity(entity)}${id}`;
}

function translateAuditAction(value: string) {
  const map: Record<string, string> = {
    create: "Создание",
    update: "Обновление",
    delete: "Удаление",
    disable: "Отключение",
    enable: "Включение",
    seed: "Создание стандартных данных",
    bulk_import: "Массовый импорт",
    check_connection: "Проверка подключения",
    dry_run_install: "Сухой запуск установки",
    install_xray: "Установка Xray",
    collect_stats: "Сбор статистики",
    regenerate_uuid: "Пересоздание UUID",
    regenerate_subscription: "Пересоздание подписки",
    reset_traffic: "Сброс трафика"
  };
  return map[value] || value;
}

function translateEntity(value: string) {
  const map: Record<string, string> = {
    access_profile: "профиль доступа",
    department: "отдел",
    vps_node: "сервер",
    vpn_user: "пользователь VPN"
  };
  return map[value] || value;
}

function prettyJson(value?: string) {
  if (!value) return "";
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

function absoluteUrl(path: string) {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${window.location.origin}${path.startsWith("/") ? path : `/${path}`}`;
}

function publicConnectToken() {
  const match = window.location.pathname.match(/^\/connect\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function connectOptions(token: string) {
  return [
    {
      id: "android-happ",
      title: "Android",
      client: "Happ",
      helpKey: "android_happ_url" as const,
      path: `/sub/${token}?platform=android&client=happ&format=raw`,
      steps: ["Установите Happ.", "Добавьте подписку по ссылке или QR-коду.", "Обновите профиль и подключитесь."]
    },
    {
      id: "iphone-happ",
      title: "iPhone / iPad",
      client: "Happ",
      helpKey: "iphone_happ_url" as const,
      path: `/sub/${token}?platform=iphone&client=happ&format=raw`,
      steps: ["Установите Happ.", "Добавьте подписку по ссылке или QR-коду.", "Разрешите VPN-профиль в iOS."]
    },
    {
      id: "windows-fclashx",
      title: "Windows",
      client: "FClashX",
      helpKey: "windows_fclashx_url" as const,
      path: `/sub/${token}?platform=windows&client=fclashx&format=clash`,
      steps: ["Установите FClashX.", "Импортируйте ссылку подписки.", "Выберите профиль akfa vpn и подключитесь."]
    },
    {
      id: "macos-fclashx",
      title: "macOS",
      client: "FClashX / Clash",
      helpKey: "macos_fclashx_url" as const,
      path: `/sub/${token}?platform=macos&client=fclashx&format=clash`,
      steps: ["Установите FClashX или Clash.", "Импортируйте ссылку YAML-подписки.", "Выберите профиль akfa vpn."]
    }
  ];
}

function maskToken(value: string) {
  if (value.length <= 12) return value;
  return `${value.slice(0, 6)}...${value.slice(-6)}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default App;
