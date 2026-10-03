<script setup>
import { computed } from 'vue'

const props = defineProps({
  scene: { type: Object, default: null },
  distanceRun: { type: Object, default: null },
  energyRun: { type: Object, default: null },
  interactive: Boolean,
})
const emit = defineEmits(['cell'])
const unit = 30
const width = computed(() => props.scene?.width || 22)
const height = computed(() => props.scene?.height || 14)
const center = (point) => point ? [(point[0] + 0.5) * unit, (point[1] + 0.5) * unit] : [0, 0]
const polyline = (path) => (path || []).map((point) => center(point).join(',')).join(' ')
const winds = computed(() => props.scene?.wind?.regions || props.scene?.wind_regions || [])
const cells = computed(() => Array.from({ length: width.value * height.value }, (_, index) => [index % width.value, Math.floor(index / width.value)]))
const visited = (target) => (props.scene?.visited_targets || []).some((item) => Array.isArray(item) && item[0] === target[0] && item[1] === target[1])
const viewPath = (run) => run?.executed_path?.length ? run.executed_path : run?.path

function onClick(event) {
  if (!props.interactive) return
  const svg = event.currentTarget
  const point = svg.createSVGPoint()
  point.x = event.clientX
  point.y = event.clientY
  const local = point.matrixTransform(svg.getScreenCTM().inverse())
  const x = Math.floor(local.x / unit)
  const y = Math.floor(local.y / unit)
  if (x >= 0 && y >= 0 && x < width.value && y < height.value) emit('cell', [x, y])
}
</script>

<template>
  <div class="map-shell">
    <div class="map-caption">
      <span>二维巡检场景</span>
      <span>{{ scene?.cell_size_m || '—' }} m / 格 · 固定高度</span>
    </div>
    <svg :viewBox="`0 0 ${width * unit} ${height * unit}`" :class="['mission-map', { interactive }]" @click="onClick" role="img" :aria-label="interactive ? '巡检地图，点击格子发送新增障碍事件' : '巡检路线、风场和无人机仿真位置'">
      <defs>
        <pattern id="obstacle-fill" width="7" height="7" patternUnits="userSpaceOnUse"><rect width="7" height="7" fill="#cbd4ce" /><path d="M-1 1L6 8M3-3L10 4" stroke="#a4b1a8" stroke-width="1" /></pattern>
        <marker id="wind-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L10 5L0 10z" fill="#6c97a0" /></marker>
      </defs>
      <rect :width="width * unit" :height="height * unit" fill="#f5f8f5" />
      <rect v-for="point in cells" :key="`c-${point}`" :x="point[0] * unit" :y="point[1] * unit" :width="unit" :height="unit" fill="none" stroke="#e2e9e3" stroke-width="0.7" />
      <g v-for="(region, index) in winds" :key="`w-${index}`">
        <rect :x="region.x_min * unit" :y="region.y_min * unit" :width="(region.x_max - region.x_min + 1) * unit" :height="(region.y_max - region.y_min + 1) * unit" fill="#dcebf0" fill-opacity="0.65" stroke="#a9c7cf" stroke-dasharray="4 4" />
        <path :d="`M${(region.x_min + 0.8) * unit},${(region.y_min + 0.8) * unit}l${(region.vector?.[0] || 0) * 7},${(region.vector?.[1] || 0) * 7}`" stroke="#6c97a0" stroke-width="2" marker-end="url(#wind-arrow)" />
        <text :x="(region.x_min + 0.4) * unit" :y="(region.y_min + 1.7) * unit" font-size="10" fill="#527580">风场 {{ region.vector?.join(', ') }} m/s</text>
      </g>
      <rect v-for="point in scene?.blocked || []" :key="`b-${point}`" :x="point[0] * unit + 1" :y="point[1] * unit + 1" :width="unit - 2" :height="unit - 2" rx="2" fill="url(#obstacle-fill)" />
      <polyline v-if="distanceRun" :points="polyline(viewPath(distanceRun))" fill="none" stroke="#bc8645" stroke-width="3" stroke-dasharray="7 5" stroke-linejoin="round" opacity="0.85" />
      <polyline v-if="energyRun" :points="polyline(viewPath(energyRun))" fill="none" stroke="#28694f" stroke-width="3.5" stroke-linejoin="round" opacity="0.9" />
      <polyline v-if="!distanceRun && !energyRun && scene?.executed_path?.length" :points="polyline(scene.executed_path)" fill="none" stroke="#98b7a5" stroke-width="3" stroke-linejoin="round" />
      <polyline v-if="!distanceRun && !energyRun" :points="polyline(scene?.path)" fill="none" stroke="#28694f" stroke-width="3.5" stroke-dasharray="6 3" stroke-linejoin="round" />
      <g v-if="scene?.start" :transform="`translate(${center(scene.start)})`">
        <rect x="-10" y="-10" width="20" height="20" rx="5" fill="#285848" />
        <path d="M-6 0L0-5L6 0V6H-6Z" fill="white" />
        <text x="13" y="4" font-size="11" fill="#285848">起点 / 回收点</text>
      </g>
      <g v-for="(target, index) in scene?.targets || []" :key="`t-${index}`" :transform="`translate(${center(target)})`">
        <circle r="12" :fill="visited(target, index) ? '#d5e8db' : '#ffffff'" stroke="#285848" stroke-width="2" />
        <text text-anchor="middle" y="4" font-size="12" font-weight="700" fill="#285848">{{ index + 1 }}</text>
        <text x="15" y="4" font-size="11" fill="#465d50">巡检点 {{ index + 1 }}</text>
      </g>
      <g v-if="scene?.position" :transform="`translate(${center(scene.position)})`">
        <circle r="15" fill="#285848" fill-opacity="0.12" />
        <circle r="7" fill="#285848" stroke="white" stroke-width="2" />
      </g>
    </svg>
    <div class="map-legend">
      <span><i class="legend-line green"></i>{{ energyRun ? '能量策略执行轨迹' : '待执行路线' }}</span>
      <span v-if="distanceRun"><i class="legend-line amber"></i>距离策略执行轨迹</span>
      <span v-if="scene?.position"><i class="legend-dot"></i>后端仿真位置</span>
      <span><i class="legend-block"></i>障碍</span>
      <span><i class="legend-wind"></i>风场区域</span>
    </div>
  </div>
</template>
