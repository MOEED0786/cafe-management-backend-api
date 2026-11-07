from fastapi import FastAPI
import psycopg2

app = FastAPI()

# 1. Database fetcher utility function
def get_live_menu():
    try:
        connection = psycopg2.connect(
            host="localhost",
            database="freelance_practice_db",
            user="postgres",
            password="@#1234#@"
        )
        cursor = connection.cursor()
        cursor.execute("SELECT id, item_name, price, category, in_stock FROM menu;")
        db_rows = cursor.fetchall()
        
        menu_list = []
        for row in db_rows:
            menu_list.append({
                "id": row[0],
                "item_name": row[1],
                "price": float(row[2]),
                "category": row[3],
                "in_stock": row[4]
            })
        return menu_list
        
    except Exception as e:
        print(f"Database read error: {e}")
        return []
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()


# 2. Reusable billing math function
def calculate_order_total(menu_list, order_ids, coupon_code=None):
    total = 0
    for item_id in order_ids:
        for item in menu_list:
            if item["id"] == item_id and item["in_stock"]:
                total += item["price"]
                break
    
    if coupon_code == "CAFE10":
        total *= 0.9  # 10% discount math
    return total


# --- API WEB ENDPOINTS ---

# Route 1: Home Welcome
@app.get("/")
def read_root():
    return {"message": "Welcome to the Cafe Management System API!"}


# Route 2: Live Menu 
@app.get("/menu")
def get_cafe_menu():
    live_menu = get_live_menu()
    return {"live_menu": live_menu}


# Route 3: Live Budget Filtering 
@app.get("/menu/affordable")
def get_affordable_items(max_budget: float):
    live_menu = get_live_menu()
    filtered_items = []
    
    for item in live_menu:
        if item["price"] <= max_budget and item["in_stock"]:
            filtered_items.append(item)
            
    return {"max_budget_limit": max_budget, "results": filtered_items}


# Route 4: Live Customer Billing 
@app.get("/checkout")
def process_cafe_checkout(coupon: str = None):
    # Customer wants an Espresso (1), Iced Latte (4), and Club Sandwich (5)
    customer_order_ids = [1, 4, 5]
    
    # Grab the fresh menu list directly from pgAdmin
    live_menu = get_live_menu()
    
    # Run our billing logic using the live data and incoming coupon!
    total_bill = calculate_order_total(live_menu, customer_order_ids, coupon_code=coupon)
    
    return {
        "ordered_items": customer_order_ids,
        "coupon_applied": coupon,
        "final_total": round(total_bill, 2)
    }
