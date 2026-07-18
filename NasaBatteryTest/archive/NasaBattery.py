import scipy.io
import matplotlib.pyplot as plt
import pandas as pd

# 修复中文
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti SC', 'PingFang SC']
plt.rcParams['axes.unicode_minus'] = False

# 读容量数据
mat = scipy.io.loadmat("B5Capacity.mat")
capacity = mat['B5Capacity'].flatten()   # 拉平成一维数组

# 循环次数：第1次、第2次...第168次
cycles = range(1, len(capacity) + 1)

# 打印基本信息
print(f"总共有 {len(capacity)} 次充放电循环")
print(f"初始容量: {capacity[0]:.4f} Ah")
print(f"最终容量: {capacity[-1]:.4f} Ah")
print(f"衰减了: {(capacity[0] - capacity[-1]):.4f} Ah ({(1 - capacity[-1]/capacity[0])*100:.1f}%)")

# 画图
plt.figure(figsize=(10, 5))
plt.plot(cycles, capacity, linewidth=1.2, color='steelblue')
plt.xlabel("充放电循环次数")
plt.ylabel("电池容量 (Ah)")
plt.title("NASA B0005电池 — 容量衰减曲线（室温，约24℃）")
plt.grid(True, alpha=0.3)

# 标注关键点
plt.annotate(f"初始: {capacity[0]:.3f}Ah", xy=(1, capacity[0]),
             xytext=(10, capacity[0]+0.02), fontsize=9)
plt.annotate(f"最终: {capacity[-1]:.3f}Ah", xy=(168, capacity[-1]),
             xytext=(130, capacity[-1]+0.03), fontsize=9)

plt.tight_layout()
plt.savefig("B5_capacity_degradation.png", dpi=150)
plt.show()
print("\n图片已保存为 B5_capacity_degradation.png")

# 读B0005特征CSV
df = pd.read_csv("B0005_feature.csv", header=None)
print(f"\nB0005_feature 形状: {df.shape}")
print(f"前5行前5列:\n{df.iloc[:5, :5]}")