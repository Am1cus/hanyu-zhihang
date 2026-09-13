<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" title="第一次使用，从这里开始" width="min(740px, 94vw)">
    <p class="guide-intro">只想查看成果？关闭此窗口，在「预测看板」选择「切换记录」，打开一条已完成的架次，无需重新回放。</p>
    <ol class="guide-steps">
      <li><h3>启动系统</h3><p>在项目目录打开终端，执行下方命令并保持运行。页面上方已显示后台和AI在线时，可跳过这一步。</p><div class="command"><code>./demo/start_demo.sh</code><el-button @click="copy('./demo/start_demo.sh', '启动命令')">复制启动命令</el-button></div></li>
      <li><h3>回放一段 AirSim 数据</h3><p>另开一个终端，仍在项目目录执行。下面的路径可改为你电脑上的数据文件；新回放不会删除历史。</p><label class="guide-field">数据包路径<el-input v-model="sourcePath" aria-label="数据包路径" /></label><div class="command"><code>{{ command }}</code><el-button :disabled="!sourcePath.trim()" @click="copy(command, '回放命令')">复制回放命令</el-button></div></li>
      <li><h3>回到看板，等曲线出现</h3><p>若看板处于历史视图，点击「跟随最新回放」；已在跟随时无需操作。2倍速下约15秒出现首次预测，再过5秒出现可核对的实际值。回放结束后曲线会保留。</p></li>
    </ol>
    <details class="help-details"><summary>怎么看懂曲线和误差？</summary><p>绿色实线是后续10秒实际发生的仿真耗电，橙色虚线是模型提前给出的预测。越接近通常越好；平均相对误差（MAPE）越小越好，但不能用100%减去它当作准确率。</p><p>「简单方法」指延续过去耗电或按平均电流估算，不使用LSTM。所有方法在相同片段上比较。末尾没有后续数据的预测不计算误差。</p></details>
    <p class="footnote">当前数据来自AirSim和公式电池，F022已参与探索性选型；不是新的盲测，也不代表真机表现。页面操作不向无人机发送控制指令。</p>
    <template #footer><el-button type="primary" @click="$emit('update:modelValue', false)">关闭指南</el-button></template>
  </el-dialog>
</template>
<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { replayCommand } from '@/utils/presentation'
defineProps({ modelValue: Boolean })
defineEmits(['update:modelValue'])
const sourcePath = ref('/Users/kedong/Downloads/dataset_v2.zip')
const command = computed(() => replayCommand(sourcePath.value.trim()))
async function copy(text, label) {
  try { await navigator.clipboard.writeText(text); ElMessage.success(label + '已复制') }
  catch { ElMessage.warning('复制不可用，请手动选择命令复制。') }
}
</script>
<style scoped>
.guide-intro{background:var(--soft);padding:16px;border-radius:8px;line-height:1.7}.guide-steps{padding-left:24px;margin:24px 0}.guide-steps li{padding-left:8px;margin-bottom:24px}.guide-steps li::marker{color:var(--green);font-weight:700}.guide-steps h3{margin-bottom:8px}.guide-steps p{color:var(--muted);line-height:1.7}.command{display:flex;gap:12px;align-items:flex-start;margin-top:12px;padding:14px;background:#f3f5f6;border:1px solid var(--line);border-radius:8px}.command code{flex:1;min-width:0;overflow-wrap:anywhere;white-space:pre-wrap;font-size:.875rem;line-height:1.7}.guide-field{display:grid;gap:8px;margin-top:12px;font-size:.875rem}.help-details{margin:20px 0}.help-details p{margin-top:12px;line-height:1.75}@media(max-width:600px){.command{flex-direction:column}}
</style>
