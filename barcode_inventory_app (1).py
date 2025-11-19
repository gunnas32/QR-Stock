import streamlit as st
import uuid
import qrcode
import os
import json

# ----------------------
# Data Storage
# ----------------------
DATA_FILE = "inventory_data.json"
QRCODE_DIR = "qrcodes"
os.makedirs(QRCODE_DIR, exist_ok=True)

# Load inventory
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        inventory = json.load(f)
else:
    inventory = {}

# Save inventory
def save_inventory():
    with open(DATA_FILE, "w") as f:
        json.dump(inventory, f, indent=4)

# ----------------------
# Streamlit UI
# ----------------------
st.title("📦 Inventory QR Code System")
st.caption("Generate QR codes, scan to check-in/out items, and track job usage.")

# Public URL needed so QR codes can link back to the hosted app
base_url = st.text_input(
    "Public App URL (for QR code links)",
    placeholder="https://your-app.streamlit.app/"
)

# ----------------------
# Generate QR Code
# ----------------------
st.header("Generate QR Code")
item_name = st.text_input("Item Name")
item_code = st.text_input("Item Code (Optional - auto-generate if blank)")

if st.button("Generate QR Code", type="primary"):
    if not item_name:
        st.error("Item name is required.")
    elif not base_url:
        st.error("You must enter the public URL where this app is hosted.")
    else:
        if not item_code:
            item_code = str(uuid.uuid4())[:8]

        # Create QR code linking back to the app with ?code=ITEMCODE
        qr_data = f"{base_url}?code={item_code}"
        qr_img = qrcode.make(qr_data)
        filepath = os.path.join(QRCODE_DIR, f"{item_code}.png")
        qr_img.save(filepath)

        inventory[item_code] = {
            "name": item_name,
            "quantity": 0,
            "history": []
        }
        save_inventory()

        st.success(f"QR code created for {item_name}")
        st.image(filepath)
        st.write("Scan this QR using your phone camera to open the item page.")

# ----------------------
# Process QR Landing Page
# ----------------------
query_params = st.query_params
if "code" in query_params:
    scanned_code = query_params.get("code")
    st.header("Scanned Item")
else:
    scanned_code = st.text_input("Scanned Item Code (from QR)")

# ----------------------
# Item Processing
# ----------------------
if scanned_code:
    if scanned_code not in inventory:
        st.error("Item not found.")
    else:
        item = inventory[scanned_code]

        st.subheader(f"Item: {item['name']}")
        st.write(f"Current Qty: {item['quantity']}")

        action = st.radio("Action", ["Check In", "Check Out"])
        qty = st.number_input("Quantity", min_value=1, step=1)

        job = None
        if action == "Check Out":
            job = st.text_input("Job / Project Name")

        if st.button("Submit Transaction"):
            if action == "Check In":
                item['quantity'] += qty
                item['history'].append({"action": "in", "qty": qty})
            else:
                item['quantity'] -= qty
                item['history'].append({"action": "out", "qty": qty, "job": job})

            save_inventory()
            st.success("Transaction Saved!")
