<template>
  <div class="settings-nav">
    <el-button
      v-for="section in sections"
      :key="section.id"
      size="small"
      text
      class="settings-nav__button"
      @click="$emit('jump', section.id)"
    >
      {{ section.label }}
    </el-button>
  </div>
</template>

<script setup>
defineProps({
  sections: {
    type: Array,
    default: () => [],
  },
})

defineEmits(['jump'])
</script>
