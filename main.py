import pandas as pd
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti SC', 'PingFang SC']
plt.rcParams['axes.unicode_minus'] = False

# 伪造一份极寒飞行数据
df = pd.DataFrame({
    "时间_秒":  [0,  60,  120, 180, 240, 300, 360, 420, 480, 540, 600],
    "温度_℃":  [-25.0, -25.3, -25.1, -25.8, -26.0, -26.5, -26.8, -27.0, -27.2, -27.5, -28.0],
    "剩余电量": [100, 96, 91, 85, 78, 70, 61, 52, 43, 35, 28]
})

print("数据长这样：")
print(df.head())

print("\n电量下降情况：")
print(f"10分钟电量从 {df['剩余电量'].iloc[0]}% 降到 {df['剩余电量'].iloc[-1]}%")

# 画图
plt.figure(figsize=(8, 5))
plt.plot(df["时间_秒"], df["剩余电量"], marker="o", label="剩余电量")
plt.xlabel("时间（秒）")
plt.ylabel("剩余电量（%）")
plt.title("极寒环境（-25℃）无人机电池放电曲线")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig("battery_discharge.png", dpi=150)
plt.show()
print("\n图片已保存为 battery_discharge.png")