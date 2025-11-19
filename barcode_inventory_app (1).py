import streamlit as st
import uuid
import qrcode
import os
import json
from datetime import datetime

# ----------------------
# Config & Data Storage
# ----------------------
DATA_FILE = "inventory_data.json"
QRCODE_DIR = "qrcodes"
os.makedirs(QRCODE_DIR, exist_ok=True)

# Load inventory from JSON
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        inventory = json.load(f)
else:
    inventory = {}


def save_inventory():
    """Save the inventory dictionary back to JSON."""
    with open(DATA_FILE, "w") as f:
        json.dump(inventory, f, indent=4)


# ----------------------
# Helper Functions
# ----------------------
def record_transaction(item_code: str, action: str, qty: int, job: str | None = None):
    """Add a transaction entry to an item, with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "action": action,  # "in" or "out"
        "qty": int(qty),
        "timestamp": ts,
    }
    if job:
        entry["job"] = job

    inventory[item_code].setdefault("history", []).append(entry)
    save_inventory()


def show_item_detail(item_code: str, section_title: str = "Item Detail"):
    """Show item info, stock, history, and check in/out controls."""
    if item_code not in inventory:
        st.error("Item not found.")
        return

    item = inventory[item_code]

    st.markdown("---")
    st.subheader(section_title)
    st.write(f"**Item Name:** {item.get('name', '')}")
    st.write(f"**Item Code:** `{item_code}`")

    current_qty = int(item.get("quantity", 0))
    st.metric("Current Stock", current_qty)

    # --- Check In / Check Out Form ---
    st.write("### Stock Transaction")

    col1, col2 = st.columns(2)
    with col1:
        action = st.radio(
            "Action",
            ["Check In", "Check Out"],
            key=f"action_{item_code}"
        )
    with col2:
        qty = st.number_input(
            "Quantity",
            min_value=1,
            step=1,
            key=f"qty_{item_code}",
        )

    job = None
    if action == "Check Out":
        job = st.text_input(
            "Job / Project (optional, but recommended)",
            key=f"job_{item_code}"
        )

    if st.button("Save Transaction", key=f"save_{item_code}"):
        if action == "Check Out" and qty > current_qty:
            st.error("Cannot check out more items than are in stock.")
        else:
            if action == "Check In":
                inventory[item_code]["quantity"] = current_qty + int(qty)
                record_transaction(item_code, "in", qty)
                st.success(f"Checked IN {qty} item(s).")
            else:
                inventory[item_code]["quantity"] = current_qty - int(qty)
                record_transaction(item_code, "out", qty, job)
                st.success(f"Checked OUT {qty} item(s).")

            st.experimental_rerun()

    # --- Transaction History ---
    st.write("### Transaction History")

    history = inventory[item_code].get("history", [])
    if not history:
        st.info("No transactions recorded yet.")
    else:
        # Show most recent first
        rows = []
        for entry in reversed(history):
            rows.append({
                "Time": entry.get("timestamp", ""),
                "Action": "IN" if entry.get("action") == "in" else "OUT",
                "Qty": entry.get("qty", 0),
                "Job": entry.get("job", ""),
            })
        st.table(rows)


# ----------------------
# Main App
# ----------------------
st.set_page_config(page_title="QR Stock", page_icon="📦", layout="centered")

st.title("📦 QR Stock – Inventory System")
st.caption("Scan QR codes to check items in/out and track stock levels.")

# ---------------------------------------------------
# 1. Detect if we were opened via QR code (?code=...)
# ---------------------------------------------------
scanned_code = None
qp = st.query_params  # Streamlit 1.30+ API

if "code" in qp and qp["code"]:
    scanned_code = qp["code"]

# ---------------------------------------------------
# 2. Inventory Search / Home Section
# ---------------------------------------------------
st.markdown("## 🔍 Search Inventory")

if not inventory:
    st.info("No items in inventory yet. Use the **Admin – Create New Item** section below to add items.")
else:
    search = st.text_input("Search by item name or code")
    # Build list of (label, code)
    items = []
    for code, item in sorted(inventory.items(), key=lambda x: x[1].get("name", "").lower()):
        label = f"{item.get('name','')} ({code})"
        items.append((label, code))

    # Filter items based on search text
    if search:
        search_lower = search.lower()
        filtered = [
            (label, code)
            for (label, code) in items
            if search_lower in label.lower()
        ]
    else:
        filtered = items

    if not filtered:
        st.warning("No items match your search.")
    else:
        labels = [label for (label, _) in filtered]
        default_index = 0
        selected_label = st.selectbox(
            "Select an item to view stock and history",
            labels,
            index=default_index,
        )
        # Get the code back from label
        selected_code = dict(filtered)[selected_label]

        show_item_detail(selected_code, section_title="Selected Item")

# ---------------------------------------------------
# 3. If opened via QR scan, show scanned item section
# ---------------------------------------------------
if scanned_code:
    show_item_detail(scanned_code, section_title="Scanned Item")


# ---------------------------------------------------
# 4. Admin Section – Create Items & Generate QR Codes
# ---------------------------------------------------
st.markdown("---")
st.markdown("## 🛠️ Admin – Create New Item & QR Code")

st.info(
    "Use this section on your computer to create items and generate QR code labels. "
    "Workers can then scan the QR codes with their phones."
)

# Public URL needed so QR codes link back correctly
base_url = st.text_input(
    "Public App URL (for QR code links)",
    help="Example: https://your-app-name.streamlit.app/",
)

item_name = st.text_input("Item Name")
item_code_input = st.text_input("Item Code (optional – leave blank to auto-generate)")

if st.button("Create Item & Generate QR Code", type="primary"):
    if not item_name:
        st.error("Please enter an item name.")
    elif not base_url:
        st.error("Please enter the public URL of this app so QR codes can link back to it.")
    else:
        # Use existing code if supplied, else auto-generate
        item_code = item_code_input.strip() or str(uuid.uuid4())[:8]

        # If item already exists, don't overwrite unless it's intentional
        if item_code in inventory:
            st.warning(f"Item code '{item_code}' already exists. Using existing item.")
        else:
            inventory[item_code] = {
                "name": item_name,
                "quantity": 0,
                "history": [],
            }
            save_inventory()

        # Ensure base_url ends with '/'
        url = base_url.strip()
        if not url.endswith("/"):
            url += "/"

        qr_data = f"{url}?code={item_code}"
        img = qrcode.make(qr_data)
        filepath = os.path.join(QRCODE_DIR, f"{item_code}.png")
        img.save(filepath)

        st.success(f"Item '{item_name}' saved with code `{item_code}`. QR code generated.")
        st.image(filepath, caption="QR code for this item")
        st.code(qr_data, language="text")
        st.caption("Print this QR code and place it on the item, bin, or shelf.")
