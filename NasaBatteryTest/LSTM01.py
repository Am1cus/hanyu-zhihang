import scipy.io
import numpy as np
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti SC', 'PingFang SC']
plt.rcParams['axes.unicode_minus'] = False

# ==================== 1. 准备数据 ====================
mat = scipy.io.loadmat("B5Capacity.mat")
capacity = mat['B5Capacity'].flatten()

lookback = 10
X_list, y_list = [], []
for i in range(len(capacity) - lookback):
    X_list.append(capacity[i:i + lookback])
    y_list.append(capacity[i + lookback])

X = np.array(X_list, dtype=np.float32)  # (158, 10)
y = np.array(y_list, dtype=np.float32)  # (158,)

# LSTM要求的输入形状: [样本数, 时间步数, 特征数]
# 目前X是(158, 10)，需要变成(158, 10, 1)
X = X.reshape(-1, lookback, 1)

# 划分训练/测试
split = int(len(X) * 0.8)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]

# 转成PyTorch张量
X_train_t = torch.from_numpy(X_train)
y_train_t = torch.from_numpy(y_train).unsqueeze(1)  # (126,) → (126,1)
X_test_t = torch.from_numpy(X_test)
y_test_t = torch.from_numpy(y_test).unsqueeze(1)

# 包装成DataLoader
dataset = TensorDataset(X_train_t, y_train_t)
loader = DataLoader(dataset, batch_size=16, shuffle=True)


# ==================== 2. 定义LSTM模型 ====================
class BatteryLSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=1,  # 每次只看1个值（容量）
            hidden_size=32,  # 隐藏层大小
            num_layers=1,  # 1层LSTM
            batch_first=True  # 输入格式: (batch, seq, feature)
        )
        self.fc = nn.Linear(32, 1)  # 全连接层：32个隐藏值 → 1个预测值

    def forward(self, x):
        out, _ = self.lstm(x)  # out形状: (batch, seq, 32)
        out = out[:, -1, :]  # 只取最后一个时间步的输出
        out = self.fc(out)  # (batch, 32) → (batch, 1)
        return out


model = BatteryLSTM()
criterion = nn.MSELoss()  # 均方误差损失
optimizer = torch.optim.Adam(model.parameters(), lr=0.005)

print(f"模型参数量: {sum(p.numel() for p in model.parameters())}")

# ==================== 3. 训练模型 ====================
epochs = 200
train_losses = []

print("\n开始训练...")
for epoch in range(epochs):
    epoch_loss = 0
    for X_batch, y_batch in loader:
        optimizer.zero_grad()
        pred = model(X_batch)
        loss = criterion(pred, y_batch)
        loss.backward()
        optimizer.step()
        epoch_loss += loss.item()

    avg_loss = epoch_loss / len(loader)
    train_losses.append(avg_loss)

    if (epoch + 1) % 40 == 0:
        print(f"Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.6f}")

# ==================== 4. 测试模型 ====================
model.eval()
with torch.no_grad():
    train_pred = model(X_train_t).numpy().flatten()
    test_pred = model(X_test_t).numpy().flatten()

# 计算测试集误差
test_mape = np.mean(np.abs((y_test - test_pred) / y_test)) * 100
print(f"\n测试集 MAPE (平均百分比误差): {test_mape:.2f}%")
print(f"测试集 MAE  (平均绝对误差):   {np.mean(np.abs(y_test - test_pred)):.4f} Ah")

# ==================== 5. 画图 ====================
fig, axes = plt.subplots(1, 3, figsize=(15, 4))

# 图1：训练loss曲线
axes[0].plot(train_losses, color='steelblue')
axes[0].set_xlabel("Epoch")
axes[0].set_ylabel("Loss (MSE)")
axes[0].set_title("训练损失下降曲线")
axes[0].grid(True, alpha=0.3)

# 图2：训练集预测 vs 真实
axes[1].scatter(y_train, train_pred, alpha=0.6, s=15, color='steelblue')
axes[1].plot([y_train.min(), y_train.max()], [y_train.min(), y_train.max()],
             'r--', linewidth=1, label='完美预测线')
axes[1].set_xlabel("真实容量 (Ah)")
axes[1].set_ylabel("预测容量 (Ah)")
axes[1].set_title(f"训练集 (126样本)")
axes[1].legend()
axes[1].grid(True, alpha=0.3)

# 图3：测试集预测 vs 真实
axes[2].scatter(y_test, test_pred, alpha=0.8, s=25, color='darkorange')
axes[2].plot([y_test.min(), y_test.max()], [y_test.min(), y_test.max()],
             'r--', linewidth=1, label='完美预测线')
axes[2].set_xlabel("真实容量 (Ah)")
axes[2].set_ylabel("预测容量 (Ah)")
axes[2].set_title(f"测试集 (32样本) | MAPE: {test_mape:.1f}%")
axes[2].legend()
axes[2].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig("lstm_results.png", dpi=150)
plt.show()
print("\n图片已保存为 lstm_results.png")