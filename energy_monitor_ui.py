import tkinter as tk
from tkinter import ttk, messagebox
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
model = joblib.load("<CHANGE_THIS_PATH>/bill_predictor_model.pkl")

# ESP32 URL (Change this to your ESP32 IP)
ESP32_URL = "http://<CHANGE_THIS_IP>/"  # Example: http://192.168.0.101/
DATASET_PATH = "<CHANGE_THIS_PATH>/dataset.csv"

# ---------- Helper Functions ----------

def fetch_realtime_data():
    global daily_energy_total, daily_temp_readings, daily_hum_readings, last_logged_date
    try:
        response = requests.get(ESP32_URL, timeout=5)
        if response.status_code == 200:
            raw = response.text.strip()

            if ',' in raw and raw.count(',') == 3:
                date, kwh, temp, hum = raw.split(',')
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

# ---------- UI Setup ----------
root = tk.Tk()
root.title(" Smart Energy Monitor & Bill Predictor")
root.geometry("400x600")
root.configure(bg="#1e1e1e")

style = ttk.Style()
style.configure("Treeview", font=("Arial", 12), rowheight=28)
style.configure("Treeview.Heading", font=("Arial", 13, "bold"))

def sync_logs_async():
    root.after(100, fetch_logged_months)

sync_button = tk.Button(
    root,
    text="Sync ESP32 Logs",
    command=sync_logs_async,
    bg="#f0f0f0",
    fg="black",
    activebackground="#d0d0d0",
    highlightthickness=0,
    font=("Arial", 13)
)
sync_button.pack(pady=10)

# Month + Year Picker UI
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

df = pd.read_csv(DATASET_PATH)
available_years = sorted(df["Year"].unique().astype(str).tolist())
year_var = tk.StringVar(value=available_years[-1] if available_years else "2024")

month_menu = ttk.Combobox(month_frame, textvariable=month_var, values=month_options, state="readonly", width=15)
year_menu = ttk.Combobox(month_frame, textvariable=year_var, values=available_years, state="readonly", width=10)
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

root.mainloop()
