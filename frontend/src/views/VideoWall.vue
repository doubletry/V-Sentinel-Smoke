<template>
  <div
    class="video-wall"
    v-loading="store.loading && !store.sources.length"
    :element-loading-text="t('videoWall.loading')"
    element-loading-background="rgba(13, 13, 26, 0.72)"
  >
    <!-- Left panel: source list -->
    <div class="left-panel">
      <SourceList />
    </div>
    <!-- Right panel: video grid -->
    <div class="right-panel">
      <VideoGrid />
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSourceStore } from '../stores/source.js'
import SourceList from '../components/SourceList.vue'
import VideoGrid from '../components/VideoGrid.vue'

const store = useSourceStore()
const { t } = useI18n()

onMounted(async () => {
  await store.fetchSources()
  await store.syncProcessorStatus()
})
</script>

<style scoped>
.video-wall {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.left-panel {
  width: 260px;
  flex-shrink: 0;
  overflow: hidden;
}

.right-panel {
  flex: 1;
  overflow: hidden;
}
</style>
