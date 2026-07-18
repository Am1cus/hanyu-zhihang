import scipy.io
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti SC', 'PingFang SC']
plt.rcParams['axes.unicode_minus'] = False

# === 1. 读数据 ===
mat = scipy.io.loadmat("B5Capacity.mat")
capacity = mat['B5Capacity'].flatten()

print(f"数据量: {len(capacity)} 次循环")

# === 2. 制作训练样本：用前N次预测第N+1次 ===
lookback = 10  # 用过去10次循环的容量，预测第11次的容量

X, y = [], []
for i in range(len(capacity) - lookback):
    X.append(capacity[i:i+lookback])   # 输入：连续10个容量值
    y.append(capacity[i+lookback])      # 输出：第11个容量值

X = np.array(X)
y = np.array(y)

print(f"输入X形状: {X.shape}")   # (158, 10) — 158个样本，每个样本10个值
print(f"输出y形状: {y.shape}")   # (158,)    — 158个对应的标签

# === 3. 划分训练集(前80%)和测试集(后20%) ===
split = int(len(X) * 0.8)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]

print(f"训练集: {len(X_train)} 样本, 测试集: {len(X_test)} 样本")

# === 4. 画图：看训练集和测试集怎么分的 ===
plt.figure(figsize=(12, 4))

plt.subplot(1, 2, 1)
plt.plot(capacity, color='steelblue', linewidth=1)
plt.axvline(x=split+lookback, color='red', linestyle='--', label='训练/测试分界')
plt.xlabel("循环次数")
plt.ylabel("容量 (Ah)")
plt.title("全部数据 & 训练/测试划分")
plt.legend()
plt.grid(True, alpha=0.3)

plt.subplot(1, 2, 2)
# 展示第一个训练样本
sample_idx = 0
plt.plot(range(lookback), X_train[sample_idx], 'o-', label='输入(10个过去值)')
plt.scatter(lookback, y_train[sample_idx], color='red', s=80, zorder=5, label='输出(要预测的值)')
plt.xlabel("相对位置")
plt.ylabel("容量 (Ah)")
plt.title(f"一个训练样本的样子\n(样本0)")
plt.legend()
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig("data_preview.png", dpi=150)
plt.show()

print("\n图片已保存为 data_preview.png")
print("\n=== 数据准备完成 ===")
print("你现在手里有：")
print(f"  X_train: {X_train.shape} ← 用来训练的'题目'")
print(f"  y_train: {y_train.shape} ← 用来训练的'答案'")
print(f"  X_test:  {X_test.shape}  ← 用来测试的'题目'")
print(f"  y_test:  {y_test.shape}  ← 用来测试的'答案'（模型没见过）")