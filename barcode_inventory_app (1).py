import streamlit as st
import uuid
import qrcode
import os
import json
from datetime import datetime
from openpyxl import Workbook, load_workbook
from PIL import Image, ImageDraw, ImageFont

# ----------------------
# Config & Data Storage
# ----------------------
APP_BASE_URL = "https://qr-stock-twdxtxesmeefyyewte5uxy.streamlit.app/"

DATA_FILE = "inventory_data.json"
QRCODE_ROOT_DIR = "qrcodes"
REPORTS_DIR = "reports"

os.makedirs(QRCODE_ROOT_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

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
# QR Code Helpers
# ----------------------
def ensure_app_url() -> str:
    url = APP_BASE_URL.strip()
    if not url.endswith("/"):
        url += "/"
    return url


def generate_qr_images(item_code: str, item_name: str):
    """
    Generate QR code image and labeled image for an item.
    Folder structure: qrcodes/<item_code>/<item_code>.png and <item_code>_label.png
    Layout: QR on top, text below. Medium size, clear text.
    """
    url = ensure_app_url()
    qr_data = f"{url}?code={item_code}"

    # Create QR with a defined size (box_size controls pixel size)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Ensure per-item folder
    item_dir = os.path.join(QRCODE_ROOT_DIR, item_code)
    os.makedirs(item_dir, exist_ok=True)

    qr_path = os.path.join(item_dir, f"{item_code}.png")
    qr_img.save(qr_path)

    # Labeled QR (QR + reasonably sized text underneath)
    width, height = qr_img.size
    label_height = int(height * 0.45)  # space for 2 lines of text
    total_height = height + label_height

    label_img = Image.new("RGB", (width, total_height), "white")
    label_img.paste(qr_img, (0, 0))

    draw = ImageDraw.Draw(label_img)
    font = ImageFont.load_default()

    text = f"{item_name}\nCode: {item_code}"

    # Center multiline text
    try:
        bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        # Fallback if older Pillow: rough size estimation
        lines = text.split("\n")
        text_w = max(draw.textlength(line, font=font) for line in lines)
        text_h = len(lines) * (font.size + 4)

    x = (width - text_w) // 2
    y = height + (label_height - text_h) // 2

    draw.multiline_text((x, y), text, fill="black", font=font, align="center")

    label_path = os.path.join(item_dir, f"{item_code}_label.png")
    label_img.save(label_path)

    return qr_path, label_path, qr_data


# ----------------------
# Excel Reporting Helpers
# ----------------------
def get_today_report_path() -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(REPORTS_DIR, f"{date_str}_report.xlsx")


def update_excel_report(item_code: str, action: str, qty: int, job: str | None, ts: str):
    """
    Update (or create) today's Excel report.
    Sheet 1: Transactions
    Sheet 2: Stock
    """
    report_path = get_today_report_path()
    if os.path.exists(report_path):
        wb = load_workbook(report_path)
    else:
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Transactions"
        ws1.append(["Time", "Item", "Code", "Action", "Qty", "Job"])
        wb.create_sheet("Stock")

    # Transactions sheet
    ws_tx = wb["Transactions"]
    item = inventory[item_code]
    action_label = {
        "in": "IN",
        "out": "OUT",
        "manual": "MANUAL",
    }.get(action, action.upper())

    ws_tx.append([
        ts,
        item.get("name", ""),
        item_code,
        action_label,
        int(qty),
        job or "",
    ])

    # Rebuild Stock sheet each time to keep it accurate
    if "Stock" in wb.sheetnames:
        ws_stock = wb["Stock"]
        wb.remove(ws_stock)
    ws_stock = wb.create_sheet("Stock")
    ws_stock.append(["Item", "Code", "Quantity"])

    for code, it in inventory.items():
        ws_stock.append([
            it.get("name", ""),
            code,
            int(it.get("quantity", 0)),
        ])

    wb.save(report_path)


# ----------------------
# Transactions & Item Detail
# ----------------------
def record_transaction(item_code: str, action: str, qty: int, job: str | None = None):
    """Add a transaction entry to an item, with timestamp and Excel update."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "action": action,  # "in", "out", or "manual"
        "qty": int(qty),
        "timestamp": ts,
    }
    if job:
        entry["job"] = job

    inventory[item_code].setdefault("history", []).append(entry)
    save_inventory()
    update_excel_report(item_code, action, qty, job, ts)


def get_qr_paths(item_code: str, item_name: str):
    """
    Ensure QR and label exist for an item, return their paths + data.
    """
    item_dir = os.path.join(QRCODE_ROOT_DIR, item_code)
    qr_path = os.path.join(item_dir, f"{item_code}.png")
    label_path = os.path.join(item_dir, f"{item_code}_label.png")

    if not os.path.exists(qr_path) or not os.path.exists(label_path):
        qr_path, label_path, qr_data = generate_qr_images(item_code, item_name)
    else:
        qr_data = f"{ensure_app_url()}?code={item_code}"

    return qr_path, label_path, qr_data


def show_item_detail(item_code: str, section_title: str = "Item Detail"):
    """Show item info, stock, history, edit UI, QR, and check in/out controls."""
    if item_code not in inventory:
        st.error("Item not found.")
        return

    item = inventory[item_code]
    st.markdown("---")
    st.subheader(section_title)

    current_qty = int(item.get("quantity", 0))

    col_top1, col_top2 = st.columns([2, 1])
    with col_top1:
        st.write(f"**Item Name:** {item.get('name', '')}")
        st.write(f"**Item Code:** `{item_code}`")
    with col_top2:
        st.metric("Current Stock", current_qty)

    # --- QR Label & Downloads ---
    st.write("### QR Label")
    qr_path, label_path, qr_data = get_qr_paths(item_code, item.get("name", ""))

    if os.path.exists(label_path):
        st.image(label_path, caption="QR label for this item")
        col_q1, col_q2 = st.columns(2)
        with col_q1:
            with open(qr_path, "rb") as f_qr:
                st.download_button(
                    "Download QR only (PNG)",
                    data=f_qr,
                    file_name=f"{item_code}_qr.png",
                    mime="image/png",
                    key=f"dl_qr_{section_title}_{item_code}",
                )
        with col_q2:
            with open(label_path, "rb") as f_lbl:
                st.download_button(
                    "Download QR label (PNG)",
                    data=f_lbl,
                    file_name=f"{item_code}_label.png",
                    mime="image/png",
                    key=f"dl_label_{section_title}_{item_code}",
                )
    else:
        st.caption("No QR label found for this item.")

    # --- Stock Transaction (Check In / Out) ---
    st.write("### Stock Transaction")
    col1, col2 = st.columns(2)
    with col1:
        action = st.radio(
            "Action",
            ["Check In", "Check Out"],
            key=f"action_{section_title}_{item_code}"
        )
    with col2:
        qty = st.number_input(
            "Quantity",
            min_value=1,
            step=1,
            key=f"qty_{section_title}_{item_code}",
        )

    job = None
    if action == "Check Out":
        job = st.text_input(
            "Job / Project (optional, but recommended)",
            key=f"job_{section_title}_{item_code}"
        )

    if st.button("Save Transaction", key=f"save_{section_title}_{item_code}"):
        if action == "Check Out" and qty > current_qty:
            st.error("Cannot check out more items than are in stock.")
        else:
            if action == "Check In":
                inventory[item_code]["quantity"] = current_qty + int(qty)
                save_inventory()
                record_transaction(item_code, "in", qty)
                st.success(f"Checked IN {qty} item(s).")
            else:
                inventory[item_code]["quantity"] = current_qty - int(qty)
                save_inventory()
                record_transaction(item_code, "out", qty, job)
                st.success(f"Checked OUT {qty} item(s).")

            st.rerun()

    # --- Edit Item Details ---
    with st.expander("✏️ Edit Item Details"):
        edit_name = st.text_input(
            "Item Name",
            value=item.get("name", ""),
            key=f"edit_name_{section_title}_{item_code}",
        )
        edit_code = st.text_input(
            "Item Code",
            value=item_code,
            key=f"edit_code_{section_title}_{item_code}",
        )
        edit_qty = st.number_input(
            "Quantity (manual override)",
            min_value=0,
            value=current_qty,
            step=1,
            key=f"edit_qty_{section_title}_{item_code}",
        )

        if st.button("Save Item Changes", key=f"edit_save_{section_title}_{item_code}"):
            code_changed = (edit_code != item_code)
            name_changed = (edit_name != item.get("name", ""))
            qty_changed = (edit_qty != current_qty)

            new_code = item_code

            # Handle code change
            if code_changed:
                if edit_code in inventory and edit_code != item_code:
                    st.error(f"Item code '{edit_code}' already exists. Choose another code.")
                    return
                new_code = edit_code
                inventory[new_code] = inventory.pop(item_code)
                item = inventory[new_code]  # update ref

            # Handle name change
            if name_changed:
                item["name"] = edit_name

            # Handle quantity change as MANUAL transaction
            if qty_changed:
                diff = int(edit_qty) - current_qty
                item["quantity"] = int(edit_qty)
                save_inventory()
                if diff != 0:
                    record_transaction(
                        new_code,
                        "manual",
                        abs(diff),
                        job=f"Manual adjust from {current_qty} to {edit_qty}",
                    )

            save_inventory()

            # Regenerate QR images if name or code changed
            if code_changed or name_changed:
                qr_path, label_path, qr_data = generate_qr_images(new_code, edit_name)
                st.success("Item details updated and QR label regenerated.")
                st.image(label_path, caption="Updated QR label")
            else:
                st.success("Item details updated.")

            st.rerun()

    # --- Transaction History ---
    st.write("### Transaction History")
    history = inventory[item_code].get("history", [])
    if not history:
        st.info("No transactions recorded yet.")
    else:
        rows = []
        for entry in reversed(history):  # most recent first
            rows.append({
                "Time": entry.get("timestamp", ""),
                "Action": {
                    "in": "IN",
                    "out": "OUT",
                    "manual": "MANUAL",
                }.get(entry.get("action"), entry.get("action", "").upper()),
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
# 1. Daily Excel Report Download (Home)
# ---------------------------------------------------
st.markdown("### 📄 Daily Excel Report")
today_report = get_today_report_path()
if os.path.exists(today_report):
    with open(today_report, "rb") as f:
        st.download_button(
            "Download Today's Report (Excel)",
            data=f,
            file_name=os.path.basename(today_report),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_report_home",
        )
else:
    st.caption("No transactions recorded today yet.")

# ---------------------------------------------------
# 2. Detect if we were opened via QR code (?code=...)
# ---------------------------------------------------
scanned_code = None
qp = st.query_params  # Streamlit 1.30+ style API

if "code" in qp and qp["code"]:
    val = qp["code"]
    if isinstance(val, list):
        scanned_code = val[0]
    else:
        scanned_code = val

# ---------------------------------------------------
# 3. Inventory Search / Home Section
# ---------------------------------------------------
st.markdown("## 🔍 Search Inventory")

selected_code = None

if not inventory:
    st.info("No items in inventory yet. Use the **Admin – Create New Item** section below to add items.")
else:
    items = []
    for code, it in sorted(inventory.items(), key=lambda x: x[1].get("name", "").lower()):
        label = f"{it.get('name','')} ({code})"
        items.append((label, code))

    labels = [label for (label, _) in items]
    labels_by_code = {label: code for (label, code) in items}

    placeholder = "[Select item]"
    ui_options = [placeholder] + labels

    selected_label = st.selectbox(
        "Search / Select item",
        ui_options,
        index=0,
    )

    if selected_label != placeholder:
        selected_code = labels_by_code[selected_label]

# Show selected item detail ONLY when not opened via QR
if selected_code and not scanned_code:
    show_item_detail(selected_code, section_title="Selected Item")

# ---------------------------------------------------
# 4. If opened via QR scan, show scanned item section
# ---------------------------------------------------
if scanned_code:
    show_item_detail(scanned_code, section_title="Scanned Item")

# ---------------------------------------------------
# 5. Admin Section – Create Items & Generate QR Codes
# ---------------------------------------------------
st.markdown("---")
st.markdown("## 🛠️ Admin – Create New Item & QR Code")

st.info(
    "Use this section on your computer to create items and generate QR code labels. "
    "Workers can then scan the QR codes with their phones."
)

st.write("### App URL used for QR codes")
st.code(ensure_app_url(), language="text")

item_name = st.text_input("New Item Name")
item_code_input = st.text_input("New Item Code (optional – leave blank to auto-generate)")

if st.button("Create Item & Generate QR Code", type="primary"):
    if not item_name:
        st.error("Please enter an item name.")
    else:
        item_code = item_code_input.strip() or str(uuid.uuid4())[:8]

        if item_code in inventory:
            st.warning(f"Item code '{item_code}' already exists. Using existing item.")
        else:
            inventory[item_code] = {
                "name": item_name,
                "quantity": 0,
                "history": [],
            }
            save_inventory()

        qr_path, label_path, qr_data = generate_qr_images(item_code, item_name)

        st.success(f"Item '{item_name}' saved with code `{item_code}`. QR code generated.")
        st.image(label_path, caption="QR label for printing")
        col_a, col_b = st.columns(2)
        with col_a:
            with open(qr_path, "rb") as f_qr:
                st.download_button(
                    "Download QR only (PNG)",
                    data=f_qr,
                    file_name=f"{item_code}_qr.png",
                    mime="image/png",
                    key=f"dl_qr_new_{item_code}",
                )
        with col_b:
            with open(label_path, "rb") as f_lbl:
                st.download_button(
                    "Download QR label (PNG)",
                    data=f_lbl,
                    file_name=f"{item_code}_label.png",
                    mime="image/png",
                    key=f"dl_label_new_{item_code}",
                )
        st.code(qr_data, language="text")
        st.caption("Print this QR label and place it on the item, bin, or shelf.")

# ---------------------------------------------------
# 6. Admin – Daily Excel Report Download (duplicate, per your request)
# ---------------------------------------------------
st.markdown("### 📄 Daily Excel Report (Admin)")
if os.path.exists(today_report):
    with open(today_report, "rb") as f:
        st.download_button(
            "Download Today's Report (Excel)",
            data=f,
            file_name=os.path.basename(today_report),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_report_admin",
        )
else:
    st.caption("No transactions recorded today yet.")
