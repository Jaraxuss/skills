import type { Assignment, Decision, Label, Person, Segment } from './types'

export function fileStem(path: string) {
  const dot = path.lastIndexOf('.')
  return (dot < 0 ? path : path.slice(0, dot)).toLocaleLowerCase()
}

export function formatSeconds(value: number) {
  return `${value.toFixed(1)} 秒`
}

export function formatDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date)
}

export function riskText(risk: string) {
  return risk === 'green' ? '低风险' : risk === 'yellow' ? '需留意' : '高风险'
}

export function displayLabel(segment: Segment) {
  return segment.display_label || `${segment.meeting_title ? `${segment.meeting_title} · ` : ''}${segment.label}`
}

export function assignmentValue(value: Assignment | undefined) {
  return typeof value === 'string' ? value : value?.include === false ? '' : value?.person_id || ''
}

export function personText(person: Pick<Person, 'name' | 'role'>) {
  const role = person.role?.trim()
  return `${person.name}${role && role !== person.name.trim() ? `（${role}）` : ''}`
}

export function organizationText(organization?: string) {
  return organization === 'yingdao' ? '我方' : organization === 'external' ? '外部' : '客户'
}

export function createDraftPerson() {
  return {
    draft_id: `new-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    name: '',
    role: '',
    organization: 'customer' as const,
  }
}

export function statusText(status: string) {
  const labels: Record<string, string> = {
    queued: '排队中',
    preparing: '准备中',
    review_required: '待审核',
    approved: '已确认',
    committing: '正在建库',
    committed: '已建库',
    cancelled: '已取消',
    expired: '已过期',
    source_changed: '源文件已变化',
    failed: '处理失败',
  }
  return labels[status] || status
}

export function assignmentCount(decision: Decision, personId: string) {
  return Object.values(decision.assignments).filter(value => assignmentValue(value) === personId).length
}

export function labelIsHandled(label: Label, segments: Segment[], decision: Decision) {
  return segments
    .filter(segment => displayLabel(segment) === label.label)
    .some(segment => Object.prototype.hasOwnProperty.call(decision.assignments, segment.segment_id))
}

export function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}
