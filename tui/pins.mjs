// Ink user-widget companion. The proposed scoped launch API is feature-detected:
// on stock Hermes this file never shadows the Python /pins fallback.
const COMMAND = 'session-pins-ui'
const safe = value => String(value ?? '').replace(/[\p{C}\u2028\u2029]/gu, '').trim()
const failed = (message = 'Invalid selector response.') => new Error(safe(message) || 'Session Pins request failed.')

function parsePage(data) {
  if (!Array.isArray(data.sessions) || !Number.isSafeInteger(data.total) || data.total < 0 ||
      !(data.next_offset === null || (Number.isSafeInteger(data.next_offset) && data.next_offset >= 1)) ||
      typeof data.scope !== 'string' || !data.scope ||
      data.sessions.some(row => !row || typeof row.id !== 'string' || !row.id || typeof row.pinned !== 'boolean')) {
    throw failed()
  }
  return data
}

export default function register(sdk) {
  if (sdk.sessionWidgetApi !== 1) return
  const { Box, Text, Overlay, React, h, isCtrl } = sdk
  let nextInstance = 0

  async function rpc(host, request) {
    const data = JSON.parse(await host.invokePluginCommand(COMMAND, JSON.stringify(request)))
    if (!data || typeof data !== 'object') throw failed()
    if (data.error) throw failed(data.error)
    return data
  }

  function update(instance, version, fn) {
    sdk.updateWidget(app, state => state.instance === instance && state.version === version ? fn(state) : state)
  }

  function query(state, changes = {}) {
    return { ...state, ...changes, version: state.version + 1, pending: 'list', error: '',
      rows: [], index: 0, total: null, next: null }
  }

  function action(state, row, op) {
    const version = state.version + 1
    // The reducer commits the pending state before a reply can resolve. No
    // composer injection, frontend RPC on the input stack, or blocking question.
    void Promise.resolve().then(async () => {
      const result = await rpc(state.host, { op, scope: state.scope, id: row.id,
        ...(op === 'set' ? { pinned: !row.pinned } : {}) })
      if (result.ok !== true) throw failed()
      if (op === 'open') {
        // Host rechecks the launch instance and source profile before switching.
        await state.host.resumeSession(row.id)
      } else {
        update(state.instance, version, current => query(current, { anchor: row.id }))
      }
    }).catch(error => update(state.instance, version, current => ({ ...current, pending: '', error: safe(error.message) })))
    return { ...state, version, pending: op, error: '' }
  }

  function Panel({ state, t, rows: height, cols }) {
    const { host, instance, version, pending, offset, pinnedOnly, needle, scope, anchor } = state
    React.useEffect(() => {
      if (pending !== 'list') return
      let active = true
      const timer = setTimeout(() => {
        void rpc(host, { op: 'list', query: needle, offset, pinned_only: pinnedOnly, ...(scope ? { scope } : {}) })
          .then(parsePage).then(data => {
            if (!active) return
            if (scope && data.scope !== scope) throw failed('The active profile changed. Close and reopen /pins.')
            update(instance, version, current => {
              if (!data.sessions.length && offset > 0) return query(current, { offset: 0, anchor: null })
              return { ...current, rows: data.sessions, total: data.total, next: data.next_offset,
                pending: '', scope: data.scope, anchor: null, index: Math.max(0, data.sessions.findIndex(r => r.id === anchor)) }
            })
          }).catch(error => {
            if (active) update(instance, version, current => ({ ...current, pending: '',
              error: safe(error?.message) || 'Could not load sessions.' }))
          })
      }, needle ? 125 : 0)
      return () => { active = false; clearTimeout(timer) }
    }, [host, instance, version, pending, offset, pinnedOnly, needle, scope, anchor])

    const width = Math.max(1, Math.min(112, cols - 4))
    const room = Math.max(1, Math.min(12, height - 11))
    const start = Math.max(0, Math.min(state.index - Math.floor(room / 2), state.rows.length - room))
    const label = (s, props = {}) => h(Text, { wrap: 'truncate-end', ...props }, s)
    const col = (size, text, props = {}) => h(Box, { width: size, flexShrink: 0 }, label(text, props))
    const date = stamp => {
      const time = new Date(stamp * 1000)
      return stamp > 0 && Number.isFinite(time.valueOf()) ? time.toISOString().slice(0, 16).replace('T', ' ') : '—'
    }
    const wide = width >= 76
    const medium = width >= 48
    const visible = state.rows.slice(start, start + room)
    const hasPage = state.total !== null
    const status = pending === 'list' ? 'Searching…' : hasPage ? `${state.total} matching ${pinnedOnly ? 'pins' : 'chats'}` : ''
    return h(Overlay, { zone: 'bottom-left' },
      h(Box, { borderStyle: 'double', borderColor: t.color.muted, opaque: true, flexDirection: 'column', paddingX: 1, width },
        label(pinnedOnly ? 'Pinned sessions' : 'Sessions', { bold: true, color: t.color.label }),
        label(`${status ? `${status} · ` : ''}Filter: ${safe(needle) || '(type title words or ID)'}`, { color: t.color.muted }),
        (hasPage && wide) && label('      ID          Last active (UTC)  Recorded model      Title', { color: t.color.muted }),
        (hasPage && offset + start > 0) && label(`↑ ${offset + start} above`, { color: t.color.muted }),
        ...visible.map((row, n) => {
          const index = start + n
          const selected = state.index === index
          const relation = row.relationship === 'fork' ? '[fork] ' : row.relationship === 'original' ? '[original] ' : ''
          const title = `${row.pinned ? '★ ' : ''}${relation}${safe(row.title) || 'Untitled chat'}`
          const style = sdk.listRowStyle?.(t, selected) ?? (selected ? { backgroundColor: t.color.completionCurrentBg, color: t.color.text } : {})
          const fg = style.color ?? t.color.muted
          return h(Box, { key: row.id, width: '100%', backgroundColor: style.backgroundColor },
            col(6, `${selected ? '▸' : ' '}${offset + index + 1}.`, { color: fg, bold: selected }),
            medium && col(12, safe(row.display_id).slice(0, 11), { color: fg }),
            wide && col(19, date(row.last_active), { color: fg }),
            wide && col(20, safe(row.recorded_model) || 'unknown', { color: fg }),
            h(Box, { flexGrow: 1, flexShrink: 1, minWidth: 0 }, label(title, { color: fg, bold: selected || row.pinned })))
        }),
        (hasPage && state.total > offset + start + visible.length) &&
          label(`↓ ${state.total - offset - start - visible.length} below`, { color: t.color.muted }),
        (hasPage && !state.rows.length) && label(pinnedOnly ? 'No matching pins. Tab shows all chats.' : 'No matching visible chats.', { color: t.color.muted }),
        state.error && label(state.error, { color: t.color.error }),
        (pending === 'set' || pending === 'open') && label(pending === 'set' ? 'Saving pin…' : 'Opening session…', { color: t.color.muted }),
        label(hasPage ? '↑↓ move · PgUp/PgDn page · Tab pins/all · Ctrl-R refresh' : 'Ctrl-R refresh · Tab pins/all', { color: t.color.muted }),
        label(hasPage ? 'Enter switch · Ctrl-P pin/unpin · Esc close' : 'Esc close', { color: t.color.muted })))
  }

  const app = sdk.defineWidgetApp({
    id: 'pins', help: 'Browse pinned sessions or find chats by title or ID', mode: 'modal',
    accepts: (arg, host) => Boolean(host?.hasPluginCommand(COMMAND)) && /^(?:manage|find(?:\s+.*)?)?$/is.test(arg.trim()),
    init(arg, host) {
      if (!host?.hasPluginCommand(COMMAND)) return null
      const raw = arg.trim()
      const find = /^find(?:\s|$)/i.test(raw)
      return { instance: ++nextInstance, host, version: 0, pinnedOnly: !find,
        needle: find ? [...raw.slice(4).trim()].slice(0, 200).join('') : '', rows: [], offset: 0,
        scope: null, anchor: null, index: 0, total: null, next: null, pending: 'list', error: '' }
    },
    usage: 'Selector unavailable for this session. Try /pins list or run hermes pins find in a separate shell.',
    reduce(state, { ch, key }) {
      if (key.escape || isCtrl(key, ch, 'c')) return null
      if (state.pending === 'set' || state.pending === 'open') return state
      if (key.tab) return query(state, { pinnedOnly: !state.pinnedOnly, offset: 0, anchor: null })
      const row = state.rows[state.index]
      if (isCtrl(key, ch, 'r')) return query(state, { anchor: row?.id ?? null })
      if (key.pageDown && !state.pending && state.next !== null) return query(state, { offset: state.next, anchor: null })
      if (key.pageUp && !state.pending && state.total !== null && state.offset > 0) return query(state, { offset: Math.max(0, state.offset - 20), anchor: null })
      if (key.upArrow || key.downArrow) {
        if (!row) return state
        return { ...state, index: Math.max(0, Math.min(state.rows.length - 1, state.index + (key.upArrow ? -1 : 1))) }
      }
      if (key.return && row && state.scope) return action(state, row, 'open')
      if (isCtrl(key, ch, 'p') && row && state.scope) return action(state, row, 'set')
      const special = key.leftArrow || key.rightArrow || key.pageUp || key.pageDown || key.wheelUp || key.wheelDown ||
        key.home || key.end || key.return || key.delete || key.fn || key.super || key.ctrl || key.meta
      const text = key.backspace ? [...state.needle].slice(0, -1).join('') : !special ?
        state.needle + ch.replace(/[\p{C}\u2028\u2029]/gu, '') : state.needle
      if (text !== state.needle && [...text].length <= 200) return query(state, { needle: text, offset: 0, anchor: null })
      return state
    },
    render: props => h(Panel, props)
  })
}
