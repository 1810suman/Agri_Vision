import requests
import sqlite3
import pandas as pd
import ollama
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
import io
import os
from datetime import datetime

# 🌦 WeatherAPI Configuration
WEATHER_API_KEY = "YOUR_API_KEY"
DEFAULT_CITY = "CITY"  # Default location

# 🌱 Load CSV Datasets (Farmer Advisor & Market Researcher)
try:
    base_path = os.path.dirname(os.path.abspath(__file__))
except NameError:
    base_path = os.getcwd()

farmer_data_path = os.path.join(base_path, "farmer_advisor_dataset.xlsx")
market_data_path = os.path.join(base_path, "market_researcher_dataset.xlsx")

# Check if files exist, if not use the original paths
if not os.path.exists(farmer_data_path):
    farmer_data_path = r"C:\Users\suman\OneDrive\Desktop\farmer_advisor_dataset.xlsx"
if not os.path.exists(market_data_path):
    market_data_path = r"C:\Users\suman\OneDrive\Desktop\market_researcher_dataset.xlsx"

farmer_data = pd.read_excel(farmer_data_path)
market_data = pd.read_excel(market_data_path)

# 📂 SQLite Database Setup (Thread-Safe)
conn = sqlite3.connect("agriculture_ai.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS farmer_recommendations (
        id INTEGER PRIMARY KEY,
        farmer_name TEXT,
        suggested_crop TEXT,
        soil_ph REAL,
        soil_moisture REAL,
        temperature REAL,
        rainfall REAL,
        sustainability_score REAL,
        weather_condition TEXT,
        market_price REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

# Global variables for UI
weather_data_global = {"temp": 0, "condition": "Unknown", "humidity": 0, "wind": 0}
recommendations_global = []
market_data_global = []
current_farmer_name = ""
current_city = DEFAULT_CITY

# 🔄 Function to ensure thread-safe database transactions
def execute_db_query(query, params=()):
    try:
        cursor.execute(query, params)
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        print("⚠️ Database Error:", e)
        return None

# 🌦 Weather Agent (Fetches real-time weather data)
def weather_agent():
    global weather_data_global, current_city
    while True:
        try:
            city = current_city  # Use the current city from UI
            response = requests.get(f"https://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}")
            weather_data = response.json()
            
            weather_data_global = {
                "temp": weather_data["current"]["temp_c"],
                "condition": weather_data["current"]["condition"]["text"],
                "humidity": weather_data["current"]["humidity"],
                "wind": weather_data["current"]["wind_kph"]
            }
            
            print(f"🌦 Weather Update: {weather_data_global['temp']}°C, {weather_data_global['condition']}")
            
            # Update UI with weather data
            if 'update_weather_ui' in globals():
                root.after(0, update_weather_ui)

        except Exception as e:
            print("⚠️ Weather API Error:", e)
            weather_data_global = {"temp": 0, "condition": "Error fetching weather", "humidity": 0, "wind": 0}
        
        time.sleep(60)  # Fetch weather every 60 seconds

# 👨‍🌾 Farmer Advisor Agent (Suggests best crops using TinyLlama)
def farmer_advisor_agent():
    global recommendations_global, current_farmer_name
    while True:
        try:
            if current_farmer_name:  # Only run if farmer name is provided
                # Get optimal crop recommendation based on dataset
                best_crop_row = farmer_data.sort_values("Sustainability_Score", ascending=False).iloc[0]
                best_crop = best_crop_row["Crop_Type"]
                soil_ph = best_crop_row["Soil_pH"]
                soil_moisture = best_crop_row["Soil_Moisture"]
                temperature = best_crop_row["Temperature_C"]
                rainfall = best_crop_row["Rainfall_mm"]
                sustainability_score = best_crop_row["Sustainability_Score"]

                # AI Model Query using TinyLlama
                user_input = f"Suggest 5 crops for {current_farmer_name} based on: Soil pH: {soil_ph}, Moisture: {soil_moisture}, Temperature: {temperature}°C, Rainfall: {rainfall}mm."
                
                try:
                    response = ollama.chat(model="tinyllama", messages=[{"role": "user", "content": user_input}])
                    ai_suggestion = response["message"]["content"]
                except Exception as ollama_error:
                    print(f"⚠️ Ollama AI Error: {ollama_error}")
                    ai_suggestion = f"Based on your conditions, consider these crops: {best_crop}, Rice, Wheat, Millet, and Sorghum."
                
                print(f"👨‍🌾 Farmer Advisor Suggestion for {current_farmer_name}: {ai_suggestion}")

                # Save AI suggestion to SQLite
                record_id = execute_db_query(
                    "INSERT INTO farmer_recommendations (farmer_name, suggested_crop, soil_ph, soil_moisture, temperature, rainfall, sustainability_score, weather_condition, market_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (current_farmer_name, ai_suggestion, soil_ph, soil_moisture, temperature, rainfall, sustainability_score, weather_data_global["condition"], 0)
                )
                
                # Update recommendations global
                recommendations_global = [(record_id, current_farmer_name, ai_suggestion, sustainability_score)]
                
                # Update UI with recommendations
                if 'update_recommendations_ui' in globals():
                    root.after(0, update_recommendations_ui)

        except Exception as e:
            print("⚠️ Farmer Advisor Error:", e)

        time.sleep(30)  # Runs every 30 seconds

# 📊 Market Researcher Agent (Analyzes profitable crops)
def market_researcher_agent():
    global market_data_global
    while True:
        try:
            # Find top 5 profitable crops based on market trends
            top_crops = market_data.sort_values("Market_Price_per_ton", ascending=False).head(5)
            
            market_data_global = []
            for _, row in top_crops.iterrows():
                product = row["Product"]
                price = row["Market_Price_per_ton"]
                market_data_global.append((product, price))
                
                # Update database with market price if crop exists
                execute_db_query("UPDATE farmer_recommendations SET market_price = ? WHERE suggested_crop LIKE ?", 
                               (price, f"%{product}%"))
            
            print(f"📊 Market Research: Top crop is {market_data_global[0][0]} at ₹{market_data_global[0][1]}/ton")
            
            # Update UI with market data
            if 'update_market_ui' in globals():
                root.after(0, update_market_ui)

        except Exception as e:
            print("⚠️ Market Research Error:", e)

        time.sleep(60)  # Runs every 60 seconds

# 🖼️ Create a function to get crop placeholder image
def get_crop_placeholder(crop_name="Generic"):
    # Create a simple colored placeholder with crop name
    fig, ax = plt.subplots(figsize=(3, 3))
    ax.text(0.5, 0.5, f"{crop_name}", fontsize=20, ha='center', va='center')
    ax.set_facecolor('#e0f0e0')  # Light green background
    ax.axis('off')
    
    # Convert to image
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    img = Image.open(buf)
    plt.close(fig)
    
    return ImageTk.PhotoImage(img)

# 📊 Create Chart for Top Profitable Crops
def create_profitability_chart(frame):
    global market_chart_canvas
    
    # Create matplotlib figure
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor('#f0f0f0')
    
    # Initial empty chart
    crops = [item[0] for item in market_data_global] if market_data_global else ["No Data"]
    prices = [item[1] for item in market_data_global] if market_data_global else [0]
    
    bars = ax.bar(crops, prices, color='#4CAF50')
    ax.set_ylabel('Price (₹/ton)')
    ax.set_title('Top 5 Most Profitable Crops')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    # Create canvas
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.pack(fill=tk.BOTH, expand=True)
    
    return canvas

# 📤 Export recommendations to Excel
def export_to_excel():
    try:
        # Query all recommendations from database
        cursor.execute("""
            SELECT farmer_name, suggested_crop, soil_ph, soil_moisture, temperature, 
                   rainfall, sustainability_score, weather_condition, market_price
            FROM farmer_recommendations
        """)
        
        data = cursor.fetchall()
        
        if not data:
            messagebox.showinfo("Export Info", "No data available to export.")
            return
            
        # Create DataFrame
        columns = ["Farmer Name", "Suggested Crops", "Soil pH", "Soil Moisture", 
                   "Temperature (°C)", "Rainfall (mm)", "Sustainability Score", 
                   "Weather Condition", "Market Price (₹/ton)"]
        
        df = pd.DataFrame(data, columns=columns)
        
        # Ask for save location
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            title="Save Recommendations"
        )
        
        if file_path:
            df.to_excel(file_path, index=False)
            messagebox.showinfo("Export Success", f"Data exported successfully to {file_path}")
    
    except Exception as e:
        messagebox.showerror("Export Error", f"Failed to export data: {str(e)}")

# 🔄 Update Weather UI function
def update_weather_ui():
    try:
        weather_temp_label.config(text=f"{weather_data_global['temp']}°C")
        weather_condition_label.config(text=f"{weather_data_global['condition']}")
        weather_humidity_label.config(text=f"Humidity: {weather_data_global['humidity']}%")
        weather_wind_label.config(text=f"Wind: {weather_data_global['wind']} km/h")
    except Exception as e:
        print(f"Error updating weather UI: {e}")

# 🔄 Update Recommendations UI function
def update_recommendations_ui():
    try:
        # Clear existing recommendations
        for widget in recommendations_frame.winfo_children():
            widget.destroy()
            
        # Create new recommendations display
        if recommendations_global:
            for rec_id, farmer, suggestion, score in recommendations_global:
                recommendation_text = f"Farmer: {farmer}\nSuggestion: {suggestion}\nSustainability Score: {score}"
                rec_label = tk.Label(recommendations_frame, text=recommendation_text, 
                                    font=("Graphik", 10), bg='white', padx=10, pady=10,
                                    wraplength=300, justify="left", relief="ridge", bd=1)
                rec_label.pack(fill=tk.X, padx=10, pady=5)
                
                # Extract first crop from suggestion for image
                first_crop = suggestion.split(",")[0].split(":")[-1].strip()
                if ":" not in first_crop:
                    first_crop = first_crop.split(" ")[-1]
                
                # Create image placeholder
                img = get_crop_placeholder(first_crop)
                img_label = tk.Label(recommendations_frame, image=img, bg='white')
                img_label.image = img  # Keep reference
                img_label.pack(padx=10, pady=5)
    except Exception as e:
        print(f"Error updating recommendations UI: {e}")

# 🔄 Update Market UI function
def update_market_ui():
    try:
        # Update market data table
        for i, (crop, price) in enumerate(market_data_global):
            if i < len(market_tree.get_children()):
                market_tree.item(market_tree.get_children()[i], values=(crop, f"₹{price}/ton"))
            else:
                market_tree.insert("", "end", values=(crop, f"₹{price}/ton"))
                
        # Update chart
        if hasattr(update_market_ui, 'chart_canvas'):
            update_market_ui.chart_canvas.get_tk_widget().destroy()
            
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor('#f0f0f0')
        
        crops = [item[0] for item in market_data_global]
        prices = [item[1] for item in market_data_global]
        
        bars = ax.bar(crops, prices, color='#4CAF50')
        ax.set_ylabel('Price (₹/ton)')
        ax.set_title('Top 5 Most Profitable Crops')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, master=chart_frame)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(fill=tk.BOTH, expand=True)
        update_market_ui.chart_canvas = canvas
        canvas.draw()
    except Exception as e:
        print(f"Error updating market UI: {e}")

# 🚀 Submit farmer info and run advisor
def submit_farmer_info():
    global current_farmer_name, current_city
    
    farmer_name = farmer_name_entry.get().strip()
    city = city_entry.get().strip()
    
    if not farmer_name:
        messagebox.showwarning("Input Required", "Please enter farmer name.")
        return
        
    if not city:
        city = DEFAULT_CITY
    
    current_farmer_name = farmer_name
    current_city = city
    
    # Update UI
    status_label.config(text=f"Processing recommendations for {farmer_name} in {city}...")
    
    # Trigger immediate weather update
    try:
        response = requests.get(f"https://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}")
        weather_data = response.json()
        
        weather_data_global.update({
            "temp": weather_data["current"]["temp_c"],
            "condition": weather_data["current"]["condition"]["text"],
            "humidity": weather_data["current"]["humidity"],
            "wind": weather_data["current"]["wind_kph"]
        })
        
        update_weather_ui()
    except Exception as e:
        print(f"Error updating weather: {e}")
        status_label.config(text=f"Error fetching weather for {city}. Using default data.")
    
    # Call farmer advisor manually
    threading.Thread(target=run_advisor_once).start()

# Run advisor once immediately
def run_advisor_once():
    try:
        # Get optimal crop recommendation based on dataset
        best_crop_row = farmer_data.sort_values("Sustainability_Score", ascending=False).iloc[0]
        best_crop = best_crop_row["Crop_Type"]
        soil_ph = best_crop_row["Soil_pH"]
        soil_moisture = best_crop_row["Soil_Moisture"]
        temperature = best_crop_row["Temperature_C"]
        rainfall = best_crop_row["Rainfall_mm"]
        sustainability_score = best_crop_row["Sustainability_Score"]

        # AI Model Query using TinyLlama
        user_input = f"Suggest 5 crops for {current_farmer_name} based on: Soil pH: {soil_ph}, Moisture: {soil_moisture}, Temperature: {temperature}°C, Rainfall: {rainfall}mm."
        
        try:
            response = ollama.chat(model="tinyllama", messages=[{"role": "user", "content": user_input}])
            ai_suggestion = response["message"]["content"]
        except Exception as ollama_error:
            print(f"⚠️ Ollama AI Error: {ollama_error}")
            ai_suggestion = f"Based on your conditions, consider these crops: {best_crop}, Rice, Wheat, Millet, and Sorghum."
        
        print(f"👨‍🌾 Farmer Advisor Suggestion for {current_farmer_name}: {ai_suggestion}")

        # Save AI suggestion to SQLite
        record_id = execute_db_query(
            "INSERT INTO farmer_recommendations (farmer_name, suggested_crop, soil_ph, soil_moisture, temperature, rainfall, sustainability_score, weather_condition, market_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (current_farmer_name, ai_suggestion, soil_ph, soil_moisture, temperature, rainfall, sustainability_score, weather_data_global["condition"], 0)
        )
        
        # Update recommendations global
        global recommendations_global
        recommendations_global = [(record_id, current_farmer_name, ai_suggestion, sustainability_score)]
        
        # Update UI with recommendations
        root.after(0, update_recommendations_ui)
        root.after(0, lambda: status_label.config(text=f"Recommendations generated for {current_farmer_name}!"))
    except Exception as e:
        print(f"Error in run_advisor_once: {e}")
        root.after(0, lambda: status_label.config(text=f"Error generating recommendations. Please try again."))

# 🎨 Create the user interface
def create_ui():
    global root, farmer_name_entry, city_entry, weather_temp_label, weather_condition_label
    global weather_humidity_label, weather_wind_label, recommendations_frame, status_label
    global market_tree, chart_frame, market_chart_canvas
    
    # Create main window
    root = tk.Tk()
    root.title("Agriculture AI Advisor")
    root.geometry("1200x800")
    root.configure(bg="#f0f0f0")
    
    # Try to set Graphik font if available, otherwise use system default
    try:
        root.option_add("*Font", "Graphik 10")
    except:
        pass
    
    # Create header frame
    header_frame = tk.Frame(root, bg="#2E7D32", padx=20, pady=15)
    header_frame.pack(fill=tk.X)
    
    header_label = tk.Label(header_frame, text="Agriculture AI Advisor", font=("Graphik", 20, "bold"), bg="#2E7D32", fg="white")
    header_label.pack(side=tk.LEFT)
    
    # Create main content frame
    content_frame = tk.Frame(root, bg="#f0f0f0", padx=20, pady=20)
    content_frame.pack(fill=tk.BOTH, expand=True)
    
    # Create left column - Input and Weather
    left_frame = tk.Frame(content_frame, bg="#f0f0f0", width=300)
    left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
    left_frame.pack_propagate(False)
    
    # Input section
    input_frame = tk.LabelFrame(left_frame, text="📥 Farmer Information", bg="white", padx=10, pady=10, font=("Graphik", 12, "bold"))
    input_frame.pack(fill=tk.X, pady=(0, 10))
    
    tk.Label(input_frame, text="Farmer Name:", bg="white").pack(anchor=tk.W, pady=(5, 0))
    farmer_name_entry = tk.Entry(input_frame, font=("Graphik", 10))
    farmer_name_entry.pack(fill=tk.X, pady=5)
    
    tk.Label(input_frame, text="City:", bg="white").pack(anchor=tk.W, pady=(5, 0))
    city_entry = tk.Entry(input_frame, font=("Graphik", 10))
    city_entry.insert(0, DEFAULT_CITY)
    city_entry.pack(fill=tk.X, pady=5)
    
    submit_button = tk.Button(input_frame, text="Get Recommendations", command=submit_farmer_info, 
                              bg="#4CAF50", fg="white", padx=10, pady=5, font=("Graphik", 10, "bold"))
    submit_button.pack(fill=tk.X, pady=10)
    
    status_label = tk.Label(input_frame, text="Enter farmer information to start", bg="white", wraplength=250)
    status_label.pack(fill=tk.X, pady=5)
    
    # Weather section
    weather_frame = tk.LabelFrame(left_frame, text="🌦️ Weather Information", bg="white", padx=10, pady=10, font=("Graphik", 12, "bold"))
    weather_frame.pack(fill=tk.X, pady=(0, 10))
    
    weather_temp_label = tk.Label(weather_frame, text="--°C", font=("Graphik", 24), bg="white")
    weather_temp_label.pack(anchor=tk.W)
    
    weather_condition_label = tk.Label(weather_frame, text="--", font=("Graphik", 14), bg="white")
    weather_condition_label.pack(anchor=tk.W)
    
    weather_humidity_label = tk.Label(weather_frame, text="Humidity: --%", bg="white")
    weather_humidity_label.pack(anchor=tk.W, pady=(10, 0))
    
    weather_wind_label = tk.Label(weather_frame, text="Wind: -- km/h", bg="white")
    weather_wind_label.pack(anchor=tk.W)
    
    # Create middle column - Recommendations
    middle_frame = tk.Frame(content_frame, bg="#f0f0f0", width=350)
    middle_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
    
    # Recommendations section
    recommendations_label_frame = tk.LabelFrame(middle_frame, text="🤖 AI Crop Recommendations", bg="white", padx=10, pady=10, font=("Graphik", 12, "bold"))
    recommendations_label_frame.pack(fill=tk.BOTH, expand=True)
    
    # Scrollable frame for recommendations
    recommendations_canvas = tk.Canvas(recommendations_label_frame, bg="white")
    scrollbar = ttk.Scrollbar(recommendations_label_frame, orient="vertical", command=recommendations_canvas.yview)
    scrollable_frame = tk.Frame(recommendations_canvas, bg="white")
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: recommendations_canvas.configure(scrollregion=recommendations_canvas.bbox("all"))
    )
    
    recommendations_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    recommendations_canvas.configure(yscrollcommand=scrollbar.set)
    
    recommendations_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    recommendations_frame = scrollable_frame
    
    # Export button
    export_button = tk.Button(middle_frame, text="📄 Export to Excel", command=export_to_excel, 
                             bg="#2196F3", fg="white", padx=10, pady=5, font=("Graphik", 10, "bold"))
    export_button.pack(fill=tk.X, pady=10)
    
    # Create right column - Market Data
    right_frame = tk.Frame(content_frame, bg="#f0f0f0", width=400)
    right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
    
    # Market data section
    market_frame = tk.LabelFrame(right_frame, text="📊 Market Research", bg="white", padx=10, pady=10, font=("Graphik", 12, "bold"))
    market_frame.pack(fill=tk.BOTH, expand=True)
    
    # Create treeview for market data
    columns = ("Crop", "Price")
    market_tree = ttk.Treeview(market_frame, columns=columns, show="headings", height=5)
    market_tree.pack(fill=tk.X, pady=(0, 10))
    
    # Configure treeview columns
    for col in columns:
        market_tree.heading(col, text=col)
        market_tree.column(col, width=100)
    
    # Add initial data
    for i in range(5):
        market_tree.insert("", "end", values=("--", "--"))
    
    # Chart frame for profitability visualization
    chart_frame = tk.Frame(market_frame, bg="white", padx=10, pady=10)
    chart_frame.pack(fill=tk.BOTH, expand=True)
    
    # Create initial chart
    update_market_ui.chart_canvas = create_profitability_chart(chart_frame)
    
    # Create footer
    footer_frame = tk.Frame(root, bg="#f0f0f0", padx=20, pady=10)
    footer_frame.pack(fill=tk.X)
    
    footer_label = tk.Label(footer_frame, text="© 2025 Agriculture AI Advisor", fg="#555555", bg="#f0f0f0")
    footer_label.pack(side=tk.RIGHT)
    
    # Configure style
    style = ttk.Style()
    style.configure("Treeview", font=("Graphik", 10))
    style.configure("Treeview.Heading", font=("Graphik", 10, "bold"))
    
    return root

# 🚀 Start the application
if __name__ == "__main__":
    # Create UI
    root = create_ui()
    
    # Start agents in separate threads
    weather_thread = threading.Thread(target=weather_agent, daemon=True)
    farmer_thread = threading.Thread(target=farmer_advisor_agent, daemon=True)
    market_thread = threading.Thread(target=market_researcher_agent, daemon=True)
    
    # Start all threads
    weather_thread.start()
    farmer_thread.start()
    market_thread.start()
    
    # Start UI main loop
    root.mainloop()
    
    # Close database connection when app closes
    conn.close()
