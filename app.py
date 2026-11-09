from builtins import Exception, dict, int, isinstance, len, list, sum
from codecs import open
from locale import str

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta

app = FastAPI(title="Real-Time Restaurant Order System")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()
    
@app.get("/index.js")
async def serve_javascript():
    with open("index.js", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="application/javascript")

# =====================================================================
# DATA VALIDATION SCHEMAS
# =====================================================================
class CartItemUpdate(BaseModel):
    item_id: int
    quantity: int

class TemplateUpdateSchema(BaseModel):
    item_id: int
    target_amount: int

# =====================================================================
# IN-MEMORY DATABASE & CONFIGS
# =====================================================================
MENU = {
    1: {"name": "Glazed Donut", "price": 250, "stock": 20},
    2: {"name": "Chocolate Donut", "price": 300, "stock": 15},
    3: {"name": "Cold Brew Coffee", "price": 400, "stock": 30},
    4: {"name": "Red Velvet Cupcake", "price": 280, "stock": 12},
    5: {"name": "Nutella Croissant", "price": 350, "stock": 10},
    6: {"name": "Caramel Macchiato", "price": 450, "stock": 25},
    7: {"name": "Blueberry Muffin", "price": 260, "stock": 18},
    8: {"name": "Matcha Latte", "price": 480, "stock": 15}
}

customer_cart = {}
orders_db = []
order_id_counter = 1

DEFAULT_RESTOCK_TEMPLATES = {
    1: 20, 2: 15, 3: 30, 4: 12, 5: 10, 6: 25, 7: 18, 8: 15
}

# =====================================================================
# WEBSOCKET CONNECTION MANAGER
# =====================================================================
class KitchenConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_order(self, order_data: dict):
        for connection in list(self.active_connections):
            try:
                serializable_order = order_data.copy()
                if isinstance(serializable_order.get("timestamp"), datetime):
                    serializable_order["timestamp"] = serializable_order["timestamp"].isoformat()
                await connection.send_json(serializable_order)
            except Exception:
                self.disconnect(connection)

notifier = KitchenConnectionManager()
# =====================================================================
# SYSTEM CHANNELS & ORDER PIPELINES
# =====================================================================
@app.websocket("/ws/kitchen")
async def kitchen_websocket_endpoint(websocket: WebSocket):
    await notifier.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        notifier.disconnect(websocket)

@app.get("/menu")
async def get_menu():
    return MENU

@app.post("/cart/update")
async def update_cart(cart_intent: CartItemUpdate):
    item_id = cart_intent.item_id
    quantity = cart_intent.quantity

    if item_id not in MENU:
        raise HTTPException(status_code=404, detail="Item not found")

    target_item = MENU[item_id]

    if quantity <= 0:
        if item_id in customer_cart:
            del customer_cart[item_id]
        return {"message": "Removed item", "cart": customer_cart}

    if target_item["stock"] <= 0:
        raise HTTPException(status_code=400, detail=f"Sorry, {target_item['name']} is completely out of stock!")

    if quantity > target_item["stock"]:
        raise HTTPException(status_code=400, detail=f"Only {target_item['stock']} units left in stock!")

    customer_cart[item_id] = quantity
    return {"message": "Updated quantity", "cart": customer_cart}

@app.get("/checkout/summary")
async def get_bill_summary():
    if not customer_cart:
        return {"total_bill": 0, "items": [], "status": "Draft (Empty)"}

    items_summary = []
    total_bill = 0
    for item_id, qty in customer_cart.items():
        item_details = MENU[item_id]
        line_total = item_details["price"] * qty
        total_bill += line_total
        items_summary.append({
            "item_id": item_id,
            "name": item_details["name"],
            "unit_price": item_details["price"],
            "quantity": qty,
            "line_total": line_total
        })

    return {"total_bill": total_bill, "items": items_summary, "status": "Draft"}

@app.post("/orders/place", status_code=status.HTTP_201_CREATED)
async def place_order():
    global order_id_counter
    if not customer_cart:
        raise HTTPException(status_code=400, detail="Cart is empty")

    for item_id, qty in customer_cart.items():
        if MENU[item_id]["stock"] < qty:
            raise HTTPException(status_code=400, detail="Stock changed error")

    order_items = []
    final_bill = 0
    for item_id, qty in customer_cart.items():
        MENU[item_id]["stock"] -= qty
        line_total = MENU[item_id]["price"] * qty
        final_bill += line_total
        order_items.append({
            "item_id": item_id, 
            "name": MENU[item_id]["name"], 
            "quantity": qty, 
            "line_total": line_total
        })

    new_order = {
        "order_id": order_id_counter,
        "items": order_items,
        "total_bill": final_bill,
        "status": "PENDING_KITCHEN",
        "timestamp": datetime.now()
    }
    orders_db.append(new_order)
    order_id_counter += 1
    customer_cart.clear()

    await notifier.broadcast_order(new_order)
    return {"message": "Success", "order": new_order}

# =====================================================================
# BACK-PANEL INVENTORY CONTROL ENDPOINTS
# =====================================================================
@app.get("/admin/templates")
async def get_templates():
    return DEFAULT_RESTOCK_TEMPLATES

@app.post("/admin/templates/save")
async def save_template_settings(payload: TemplateUpdateSchema):
    if payload.item_id not in MENU:
        raise HTTPException(status_code=404, detail="Item not found in menu")
    if payload.target_amount < 0:
        raise HTTPException(status_code=400, detail="Target baseline cannot be negative")
        
    DEFAULT_RESTOCK_TEMPLATES[payload.item_id] = payload.target_amount
    return {"message": "Saved standard defaults successfully"}

@app.post("/admin/restock/apply-batch")
async def apply_batch_restock(modifications: dict):
    for item_key, fresh_stock in modifications.items():
        item_id = int(item_key)
        if item_id in MENU:
            MENU[item_id]["stock"] = fresh_stock
    return {"message": "Active catalog stock synced successfully!"}

# =====================================================================
# BUSINESS PERIOD CALENDAR REPORT ENGINE
# =====================================================================
@app.get("/admin/reports/sales-summary")
async def get_sales_report(period = None):
    now = datetime.now()
    
    search_period = f"{period}".lower().strip()
    if not period:
        search_period = "today"
    else:
        search_period = f"{period}".lower().strip()
    if search_period == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif search_period == "week":
        start_time = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif search_period == "month":
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif search_period == "year":
        start_time = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

    filtered_orders = [o for o in orders_db if o["timestamp"] >= start_time]
    
    total_revenue = sum(o["total_bill"] for o in filtered_orders)
    total_orders_processed = len(filtered_orders)

    sales_volumes = {item_id: 0 for item_id in MENU.keys()}
    for order in filtered_orders:
        for item in order["items"]:
            item_id = int(item["item_id"])
            if item_id in sales_volumes:
                sales_volumes[item_id] += item["quantity"]

    item_performance_list = []
    best_selling_item = {"name": "None", "quantity": 0}
    items_not_sold = []

    max_qty = 0
    for item_id, qty_sold in sales_volumes.items():
        item_name = MENU[item_id]["name"]
        item_performance_list.append({"name": item_name, "units_sold": qty_sold})
        
        if qty_sold > max_qty:
            max_qty = qty_sold
            best_selling_item = {"name": item_name, "quantity": qty_sold}
            
        if qty_sold == 0:
            items_not_sold.append(item_name)

    return {
        "report_period": search_period,
        "total_revenue": total_revenue,
        "total_orders": total_orders_processed,
        "best_seller": best_selling_item,
        "dead_stock_items": items_not_sold,
        "all_item_breakdown": item_performance_list
    }

@app.post("/admin/test/seed-historical-data")
async def seed_historical_data():
    """
    Injects mock orders into the database at different calendar timestamps
    to thoroughly test that Today, Week, Month, and Year filter modules work perfectly.
    """
    global order_id_counter
    
    now = datetime.now()
    
    # 1. An order from 3 days ago (Should show up in Week, Month, Year - NOT Today)
    orders_db.append({
        "order_id": order_id_counter,
        "items": [{"item_id": 1, "name": "Glazed Donut", "quantity": 4, "line_total": 1000}],
        "total_bill": 1000,
        "status": "COMPLETED",
        "timestamp": now - timedelta(days=3)
    })
    order_id_counter += 1

    # 2. An order from 14 days ago (Should show up in Month, Year - NOT Today or Week)
    orders_db.append({
        "order_id": order_id_counter,
        "items": [{"item_id": 3, "name": "Cold Brew Coffee", "quantity": 2, "line_total": 800}],
        "total_bill": 800,
        "status": "COMPLETED",
        "timestamp": now - timedelta(days=14)
    })
    order_id_counter += 1

    # 3. An order from 45 days ago (Should show up ONLY in Year)
    orders_db.append({
        "order_id": order_id_counter,
        "items": [{"item_id": 2, "name": "Chocolate Donut", "quantity": 5, "line_total": 1500}],
        "total_bill": 1500,
        "status": "COMPLETED",
        "timestamp": now - timedelta(days=45)
    })
    order_id_counter += 1

    return {"message": "Historical test orders injected successfully!", "total_orders_in_db": len(orders_db)}
