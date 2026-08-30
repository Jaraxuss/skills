import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import {
  Activity,
  Archive,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Database,
  FileAudio,
  LayoutDashboard,
  ListChecks,
  Mic2,
  Plus,
  ShieldCheck,
  UsersRound,
} from 'lucide-react'
import type { Summary } from './types'
import { statusText } from './utils'

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status}`}><span className="status-dot" />{statusText(status)}</span>
}

export function IconButton({
  label,
  onClick,
  children,
  variant = 'ghost',
  disabled = false,
}: {
  label: string
  onClick: () => void
  children: ReactNode
  variant?: 'ghost' | 'danger'
  disabled?: boolean
}) {
  return <button type="button" className={`icon-button icon-button-${variant}`} aria-label={label} title={label} onClick={onClick} disabled={disabled}>{children}</button>
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return <div className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="page-header-actions">{actions}</div>}</div>
}

export function MetricCard({
  label,
  value,
  helper,
  icon,
  tone = 'indigo',
}: {
  label: string
  value: number | string
  helper: string
  icon: ReactNode
  tone?: 'indigo' | 'cyan' | 'amber' | 'green'
}) {
  return <article className={`metric-card metric-${tone}`}><div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div><strong>{value}</strong><small>{helper}</small></article>
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return <div className="empty-state">{icon && <div className="empty-icon">{icon}</div>}<strong>{title}</strong>{description && <p>{description}</p>}{action}</div>
}

export function LoadingState({ label = '正在加载…' }: { label?: string }) {
  return <div className="loading-state"><Activity size={16} className="spin" />{label}</div>
}

export function ProgressBar({ value, max, tone = 'indigo' }: { value: number; max: number; tone?: 'indigo' | 'green' | 'amber' }) {
  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  return <div className={`progress-bar progress-${tone}`}><i style={{ width: `${percent}%` }} /></div>
}

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? 'nav-link nav-link-active' : 'nav-link'
}

export function AppShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return <div className="app-frame"><aside className="app-sidebar"><div className="brand"><div className="brand-mark"><Mic2 size={19} /></div><div><strong>声纹建库</strong><span>控制台</span></div></div><div className="nav-section-label">工作区</div><nav className="app-nav"><NavLink to="/" end className={navClass}><LayoutDashboard size={17} /><span>概览</span></NavLink><NavLink to="/enrollments" className={navClass}><ListChecks size={17} /><span>建库任务</span></NavLink><NavLink to="/profiles" className={navClass}><UsersRound size={17} /><span>声纹档案</span></NavLink></nav><div className="sidebar-spacer" /><div className="sidebar-status"><div className="online-indicator"><CircleDot size={13} />本机服务正常</div><span>本地 CPU 推理 · 数据不出机</span></div></aside><div className="app-main"><header className="app-topbar"><div><span className="topbar-kicker">{title}</span>{subtitle && <span className="topbar-subtitle">{subtitle}</span>}</div><div className="topbar-meta"><ShieldCheck size={15} />本地工作区</div></header><main className="page-content">{children}</main></div></div>
}

export function DashboardIcon({ kind }: { kind: 'tasks' | 'profiles' | 'audio' | 'database' }) {
  if (kind === 'tasks') return <ListChecks size={18} />
  if (kind === 'profiles') return <UsersRound size={18} />
  if (kind === 'audio') return <FileAudio size={18} />
  return <Database size={18} />
}

export function QuickAction({ to, children }: { to: string; children: ReactNode }) {
  return <NavLink to={to} className="quick-action"><Plus size={16} />{children}<ChevronRight size={15} /></NavLink>
}

export function TaskStatusIcon({ status }: { status: string }) {
  if (status === 'committed') return <CheckCircle2 size={15} />
  if (status === 'failed' || status === 'source_changed') return <Archive size={15} />
  return <CircleDot size={15} />
}

export function SummaryStatus({ summary, status }: { summary: Summary; status: string }) {
  return <span className="summary-status"><TaskStatusIcon status={status} />{summary.tasks[status] || 0}</span>
}
