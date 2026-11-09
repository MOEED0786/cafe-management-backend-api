const API_URL = "http://127.0.0.1:8000";
let globalMenuData = {};
let globalTemplateData = {};
let localCart = {}; 
let listAEditingWorkspace = {}; 

function switchPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
    if(pageId === 'adminPage') {
        loadAdminDashboard();
    } else {
        loadMenu();
    }
}

async function loadMenu() {
    try {
        const res = await fetch(`${API_URL}/menu`);
        globalMenuData = await res.json();
        const container = document.getElementById("menuContainer");
        container.innerHTML = "";

        Object.entries(globalMenuData).forEach(([id, item]) => {
            if (!(id in localCart)) localCart[id] = 0;
            
            const isOutOfStock = item.stock <= 0;
            const itemStatusText = isOutOfStock ? `<span style="color:red; font-weight:bold;">OUT OF STOCK</span>` : `Stock: ${item.stock}`;

            container.innerHTML += `
                <div class="food-item" style="${isOutOfStock ? 'opacity: 0.5;' : ''}">
                    <div>
                        <strong>${item.name}</strong>
                        <div style="font-size:0.85em; color:#6b7280;">Rs. ${item.price} | ${itemStatusText}</div>
                    </div>
                    <div class="counter">
                        <button class="btn-circle" onclick="changeQty('${id}', -1)">-</button>
                        <span class="qty-val" id="qty-${id}">${localCart[id]}</span>
                        <button class="btn-circle" onclick="changeQty('${id}', 1)" ${isOutOfStock ? 'disabled' : ''}>+</button>
                    </div>
                </div>
            `;
        });
    } catch (err) {
        console.error(err);
        document.getElementById("menuContainer").innerHTML = `<p style="color: red;">⚠️ Connection error with server backend.</p>`;
    }
}

async function changeQty(itemId, amount) {
    const key = String(itemId);
    let current = localCart[key] || 0;
    let target = current + amount;
    if (target < 0) return;

    const itemStock = globalMenuData[key].stock;
    if (amount > 0 && target > itemStock) {
        alert(`Cannot exceed maximum items in stock! Only ${itemStock} available.`);
        return;
    }

    localCart[key] = target;
    document.getElementById(`qty-${key}`).innerText = target;

    await fetch(`${API_URL}/cart/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_id: parseInt(key), quantity: target })
    });

    refreshReceiptSummary();
}

async function refreshReceiptSummary() {
    try {
        const res = await fetch(`${API_URL}/checkout/summary`);
        const summary = await res.json();
        const container = document.getElementById("receiptContainer");

        if (!summary.items || summary.items.length === 0) {
            container.innerHTML = `<p style="color: #6b7280;">Your current tray is completely empty.</p>`;
            return;
        }

        let html = summary.items.map(i => `
            <div class="receipt-item">
                <span>${i.quantity}x ${i.name}</span>
                <span style="font-weight:600;">Rs. ${i.line_total}</span>
            </div>
        `).join('');

        container.innerHTML = `
            <div>${html}</div>
            <hr style="border:0; border-top:1px solid #e5e7eb; margin:15px 0;">
            <div class="receipt-item" style="font-size:1.2em; font-weight:bold;">
                <span>Grand Total:</span>
                <span style="color:#10b981;">Rs. ${summary.total_bill}</span>
            </div>
        `;
    } catch (err) {
        console.error(err);
    }
}

async function placeOrder() {
    const res = await fetch(`${API_URL}/orders/place`, { method: "POST" });
    if (res.ok) {
        alert("Order successfully sent down pipeline!");
        localCart = {}; 
        await loadMenu(); 
        document.getElementById("receiptContainer").innerHTML = `<p style="color: #6b7280;">Your current tray is completely empty.</p>`;
    } else {
        const err = await res.json();
        alert(err.detail);
    }
}

async function loadAdminDashboard() {
    try {
        const menuRes = await fetch(`${API_URL}/menu`);
        globalMenuData = await menuRes.json();

        const templateRes = await fetch(`${API_URL}/admin/templates`);
        globalTemplateData = await templateRes.json();

        renderListB();
        
        if (Object.keys(listAEditingWorkspace).length === 0) {
            Object.entries(globalMenuData).forEach(([id, item]) => {
                listAEditingWorkspace[id] = item.stock;
            });
        }
        renderListA();

        const lookbackPeriod = document.getElementById("reportPeriodSelect").value;
        loadSalesReport(lookbackPeriod);
    } catch(err) {
        console.error(err);
    }
}

function renderListA() {
    const container = document.getElementById("listAWorkspace");
    container.innerHTML = "";

    Object.entries(globalMenuData).forEach(([id, item]) => {
        const currentDraftVal = listAEditingWorkspace[id] ?? item.stock;
        container.innerHTML += `
            <div class="admin-item">
                <div>
                    <strong>${item.name}</strong>
                    <div style="font-size:0.82em; color:#6b7280;">Current Shop Floor Stock: <b style="color:#1e293b;">${item.stock}</b></div>
                </div>
                <div class="counter">
                    <button class="btn-circle" onclick="updateWorkspaceItem('${id}', -1)">-</button>
                    <input type="number" id="workspace-input-${id}" value="${currentDraftVal}" onchange="syncWorkspaceManualInput('${id}', this.value)">
                    <button class="btn-circle" onclick="updateWorkspaceItem('${id}', 1)">+</button>
                </div>
            </div>
        `;
    });
}

function renderListB() {
    const container = document.getElementById("listBConfig");
    container.innerHTML = "";

    Object.entries(globalMenuData).forEach(([id, item]) => {
        const targetBaseline = globalTemplateData[id] ?? 0;
        container.innerHTML += `
            <div class="admin-item">
                <span>${item.name}</span>
                <div>
                    <span style="font-size:0.8em; color:#4b5563; margin-right:8px;">Target Par:</span>
                    <input type="number" value="${targetBaseline}" onchange="saveTemplateChange('${id}', this.value)">
                </div>
            </div>
        `;
    });
}

function updateWorkspaceItem(id, amount) {
    let val = parseInt(listAEditingWorkspace[id] || 0) + amount;
    if (val < 0) val = 0;
    listAEditingWorkspace[id] = val;
    document.getElementById(`workspace-input-${id}`).value = val;
}

function syncWorkspaceManualInput(id, val) {
    let cleanVal = parseInt(val) || 0;
    if (cleanVal < 0) cleanVal = 0;
    listAEditingWorkspace[id] = cleanVal;
}

function generateAutoRestockPreview() {
    Object.keys(globalMenuData).forEach(id => {
        const targetPar = globalTemplateData[id] || 0;
        listAEditingWorkspace[id] = targetPar;
    });
    renderListA();
    alert("List A has been auto-filled using your saved targets!");
}

async function saveTemplateChange(id, value) {
    let cleanVal = parseInt(value) || 0;
    if(cleanVal < 0) cleanVal = 0;
    
    await fetch(`${API_URL}/admin/templates/save`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ item_id: parseInt(id), target_amount: cleanVal })
    });
    globalTemplateData[id] = cleanVal;
}

async function commitWorkspaceToLiveInventory() {
    const res = await fetch(`${API_URL}/admin/restock/apply-batch`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(listAEditingWorkspace)
    });

    if(res.ok) {
        alert("Inventory updated and synced live across screens!");
        listAEditingWorkspace = {}; 
        loadAdminDashboard();
    }
}

async function loadSalesReport(period) {
    try {
        // Explicitly clean string formatting before requesting data from the server
        const cleanPeriod = String(period).toLowerCase().trim();
        
        const res = await fetch(`${API_URL}/admin/reports/sales-summary?period=${cleanPeriod}`, {
            method: "GET",
            headers: {
                "Accept": "application/json"
            }
        });
        
        if (!res.ok) {
            console.error(`Dashboard server error status code: ${res.status}`);
            return;
        }
        
        const data = await res.json();

        document.getElementById("repTotalRevenue").innerText = `Rs. ${data.total_revenue}`;
        document.getElementById("repTotalOrders").innerText = data.total_orders;
        
        document.getElementById("repBestSeller").innerText = data.best_seller.quantity > 0 
            ? `${data.best_seller.name} (${data.best_seller.quantity} sold)` 
            : "No items sold yet";
            
        document.getElementById("repDeadStockCount").innerText = `${data.dead_stock_items.length} Items`;
        
        if(data.dead_stock_items.length > 0) {
            document.getElementById("repDeadStockList").innerHTML = `<strong>Items needing attention (0 sales):</strong> ${data.dead_stock_items.join(", ")}`;
        } else {
            document.getElementById("repDeadStockList").innerHTML = `🎉 <b>Excellent traction!</b> Every item in the catalog has logged sales this period.`;
        }
    } catch(err) {
        console.error("Failed parsing analytics payloads:", err);
    }
}


function connectWebSocket() {
    const ws = new WebSocket("ws://127.0.0.1:8000/ws/kitchen");
    
    ws.onopen = () => {
        const tag = document.getElementById("wsStatus");
        tag.innerText = "● Live Stream Connected";
        tag.style.color = "#10b981";
    };

     ws.onmessage = (event) => {
        const order = JSON.parse(event.data);
        const container = document.getElementById("kitchenTickets");
        if (container.innerText.includes("No pending")) container.innerHTML = "";

        let itemsList = order.items.map(i => `<li>${i.quantity}x ${i.name}</li>`).join('');
                container.innerHTML = `
            <div class="ticket">
                <span class="status-badge">${order.status}</span>
                <strong>ORDER REF: #${order.order_id}</strong>
                <ul style="margin:10px 0; padding-left:20px;">${itemsList}</ul>
                <div style="font-weight:600; text-align:right;">Bill Total: Rs. ${order.total_bill}</div>
            </div>
        ` + container.innerHTML;

        const currentPeriod = document.getElementById("reportPeriodSelect").value;
loadSalesReport(currentPeriod);

    };
    

    ws.onclose = () => {
        const tag = document.getElementById("wsStatus");
        tag.innerText = "● Off air (Reconnecting...)";
        tag.style.color = "#ef4444";
        setTimeout(connectWebSocket, 3000);
    };
}

window.onload = () => {
    loadMenu();
    connectWebSocket();
};
