<script setup>
defineProps({ name: { type: String, default: 'route' } })
const paths = {
  route: ['M5 5h5a4 4 0 0 1 0 8H8a4 4 0 0 0 0 8h11', 'M16 18l3 3-3 2', 'M3 5a2 2 0 1 0 4 0 2 2 0 1 0-4 0'],
  play: ['M9 5l11 7-11 7V5Z', 'M4 5v14'],
  archive: ['M4 4h16v4H4Z', 'M6 8v12h12V8', 'M10 12h4'],
  snow: ['M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9', 'M9 5l3 3 3-3M9 19l3-3 3 3'],
  drone: ['M8 9h8v6H8Z', 'M8 9L5 6M16 9l3-3M8 15l-3 3M16 15l3 3', 'M2 5h6M16 5h6M2 19h6M16 19h6', 'M12 7V4'],
  compass: ['M12 2a10 10 0 1 0 0 20 10 10 0 1 0 0-20', 'M15 9l-2 4-4 2 2-4 4-2Z'],
}
</script>
<template>
  <svg class="app-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path v-for="(d, index) in paths[name] || paths.route" :key="index" :d="d" /></svg>
</template>
