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
import { api, type AccessProfile, type ConfigApplySummary, type DashboardStats, type Department, type NodeMetric, type NodeRead, type SniCheckResult, type SshCheckResult, type SubscriptionVlessUri, type TrafficUser, type VpnUser } from "./lib/api";
import { formatBytes } from "./lib/utils";

type SessionState = "checking" | "login" | "totp" | "ready";
type NodeAction = "check" | "dry-run" | "install" | "verify" | "apply-config";
type PreviewBlock = { label: string; value: string; mono?: boolean };
type PreviewState = { title: string; empty: string; blocks: PreviewBlock[] };
type ConfirmState = { title: string; text: string; onConfirm: () => void; confirmLabel?: string } | null;
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
  traffic_limit_gb: "",
  expires_at: "",
  status: "active",
  allowed_node_ids: [] as number[],
  primary_node_id: ""
};

function App() {
  const [session, setSession] = useState<SessionState>("checking");
  const [page, setPage] = useState<PageKey>("dashboard");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    api
      .me()
      .then(() => setSession("ready"))
      .catch(() => setSession("login"));
  }, []);

  if (session === "checking") return <Splash />;
  if (session === "login" || session === "totp") {
    return (
      <LoginPage
        mode={session}
        onTotp={() => setSession("totp")}
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

function Splash() {
  return <div className="grid min-h-screen place-items-center text-sm text-akfa-muted">AKFA</div>;
}

function LoginPage({
  mode,
  onTotp,
  onReady,
  onNotice,
  notice
}: {
  mode: SessionState;
  onTotp: () => void;
  onReady: () => void;
  onNotice: (value: string) => void;
  notice: string;
}) {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    try {
      if (mode === "totp") {
        const response = await api.verify2fa(code);
        if (response.csrf_token) api.setCsrf(response.csrf_token);
        onReady();
        return;
      }
      const response = await api.login(email, password);
      if (response.requires_2fa) onTotp();
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
            <div className="grid h-10 w-10 place-items-center rounded-md bg-akfa-red text-lg font-bold text-white">A</div>
            <div>
              <h1 className="text-xl font-semibold">AKFA</h1>
              <div className="text-sm text-akfa-muted">Вход администратора</div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4">
          {notice ? <Message tone="error" text={notice} /> : null}
          {mode === "totp" ? (
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
            {loading ? "Проверка..." : "Войти"}
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
  const [users, setUsers] = useState<VpnUser[]>([]);
  const [trafficRows, setTrafficRows] = useState<TrafficUser[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [profiles, setProfiles] = useState<AccessProfile[]>([]);
  const [auditRows, setAuditRows] = useState<Array<Record<string, unknown>>>([]);
  const [selectedUser, setSelectedUser] = useState<VpnUser | null>(null);
  const [selectedNode, setSelectedNode] = useState<NodeRead | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<AccessProfile | null>(null);
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
        api.nodeMetrics(),
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
  }, [onNotice]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const refreshVisibleData = useCallback(async (targetPage: PageKey) => {
    if (targetPage === "dashboard") {
      const [stats, metricList, userList] = await Promise.all([api.dashboard(), api.nodeMetrics(), api.users()]);
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
      const [nodeList, metricList] = await Promise.all([api.nodes(), api.nodeMetrics()]);
      setNodes(nodeList);
      setNodeMetrics(metricList);
      setSelectedNode((current) => nodeList.find((node) => node.id === current?.id) || current);
    }
  }, []);

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
    try {
      onNotice(action === "check" ? "Проверяю SSH-подключение..." : action === "dry-run" ? "Выполняю сухой запуск..." : action === "verify" ? "Проверяю состояние Xray..." : action === "apply-config" ? "Применяю конфиг Xray..." : "Запускаю установку Xray...");
      const updated = action === "apply-config" ? await api.applyConfig(node.id) : await api.nodeAction(node.id, action);
      upsertNode(updated);
      noticeWithApplyStatus(action === "check" ? "Проверка завершена" : action === "dry-run" ? "Сухой запуск завершен" : action === "verify" ? "Проверка Xray завершена" : action === "apply-config" ? "Конфиг Xray применен" : "Установка завершена", updated.apply_status);
      await refresh();
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Действие не выполнено");
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
    setConfirm({
      title: "Удалить пользователя VPN?",
      text: `Удалить пользователя ${user.last_name} ${user.first_name}? Пользователь исчезнет из AKFA и будет исключен из Xray config.`,
      confirmLabel: "Удалить",
      onConfirm: async () => {
        setConfirm(null);
        try {
          const result = await api.deleteUser(user.id);
          setUsers((items) => items.filter((item) => item.id !== user.id));
          setSelectedUser((current) => (current?.id === user.id ? null : current));
          onNotice(result.diagnostics || "Пользователь удален");
          await refresh();
        } catch (error) {
          onNotice(error instanceof Error ? error.message : "Пользователь не удален");
        }
      }
    });
  }

  async function deleteServer(node: NodeRead) {
    setConfirm({
      title: "Удалить сервер из AKFA?",
      text: `${node.name}. Будет удалена только запись в AKFA. Xray и файлы на VPS не удаляются.`,
      onConfirm: async () => {
        setConfirm(null);
        try {
          const result = await api.deleteNode(node.id);
          setNodes(nodes.filter((item) => item.id !== node.id));
          setSelectedNode((current) => (current?.id === node.id ? null : current));
          onNotice(result.message || "Сервер удален из AKFA");
          await refresh();
          setPage("servers");
        } catch (error) {
          onNotice(error instanceof Error ? error.message : "Сервер не удален");
        }
      }
    });
  }

  const pages = {
    dashboard: <DashboardPage stats={dashboard} nodeMetrics={nodeMetrics} users={users} setPage={setPage} onRefresh={() => refreshVisibleData("dashboard")} />,
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
        onPreview={loadConfigPreview}
        onBack={() => setPage("servers")}
        onUpdated={async (node) => {
          upsertNode(node);
          await refresh();
        }}
        onNotice={noticeWithApplyStatus}
        onDelete={selectedNode ? () => deleteServer(selectedNode) : undefined}
      />
    ),
    "install-xray": (
      <InstallWizardPage
        nodes={nodes}
        node={selectedNode}
        onSelect={setSelectedNode}
        onAction={runNodeAction}
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
    </>
  );
}

function DashboardPage({
  stats,
  nodeMetrics,
  users,
  setPage,
  onRefresh
}: {
  stats: DashboardStats | null;
  nodeMetrics: NodeMetric[];
  users: VpnUser[];
  setPage: (page: PageKey) => void;
  onRefresh: () => Promise<void>;
}) {
  const visibleUserRows = visibleUsers(users).filter((user) => user.status === "active");
  const tiles = [
    ["Серверы", stats?.nodes_total ?? 0],
    ["Онлайн", stats?.nodes_online ?? 0],
    ["Пользователи", stats?.users_total ?? 0],
    ["Активные", stats?.users_active ?? 0]
  ];
  return (
    <div className="grid gap-5">
      <PageHeader
        title="Дашборд"
        description="Состояние серверов, пользователей и текущей нагрузки."
        action={<Button onClick={() => setPage("add-server")}><Plus size={16} />Добавить VPS</Button>}
      />
      <div className="grid gap-4 md:grid-cols-4">
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
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onRefresh}><RefreshCcw size={16} />Обновить</Button>
            <Button variant="secondary" onClick={() => setPage("servers")}>Серверы</Button>
          </div>
        </CardHeader>
        <CardContent className="max-h-[520px] overflow-auto">
          {!nodeMetrics.length ? (
            <EmptyPanel title="Серверы пока не добавлены" text="Добавьте VPS, чтобы увидеть метрики CPU, RAM, диска и traffic." />
          ) : (
            <div className="grid gap-3">
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
      <div className="mt-3 grid gap-2 rounded-md bg-zinc-50 px-3 py-2 text-sm md:grid-cols-4">
        <div><span className="text-akfa-muted">Upload</span><div className="font-medium">{formatBytes(metric.traffic_upload_bytes)}</div></div>
        <div><span className="text-akfa-muted">Download</span><div className="font-medium">{formatBytes(metric.traffic_download_bytes)}</div></div>
        <div><span className="text-akfa-muted">Total</span><div className="font-medium">{formatBytes(metric.traffic_total_bytes)}</div></div>
        <div><span className="text-akfa-muted">Источник</span><div className="font-medium">{metric.traffic_source === "xray_inbound" ? "Xray inbound" : "Users sum"}</div></div>
      </div>
      {metric.errors.length ? <div className="mt-2 text-xs text-akfa-red">{metric.errors.join("; ")}</div> : null}
    </div>
  );
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
            <Table>
              <thead>
                <tr className="border-b border-akfa-line text-akfa-muted">
                  <th className="py-2">Название</th>
                  <th>IP-адрес</th>
                  <th>Локация</th>
                  <th>Порт VLESS</th>
                  <th>Статус</th>
                  <th>Синхронизация</th>
                  <th className="text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => (
                  <tr key={node.id} className="border-b border-akfa-line last:border-0">
                    <td className="py-3 font-medium">{node.name}</td>
                    <td>{node.ip_address}</td>
                    <td>{node.location || "-"}</td>
                    <td>{node.vless_port}</td>
                    <td><StatusBadge value={node.status} /></td>
                    <td>{syncLabel(node)}</td>
                    <td className="flex justify-end gap-2 py-2">
                      <Button variant="secondary" onClick={() => onPreview(node.id)}><FileJson size={15} />Конфиг</Button>
                      <Button variant="ghost" onClick={() => onSelect(node)}>Открыть</Button>
                      <Button variant="danger" onClick={() => onDelete(node)}><Trash2 size={15} />Удалить</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
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
  const [loading, setLoading] = useState<"save" | "check" | "sni" | null>(null);
  const [success, setSuccess] = useState("");
  const [sniMode, setSniMode] = useState("preset");
  const [sniResult, setSniResult] = useState<SniCheckResult | null>(null);
  const [sshResult, setSshResult] = useState<SshCheckResult | null>(null);
  const [savedNode, setSavedNode] = useState<NodeRead | null>(null);

  function update(key: string, value: string | number) {
    setForm({ ...form, [key]: value });
    setErrors({ ...errors, [key]: "" });
    setSuccess("");
    setSshResult(null);
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
  onAction,
  onPreview,
  onBack,
  onUpdated,
  onNotice,
  onDelete
}: {
  node: NodeRead | null;
  onAction: (action: NodeAction) => void;
  onPreview: () => void;
  onBack: () => void;
  onUpdated: (node: NodeRead) => Promise<void>;
  onNotice: (value: string, applyStatus?: ConfigApplySummary | null) => void;
  onDelete?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Record<string, string | number>>({});
  const [saving, setSaving] = useState(false);

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

  if (!node) {
    return <EmptyPanel title="Сервер не выбран" text="Откройте список серверов и выберите VPS для просмотра деталей." />;
  }

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
          <Button variant="secondary" onClick={() => onAction("check")}>Проверить подключение</Button>
          <Button variant="secondary" onClick={() => onAction("verify")}><ShieldCheck size={16} />Проверить состояние Xray</Button>
          <Button variant="secondary" onClick={() => onAction("dry-run")}>Сухой запуск установки</Button>
          <Button onClick={() => onAction(node.status === "online" ? "apply-config" : "install")}><Play size={16} />{node.status === "online" ? "Применить конфиг" : "Установить Xray"}</Button>
          <Button variant="secondary" onClick={() => setEditing((value) => !value)}><Save size={16} />Редактировать</Button>
          <Button variant="ghost" onClick={onPreview}><FileJson size={16} />Предпросмотр конфига</Button>
          {onDelete ? <Button variant="danger" onClick={onDelete}><Trash2 size={16} />Удалить сервер</Button> : null}
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
  onAdd
}: {
  nodes: NodeRead[];
  node: NodeRead | null;
  onSelect: (node: NodeRead) => void;
  onAction: (action: NodeAction) => void;
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
  return (
    <div className="grid gap-5">
      <PageHeader
        title="Установка Xray"
        description="Проверьте SSH, выполните сухой запуск и только затем запустите реальную установку."
      />
      <Card>
        <CardContent className="grid gap-4 lg:grid-cols-[360px_1fr]">
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
          {node ? (
            <div className="grid gap-2 rounded-md border border-akfa-line bg-akfa-soft p-3 text-sm md:grid-cols-4">
              <Line k="VPS IP" v={node.ip_address} />
              <Line k="VLESS port" v={node.vless_port} />
              <Line k="SNI / Reality target" v={node.sni} />
              <Line k="Fingerprint" v={node.fingerprint} />
              <Line k="Flow" v="xtls-rprx-vision" />
              <Line k="Security" v="reality" />
              <Line k="Network" v="tcp" />
              <Line k="Статус" v={translateStatus(node.status)} />
            </div>
          ) : null}
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-3">
        <StepCard
          step="1"
          title="Проверить подключение"
          text="Проверяет SSH-доступ без вывода пароля и без установки пакетов."
          action={<Button variant="secondary" disabled={!node} onClick={() => onAction("check")}><ShieldCheck size={16} />Проверить</Button>}
        />
        <StepCard
          step="2"
          title="Сухой запуск"
          text="Генерирует команды и конфиг, чтобы увидеть будущие действия без изменения сервера."
          action={<Button variant="secondary" disabled={!node} onClick={() => onAction("dry-run")}><FileJson size={16} />Сухой запуск</Button>}
        />
        <StepCard
          step="3"
          title={node?.status === "online" ? "Применить конфиг" : "Установить Xray"}
          text={node?.status === "online" ? "Обновляет Xray config без переустановки бинарника и перезапускает сервис." : "Выполняет установку на VPS. Перед запуском появится подтверждение."}
          action={<Button disabled={!node} onClick={() => onAction(node?.status === "online" ? "apply-config" : "install")}><Play size={16} />{node?.status === "online" ? "Применить конфиг" : "Установить Xray"}</Button>}
          warning
        />
      </div>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <h2 className="font-semibold">Журнал команд</h2>
          <Button variant="secondary" disabled={!node} onClick={() => onAction("verify")}><ShieldCheck size={16} />Проверить состояние Xray</Button>
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
                const active = departmentUsers.filter((user) => user.status === "active").length;
                const disabled = departmentUsers.filter((user) => user.status !== "active").length;
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
                    <div className="mt-3 grid gap-2 text-sm md:grid-cols-4">
                      <Line k="Всего пользователей" v={departmentUsers.length} />
                      <Line k="Активных" v={active} />
                      <Line k="Отключенных" v={disabled} />
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
    <div className="grid gap-5">
      <PageHeader
        title="Профили доступа"
        description="Маршрутизация, лимиты, срок действия и шаблон клиентской конфигурации."
        action={<div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={onSeed}>Базовые профили</Button><Button onClick={onNew}><Plus size={16} />Новый профиль</Button></div>}
      />
      <Card>
        <CardContent>
          {!items.length ? (
            <EmptyPanel
              title="Профили доступа пока не созданы"
              text="Создайте профиль или добавьте базовые политики доступа, чтобы назначать их отделам и пользователям."
              action={<Button onClick={onSeed}>Создать базовые профили</Button>}
            />
          ) : (
            <Table>
              <thead>
                <tr className="border-b border-akfa-line text-akfa-muted">
                  <th className="py-2">Название</th>
                  <th>Режим маршрутизации</th>
                  <th>Лимит</th>
                  <th>Срок</th>
                  <th>Шаблон</th>
                  <th className="text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-akfa-line last:border-0">
                    <td className="py-3">
                      <div className="font-medium">{item.name}</div>
                      <div className="text-xs text-akfa-muted">{item.description || "Описание не указано"}</div>
                    </td>
                    <td><StatusBadge value={item.routing_mode} /></td>
                    <td>{item.traffic_limit_bytes ? formatBytes(item.traffic_limit_bytes) : "Без лимита"}</td>
                    <td>{item.expires_in_days ? `${item.expires_in_days} дн.` : "Без срока"}</td>
                    <td><StatusBadge value={item.client_template} /></td>
                    <td className="flex justify-end gap-2 py-2">
                      <Button variant="secondary" onClick={() => onEdit(item)}>Редактировать</Button>
                      <Button variant="danger" onClick={() => onDelete(item)}><Trash2 size={15} />Удалить</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
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
  onNotice
}: {
  users: VpnUser[];
  nodes: NodeRead[];
  departments: Department[];
  profiles: AccessProfile[];
  onCreated: (user: VpnUser) => void;
  onSelect: (user: VpnUser) => void;
  onDelete: (user: VpnUser) => void;
  onNotice: (value: string) => void;
}) {
  const [form, setForm] = useState(defaultUserForm);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [grouped, setGrouped] = useState(false);
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
    if (!form.first_name.trim() || !form.last_name.trim() || !form.username.trim()) {
      onNotice("Укажите имя, фамилию и логин пользователя");
      return;
    }
    if (form.status === "active" && activeNodeIds.length > 0 && !form.allowed_node_ids.length) {
      onNotice("Выберите хотя бы один доступный сервер");
      return;
    }
    const payload = userPayload(form);
    try {
      const created = await api.createUser(payload);
      setForm({ ...defaultUserForm, allowed_node_ids: activeNodeIds, primary_node_id: activeNodeIds[0] ? String(activeNodeIds[0]) : "" });
      onCreated(created);
      onNotice(formatApplyStatusMessage("Пользователь создан", created.apply_status));
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Пользователь не создан");
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
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[minmax(0,1fr)_340px]">
      <PageHeader title="Пользователи VPN" description="Создание доступов, подписки, статусы и лимиты трафика." />
      <Card className="overflow-hidden">
        <CardHeader className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <h2 className="font-semibold">Список пользователей</h2>
            <div className="mt-0.5 text-xs text-akfa-muted">Показано {filteredUsers.length} из {visibleUserRows.length}</div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 px-4 py-3">
          <div className="grid items-center gap-2 lg:grid-cols-[minmax(260px,1fr)_150px_180px_auto]">
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
                  <div className="p-2">
                    <UsersTable users={group.users} departments={departments} profiles={profiles} onSelect={onSelect} onDelete={onDelete} />
                  </div>
                </details>
                ))}
              </div>
            )
          ) : (
            <div className="w-full">
              <UsersTable users={filteredUsers} departments={departments} profiles={profiles} onSelect={onSelect} onDelete={onDelete} />
            </div>
          )}
        </CardContent>
      </Card>
      <Card className="xl:sticky xl:top-20">
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
          <Button className="mt-1 h-9" onClick={create}><UserPlus size={16} />Создать пользователя</Button>
        </CardContent>
      </Card>
    </div>
  );
}

function UsersTable({
  users,
  departments,
  profiles,
  onSelect,
  onDelete
}: {
  users: VpnUser[];
  departments: Department[];
  profiles: AccessProfile[];
  onSelect: (user: VpnUser) => void;
  onDelete: (user: VpnUser) => void;
}) {
  if (!users.length) return <EmptyPanel title="Ничего не найдено" text="Измените поиск или фильтры." />;
  return (
    <div className="overflow-x-auto rounded-md border border-akfa-line">
      <Table className="min-w-[860px] table-fixed">
        <thead className="bg-zinc-50">
          <tr className="border-b border-akfa-line text-xs font-semibold text-akfa-muted">
            <th className="w-[24%] py-2.5 pl-3 pr-4">ФИО</th>
            <th className="w-[15%] px-3">Логин</th>
            <th className="w-[14%] px-3">Отдел</th>
            <th className="w-[20%] px-3">Профиль</th>
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
              <td className="px-3 py-2.5"><StatusBadge value={user.online_status || "offline"} /></td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">{formatBytes(user.used_total_bytes)}</td>
              <td className="px-3 py-2">
                <div className="flex flex-nowrap justify-end gap-1">
                  <Button className="h-8 w-8 px-0" variant="secondary" title="Доступ и подписка" aria-label="Доступ и подписка" onClick={() => onSelect(user)}><Link2 size={15} /></Button>
                  <Button className="h-8 w-8 px-0" variant="danger" title="Удалить" aria-label="Удалить" onClick={() => onDelete(user)}><Trash2 size={15} /></Button>
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
  onUpdated: (user: VpnUser) => void;
  onBack: () => void;
  onNotice: (value: string) => void;
}) {
  const [accessBlocks, setAccessBlocks] = useState<PreviewBlock[]>([]);
  const [vlessEntries, setVlessEntries] = useState<SubscriptionVlessUri[]>([]);
  const [nodeSelection, setNodeSelection] = useState<{ ids: number[]; primaryId: number | null }>({ ids: [], primaryId: null });
  const [activeTab, setActiveTab] = useState("Ссылка подписки");
  const [confirm, setConfirm] = useState<ConfirmState>(null);

  useEffect(() => {
    if (!user) {
      setAccessBlocks([]);
      setVlessEntries([]);
      return;
    }
    setNodeSelection({ ids: user.allowed_node_ids || [], primaryId: user.primary_node_id || null });
    const subscriptionUrl = absoluteUrl(`/sub/${user.subscription_token}`);
    setAccessBlocks([{ label: "Ссылка подписки", value: subscriptionUrl }]);
    setVlessEntries([]);
    setActiveTab("Ссылка подписки");
    api
      .subscriptionPreview(user.id)
      .then((data) => {
        setVlessEntries(data.vless_uris || []);
        setAccessBlocks(
          [
            { label: "Ссылка подписки", value: absoluteUrl(data.subscription_url || `/sub/${user.subscription_token}`) },
            { label: "VLESS URI", value: data.vless_uri || "", mono: true },
            { label: "Xray JSON", value: prettyJson(data.xray_json), mono: true },
            { label: "sing-box JSON", value: prettyJson(data.sing_box), mono: true },
          ].filter((item) => item.value)
        );
      })
      .catch((error) => onNotice(error instanceof Error ? error.message : "Подписка недоступна"));
  }, [onNotice, user]);

  if (!user) return <EmptyPanel title="Пользователь не выбран" text="Откройте список пользователей и выберите доступ для просмотра." />;

  const subscriptionUrl = absoluteUrl(`/sub/${user.subscription_token}`);
  const tokenMasked = maskToken(user.subscription_token);
  const userId = user.id;
  const currentTab = activeTab === "QR-код" ? null : accessBlocks.find((block) => block.label === activeTab) || accessBlocks[0];
  const qrValue = subscriptionUrl;

  async function action(actionName: "enable" | "disable" | "regenerate-uuid" | "regenerate-subscription" | "reset-traffic", message: string) {
    try {
      const updated = await api.userAction(userId, actionName);
      onUpdated(updated);
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
        expires_at: user.expires_at || null,
        status: user.status,
        allowed_node_ids: nodeSelection.ids,
        primary_node_id: nodeSelection.primaryId
      });
      onUpdated(updated);
      onNotice(formatApplyStatusMessage("Доступные серверы сохранены", updated.apply_status));
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Серверы пользователя не сохранены");
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
          <CardHeader><h2 className="font-semibold">Доступные серверы</h2></CardHeader>
          <CardContent className="grid gap-3">
            <NodeAccessSelector
              nodes={nodes}
              selectedIds={nodeSelection.ids}
              primaryNodeId={nodeSelection.primaryId}
              onChange={(ids, primaryId) => setNodeSelection({ ids, primaryId })}
            />
            <Button onClick={saveNodeAccess}><Save size={16} />Сохранить серверы</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><h2 className="font-semibold">Действия</h2></CardHeader>
          <CardContent className="grid gap-2">
          <Button variant="secondary" onClick={copyLink}><Copy size={16} />Скопировать ссылку</Button>
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
    </div>
    <ConfirmDialog open={Boolean(confirm)} title={confirm?.title || ""} text={confirm?.text || ""} confirmLabel={confirm?.confirmLabel} onCancel={() => setConfirm(null)} onConfirm={() => confirm?.onConfirm()} />
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
        description="Снимки отправленного и полученного трафика, а также ручной сбор статистики с Xray API."
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={resetSort}>Сбросить сортировку</Button>
            <Button variant="secondary" onClick={collect}>Собрать статистику сейчас</Button>
          </div>
        }
      />
      <Card>
        <CardContent className="grid gap-4">
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
                    <th className="px-3 py-3 font-medium">Последний сбор</th>
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
                      <td className="whitespace-nowrap px-3 py-4 text-akfa-muted">{row.last_traffic_collected_at ? formatDate(row.last_traffic_collected_at) : row.collected ? "Собрана" : "0 Б, ожидает сбора"}</td>
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
  return (
    <div className="grid gap-5">
      <PageHeader title="Настройки администратора" description="Текущие механизмы безопасности панели." />
      <Card>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <StatusBadge value="secure_cookies" />
          <StatusBadge value="totp_2fa" />
          <StatusBadge value="csrf" />
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

function EmptyPanel({ title, text, action }: { title: string; text: string; action?: JSX.Element }) {
  return (
    <div className="rounded-md border border-dashed border-akfa-line bg-akfa-soft p-6">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-akfa-muted">{text}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

function Message({ tone, text }: { tone: "success" | "error" | "warning"; text: string }) {
  const classes = {
    success: "border-green-200 bg-green-50 text-akfa-green",
    error: "border-red-200 bg-red-50 text-akfa-red",
    warning: "border-amber-200 bg-amber-50 text-amber-800"
  };
  const Icon = tone === "success" ? CheckCircle2 : tone === "error" ? AlertTriangle : AlertTriangle;
  return (
    <div className={`flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${classes[tone]}`}>
      <Icon className="mt-0.5 shrink-0" size={16} />
      <span>{text}</span>
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
    traffic_limit_bytes: form.traffic_limit_gb ? Math.round(Number(form.traffic_limit_gb) * 1024 * 1024 * 1024) : null,
    expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
    status: form.status
  };
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

function formatApplyStatusMessage(base: string, applyStatus?: ConfigApplySummary | null) {
  if (!applyStatus || applyStatus.failed === 0) return base;
  const failedNodes = applyStatus.results.filter((item) => !item.ok).map((item) => item.node_name).join(", ");
  return `${base}, но конфиг не применился${failedNodes ? ` на нодах: ${failedNodes}` : ""}`;
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
    failed: "ошибка"
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

function maskToken(value: string) {
  if (value.length <= 12) return value;
  return `${value.slice(0, 6)}...${value.slice(-6)}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default App;
