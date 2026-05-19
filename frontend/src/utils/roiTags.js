const ROI_TAG_LABELS = {
  smoke: {
    smoke_zone: {
      zh: '烟雾区域',
      en: 'Smoke Zone',
    },
    fire_zone: {
      zh: '火焰区域',
      en: 'Fire Zone',
    },
  },
  template: {
    template_zone: {
      zh: '模板区域',
      en: 'Template Zone',
    },
  },
}

export function localizedSceneLabel(scene, locale) {
  if (!scene) return ''
  return locale === 'en-US' ? scene.label_en : scene.label_zh
}

export function localizedRoiTagLabel(sceneId, tag, locale) {
  const labels = ROI_TAG_LABELS[sceneId]?.[tag]
  if (!labels) return tag
  return locale === 'en-US' ? labels.en : labels.zh
}

export function sceneScopedRoiTagLabel(scene, tag, locale) {
  const sceneLabel = localizedSceneLabel(scene, locale) || scene?.id || ''
  const tagLabel = localizedRoiTagLabel(scene?.id, tag, locale)
  return sceneLabel ? `${sceneLabel} · ${tagLabel}` : tagLabel
}
