import { describe, expect, it } from 'vitest'
import {
  ALL_NOTIFICATION_SOURCES_VALUE,
  applyNotificationSourceSelection,
  buildNotificationInstancePayload,
  createDefaultNotificationInstanceForm,
  defaultSocketMessageTemplate,
  formatSocketHexBytes,
  serializeNotificationSourceSelection,
  serializeNotificationInstanceForEdit,
} from '../notificationInstances.js'

const t = (key) => key

describe('notification instance helpers', () => {
  it('creates a default form with all-sources enabled', () => {
    const form = createDefaultNotificationInstanceForm()
    expect(form.apply_to_all_sources).toBe(true)
    expect(form.source_ids).toEqual([])
    expect(form.socket_message_text).toBe(defaultSocketMessageTemplate)
    expect(serializeNotificationSourceSelection(form)).toEqual([ALL_NOTIFICATION_SOURCES_VALUE])
  })

  it('keeps all-sources as a dedicated dropdown option', () => {
    expect(
      applyNotificationSourceSelection(createDefaultNotificationInstanceForm('socket'), [ALL_NOTIFICATION_SOURCES_VALUE]),
    ).toEqual({
      apply_to_all_sources: true,
      source_ids: [],
    })
  })

  it('switches from all-sources to specific sources when a source is picked from the dropdown', () => {
    expect(
      applyNotificationSourceSelection(createDefaultNotificationInstanceForm('socket'), [ALL_NOTIFICATION_SOURCES_VALUE, 'source-a']),
    ).toEqual({
      apply_to_all_sources: false,
      source_ids: ['source-a'],
    })
  })

  it('builds a socket string payload with scoped sources', () => {
    const form = {
      ...createDefaultNotificationInstanceForm('socket'),
      name: 'Ops Socket',
      apply_to_all_sources: false,
      source_ids: ['source-a', 'source-b'],
      socket_protocol: 'tcp',
      socket_host: '127.0.0.1',
      socket_port: '9527',
      socket_message_mode: 'string',
      socket_message_text: 'Alert from {source_name}',
      socket_encoding: 'gbk',
      socket_wait_for_response: true,
      socket_response_timeout_seconds: '1.5',
    }

    expect(buildNotificationInstancePayload(form, t)).toEqual({
      name: 'Ops Socket',
      type: 'socket',
      enabled: true,
      apply_to_all_sources: false,
      source_ids: ['source-a', 'source-b'],
      config: {
        cooldown_seconds: '300',
        protocol: 'tcp',
        host: '127.0.0.1',
        port: '9527',
        message_mode: 'string',
        message_text: 'Alert from {source_name}',
        encoding: 'gbk',
        wait_for_response: true,
        response_timeout_seconds: '1.5',
      },
    })
  })

  it('normalizes socket hex payloads', () => {
    const form = {
      ...createDefaultNotificationInstanceForm('socket'),
      name: 'Hex Socket',
      socket_host: '127.0.0.1',
      socket_port: '9528',
      socket_message_mode: 'hex',
      socket_message_hex: '41 42 43 44',
    }

    expect(buildNotificationInstancePayload(form, t).config.message_hex).toBe('41424344')
  })

  it('formats socket hex bytes with separators for display', () => {
    expect(formatSocketHexBytes('41 42-4344')).toBe('41-42-43-44')
  })

  it('requires at least one source when all-sources is off', () => {
    const form = {
      ...createDefaultNotificationInstanceForm('socket'),
      name: 'Scoped Socket',
      apply_to_all_sources: false,
      source_ids: [],
      socket_host: '127.0.0.1',
      socket_port: '9528',
    }

    expect(() => buildNotificationInstancePayload(form, t)).toThrow('settings.notificationSourceSelectionRequired')
  })

  it('rehydrates source scope and socket config for editing', () => {
    const form = serializeNotificationInstanceForEdit({
      name: 'Ops Socket',
      type: 'socket',
      enabled: true,
      apply_to_all_sources: false,
      source_ids: ['source-a'],
      config: {
        protocol: 'udp',
        host: '127.0.0.1',
        port: 9527,
        message_mode: 'hex',
        message_hex: '41424344',
        wait_for_response: true,
        response_timeout_seconds: 2,
      },
    })

    expect(form.apply_to_all_sources).toBe(false)
    expect(form.source_ids).toEqual(['source-a'])
    expect(form.socket_protocol).toBe('udp')
    expect(form.socket_message_mode).toBe('hex')
    expect(form.socket_message_hex).toBe('41424344')
    expect(form.socket_wait_for_response).toBe(true)
    expect(form.socket_response_timeout_seconds).toBe('2')
  })

  it('rejects non-positive tcp response timeout', () => {
    const form = {
      ...createDefaultNotificationInstanceForm('socket'),
      name: 'Wait Socket',
      socket_host: '127.0.0.1',
      socket_port: '9527',
      socket_wait_for_response: true,
      socket_response_timeout_seconds: '0',
    }

    expect(() => buildNotificationInstancePayload(form, t)).toThrow('settings.notificationSocketTimeoutInvalid')
  })
})