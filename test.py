import matplotlib
matplotlib.use("TkAgg")  # 또는 "Qt5Agg", "Agg" 등

import matplotlib.pyplot as plt

times = ["9:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]
values = [11.5, 12.6, 13.8, 15.2, 15.9, 16.3, 15.6]

plt.plot(times, values, marker='o')
plt.xlabel("Time")
plt.ylabel("Value")
plt.title("Values over Time")
plt.grid(True)
plt.show()
