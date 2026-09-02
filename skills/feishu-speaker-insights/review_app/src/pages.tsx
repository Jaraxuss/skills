import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import WaveSurfer from "wavesurfer.js";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Clock3,
  FileAudio,
  FileText,
  FolderOpen,
  GitBranch,
  Headphones,
  Layers3,
  LayoutList,
  Loader2,
  Pause,
  Play,
  Plus,
  Power,
  PowerOff,
  RotateCcw,
  Save,
  Search,
  Settings2,
  ShieldAlert,
  SlidersHorizontal,
  Trash2,
  UserPlus,
  UsersRound,
  X,
} from "lucide-react";
import {
  api,
  getCandidates,
  getCustomers,
  getFiles,
  getProfileCatalogue,
  getProfileVersion,
  getProfileVersions,
  getSession,
  getSessions,
  getSummary,
  getTranscriptPreview,
  getTranscriptSpeakers,
  retryFailedSession,
} from "./api";
import type {
  Assignment,
  Cluster,
  Customer,
  Decision,
  FileItem,
  Label,
  MeetingDraft,
  NewPerson,
  Package,
  Person,
  ProfilePage,
  ProfileSummary,
  ProfileVersionDetail,
  ProfileVersionSummary,
  ReviewProgress as ReviewProgressData,
  Segment,
  Session,
  Summary,
  TranscriptPreview,
  ValidationResult,
} from "./types";
import {
  AppShell,
  EmptyState,
  IconButton,
  LoadingState,
  MetricCard,
  PageHeader,
  ProgressBar,
  QuickAction,
  StatusBadge,
  SummaryStatus,
  TaskStatusIcon,
} from "./ui";
import {
  assignmentCount,
  assignmentValue,
  clamp,
  createDraftPerson,
  displayLabel,
  fileStem,
  formatDate,
  formatSeconds,
  labelIsHandled,
  organizationText,
  personText,
  riskText,
  statusText,
} from "./utils";

type MessageProps = { message: string; onClose?: () => void };

export function InlineMessage({ message, onClose }: MessageProps) {
  if (!message) return null;
  return (
    <div className="inline-message">
      <AlertTriangle size={16} />
      <span>{message}</span>
      {onClose && (
        <IconButton label="关闭提示" onClick={onClose}>
          <X size={15} />
        </IconButton>
      )}
    </div>
  );
}

function TaskRow({
  session,
  action,
}: {
  session: Session;
  action?: ReactNode;
}) {
  const taskType =
    session.kind === "profile_revision"
      ? "版本修订"
      : session.kind === "profile_expansion"
        ? "声纹扩充"
        : "首次建库";
  return (
    <article className="task-row">
      <Link
        to={`/enrollments/${encodeURIComponent(session.session_id)}`}
        className="task-row-link"
      >
        <div className="task-row-title">
          <TaskStatusIcon status={session.status} />
          <div>
            <strong>{session.display_title || "声纹审核任务"}</strong>
            <span>
              {taskType} · {session.customer_name || session.customer_id || "未命名客户"}
              {session.kind === "enrollment"
                ? ` · ${session.recording_count || 1} 份录音`
                : ""}
            </span>
          </div>
        </div>
        <StatusBadge status={session.status} />
        <time>{formatDate(session.updated_at || session.created_at)}</time>
      </Link>
      {action && <div className="task-row-action">{action}</div>}
    </article>
  );
}

export function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [message, setMessage] = useState("");
  const load = async () => {
    try {
      setSummary((await getSummary()) as Summary);
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 12000);
    return () => window.clearInterval(timer);
  }, []);
  const tasks = summary?.tasks || {};
  return (
    <AppShell>
      <PageHeader
        title="概览"
        actions={<QuickAction to="/enrollments/new">新建建库任务</QuickAction>}
      />
      {message && (
        <InlineMessage message={message} onClose={() => setMessage("")} />
      )}
      {!summary ? (
        <LoadingState label="正在读取工作区概览…" />
      ) : (
        <>
          <section className="metric-grid">
            <MetricCard
              label="客户"
              value={summary.customers_total}
              helper="已接入本机目录"
              tone="cyan"
              icon={<UsersRound size={18} />}
            />
            <MetricCard
              label="待审核任务"
              value={tasks.review_required || 0}
              helper="需要人工分配片段"
              tone="amber"
              icon={<LayoutList size={18} />}
            />
            <MetricCard
              label="有效声纹"
              value={summary.active_profile_people}
              helper={`${summary.profile_versions_total} 个历史版本`}
              tone="indigo"
              icon={<CircleDot size={18} />}
            />
            <MetricCard
              label="处理中"
              value={
                (tasks.queued || 0) +
                (tasks.preparing || 0) +
                (tasks.committing || 0)
              }
              helper="本地 Worker 队列"
              tone="green"
              icon={<Clock3 size={18} />}
            />
          </section>
          <div className="dashboard-grid">
            <section className="content-card">
              <div className="card-heading">
                <div>
                  <span className="section-kicker">近期动态</span>
                  <h2>最近声纹任务</h2>
                </div>
                <Link className="text-link" to="/enrollments">
                  查看全部 <ChevronRight size={15} />
                </Link>
              </div>
              {summary.recent_sessions.length ? (
                <div className="task-list">
                  {summary.recent_sessions.slice(0, 6).map((session) => (
                    <TaskRow key={session.session_id} session={session} />
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={<FileAudio size={22} />}
                  title="还没有声纹任务"
                  description="从一个客户目录开始建立第一份声纹档案。"
                  action={
                    <QuickAction to="/enrollments/new">创建任务</QuickAction>
                  }
                />
              )}
            </section>
            <aside className="content-card attention-card">
              <div className="card-heading">
                <div>
                  <span className="section-kicker">需要关注</span>
                  <h2>任务状态</h2>
                </div>
                <Settings2 size={17} className="subtle-icon" />
              </div>
              <div className="status-overview">
                <div>
                  <span>待审核</span>
                  <SummaryStatus summary={summary} status="review_required" />
                </div>
                <div>
                  <span>处理中</span>
                  <SummaryStatus summary={summary} status="preparing" />
                </div>
                <div>
                  <span>已建库</span>
                  <SummaryStatus summary={summary} status="committed" />
                </div>
                <div>
                  <span>失败</span>
                  <SummaryStatus summary={summary} status="failed" />
                </div>
              </div>
              <div className="attention-note">
                <ShieldAlert size={16} />
                <span>
                  {summary.pending_candidates
                    ? `${summary.pending_candidates} 个声纹扩充候选等待处理。`
                    : "当前没有待处理的声纹扩充候选。"}
                </span>
              </div>
            </aside>
          </div>
        </>
      )}
    </AppShell>
  );
}

const taskFilters = [
  "all",
  "queued",
  "preparing",
  "review_required",
  "committed",
  "failed",
  "cancelled",
];

export function EnrollmentListPage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [filter, setFilter] = useState("all");
  const [customerId, setCustomerId] = useState("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [retryingSessionId, setRetryingSessionId] = useState("");
  const load = async () => {
    try {
      const [sessionResult, customerResult] = await Promise.all([
        getSessions(),
        getCustomers(),
      ]);
      setSessions(sessionResult.sessions as Session[]);
      setCustomers(customerResult.customers as Customer[]);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, []);
  const restart = async (event: MouseEvent, sessionId: string) => {
    event.preventDefault();
    event.stopPropagation();
    try {
      await api(
        `/api/v1/enrollment-sessions/${encodeURIComponent(sessionId)}/restart`,
        { method: "POST", body: "{}" },
      );
      setMessage("已按原素材重新创建准备任务。");
      await load();
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  const retryEdit = async (event: MouseEvent, session: Session) => {
    event.preventDefault();
    event.stopPropagation();
    setRetryingSessionId(session.session_id);
    try {
      await retryFailedSession(session.session_id, session.revision);
      navigate(`/enrollments/${encodeURIComponent(session.session_id)}`);
    } catch (error) {
      setMessage((error as Error).message);
      await load();
    } finally {
      setRetryingSessionId("");
    }
  };
  const filtered = sessions.filter((session) => {
    if (filter !== "all" && session.status !== filter) return false;
    if (customerId !== "all" && session.customer_id !== customerId)
      return false;
    const text =
      `${session.display_title || ""} ${session.customer_name || ""} ${session.session_id}`.toLocaleLowerCase();
    return !query.trim() || text.includes(query.trim().toLocaleLowerCase());
  });
  return (
    <AppShell>
      <PageHeader
        title="声纹任务"
        actions={<QuickAction to="/enrollments/new">新建建库任务</QuickAction>}
      />
      {message && (
        <InlineMessage message={message} onClose={() => setMessage("")} />
      )}
      <section className="toolbar-card">
        <div className="search-field">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索客户或录音名称"
          />
        </div>
        <div className="toolbar-filters">
          <SlidersHorizontal size={15} />
          <select
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
          >
            <option value="all">全部客户</option>
            {customers.map((customer) => (
              <option key={customer.customer_id} value={customer.customer_id}>
                {customer.name}
              </option>
            ))}
          </select>
        </div>
      </section>
      <section className="content-card task-table-card">
        <div className="filter-tabs">
          {taskFilters.map((status) => (
            <button
              key={status}
              type="button"
              className={filter === status ? "filter-tab active" : "filter-tab"}
              onClick={() => setFilter(status)}
            >
              {status === "all" ? "全部" : statusText(status)}
              <span>
                {status === "all"
                  ? sessions.length
                  : sessions.filter((item) => item.status === status).length}
              </span>
            </button>
          ))}
        </div>
        {loading ? (
          <LoadingState label="正在读取任务…" />
        ) : filtered.length ? (
          <div className="task-list">
            {filtered.map((session) => (
              <TaskRow
                key={session.session_id}
                session={session}
                action={
                  session.status === "cancelled" &&
                  session.kind === "enrollment" ? (
                    <button
                      type="button"
                      className="icon-text-button"
                      onClick={(event) =>
                        void restart(event, session.session_id)
                      }
                    >
                      <RotateCcw size={14} />
                      重新开始
                    </button>
                  ) : session.status === "failed" &&
                    session.can_retry_edit ? (
                    <button
                      type="button"
                      className="icon-text-button"
                      disabled={retryingSessionId === session.session_id}
                      onClick={(event) => void retryEdit(event, session)}
                    >
                      {retryingSessionId === session.session_id ? (
                        <Loader2 size={14} className="spin" />
                      ) : (
                        <RotateCcw size={14} />
                      )}
                      {retryingSessionId === session.session_id
                        ? "正在恢复"
                        : "继续编辑"}
                    </button>
                  ) : undefined
                }
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<LayoutList size={22} />}
            title="没有符合条件的任务"
            description="可以清除筛选，或新建一项首次建库任务。"
          />
        )}
      </section>
    </AppShell>
  );
}

type AttendeeDraft = {
  name: string;
  role: string;
  organization: "customer" | "yingdao" | "external";
};

export function NewEnrollmentPage() {
  const navigate = useNavigate();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState("");
  const [files, setFiles] = useState<FileItem[]>([]);
  const [meetings, setMeetings] = useState<MeetingDraft[]>([
    { audio: "", transcript: "" },
  ]);
  const [attendees, setAttendees] = useState<AttendeeDraft[]>([
    { name: "", role: "", organization: "customer" },
  ]);
  const [preview, setPreview] = useState<TranscriptPreview | null>(null);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [findingSpeakers, setFindingSpeakers] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    void getCustomers()
      .then((result) => setCustomers(result.customers as Customer[]))
      .catch((error) => setMessage((error as Error).message));
  }, []);
  useEffect(() => {
    if (!customerId) {
      setFiles([]);
      setMeetings([{ audio: "", transcript: "" }]);
      setPreview(null);
      return;
    }
    setLoadingFiles(true);
    setPreview(null);
    void getFiles(customerId)
      .then((result) => {
        const unique = Array.from(
          new Map(
            (result.files as FileItem[]).map((item) => [
              `${item.kind}:${item.path}`,
              item,
            ]),
          ).values(),
        );
        const transcripts = new Map(
          unique
            .filter((item) => item.kind === "transcript")
            .map((item) => [fileStem(item.path), item.path]),
        );
        const defaults = unique
          .filter((item) => item.kind === "audio")
          .map((item) => ({
            audio: item.path,
            transcript: transcripts.get(fileStem(item.path)) || "",
          }));
        setFiles(unique);
        setMeetings(
          defaults.length ? defaults : [{ audio: "", transcript: "" }],
        );
      })
      .catch((error) => setMessage((error as Error).message))
      .finally(() => setLoadingFiles(false));
  }, [customerId]);
  const customer = customers.find((item) => item.customer_id === customerId);
  const audioFiles = files.filter((item) => item.kind === "audio");
  const transcriptFiles = files.filter((item) => item.kind === "transcript");
  const pairedCount = meetings.filter(
    (item) => item.audio && item.transcript,
  ).length;
  const updateMeeting = (
    index: number,
    field: "audio" | "transcript",
    value: string,
  ) =>
    setMeetings((current) =>
      current.map((meeting, itemIndex) => {
        if (itemIndex !== index) return meeting;
        const next = { ...meeting, [field]: value };
        if (field === "audio")
          next.transcript =
            transcriptFiles.find(
              (file) => fileStem(file.path) === fileStem(value),
            )?.path || "";
        return next;
      }),
    );
  const togglePreview = async (path: string) => {
    if (!customerId || !path) return;
    if (preview?.path === path) {
      setPreview(null);
      return;
    }
    try {
      setPreview({ path, ...(await getTranscriptPreview(customerId, path)) });
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  const batchAddAttendees = async () => {
    if (!customerId || findingSpeakers) return;
    if (!transcriptFiles.length) {
      setMessage("当前客户目录没有可识别的转写文件。");
      return;
    }
    setFindingSpeakers(true);
    try {
      const result = (await getTranscriptSpeakers(
        customerId,
        transcriptFiles.map((item) => item.path),
      )) as { labels: string[] };
      const existing = new Set(
        attendees.map((person) => person.name.trim()).filter(Boolean),
      );
      const additions = result.labels
        .filter((label) => !existing.has(label))
        .map((name) => ({ name, role: "", organization: "customer" as const }));
      if (additions.length)
        setAttendees((current) => [
          ...current.filter((person) => person.name.trim()),
          ...additions,
        ]);
      setMessage(
        additions.length
          ? `已从 ${transcriptFiles.length} 份转写添加 ${additions.length} 位说话人。`
          : "没有发现新的“说话人 N”标签，或它们已在参会人列表中。",
      );
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setFindingSpeakers(false);
    }
  };
  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (
      !customer ||
      meetings.some((item) => !item.audio || !item.transcript) ||
      attendees.some((item) => !item.name.trim())
    ) {
      setMessage("请完整填写客户、每组录音与转写，以及参会人。");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api("/api/v1/enrollment-sessions", {
        method: "POST",
        body: JSON.stringify({
          manifest: {
            schema_version: 1,
            customer: { id: customer.customer_id, name: customer.name },
            meetings,
            attendees,
            known_label_map: {},
            excluded_labels: [],
          },
        }),
      });
      navigate(`/enrollments/${encodeURIComponent(result.session_id)}`);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <AppShell>
      <PageHeader
        eyebrow="建库任务 / 新建"
        title="新建任务"
        actions={
          <Link className="button-secondary" to="/enrollments">
            <ArrowLeft size={16} />
            返回任务
          </Link>
        }
      />
      {message && (
        <InlineMessage message={message} onClose={() => setMessage("")} />
      )}
      <form className="new-enrollment-layout" onSubmit={create}>
        <div className="new-enrollment-main">
          <section className="form-card">
            <div className="form-card-heading">
              <div>
                <span className="section-kicker">01 · 工作范围</span>
                <h2>选择客户</h2>
              </div>
              <FolderOpen size={19} className="section-icon" />
            </div>
            <label className="field-label">
              客户目录
              <select
                value={customerId}
                onChange={(event) => setCustomerId(event.target.value)}
              >
                <option value="">选择客户目录</option>
                {customers.map((item) => (
                  <option value={item.customer_id} key={item.customer_id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="field-hint">
              客户列表由本机客户根目录实时读取，不需要先通过 OpenClaw 创建。
            </p>
          </section>
          <section className="form-card">
            <div className="form-card-heading">
              <div>
                <span className="section-kicker">02 · 建库素材</span>
                <h2>录音与转写</h2>
              </div>
              <FileAudio size={19} className="section-icon" />
            </div>
            {customerId && (
              <div className="source-summary">
                <span>
                  {loadingFiles
                    ? "正在扫描客户目录…"
                    : `自动加载 ${meetings.length} 份录音`}
                </span>
                <span>{pairedCount} 份已配对转写</span>
              </div>
            )}
            {meetings.map((meeting, index) => (
              <div className="meeting-card" key={`${meeting.audio}-${index}`}>
                <div className="meeting-card-title">
                  <strong>录音 {String(index + 1).padStart(2, "0")}</strong>
                  {meetings.length > 1 && (
                    <IconButton
                      label="移除这组素材"
                      variant="danger"
                      onClick={() =>
                        setMeetings((items) =>
                          items.filter((_, itemIndex) => itemIndex !== index),
                        )
                      }
                    >
                      <Trash2 size={15} />
                    </IconButton>
                  )}
                </div>
                <div className="field-grid">
                  <label className="field-label">
                    录音
                    <select
                      value={meeting.audio}
                      onChange={(event) =>
                        updateMeeting(index, "audio", event.target.value)
                      }
                    >
                      <option value="">选择客户目录中的录音</option>
                      {audioFiles.map((item) => (
                        <option value={item.path} key={item.path}>
                          {item.relative_path}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field-label">
                    对应转写
                    <div className="select-with-action">
                      <select
                        value={meeting.transcript}
                        onChange={(event) =>
                          updateMeeting(index, "transcript", event.target.value)
                        }
                      >
                        <option value="">选择对应转写</option>
                        {transcriptFiles.map((item) => (
                          <option value={item.path} key={item.path}>
                            {item.relative_path}
                          </option>
                        ))}
                      </select>
                      <IconButton
                        label="预览转写"
                        onClick={() => void togglePreview(meeting.transcript)}
                        disabled={!meeting.transcript}
                      >
                        <FileText size={15} />
                      </IconButton>
                    </div>
                  </label>
                </div>
                {preview?.path === meeting.transcript && (
                  <pre className="transcript-preview">
                    <strong>{preview.relative_path}</strong>
                    {"\n\n"}
                    {preview.content}
                    {preview.truncated && "\n\n… 预览仅显示前 20,000 个字符。"}
                  </pre>
                )}
              </div>
            ))}
            <button
              type="button"
              className="button-secondary add-material"
              onClick={() =>
                setMeetings((items) => [
                  ...items,
                  { audio: "", transcript: "" },
                ])
              }
            >
              <Plus size={15} />
              添加一组录音和转写
            </button>
          </section>
          <section className="form-card">
            <div className="form-card-heading">
              <div>
                <span className="section-kicker">03 · 参会人</span>
                <h2>参会人名单</h2>
              </div>
              <UsersRound size={19} className="section-icon" />
            </div>
            <p className="field-hint">
              填写真人姓名和职位即可，不要求与飞书转写标签一致；标签归属会在审核工作区确认。
            </p>
            <div className="attendee-list">
              {attendees.map((person, index) => (
                <div className="attendee-row" key={index}>
                  <input
                    placeholder="姓名"
                    value={person.name}
                    onChange={(event) =>
                      setAttendees((items) =>
                        items.map((item, itemIndex) =>
                          itemIndex === index
                            ? { ...item, name: event.target.value }
                            : item,
                        ),
                      )
                    }
                  />
                  <input
                    placeholder="职位（可选）"
                    value={person.role}
                    onChange={(event) =>
                      setAttendees((items) =>
                        items.map((item, itemIndex) =>
                          itemIndex === index
                            ? { ...item, role: event.target.value }
                            : item,
                        ),
                      )
                    }
                  />
                  <select
                    value={person.organization}
                    onChange={(event) =>
                      setAttendees((items) =>
                        items.map((item, itemIndex) =>
                          itemIndex === index
                            ? {
                                ...item,
                                organization: event.target
                                  .value as AttendeeDraft["organization"],
                              }
                            : item,
                        ),
                      )
                    }
                  >
                    <option value="customer">客户</option>
                    <option value="yingdao">我方</option>
                    <option value="external">外部</option>
                  </select>
                  <IconButton
                    label="删除参会人"
                    onClick={() =>
                      setAttendees((items) =>
                        items.filter((_, itemIndex) => itemIndex !== index),
                      )
                    }
                  >
                    <X size={15} />
                  </IconButton>
                </div>
              ))}
            </div>
            <div className="attendee-actions">
              <button
                type="button"
                className="button-secondary"
                onClick={() =>
                  setAttendees((items) => [
                    ...items,
                    { name: "", role: "", organization: "customer" },
                  ])
                }
              >
                <UserPlus size={15} />
                添加参会人
              </button>
              <button
                type="button"
                className="button-secondary"
                disabled={!customerId || findingSpeakers}
                onClick={() => void batchAddAttendees()}
              >
                {findingSpeakers ? (
                  <Loader2 size={15} className="spin" />
                ) : (
                  <Search size={15} />
                )}
                {findingSpeakers ? "正在识别…" : "从转写批量添加"}
              </button>
            </div>
          </section>
        </div>
        <aside className="form-summary">
          <div className="summary-sticky">
            <span className="section-kicker">任务摘要</span>
            <h2>{customer?.name || "尚未选择客户"}</h2>
            <p>准备完成后进入审核工作区，正式声纹只在确认建库后生成。</p>
            <div className="summary-stat">
              <span>录音组</span>
              <strong>{meetings.filter((item) => item.audio).length}</strong>
            </div>
            <div className="summary-stat">
              <span>已配对</span>
              <strong>{pairedCount}</strong>
            </div>
            <div className="summary-stat">
              <span>参会人</span>
              <strong>
                {attendees.filter((item) => item.name.trim()).length}
              </strong>
            </div>
            <div className="summary-divider" />
            <button
              type="submit"
              className="button-primary button-wide"
              disabled={submitting || !customerId}
            >
              {submitting ? (
                <>
                  <Loader2 size={16} className="spin" />
                  正在创建…
                </>
              ) : (
                <>
                  <Check size={16} />
                  开始准备审核包
                </>
              )}
            </button>
          </div>
        </aside>
      </form>
    </AppShell>
  );
}

type CandidateSummary = {
  candidate_id: string;
  predicted_identity?: string;
  status: string;
  usable_seconds?: number;
};
type VersionResponse = { person: Person; versions: ProfileVersionSummary[] };

function profileVersionLabel(version: number) {
  return `v${String(version).padStart(4, "0")}`;
}

export function ProfilesPage() {
  const navigate = useNavigate();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState("");
  const [scope, setScope] = useState("");
  const [status, setStatus] = useState("");
  const [queryDraft, setQueryDraft] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [catalogue, setCatalogue] = useState<ProfilePage>({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
    pages: 1,
  });
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedPerson, setSelectedPerson] = useState<ProfileSummary | null>(
    null,
  );
  const [versions, setVersions] = useState<ProfileVersionSummary[]>([]);
  const [detail, setDetail] = useState<ProfileVersionDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [creatingRevision, setCreatingRevision] = useState(false);

  const loadProfiles = async () => {
    setLoading(true);
    try {
      const result = (await getProfileCatalogue({
        page,
        pageSize,
        customerId,
        scope,
        status,
        keyword,
      })) as ProfilePage;
      setCatalogue(result);
      if (result.page !== page) setPage(result.page);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void getCustomers()
      .then((result) => setCustomers(result.customers as Customer[]))
      .catch((error) => setMessage((error as Error).message));
  }, []);
  useEffect(() => {
    void loadProfiles();
  }, [page, pageSize, customerId, scope, status, keyword]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(1);
      setKeyword(queryDraft.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [queryDraft]);
  useEffect(() => {
    if (!customerId) {
      setCandidates([]);
      return;
    }
    void getCandidates(customerId)
      .then((result) => setCandidates(result.candidates as CandidateSummary[]))
      .catch((error) => setMessage((error as Error).message));
  }, [customerId]);

  const loadVersionDetail = async (
    personId: string,
    version: number,
  ) => {
    setDrawerLoading(true);
    try {
      const result = (await getProfileVersion(
        personId,
        version,
      )) as ProfileVersionDetail;
      setDetail(result);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setDrawerLoading(false);
    }
  };
  const openVersions = async (person: ProfileSummary) => {
    setSelectedPerson(person);
    setVersions([]);
    setDetail(null);
    setDrawerLoading(true);
    try {
      const result = (await getProfileVersions(
        person.person_id,
      )) as VersionResponse;
      setVersions(result.versions);
      const initial =
        result.versions.find((item) => item.is_current) || result.versions[0];
      if (initial) await loadVersionDetail(person.person_id, initial.version);
    } catch (error) {
      setMessage((error as Error).message);
      setDrawerLoading(false);
    }
  };
  const refreshDrawer = async (personId: string, preferredVersion?: number) => {
    const result = (await getProfileVersions(personId)) as VersionResponse;
    setVersions(result.versions);
    const chosen =
      result.versions.find((item) => item.version === preferredVersion) ||
      result.versions.find((item) => item.is_current) ||
      result.versions[0];
    if (chosen) await loadVersionDetail(personId, chosen.version);
  };
  const mutateProfile = async (
    path: string,
    body: Record<string, unknown> = {},
    confirmation?: string,
  ) => {
    if (confirmation && !window.confirm(confirmation)) return;
    try {
      await api(path, { method: "POST", body: JSON.stringify(body) });
      await loadProfiles();
      if (selectedPerson)
        await refreshDrawer(selectedPerson.person_id, detail?.summary.version);
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  const switchVersion = async (version: number) => {
    if (!selectedPerson) return;
    await mutateProfile(
      `/api/v1/profiles/${encodeURIComponent(selectedPerson.person_id)}/current-version`,
      { version },
    );
  };
  const createRevisionTask = async () => {
    if (!selectedPerson || !detail) return;
    setCreatingRevision(true);
    try {
      const result = await api(
        `/api/v1/profiles/${encodeURIComponent(selectedPerson.person_id)}/versions/${detail.summary.version}/review`,
        { method: "POST", body: "{}" },
      );
      navigate(`/enrollments/${encodeURIComponent(result.session_id)}`);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setCreatingRevision(false);
    }
  };
  const pendingCandidates = candidates.filter(
    (item) => item.status === "pending_confirmation",
  );
  const hasActiveFilters = Boolean(customerId || scope || status || keyword);

  return (
    <AppShell>
      <PageHeader title="声纹档案" />
      {message && (
        <InlineMessage message={message} onClose={() => setMessage("")} />
      )}
      <section className="content-card profile-catalogue-card">
        <div className="catalogue-heading">
          <div>
            <strong>{catalogue.total} 份人员档案</strong>
            <span>我方人员全局共享，客户人员仅用于所属客户</span>
          </div>
          <button
            type="button"
            className="button-quiet"
            onClick={() => void loadProfiles()}
          >
            {loading ? (
              <Loader2 size={14} className="spin" />
            ) : (
              <RotateCcw size={14} />
            )}
            刷新
          </button>
        </div>
        <div className="profile-filter-bar">
          <div className="search-field profile-search-field">
            <Search size={16} />
            <input
              value={queryDraft}
              onChange={(event) => setQueryDraft(event.target.value)}
              placeholder="搜索姓名、职位或客户"
            />
          </div>
          <select
            aria-label="筛选客户"
            value={customerId}
            onChange={(event) => {
              setPage(1);
              setCustomerId(event.target.value);
              if (event.target.value && scope === "staff") setScope("customer");
            }}
          >
            <option value="">全部客户</option>
            {customers.map((customer) => (
              <option key={customer.customer_id} value={customer.customer_id}>
                {customer.name}
              </option>
            ))}
          </select>
          <select
            aria-label="筛选归属"
            value={scope}
            onChange={(event) => {
              setPage(1);
              setScope(event.target.value);
              if (event.target.value === "staff") setCustomerId("");
            }}
          >
            <option value="">全部归属</option>
            <option value="customer">客户人员</option>
            <option value="staff">我方人员</option>
          </select>
          <select
            aria-label="筛选状态"
            value={status}
            onChange={(event) => {
              setPage(1);
              setStatus(event.target.value);
            }}
          >
            <option value="">全部状态</option>
            <option value="enabled">使用中</option>
            <option value="disabled">已停用</option>
          </select>
          {hasActiveFilters && (
            <button
              type="button"
              className="button-quiet profile-filter-reset"
              onClick={() => {
                setQueryDraft("");
                setKeyword("");
                setCustomerId("");
                setScope("");
                setStatus("");
                setPage(1);
              }}
            >
              <X size={14} />
              清空
            </button>
          )}
        </div>
        {loading ? (
          <LoadingState label="正在读取声纹档案…" />
        ) : catalogue.items.length ? (
          <div className="profile-table-wrap">
            <table className="profile-table">
              <thead>
                <tr>
                  <th>人员</th>
                  <th>范围</th>
                  <th>状态</th>
                  <th>当前版本</th>
                  <th>声纹素材</th>
                  <th>更新时间</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {catalogue.items.map((person) => {
                  const summary = person.current_version_summary;
                  return (
                    <tr
                      key={person.person_id}
                      className={
                        person.profile_status === "disabled"
                          ? "profile-disabled"
                          : ""
                      }
                    >
                      <td>
                        <div className="profile-person">
                          <div className="avatar avatar-indigo">
                            {person.name.slice(0, 1)}
                          </div>
                          <div>
                            <strong>{person.name}</strong>
                            <span>{person.role || "未填写职位"}</span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <strong className="table-scope">
                          {person.scope === "staff"
                            ? "我方共享"
                            : person.customer_name || "客户"}
                        </strong>
                        <span className="table-subtle">
                          {organizationText(person.organization)}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`profile-state ${person.profile_status}`}
                        >
                          {person.profile_status === "enabled"
                            ? "使用中"
                            : "已停用"}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="version-link"
                          onClick={() => void openVersions(person)}
                        >
                          {person.current_version
                            ? profileVersionLabel(person.current_version)
                            : "未选择"}
                          <span>{person.version_count} 个版本</span>
                        </button>
                      </td>
                      <td>
                        <strong>
                          {summary
                            ? `${summary.reference_count + summary.holdout_count} 段`
                            : "—"}
                        </strong>
                        <span className="table-subtle">
                          {summary
                            ? `${summary.source_count} 份来源 · ${
                                summary.usable_seconds != null
                                  ? formatSeconds(summary.usable_seconds)
                                  : "时长未记录"
                              }`
                            : "暂无摘要"}
                        </span>
                      </td>
                      <td>
                        <span>
                          {formatDate(person.current_version_created_at || "")}
                        </span>
                      </td>
                      <td>
                        <div className="profile-actions">
                          <button
                            type="button"
                            className="button-quiet"
                            onClick={() => void openVersions(person)}
                          >
                            <Layers3 size={14} />
                            版本
                          </button>
                          {person.profile_status === "enabled" ? (
                            <button
                              type="button"
                              className="button-quiet"
                              onClick={() =>
                                void mutateProfile(
                                  `/api/v1/profiles/${encodeURIComponent(person.person_id)}/disable`,
                                  {},
                                  `停用 ${person.name} 的声纹档案？历史版本会保留，但后续匹配不再加载。`,
                                )
                              }
                            >
                              <PowerOff size={14} />
                              停用
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="button-quiet"
                              onClick={() =>
                                void mutateProfile(
                                  `/api/v1/profiles/${encodeURIComponent(person.person_id)}/enable`,
                                )
                              }
                            >
                              <Power size={14} />
                              启用
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={<UsersRound size={24} />}
            title="没有符合条件的声纹档案"
            description="调整筛选条件后重试。"
          />
        )}
        <div className="pagination">
          <span>
            第 {catalogue.page} / {catalogue.pages} 页
          </span>
          <select
            value={pageSize}
            onChange={(event) => {
              setPage(1);
              setPageSize(Number(event.target.value));
            }}
          >
            <option value="10">每页 10 条</option>
            <option value="20">每页 20 条</option>
            <option value="50">每页 50 条</option>
          </select>
          <button
            type="button"
            className="icon-button"
            aria-label="上一页"
            disabled={page <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="下一页"
            disabled={page >= catalogue.pages}
            onClick={() =>
              setPage((value) => Math.min(catalogue.pages, value + 1))
            }
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </section>
      {pendingCandidates.length > 0 && (
        <section className="content-card candidate-card">
          <div className="card-heading">
            <div>
              <span className="section-kicker">待处理</span>
              <h2>声纹扩充候选</h2>
            </div>
            <Headphones size={18} className="section-icon" />
          </div>
          <div className="candidate-list">
            {pendingCandidates.map((candidate) => (
              <div className="candidate-row" key={candidate.candidate_id}>
                <div>
                  <strong>
                    {candidate.predicted_identity || candidate.candidate_id}
                  </strong>
                  <span>
                    {candidate.usable_seconds
                      ? formatSeconds(candidate.usable_seconds)
                      : "候选语音"}{" "}
                    · 需要人工确认
                  </span>
                </div>
                <div>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() =>
                      void api(
                        `/api/v1/profile-candidates/${candidate.candidate_id}/review`,
                        { method: "POST", body: "{}" },
                      )
                        .then(
                          (result) =>
                            (window.location.href = `/enrollments/${encodeURIComponent(result.session_id)}`),
                        )
                        .catch((error) => setMessage(error.message))
                    }
                  >
                    进入审核
                  </button>
                  <button
                    type="button"
                    className="button-quiet"
                    onClick={() =>
                      void mutateProfile(
                        `/api/v1/profile-candidates/${candidate.candidate_id}/reject`,
                      )
                    }
                  >
                    拒绝
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {selectedPerson && (
        <div
          className="drawer-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedPerson(null);
          }}
        >
          <aside
            className="version-drawer"
            aria-label={`${selectedPerson.name} 的声纹版本`}
          >
            <header className="drawer-header">
              <div>
                <span className="section-kicker">人员声纹</span>
                <h2>{selectedPerson.name}</h2>
                <p>
                  {selectedPerson.role || "未填写职位"} ·{" "}
                  {selectedPerson.scope === "staff"
                    ? "我方共享"
                    : selectedPerson.customer_name}
                </p>
              </div>
              <IconButton
                label="关闭版本面板"
                onClick={() => setSelectedPerson(null)}
              >
                <X size={17} />
              </IconButton>
            </header>
            <div className="drawer-body">
              <section className="version-rail">
                <div className="drawer-section-heading">
                  <strong>全部版本</strong>
                  <span>{versions.length}</span>
                </div>
                {versions.map((version) => (
                  <article
                    key={version.version}
                    className={
                      detail?.summary.version === version.version
                        ? "version-item selected"
                        : "version-item"
                    }
                  >
                    <button
                      type="button"
                      onClick={() =>
                        void loadVersionDetail(
                          selectedPerson.person_id,
                          version.version,
                        )
                      }
                    >
                      <span className="version-item-title">
                        <strong>{profileVersionLabel(version.version)}</strong>
                        {version.is_current && <em>当前版本</em>}
                      </span>
                      <small>
                        {version.source_count} 份来源 ·{" "}
                        {version.reference_count + version.holdout_count} 段
                      </small>
                      <time>{formatDate(version.created_at || "")}</time>
                    </button>
                    {!version.is_current && (
                      <button
                        type="button"
                        className="version-switch"
                        onClick={() => void switchVersion(version.version)}
                      >
                        设为当前
                      </button>
                    )}
                  </article>
                ))}
              </section>
              <section className="version-detail">
                {drawerLoading && !detail ? (
                  <LoadingState label="正在读取版本…" />
                ) : detail ? (
                  <>
                    <div className="version-detail-heading">
                      <div>
                        <span className="section-kicker">版本详情</span>
                        <h3>
                          {profileVersionLabel(detail.summary.version)}
                          {detail.summary.is_current && <em>当前版本</em>}
                        </h3>
                      </div>
                      <button
                        type="button"
                        className="button-primary"
                        disabled={!detail.windows.length || creatingRevision}
                        onClick={() => void createRevisionTask()}
                      >
                        {creatingRevision ? (
                          <Loader2 size={14} className="spin" />
                        ) : (
                          <GitBranch size={14} />
                        )}
                        创建版本修订任务
                      </button>
                    </div>
                    <div className="version-metrics">
                      <div>
                        <span>来源录音</span>
                        <strong>{detail.summary.source_count}</strong>
                      </div>
                      <div>
                        <span>有效窗口</span>
                        <strong>
                          {detail.summary.reference_count +
                            detail.summary.holdout_count}
                        </strong>
                      </div>
                      <div>
                        <span>有效语音</span>
                        <strong>
                          {detail.summary.usable_seconds != null
                            ? formatSeconds(detail.summary.usable_seconds)
                            : "未记录"}
                        </strong>
                      </div>
                      <div>
                        <span>派生自</span>
                        <strong>
                          {detail.summary.parent_version
                            ? profileVersionLabel(detail.summary.parent_version)
                            : "初始建库"}
                        </strong>
                      </div>
                    </div>
                    <div className="version-source-list">
                      <div className="drawer-section-heading">
                        <strong>来源文件</strong>
                        <span>{detail.sources.length}</span>
                      </div>
                      {detail.sources.length ? (
                        detail.sources.map((source, index) => (
                          <article
                            className="version-source"
                            key={`${source.source_id || source.meeting_id || index}`}
                          >
                            <FileAudio size={16} />
                            <div>
                              <strong>
                                {source.title ||
                                  source.audio_relative_path ||
                                  `来源 ${index + 1}`}
                              </strong>
                              <span>
                                {source.audio_relative_path ||
                                  "历史版本未记录录音相对路径"}
                              </span>
                              {source.transcript_relative_path && (
                                <span>{source.transcript_relative_path}</span>
                              )}
                            </div>
                            <small>
                              {source.selected_window_count
                                ? `${source.selected_window_count} 段`
                                : ""}
                            </small>
                          </article>
                        ))
                      ) : (
                        <p className="empty-inline">
                          该历史版本没有完整的来源文件记录。
                        </p>
                      )}
                    </div>
                    <div className="version-window-list">
                      <div className="drawer-section-heading">
                        <strong>声纹窗口</strong>
                        <span>{detail.windows.length}</span>
                      </div>
                      {!detail.windows.length && (
                        <p className="empty-inline">
                          该历史版本没有可编辑的窗口来源，仍可切换使用，但不能从它派生新版。
                        </p>
                      )}
                      {detail.windows.map((windowItem) => (
                        <article
                          className="version-window selected"
                          key={windowItem.window_id}
                        >
                          <div>
                            <strong>
                              {windowItem.meeting_title ||
                                windowItem.label ||
                                "历史片段"}{" "}
                              ·{" "}
                              {windowItem.timestamp ||
                                formatSeconds(Number(windowItem.start || 0))}
                            </strong>
                            <p>
                              {windowItem.text || "该历史片段未保存转写文本。"}
                            </p>
                          </div>
                          <span>
                            {formatSeconds(Number(windowItem.duration || 0))}
                          </span>
                        </article>
                      ))}
                    </div>
                  </>
                ) : (
                  <EmptyState
                    title="选择一个版本"
                    description="查看来源文件和声纹窗口。"
                  />
                )}
              </section>
            </div>
          </aside>
        </div>
      )}
    </AppShell>
  );
}

function WavePlayer({
  sessionId,
  segmentId,
  active,
  onActivate,
  onDeactivate,
}: {
  sessionId: string;
  segmentId: string;
  active: boolean;
  onActivate: (id: string) => void;
  onDeactivate: (id: string) => void;
}) {
  const mount = useRef<HTMLDivElement>(null);
  const wave = useRef<WaveSurfer | null>(null);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!mount.current) return;
    const instance = WaveSurfer.create({
      container: mount.current,
      height: 40,
      waveColor: "#c5cde0",
      progressColor: "#6978ff",
      cursorColor: "#4655d8",
      barWidth: 2,
      barGap: 1,
    });
    instance.load(
      `/api/v1/enrollment-sessions/${encodeURIComponent(sessionId)}/segments/${encodeURIComponent(segmentId)}/audio`,
    );
    instance.on("play", () => {
      setPlaying(true);
      onActivate(segmentId);
      void api(
        `/api/v1/enrollment-sessions/${encodeURIComponent(sessionId)}/segments/${encodeURIComponent(segmentId)}/playback`,
        { method: "POST", body: "{}" },
      ).catch(() => undefined);
    });
    instance.on("pause", () => setPlaying(false));
    instance.on("finish", () => {
      setPlaying(false);
      onDeactivate(segmentId);
    });
    wave.current = instance;
    return () => {
      instance.destroy();
      wave.current = null;
    };
  }, [sessionId, segmentId]);
  useEffect(() => {
    if (!active) wave.current?.pause();
  }, [active]);
  const toggle = () => {
    if (active) {
      wave.current?.pause();
      onDeactivate(segmentId);
    } else {
      onActivate(segmentId);
      void wave.current?.play();
    }
  };
  return (
    <div className="wave-player">
      <div ref={mount} />
      <button
        type="button"
        className={`play-button ${playing ? "is-playing" : ""}`}
        title={playing ? "暂停片段" : "播放片段"}
        aria-label={playing ? "暂停片段" : "播放片段"}
        onClick={toggle}
      >
        {playing ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
      </button>
    </div>
  );
}

function PreparationProgress({
  progress,
}: {
  progress?: ReviewProgressData | null;
}) {
  if (!progress?.message)
    return (
      <div className="preparing-placeholder">
        <Loader2 size={16} className="spin" />
        正在等待本地处理进度…
      </div>
    );
  const completed = Number(progress.embedding_completed || 0);
  const total = Number(progress.embedding_total || 0);
  return (
    <div className="preparing-progress">
      <div className="preparing-heading">
        <Loader2 size={15} className="spin" />
        <strong>{progress.message}</strong>
      </div>
      {total > 0 && (
        <>
          <ProgressBar value={completed} max={total} />
          <small>
            声纹窗口 {completed} / {total}
          </small>
        </>
      )}
      {progress.phase === "transcoding" && (
        <small>
          转码进度：第 {progress.meeting_index} / {progress.meeting_total}{" "}
          份录音
        </small>
      )}
      {progress.phase === "screening" &&
        progress.valid_window_count != null && (
          <small>已筛出 {progress.valid_window_count} 个有效窗口</small>
        )}
      {progress.label && (
        <small>
          当前标签：{progress.label}（{progress.label_index} /{" "}
          {progress.label_total}）
        </small>
      )}
    </div>
  );
}

function BuildProgress({
  people,
  segments,
  decision,
  requirements,
  revisionMode = false,
}: {
  people: Person[];
  segments: Segment[];
  decision: Decision;
  requirements: Package["selection_requirements"];
  revisionMode?: boolean;
}) {
  return (
    <section className="build-progress-card">
      <div className="side-card-heading">
        <div>
          <span className="section-kicker">提交前检查</span>
          <h2>{revisionMode ? "新版素材进度" : "建库进度"}</h2>
        </div>
        <CheckCircle2 size={18} className="section-icon" />
      </div>
      <p className="side-card-hint">
        {revisionMode ? "新版本" : "每人"}至少 {requirements.minimum_windows} 段、
        {requirements.minimum_seconds} 秒有效语音。
      </p>
      <div className="person-progress-list">
        {people.map((person) => {
          const chosen = segments.filter(
            (segment) =>
              assignmentValue(decision.assignments[segment.segment_id]) ===
              person.person_id,
          );
          const seconds = chosen.reduce(
            (sum, segment) => sum + segment.duration,
            0,
          );
          const ready =
            chosen.length >= requirements.minimum_windows &&
            seconds >= requirements.minimum_seconds;
          return (
            <article
              className={ready ? "person-progress ready" : "person-progress"}
              key={person.person_id}
            >
              <div className="person-progress-top">
                <strong>{personText(person)}</strong>
                <span>{ready ? (revisionMode ? "可保存" : "可建库") : "待补充"}</span>
              </div>
              <ProgressBar
                value={
                  Math.min(
                    chosen.length / requirements.minimum_windows,
                    seconds / requirements.minimum_seconds,
                  ) * 100
                }
                max={100}
                tone={ready ? "green" : "indigo"}
              />
              <small>
                {chosen.length} / {requirements.minimum_windows} 段 ·{" "}
                {formatSeconds(seconds)} / {requirements.minimum_seconds} 秒
              </small>
            </article>
          );
        })}
      </div>
    </section>
  );
}

type ReviewLayout = {
  leftWidth: number;
  rightWidth: number;
  leftCollapsed: boolean;
  rightCollapsed: boolean;
};
const REVIEW_LAYOUT_KEY = "feishu-speaker-review-layout-v2";
const DEFAULT_REVIEW_LAYOUT: ReviewLayout = {
  leftWidth: 280,
  rightWidth: 360,
  leftCollapsed: false,
  rightCollapsed: false,
};
function readReviewLayout(): ReviewLayout {
  try {
    const value = JSON.parse(
      window.localStorage.getItem(REVIEW_LAYOUT_KEY) || "{}",
    ) as Partial<ReviewLayout>;
    const leftWidth = Number(value.leftWidth);
    const rightWidth = Number(value.rightWidth);
    const validWidths =
      Number.isFinite(leftWidth) &&
      Number.isFinite(rightWidth) &&
      leftWidth >= 220 &&
      leftWidth <= 420 &&
      rightWidth >= 300 &&
      rightWidth <= 480;
    const desktopWidth = window.innerWidth > 1240;
    const fitsWorkspace = leftWidth + rightWidth + 640 <= window.innerWidth;
    if (!validWidths || (desktopWidth && !fitsWorkspace))
      return DEFAULT_REVIEW_LAYOUT;
    return {
      leftWidth,
      rightWidth,
      leftCollapsed: value.leftCollapsed === true,
      rightCollapsed: value.rightCollapsed === true,
    };
  } catch {
    return DEFAULT_REVIEW_LAYOUT;
  }
}

function Acoustic({
  acoustic,
  people,
}: {
  acoustic: Record<string, unknown>;
  people: Person[];
}) {
  const name = (id: unknown) =>
    people.find((person) => person.person_id === id)?.name || "—";
  if (!acoustic.top1_person_id)
    return <div className="acoustic-note">暂无可比对的已建声纹</div>;
  return (
    <div className="acoustic-bar">
      <span>声纹参考</span>
      <strong>Top‑1 {name(acoustic.top1_person_id)}</strong>
      <em>{Number(acoustic.top1_score).toFixed(3)}</em>
      <span>Top‑2 {name(acoustic.top2_person_id)}</span>
      <em>
        {acoustic.top2_score == null
          ? "—"
          : Number(acoustic.top2_score).toFixed(3)}
      </em>
      <span>分差</span>
      <em>
        {acoustic.score_margin == null
          ? "—"
          : Number(acoustic.score_margin).toFixed(3)}
      </em>
    </div>
  );
}

function ReviewLabelGroup({
  groups,
  selected,
  onSelect,
  handled,
  labels,
  segments,
  decision,
}: {
  groups: { title: string; items: { item: Label; index: number }[] }[];
  selected: number;
  onSelect: (index: number) => void;
  handled: (item: Label) => boolean;
  labels: Label[];
  segments: Segment[];
  decision: Decision;
}) {
  return (
    <>
      {groups.map((group, groupIndex) => (
        <section className="label-group" key={`${group.title}-${groupIndex}`}>
          <div className="label-group-heading">
            <span>{group.title}</span>
            <small>{group.items.length} 个标签</small>
          </div>
          {group.items.map(({ item, index }) => {
            const name = item.label.split(" · ").slice(-1)[0];
            const isHandled = handled(item);
            return (
              <button
                type="button"
                key={`${item.label}-${index}`}
                className={
                  index === selected ? "label-item selected" : "label-item"
                }
                onClick={() => onSelect(index)}
              >
                <i className={`risk-dot ${item.risk}`} />
                <div className="label-item-main">
                  <strong>{name}</strong>
                  {isHandled && <em>已操作</em>}
                </div>
                <small>
                  {riskText(item.risk)} · {item.quality.window_count} 个取样 /{" "}
                  {item.quality.candidate_window_count ??
                    item.quality.window_count}{" "}
                  个合格窗口
                </small>
                <small>
                  {formatSeconds(item.quality.usable_seconds)}
                  {item.quality.expanded_for_mixture ? " · 已补样" : ""}
                </small>
                <small>
                  {item.excluded_by_manifest
                    ? "已按清单排除"
                    : item.suggestion.name
                      ? `建议：${item.suggestion.name}`
                      : "暂无身份建议"}
                </small>
              </button>
            );
          })}
        </section>
      ))}
    </>
  );
}

function ReviewPage({
  session,
  onRefresh,
}: {
  session: Session;
  onRefresh: () => Promise<Session>;
}) {
  const navigate = useNavigate();
  const packageData = session.package;
  const revisionMode = session.kind === "profile_revision";
  const [decision, setDecision] = useState<Decision>(
    session.decision || { assignments: {}, new_people: [] },
  );
  const [selectedLabel, setSelectedLabel] = useState(0);
  const [expandedClusters, setExpandedClusters] = useState<
    Record<string, boolean>
  >({});
  const [activeSegmentId, setActiveSegmentId] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [message, setMessage] = useState("");
  const [layout, setLayout] = useState<ReviewLayout>(() => readReviewLayout());
  const [resize, setResize] = useState<{
    side: "left" | "right";
    startX: number;
    startWidth: number;
  } | null>(null);
  const workspace = useRef<HTMLDivElement>(null);
  const labels = packageData?.labels || [];
  const label = labels[selectedLabel];
  const labelGroups = useMemo(() => {
    const groups: { title: string; items: { item: Label; index: number }[] }[] =
      [];
    labels.forEach((item, index) => {
      const title = item.meeting_title || item.label.split(" · ")[0] || "录音";
      const current = groups[groups.length - 1];
      if (!current || current.title !== title)
        groups.push({ title, items: [{ item, index }] });
      else current.items.push({ item, index });
    });
    return groups;
  }, [labels]);
  useEffect(() => {
    setDecision(session.decision || { assignments: {}, new_people: [] });
    setValidation(null);
    setExpandedClusters({});
    setActiveSegmentId(null);
  }, [session.session_id, session.revision]);
  useEffect(() => {
    try {
      window.localStorage.setItem(REVIEW_LAYOUT_KEY, JSON.stringify(layout));
    } catch {
      /* local storage is optional */
    }
  }, [layout]);
  useEffect(() => {
    if (selectedLabel >= labels.length)
      setSelectedLabel(Math.max(0, labels.length - 1));
  }, [labels.length, selectedLabel]);
  useEffect(() => {
    if (!resize) return;
    const onMove = (event: PointerEvent) => {
      const width =
        workspace.current?.getBoundingClientRect().width || window.innerWidth;
      if (resize.side === "left") {
        setLayout((current) => {
          const maxWidth = Math.max(
            220,
            Math.min(
              420,
              width - (current.rightCollapsed ? 52 : current.rightWidth) - 620,
            ),
          );
          return {
            ...current,
            leftWidth: clamp(
              resize.startWidth + event.clientX - resize.startX,
              220,
              maxWidth,
            ),
          };
        });
      } else {
        setLayout((current) => {
          const maxWidth = Math.max(
            300,
            Math.min(
              480,
              width - (current.leftCollapsed ? 52 : current.leftWidth) - 620,
            ),
          );
          return {
            ...current,
            rightWidth: clamp(
              resize.startWidth - (event.clientX - resize.startX),
              300,
              maxWidth,
            ),
          };
        });
      }
    };
    const onUp = () => setResize(null);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [resize]);
  if (!packageData || !label)
    return <ReviewStatusPage session={session} onRefresh={onRefresh} />;
  const knownPeople = packageData.people.filter((person) =>
    Boolean(person.person_id),
  );
  const draftPeople: Person[] = decision.new_people.map((person) => ({
    person_id: person.draft_id,
    name: person.name || "未命名人员",
    role: person.role,
    organization: person.organization,
    scope: person.organization === "yingdao" ? "staff" : "customer",
  }));
  const personOptions = Array.from(
    new Map(
      [...knownPeople, ...draftPeople].map((person) => [
        person.person_id,
        person,
      ]),
    ).values(),
  );
  const labelHandled = (item: Label) =>
    packageData.segments
      .filter((segment) => displayLabel(segment) === item.label)
      .some((segment) =>
        Object.prototype.hasOwnProperty.call(
          decision.assignments,
          segment.segment_id,
        ),
      );
  const assignment = (segmentId: string, value: string) =>
    setDecision((current) => ({
      ...current,
      assignments: { ...current.assignments, [segmentId]: value },
    }));
  const fillCluster = (cluster: Cluster, value: string) =>
    setDecision((current) => ({
      ...current,
      assignments: {
        ...current.assignments,
        ...Object.fromEntries(cluster.segment_ids.map((id) => [id, value])),
      },
    }));
  const clusterValue = (cluster: Cluster) => {
    const values = cluster.segment_ids.map((id) =>
      assignmentValue(decision.assignments[id]),
    );
    return values.length && values.every((value) => value === values[0])
      ? values[0]
      : "";
  };
  const removeNewPerson = (draftId: string) => {
    const used = assignmentCount(decision, draftId);
    if (
      used &&
      !window.confirm(
        `该人员已有 ${used} 个片段分配。删除后会清除这些分配，是否继续？`,
      )
    )
      return;
    setDecision((current) => ({
      ...current,
      new_people: current.new_people.filter(
        (person) => person.draft_id !== draftId,
      ),
      assignments: Object.fromEntries(
        Object.entries(current.assignments).map(([id, value]) => [
          id,
          assignmentValue(value) === draftId ? "" : value,
        ]),
      ),
    }));
  };
  const save = async () => {
    try {
      await api(
        `/api/v1/enrollment-sessions/${encodeURIComponent(session.session_id)}/decision`,
        {
          method: "PUT",
          body: JSON.stringify({ revision: session.revision, decision }),
        },
      );
      await onRefresh();
      setMessage("选择已保存。");
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  const validate = async () => {
    try {
      setValidation(
        (await api(
          `/api/v1/enrollment-sessions/${encodeURIComponent(session.session_id)}/validate`,
          { method: "POST", body: JSON.stringify({ decision }) },
        )) as ValidationResult,
      );
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  const commit = async (makeCurrent = true) => {
    try {
      const committedDecision = revisionMode
        ? { ...decision, make_current: makeCurrent }
        : decision;
      const saved = (await api(
        `/api/v1/enrollment-sessions/${encodeURIComponent(session.session_id)}/decision`,
        {
          method: "PUT",
          body: JSON.stringify({
            revision: session.revision,
            decision: committedDecision,
          }),
        },
      )) as Session;
      const result = await api(
        `/api/v1/enrollment-sessions/${encodeURIComponent(session.session_id)}/commit`,
        { method: "POST", body: JSON.stringify({ revision: saved.revision }) },
      );
      if (result.status === "validation_failed")
        setValidation(result as ValidationResult);
      else {
        setMessage(revisionMode ? "新版本已保存。" : "声纹已正式建库。");
        await onRefresh();
      }
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  const cancel = async () => {
    if (
      !window.confirm(
        "取消这个审核任务？待审核的临时向量会被清理，不会创建正式声纹。",
      )
    )
      return;
    try {
      await api(
        `/api/v1/enrollment-sessions/${encodeURIComponent(session.session_id)}/cancel`,
        { method: "POST", body: "{}" },
      );
      await onRefresh();
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  const resetLayout = () => setLayout(DEFAULT_REVIEW_LAYOUT);
  const adjustWidth = (side: "left" | "right", delta: number) =>
    setLayout((current) =>
      side === "left"
        ? { ...current, leftWidth: clamp(current.leftWidth + delta, 220, 420) }
        : {
            ...current,
            rightWidth: clamp(current.rightWidth + delta, 300, 480),
          },
    );
  const gridStyle = {
    gridTemplateColumns: `${layout.leftCollapsed ? 52 : layout.leftWidth}px 10px minmax(600px, 1fr) 10px ${layout.rightCollapsed ? 52 : layout.rightWidth}px`,
  };
  return (
    <main className="review-focus">
      <header className="review-topbar">
        <div className="review-topbar-left">
          <button
            type="button"
            className="back-button"
            onClick={() => navigate(revisionMode ? "/profiles" : "/enrollments")}
          >
            <ArrowLeft size={17} />
            {revisionMode ? "返回档案" : "返回任务"}
          </button>
          <div className="review-breadcrumb">
            <span>{packageData.manifest.customer.name}</span>
            <ChevronRight size={14} />
            <strong>
              {packageData.display_title || packageData.manifest.meeting.title}
            </strong>
          </div>
        </div>
        <div className="review-topbar-right">
          <StatusBadge status={session.status} />
          {["queued", "preparing", "review_required"].includes(
            session.status,
          ) && (
            <button
              type="button"
              className="button-danger-quiet"
              onClick={() => void cancel()}
            >
              取消任务
            </button>
          )}
        </div>
      </header>
      {message && (
        <InlineMessage message={message} onClose={() => setMessage("")} />
      )}
      <div className="review-workspace" ref={workspace} style={gridStyle}>
        <aside
          className={
            layout.leftCollapsed
              ? "review-panel labels-panel collapsed"
              : "review-panel labels-panel"
          }
        >
          {layout.leftCollapsed ? (
            <div className="collapsed-panel">
              <IconButton
                label="展开标签栏"
                onClick={() =>
                  setLayout((current) => ({ ...current, leftCollapsed: false }))
                }
              >
                <ChevronRight size={18} />
              </IconButton>
              <strong>{labels.length}</strong>
              <span>{revisionMode ? "来源" : "标签"}</span>
              <small>
                {labels.filter((item) => labelHandled(item)).length} 已操作
              </small>
            </div>
          ) : (
            <>
              <div className="panel-heading">
                <div>
                  <span className="section-kicker">
                    {revisionMode ? "版本素材" : "审核队列"}
                  </span>
                  <h2>{revisionMode ? "来源片段" : "转写标签"}</h2>
                </div>
                <IconButton
                  label="收起标签栏"
                  onClick={() =>
                    setLayout((current) => ({
                      ...current,
                      leftCollapsed: true,
                    }))
                  }
                >
                  <ChevronLeft size={18} />
                </IconButton>
              </div>
              <div className="label-list">
                <ReviewLabelGroup
                  groups={labelGroups}
                  selected={selectedLabel}
                  onSelect={setSelectedLabel}
                  handled={labelHandled}
                  labels={labels}
                  segments={packageData.segments}
                  decision={decision}
                />
              </div>
            </>
          )}
        </aside>
        <ResizeHandle
          side="left"
          disabled={layout.leftCollapsed}
          onStart={(event) =>
            setResize({
              side: "left",
              startX: event.clientX,
              startWidth: layout.leftWidth,
            })
          }
          onReset={resetLayout}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") adjustWidth("left", -16);
            if (event.key === "ArrowRight") adjustWidth("left", 16);
          }}
        />
        <section className="review-panel transcript-panel">
          <div className="transcript-heading">
            <div>
              <span className="section-kicker">
                {revisionMode ? "当前来源" : "当前审核标签"}
              </span>
              <h1>
                {label.label.split(" · ").slice(-1)[0]}{" "}
                <span className={`risk-pill ${label.risk}`}>
                  {riskText(label.risk)}
                </span>
              </h1>
              <p>
                {label.risk_notes.join("；") ||
                  "主聚类稳定，可根据需要试听代表片段。"}
              </p>
            </div>
            <div className="transcript-heading-meta">
              <span>{label.quality.window_count} 个取样</span>
              <span>{formatSeconds(label.quality.usable_seconds)}</span>
            </div>
          </div>
          {!revisionMode && (
            <Acoustic acoustic={label.acoustic} people={personOptions} />
          )}
          <div className="cluster-list">
            {label.clusters.map((cluster) => {
              const visible = expandedClusters[cluster.cluster_id]
                ? cluster.segment_ids
                : cluster.representative_segment_ids;
              return (
                <article className="cluster-card" key={cluster.cluster_id}>
                  <div className="cluster-heading">
                    <div>
                      <strong>
                        聚类 {cluster.cluster_id.split("-").pop()}
                      </strong>
                      <span>
                        {cluster.window_count} 段 ·{" "}
                        {formatSeconds(cluster.seconds)}
                      </span>
                    </div>
                    <label className="cluster-assignment">
                      <span>整组分配</span>
                      <select
                        value={clusterValue(cluster)}
                        onChange={(event) =>
                          fillCluster(cluster, event.target.value)
                        }
                      >
                        {revisionMode ? (
                          <>
                            <option value={personOptions[0]?.person_id || ""}>
                              保留到新版本
                            </option>
                            <option value="skip">从新版本排除</option>
                          </>
                        ) : (
                          <>
                            <option value="">选择人员</option>
                            {personOptions.map((person) => (
                              <option
                                value={person.person_id}
                                key={person.person_id}
                              >
                                {personText(person)}
                              </option>
                            ))}
                            <option value="unknown">未知</option>
                            <option value="background">路人/杂音</option>
                            <option value="skip">暂不建库</option>
                          </>
                        )}
                      </select>
                      <ChevronDown size={15} />
                    </label>
                  </div>
                  {cluster.segment_ids.length > visible.length && (
                    <button
                      type="button"
                      className="show-all-button"
                      onClick={() =>
                        setExpandedClusters((current) => ({
                          ...current,
                          [cluster.cluster_id]: true,
                        }))
                      }
                    >
                      显示全部 {cluster.segment_ids.length} 个窗口{" "}
                      <ChevronDown size={14} />
                    </button>
                  )}
                  {expandedClusters[cluster.cluster_id] && (
                    <button
                      type="button"
                      className="show-all-button secondary"
                      onClick={() =>
                        setExpandedClusters((current) => ({
                          ...current,
                          [cluster.cluster_id]: false,
                        }))
                      }
                    >
                      只显示代表片段 <ChevronLeft size={14} />
                    </button>
                  )}
                  <div className="segment-list">
                    {visible.map((segmentId) => {
                      const segment = packageData.segments.find(
                        (item) => item.segment_id === segmentId,
                      );
                      if (!segment) return null;
                      return (
                        <article className="segment-card" key={segmentId}>
                          {segment.playable === false ? (
                            <div
                              className="wave-player unavailable"
                              title="历史版本未记录可试听的原始录音路径"
                            >
                              <Headphones size={16} />
                            </div>
                          ) : (
                            <WavePlayer
                              sessionId={session.session_id}
                              segmentId={segmentId}
                              active={activeSegmentId === segmentId}
                              onActivate={setActiveSegmentId}
                              onDeactivate={(id) =>
                                setActiveSegmentId((current) =>
                                  current === id ? null : current,
                                )
                              }
                            />
                          )}
                          <div className="segment-copy">
                            <div className="segment-meta">
                              <strong>{segment.meeting_title || ""}</strong>
                              <span>
                                {segment.timestamp} ·{" "}
                                {formatSeconds(segment.duration)}
                              </span>
                            </div>
                            <p>{segment.text}</p>
                            <small>质量 {segment.quality.toFixed(2)}</small>
                          </div>
                          <select
                            value={assignmentValue(
                              decision.assignments[segmentId],
                            )}
                            onChange={(event) =>
                              assignment(segmentId, event.target.value)
                            }
                          >
                            {revisionMode ? (
                              <>
                                <option value={personOptions[0]?.person_id || ""}>
                                  保留到新版本
                                </option>
                                <option value="skip">从新版本排除</option>
                              </>
                            ) : (
                              <>
                                <option value="">不纳入建库</option>
                                {personOptions.map((person) => (
                                  <option
                                    value={person.person_id}
                                    key={person.person_id}
                                  >
                                    {personText(person)}
                                  </option>
                                ))}
                                <option value="unknown">未知</option>
                                <option value="background">路人/杂音</option>
                                <option value="skip">暂不建库</option>
                              </>
                            )}
                          </select>
                        </article>
                      );
                    })}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
        <ResizeHandle
          side="right"
          disabled={layout.rightCollapsed}
          onStart={(event) =>
            setResize({
              side: "right",
              startX: event.clientX,
              startWidth: layout.rightWidth,
            })
          }
          onReset={resetLayout}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") adjustWidth("right", 16);
            if (event.key === "ArrowRight") adjustWidth("right", -16);
          }}
        />
        <aside
          className={
            layout.rightCollapsed
              ? "review-panel action-panel collapsed"
              : "review-panel action-panel"
          }
        >
          {layout.rightCollapsed ? (
            <div className="collapsed-panel">
              <IconButton
                label="展开操作栏"
                onClick={() =>
                  setLayout((current) => ({
                    ...current,
                    rightCollapsed: false,
                  }))
                }
              >
                <ChevronLeft size={18} />
              </IconButton>
              <strong>
                {
                  personOptions.filter((person) => {
                    const segments = packageData.segments.filter(
                      (segment) =>
                        assignmentValue(
                          decision.assignments[segment.segment_id],
                        ) === person.person_id,
                    );
                    return (
                      segments.length >=
                        packageData.selection_requirements.minimum_windows &&
                      segments.reduce(
                        (sum, segment) => sum + segment.duration,
                        0,
                      ) >= packageData.selection_requirements.minimum_seconds
                    );
                  }).length
                }
              </strong>
              <span>{revisionMode ? "可保存" : "人可建库"}</span>
            </div>
          ) : (
            <>
              <div className="panel-heading">
                <div>
                  <span className="section-kicker">审核结果</span>
                  <h2>{revisionMode ? "版本修订" : "确认建库"}</h2>
                </div>
                <IconButton
                  label="收起操作栏"
                  onClick={() =>
                    setLayout((current) => ({
                      ...current,
                      rightCollapsed: true,
                    }))
                  }
                >
                  <ChevronRight size={18} />
                </IconButton>
              </div>
              <BuildProgress
                people={personOptions}
                segments={packageData.segments}
                decision={decision}
                requirements={packageData.selection_requirements}
                revisionMode={revisionMode}
              />
              <section className="commit-card">
                <p>
                  {revisionMode
                    ? `确认后会从 ${profileVersionLabel(packageData.profile_revision?.base_version || 0)} 派生不可变的新版本；被排除的片段不会进入新版。`
                    : "确认后会创建正式声纹版本；未分配、未知、路人/杂音和暂不建库的片段不会写入声纹库。"}
                </p>
                {!revisionMode && (
                  <>
                    <div className="commit-section-heading">
                      <span>新增人员</span>
                      <span className="commit-section-hint">
                        可删除未达要求的人员
                      </span>
                    </div>
                    {decision.new_people.map((person) => (
                      <div className="new-person-row" key={person.draft_id}>
                        <div className="new-person-fields">
                          <input
                            placeholder="姓名"
                            value={person.name}
                            onChange={(event) =>
                              setDecision((current) => ({
                                ...current,
                                new_people: current.new_people.map((item) =>
                                  item.draft_id === person.draft_id
                                    ? { ...item, name: event.target.value }
                                    : item,
                                ),
                              }))
                            }
                          />
                          <input
                            placeholder="职位（可选）"
                            value={person.role}
                            onChange={(event) =>
                              setDecision((current) => ({
                                ...current,
                                new_people: current.new_people.map((item) =>
                                  item.draft_id === person.draft_id
                                    ? { ...item, role: event.target.value }
                                    : item,
                                ),
                              }))
                            }
                          />
                          <select
                            value={person.organization}
                            onChange={(event) =>
                              setDecision((current) => ({
                                ...current,
                                new_people: current.new_people.map((item) =>
                                  item.draft_id === person.draft_id
                                    ? {
                                        ...item,
                                        organization: event.target
                                          .value as NewPerson["organization"],
                                      }
                                    : item,
                                ),
                              }))
                            }
                          >
                            <option value="customer">客户</option>
                            <option value="yingdao">我方</option>
                          </select>
                        </div>
                        <IconButton
                          label={`删除新增人员 ${person.name || "未命名人员"}`}
                          variant="danger"
                          onClick={() => removeNewPerson(person.draft_id)}
                        >
                          <Trash2 size={14} />
                        </IconButton>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="button-secondary button-wide"
                      onClick={() =>
                        setDecision((current) => ({
                          ...current,
                          new_people: [
                            ...current.new_people,
                            createDraftPerson(),
                          ],
                        }))
                      }
                    >
                      <UserPlus size={15} />
                      新增人员
                    </button>
                  </>
                )}
                <div className="commit-actions">
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => void save()}
                  >
                    <Save size={15} />
                    保存
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => void validate()}
                  >
                    <CheckCircle2 size={15} />
                    校验
                  </button>
                </div>
                {revisionMode ? (
                  <div className="revision-commit-actions">
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => void commit(false)}
                    >
                      仅保存新版
                    </button>
                    <button
                      type="button"
                      className="button-primary"
                      onClick={() => void commit(true)}
                    >
                      <Check size={16} />
                      保存新版并设为当前
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="button-primary button-wide"
                    onClick={() => void commit()}
                  >
                    <Check size={16} />
                    确认建库
                  </button>
                )}
                {validation && (
                  <div
                    className={
                      validation.valid
                        ? "validation-box ok"
                        : "validation-box bad"
                    }
                  >
                    <strong>
                      {validation.valid ? "可以提交" : "暂不能提交"}
                    </strong>
                    {validation.errors.map((error) => (
                      <p key={error}>{error}</p>
                    ))}
                    {validation.warnings.map((warning) => (
                      <p key={warning}>提示：{warning}</p>
                    ))}
                  </div>
                )}
                <p className="playback-note">
                  已试听 {session.playback_count || 0} 个片段
                </p>
              </section>
            </>
          )}
        </aside>
      </div>
      <div className="review-footer">
        <span>
          <Settings2 size={14} />
          拖动分隔线调整栏宽 · 双击分隔线恢复默认
        </span>
        <button type="button" className="button-quiet" onClick={resetLayout}>
          恢复默认布局
        </button>
      </div>
    </main>
  );
}

function ResizeHandle({
  side,
  disabled,
  onStart,
  onReset,
  onKeyDown,
}: {
  side: "left" | "right";
  disabled: boolean;
  onStart: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onReset: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      className={`resize-handle resize-${side}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={`${side === "left" ? "左侧" : "右侧"}栏宽度`}
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      onPointerDown={(event) => {
        if (!disabled) onStart(event);
      }}
      onDoubleClick={(event) => {
        if (!disabled) {
          event.preventDefault();
          onReset();
        }
      }}
      onKeyDown={onKeyDown}
    >
      <span />
    </div>
  );
}

function ReviewStatusPage({
  session,
  onRefresh,
}: {
  session: Session;
  onRefresh: () => Promise<Session>;
}) {
  const navigate = useNavigate();
  const [message, setMessage] = useState("");
  const [retrying, setRetrying] = useState(false);
  const active = ["queued", "preparing"].includes(session.status);
  const revisionMode = session.kind === "profile_revision";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => void onRefresh(), 2500);
    return () => window.clearInterval(timer);
  }, [active, onRefresh]);
  const cancel = async () => {
    if (!window.confirm("取消这个审核任务？不会创建正式声纹。")) return;
    try {
      await api(
        `/api/v1/enrollment-sessions/${encodeURIComponent(session.session_id)}/cancel`,
        { method: "POST", body: "{}" },
      );
      await onRefresh();
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  const restart = async () => {
    try {
      const result = await api(
        `/api/v1/enrollment-sessions/${encodeURIComponent(session.session_id)}/restart`,
        { method: "POST", body: "{}" },
      );
      navigate(`/enrollments/${encodeURIComponent(result.session_id)}`);
    } catch (error) {
      setMessage((error as Error).message);
    }
  };
  const retryEdit = async () => {
    setRetrying(true);
    try {
      await retryFailedSession(session.session_id, session.revision);
      await onRefresh();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setRetrying(false);
    }
  };
  const title =
    session.status === "committed"
      ? revisionMode
        ? "新版本已保存"
        : "声纹已建库"
      : session.status === "cancelled"
      ? "任务已取消"
      : session.status === "failed"
        ? "任务处理失败"
        : "正在准备审核工作区";
  return (
    <main className="review-status-page">
      <header className="review-topbar">
        <button
          type="button"
          className="back-button"
          onClick={() => navigate(revisionMode ? "/profiles" : "/enrollments")}
        >
          <ArrowLeft size={17} />
          {revisionMode ? "返回档案" : "返回任务"}
        </button>
        <StatusBadge status={session.status} />
      </header>
      <section className="status-card">
        <div className="status-card-icon">
          {session.status === "committed" ? (
            <CheckCircle2 size={25} />
          ) : session.status === "failed" ? (
            <ShieldAlert size={25} />
          ) : session.status === "cancelled" ? (
            <X size={25} />
          ) : (
            <Loader2 size={25} className="spin" />
          )}
        </div>
        <span className="section-kicker">
          {session.customer_name || "本地客户"}
        </span>
        <h1>{title}</h1>
        <p>
          {session.status === "failed" && session.can_retry_edit
            ? `上次提交失败：${session.error_message || "未知错误"}。原审核内容仍然完整，可以恢复后继续编辑并重新提交。`
            : session.error_message ||
            (session.status === "committed"
              ? revisionMode
                ? "新版本已经生成；基础版本及其他历史版本保持不变。"
                : "审核结果已经写入正式声纹库。"
              : session.status === "cancelled"
              ? "没有创建或修改正式声纹。你可以按原素材重新开始。"
              : "音频转码、质量筛选、向量提取和聚类由本地 Worker 顺序完成。")}
        </p>
        {active && <PreparationProgress progress={session.job?.progress} />}
        {message && (
          <InlineMessage message={message} onClose={() => setMessage("")} />
        )}
        <div className="status-card-actions">
          {active && (
            <button
              type="button"
              className="button-danger-quiet"
              onClick={() => void cancel()}
            >
              取消任务
            </button>
          )}
          {session.status === "cancelled" && session.kind === "enrollment" && (
            <button
              type="button"
              className="button-primary"
              onClick={() => void restart()}
            >
              <RotateCcw size={16} />
              按原素材重新开始
            </button>
          )}
          {session.status === "failed" && session.can_retry_edit && (
            <button
              type="button"
              className="button-primary"
              disabled={retrying}
              onClick={() => void retryEdit()}
            >
              {retrying ? (
                <Loader2 size={16} className="spin" />
              ) : (
                <RotateCcw size={16} />
              )}
              {retrying ? "正在恢复…" : "重试并继续编辑"}
            </button>
          )}
          {session.status === "failed" &&
            !session.can_retry_edit &&
            session.retry_edit_reason && (
              <span className="status-action-note">
                {session.retry_edit_reason}
              </span>
            )}
          <button
            type="button"
            className="button-secondary"
            onClick={() => void onRefresh()}
          >
            刷新状态
          </button>
        </div>
      </section>
    </main>
  );
}

export function ReviewRoute() {
  const { sessionId } = useParams();
  const [session, setSession] = useState<Session | null>(null);
  const [message, setMessage] = useState("");
  const refresh = async () => {
    if (!sessionId) return session as Session;
    try {
      const next = (await getSession(sessionId)) as Session;
      setSession(next);
      return next;
    } catch (error) {
      setMessage((error as Error).message);
      throw error;
    }
  };
  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [sessionId]);
  if (message && !session)
    return (
      <main className="review-status-page">
        <InlineMessage message={message} />
      </main>
    );
  if (!session)
    return (
      <main className="review-status-page">
        <LoadingState label="正在打开审核任务…" />
      </main>
    );
  return session.package && session.status === "review_required" ? (
    <ReviewPage session={session} onRefresh={refresh} />
  ) : (
    <ReviewStatusPage session={session} onRefresh={refresh} />
  );
}
