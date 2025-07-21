import tkinter as tk
from tkinter import ttk, messagebox
#
import pandas as pd
import joblib
import requests
import numpy as np
from datetime import datetime
from calendar import monthrange
import matplotlib.pyplot as plt

# --- Monthly Accumulators ---
daily_energy_total = 0.0
daily_temp_readings = []
daily_hum_readings = []
last_logged_date = None

# Load ML Model
model = joblib.load("/Users/gautamdevaraj/Desktop/Monitor/bill_predictor_model.pkl")

# ESP32 URL (Change this to your ESP32 IP)
ESP32_URL = "http://192.168.1.17/"  # Replace with your actual ESP32 IP
DATASET_PATH = "/Users/gautamdevaraj/Desktop/Monitor/dataset.csv"

# ---------- Helper Functions ----------

def fetch_realtime_data():
    global daily_energy_total, daily_temp_readings, daily_hum_readings, last_logged_date
    try:
        response = requests.get(ESP32_URL, timeout=5)
        if response.status_code == 200:
            raw = response.text.strip()

            # Log format: "13/07/2025,2.56,32.4,65.0"
            if ',' in raw and raw.count(',') == 3:
                date, kwh, temp, hum = raw.split(',')

            # Live format: 
            # Live Energy: 1.2345 kWh
            # Temp: 32.55 °C
            # Humidity: 67.33 %
            elif "Live Energy" in raw:
                lines = raw.split('\n')
                if len(lines) < 3:
                    raise ValueError("Incomplete ESP32 live data format")

                kwh = float(lines[0].split(':')[-1].strip().split()[0])
                temp = float(lines[1].split(':')[-1].strip().split()[0])
                hum = float(lines[2].split(':')[-1].strip().split()[0])
                date = datetime.now().strftime("%d/%m/%Y")

            else:
                raise ValueError("Unknown ESP32 response format")

            # Store for monthly log
            if date != last_logged_date:
                last_logged_date = date
                daily_energy_total += float(kwh)
                daily_temp_readings.append(float(temp))
                daily_hum_readings.append(float(hum)) 

                day, month, year = map(int, date.split('/'))
                last_day = monthrange(year, month)[1]

                if day == last_day:
                    df = pd.read_csv(DATASET_PATH)
                    new_row = {
                        "Year": year,
                        "Month": month,
                        "Median_Temp": np.median(daily_temp_readings),
                        "Median_Humidity": np.median(daily_hum_readings),
                        "Total_kWh": round(daily_energy_total, 2)
                    }
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    df.to_csv(DATASET_PATH, index=False)

                    daily_energy_total = 0.0
                    daily_temp_readings = []
                    daily_hum_readings = []

            return {
                "date": date,
                "kwh": float(kwh),
                "temp": float(temp),
                "hum": float(hum)
            }
        else:
            raise Exception("Invalid response from ESP32")

    except Exception as e:
        messagebox.showerror("ESP32 Error", f"Could not fetch data:\n{e}")
        return None


# --- Fetch logged months from ESP32 and update local dataset ---
def fetch_logged_months():
    try:
        response = requests.get(ESP32_URL + "monthly", timeout=5)
        if response.status_code == 200:
            lines = response.text.strip().splitlines()
            df = pd.read_csv(DATASET_PATH)

            for line in lines:
                if line.strip().count(',') == 3:
                    date_str, kwh, temp, hum = line.split(',')
                    day, month, year = map(int, date_str.split('/'))
                    kwh = float(kwh)
                    temp = float(temp)
                    hum = float(hum)

                    new_row = {
                        "Year": year,
                        "Month": month,
                        "Median_Temp": temp,
                        "Median_Humidity": hum,
                        "Total_kWh": round(kwh, 2)
                    }

                    if not ((df["Year"] == year) & (df["Month"] == month)).any():
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            df.to_csv(DATASET_PATH, index=False)
            messagebox.showinfo("Sync Complete", "Logged monthly data successfully added.")
        else:
            raise ValueError("Failed to fetch logs from ESP32")

    except Exception as e:
        messagebox.showerror("Log Sync Error", f"Error fetching logs:\n{e}")

def check_selected_month():
    try:
        df = pd.read_csv(DATASET_PATH)
        if not all(col in df.columns for col in ["Year", "Month", "Median_Temp", "Median_Humidity", "Total_kWh"]):
            raise ValueError("Required columns not found in dataset")

        selected_month = month_options.index(month_var.get()) + 1
        selected_year = int(year_var.get())

        row = df[(df["Year"] == selected_year) & (df["Month"] == selected_month)]
        if not row.empty:
            kwh = round(row.iloc[0]["Total_kWh"], 2)
            temp = round(row.iloc[0]["Median_Temp"], 1)
            hum = round(row.iloc[0]["Median_Humidity"], 1)
            bill = round(kwh * 6.5, 2)
        else:
            kwh = temp = hum = bill = "--"

        for row in month_result.get_children():
            month_result.delete(row)
        month_result.insert("", "end", values=(month_var.get(), year_var.get(), kwh, bill, temp, hum))

    except Exception as e:
        messagebox.showerror("Month View Error", str(e))

def check_now():
    data = fetch_realtime_data()
    if data is None:
        return

    kwh = data["kwh"]
    temp = data["temp"]
    hum = data["hum"]
    date = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # Clear existing data
    for row in now_result_table.get_children():
        now_result_table.delete(row)

    # Insert data into the Treeview
    now_result_table.insert("", "end", values=(date, f"{kwh:.3f} kWh", f"{temp:.2f} °C", f"{hum:.2f} %"))

def predict_bill():
    choice = prediction_choice.get()
    try:
        df = pd.read_csv(DATASET_PATH)
        if not all(col in df.columns for col in ["Month", "Median_Temp", "Median_Humidity", "Total_kWh"]):
            raise ValueError("Required columns not found in dataset")

        current_month = datetime.now().month
        temp_group = df.groupby("Month")["Median_Temp"].median()
        hum_group = df.groupby("Month")["Median_Humidity"].median()

        if choice == "next":
            # Get last recorded month and year
            last_row = df.sort_values(by=["Year", "Month"]).iloc[-1]
            m = int(last_row["Month"]) + 1
            y = int(last_row["Year"])
            if m > 12:
                m = 1
                y += 1

            temp = df[df["Month"] == m]["Median_Temp"].median()
            hum = df[df["Month"] == m]["Median_Humidity"].median()

            if pd.isna(temp):
                temp = df["Median_Temp"].mean()
            if pd.isna(hum):
                hum = df["Median_Humidity"].mean()

            input_data = np.array([[y, m, temp, hum]])
            pred = model.predict(input_data)[0]
            bill = pred * 6.5

            # Replace text label with Treeview display
            for row in next_result.get_children():
                next_result.delete(row)
            next_result.insert("", "end", values=(f"{month_options[m-1]}", f"{y}", f"{pred:.2f}", f"{bill:.2f}", f"{temp:.1f}", f"{hum:.1f}"))

        elif choice == "rest":
            future_months = pd.DataFrame({
                "Year": [datetime.now().year] * (12 - current_month),
                "Month": list(range(current_month + 1, 13))
            })

            recent = df.tail(6)
            median_temp = recent["Median_Temp"].median()
            median_humidity = recent["Median_Humidity"].median()

            np.random.seed(42)
            future_months["Median_Temp"] = median_temp + np.random.uniform(-1.5, 1.5, size=len(future_months))
            future_months["Median_Humidity"] = median_humidity + np.random.uniform(-3.0, 3.0, size=len(future_months))

            X_future = future_months[["Year", "Month", "Median_Temp", "Median_Humidity"]].values
            pred_kwh = model.predict(X_future)
            pred_kwh *= (1 + np.random.uniform(-0.07, 0.1, size=len(pred_kwh)))

            bill_total = sum(pred_kwh) * 6.5

            # Clear text label
            result_label.config(text="")

            # Generate Month-Year labels
            now = datetime.now()
            year = now.year
            months = list(range(current_month + 1, 13))
            labels = [f"{year}-{str(m).zfill(2)}" for m in months]

            # Calculate predicted bills
            bills = [round(p * 6.5) for p in pred_kwh]

            # Plot with bill annotations
            plt.figure(figsize=(10, 5))
            bars = plt.bar(labels, pred_kwh, color="#4CAF50", edgecolor="black")
            plt.title("📊 Smarter & Realistic Prediction: Aug–Dec 2025")
            plt.xlabel("Month-Year")
            plt.ylabel("Predicted Usage (kWh)")
            plt.grid(axis="y")

            for bar, bill in zip(bars, bills):
                plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 3, f"₹{bill}", ha="center", va="bottom", fontweight="bold")

            plt.tight_layout()
            plt.show()

    except Exception as e:
        messagebox.showerror("Prediction Error", str(e))

# ---------- UI Setup ----------
root = tk.Tk()
root.title(" Smart Energy Monitor & Bill Predictor")
root.geometry("400x600")
root.configure(bg="#1e1e1e")  # Dark gray background

style = ttk.Style()
style.configure("Treeview", font=("Arial", 12), rowheight=28)
style.configure("Treeview.Heading", font=("Arial", 13, "bold"))

#
# --- Sync ESP32 Logs Button ---
tk.Button(
    root,
    text="Sync ESP32 Logs",
    command=fetch_logged_months,
    bg="#4CAF50",
    fg="white",
    font=("Arial", 12, "bold")
).pack(pady=10)

# --- Monthly Picker ---
tk.Label(
    root,
    text="Select Month to View Usage",
    font=("Verdana", 16, "bold"),
    bg="#1e1e1e",
    fg="white"
).pack(pady=5)

month_frame = tk.Frame(root, bg="#1e1e1e")
month_frame.pack(pady=5)

month_options = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
month_var = tk.StringVar(value="July")
year_var = tk.StringVar(value="2024")

month_menu = ttk.Combobox(month_frame, textvariable=month_var, values=month_options, state="readonly", width=15)
year_menu = ttk.Combobox(month_frame, textvariable=year_var, values=["2023", "2024"], state="readonly", width=10)
check_button = tk.Button(
    month_frame,
    text="Check Month",
    command=check_selected_month,
    bg="#f0f0f0",
    fg="black",
    activebackground="#d0d0d0",
    highlightthickness=0,
    font=("Arial", 13)
)

month_menu.pack(side="left", padx=5)
year_menu.pack(side="left", padx=5)
check_button.pack(side="left", padx=5)

# Treeview for month result
month_result = ttk.Treeview(root, columns=("month", "year", "kwh", "bill", "temp", "hum"), show="headings", height=1)
month_result.heading("month", text="Month")
month_result.heading("year", text="Year")
month_result.heading("kwh", text="kWh")
month_result.heading("bill", text="Bill (₹)")
month_result.heading("temp", text="Temp (°C)")
month_result.heading("hum", text="Humidity (%)")
month_result.column("month", anchor="center", width=80)
month_result.column("year", anchor="center", width=80)
month_result.column("kwh", anchor="center", width=80)
month_result.column("bill", anchor="center", width=80)
month_result.column("temp", anchor="center", width=80)
month_result.column("hum", anchor="center", width=100)
month_result.pack(pady=10)

# --- Check Now ---
tk.Label(
    root,
    text="Real-Time Energy Stats",
    font=("Verdana", 16, "bold"),
    bg="#1e1e1e",
    fg="white"
).pack(pady=5)
tk.Button(
    root,
    text="Check Now",
    command=check_now,
    bg="#f0f0f0",
    fg="black",
    activebackground="#d0d0d0",
    highlightthickness=0,
    font=("Arial", 13)
).pack(pady=5)

# Treeview for real-time stats
now_result_table = ttk.Treeview(root, columns=("time", "kwh", "temp", "hum"), show="headings", height=1)
now_result_table.heading("time", text="Time")
now_result_table.heading("kwh", text="kWh")
now_result_table.heading("temp", text="Temp (°C)")
now_result_table.heading("hum", text="Humidity (%)")
now_result_table.column("time", anchor="center", width=150)
now_result_table.column("kwh", anchor="center", width=80)
now_result_table.column("temp", anchor="center", width=80)
now_result_table.column("hum", anchor="center", width=100)
now_result_table.pack(pady=10)

# --- Prediction Options ---
tk.Label(
    root,
    text="Bill Prediction Options",
    font=("Verdana", 16, "bold"),
    bg="#1e1e1e",
    fg="white"
).pack(pady=5)
prediction_choice = tk.StringVar()
prediction_choice.set("next")
tk.Radiobutton(
    root,
    text="Next Month",
    variable=prediction_choice,
    value="next",
    bg="#f0f0f0",
    fg="black",
    selectcolor="#d0d0d0",
    highlightthickness=0,
    font=("Arial", 13)
).pack()
tk.Radiobutton(
    root,
    text="Remaining Year",
    variable=prediction_choice,
    value="rest",
    bg="#f0f0f0",
    fg="black",
    selectcolor="#d0d0d0",
    highlightthickness=0,
    font=("Arial", 13)
).pack()
tk.Button(
    root,
    text="Predict Bill",
    command=predict_bill,
    bg="#f0f0f0",
    fg="black",
    activebackground="#d0d0d0",
    highlightthickness=0,
    font=("Arial", 13)
).pack(pady=10)
result_label = tk.Label(
    root,
    text="",
    font=("Arial", 13),
    justify="center",
    bg="#1e1e1e",
    fg="white"
)
result_label.pack(pady=10)

# Treeview for next month prediction
next_result = ttk.Treeview(root, columns=("month", "year", "kwh", "bill", "temp", "hum"), show="headings", height=1)
next_result.heading("month", text="Month")
next_result.heading("year", text="Year")
next_result.heading("kwh", text="kWh")
next_result.heading("bill", text="Bill (₹)")
next_result.heading("temp", text="Temp (°C)")
next_result.heading("hum", text="Humidity (%)")
next_result.column("month", anchor="center", width=80)
next_result.column("year", anchor="center", width=80)
next_result.column("kwh", anchor="center", width=80)
next_result.column("bill", anchor="center", width=80)
next_result.column("temp", anchor="center", width=80)
next_result.column("hum", anchor="center", width=100)
next_result.pack(pady=10)

root.mainloop()